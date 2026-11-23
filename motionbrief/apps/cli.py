# SPDX-License-Identifier: Apache-2.0
"""MotionBrief CLI — the production entry point.

  motionbrief validate fixtures/isp_v01.json
  motionbrief produce  fixtures/isp_v01.json --scenes s03     # sprint acceptance (s03 Layer A + G1)
  motionbrief produce  fixtures/isp_v01.json                  # full ISP 70s hero
  motionbrief qa       fixtures/isp_v01.json --bundle work/isp_v01
  motionbrief route    code_generation "hello"
  motionbrief run-task task.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

from motionbrief.paths import REPO_ROOT


def _rel(p: str) -> str:
    path = Path(p).resolve()
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def cmd_validate(a) -> int:
    from motionbrief.quality.deterministic import check_ir
    ir, rep = check_ir(json.loads(Path(a.ir).read_text(encoding="utf-8")))
    print(rep.summary())
    if ir:
        print(f"VALID irVersion=1.2.0 video={ir.video.id} duration={ir.duration}s tier={ir.video.durationTier} "
              f"scenes={len(ir.scenes)}" if rep.passed else "INVALID")
    return 0 if rep.passed else 1


def cmd_export_schema(a) -> int:
    from motionbrief.ir.models import SCHEMA_PATH, export_json_schema
    txt = json.dumps(export_json_schema(), indent=2, ensure_ascii=False) + "\n"
    if a.check:
        ok = SCHEMA_PATH.exists() and SCHEMA_PATH.read_text(encoding="utf-8") == txt
        print("schema up to date" if ok else "schema OUT OF DATE: run `motionbrief export-schema`")
        return 0 if ok else 1
    SCHEMA_PATH.write_text(txt, encoding="utf-8")
    print(f"wrote {SCHEMA_PATH.relative_to(REPO_ROOT)}")
    return 0


def cmd_probe(a) -> int:
    from motionbrief.render.probe import probe
    print(json.dumps(probe(), indent=2))
    return 0


def _fingerprint(ir_ref: str, out: str, kind: str) -> str:
    """Idempotency fingerprint = every input that can change the task's output."""
    from motionbrief import __version__
    from motionbrief.paths import source_hash
    h = hashlib.sha256((REPO_ROOT / ir_ref).read_bytes())
    h.update(source_hash().encode())
    for f in ("motion/tokens.json", "motion/registry.json"):
        h.update((REPO_ROOT / f).read_bytes())
    h.update(__version__.encode())
    bundle = Path(out) if Path(out).is_absolute() else REPO_ROOT / out
    if kind in ("render_scene", "mix_audio", "assemble", "qa_g1"):
        for rel in ("subs/subtitles.srt", "scene_ir.timed.json"):
            if (bundle / rel).exists():
                h.update((bundle / rel).read_bytes())
    if kind in ("assemble", "qa_g1"):
        for p in sorted((bundle / "frames").glob("*.hash")) + sorted((bundle / "audio").glob("*.wav")):
            h.update(p.name.encode() + str(p.stat().st_mtime_ns).encode())
    return h.hexdigest()[:12]


def _task(kind: str, ir_ref: str, out: str, scene: str | None = None, **cmd) -> dict:
    key = f"{kind}-{scene or 'all'}-{_fingerprint(ir_ref, out, kind)}"
    t = {"taskId": f"{kind}_{scene or 'all'}", "type": kind, "idempotencyKey": key, "irRef": ir_ref,
         "outDir": out, "retries": 2, "degrade": True, "checkpoint": True, "renderer": "auto"}
    if scene:
        t["sceneId"] = scene
    if cmd:
        t["cmd"] = cmd
    return t


def _report(t: dict, r: dict) -> bool:
    flag = "SKIP" if r.get("skipped") else r["status"].upper()
    extra = ""
    if r.get("degradations"):
        extra = f" degradations={[(d.get('object', ''), d['from'], d['to']) for d in r['degradations']]}"
    if t["type"] == "render_scene" and r["status"] in ("ok", "degraded"):
        m = r["metrics"]
        extra += f" frames={m.get('frames', 'cached')} {'(checkpoint)' if m.get('checkpointHit') else ''}"
    print(f"[{flag:9}] {t['taskId']}{extra}", flush=True)
    if t["type"] == "qa_g1":
        for line in (r["metrics"].get("summary") or []):
            print("   " + line.replace("\n", "\n   "))
    if r["status"] not in ("ok", "degraded"):
        print(f"   error: {r['error']['kind']}: {r['error']['message'][:1500]}")
        return False
    return True


def _run_renders(tasks: list[dict], dur: dict[str, float], fps: int, jobs: int,
                 gpu_scenes: frozenset = frozenset()) -> list[dict]:
    """Cut scenes into ~MOTIONBRIEF_SLICE_FRAMES-frame slices and drain one longest-scene-first queue with
    `jobs` local processes plus MOTIONBRIEF_RENDER_JOBS remote slots, then join each scene's slices.
    Whichever slot frees up takes the next slice, so laptop and LAN PC finish together, and a slow or
    absent remote host never stalls the run."""
    import queue
    import threading
    from concurrent.futures import ProcessPoolExecutor

    from motionbrief.agent.executor import execute
    from motionbrief.render import remote

    rjobs = remote.jobs()
    if not rjobs and (jobs <= 1 or len(tasks) <= 1):
        return [execute(t) for t in tasks]
    per = int(os.environ.get("MOTIONBRIEF_SLICE_FRAMES", 90))
    nseg = {t["taskId"]: max(1, round(dur.get(t.get("sceneId"), 0) * fps / per)) for t in tasks}
    # scenes with GPU (three) objects can only be drawn on the remote host: remote slots take them first
    gpu_q: queue.Queue = queue.Queue()
    todo: queue.Queue = queue.Queue()
    for t in sorted(tasks, key=lambda t: -dur.get(t.get("sceneId"), 0)):
        n = nseg[t["taskId"]]
        q = gpu_q if rjobs and t.get("sceneId") in gpu_scenes else todo
        for k in range(n):
            q.put({**t, "taskId": f"{t['taskId']}.{k:03d}", "idempotencyKey": f"{t['idempotencyKey']}-{k}of{n}",
                   "cmd": {**t.get("cmd", {}), "segment": [k, n]}})
    results: dict[str, dict] = {}
    lock = threading.Lock()

    def slot(pool: ProcessPoolExecutor | None) -> None:
        while True:
            try:
                t = (gpu_q if pool is None and not gpu_q.empty() else todo).get_nowait()
            except queue.Empty:
                return
            if pool is None:
                r = execute({**t, "cmd": {**t.get("cmd", {}), "worker": "remote"}})
            else:
                r = pool.submit(execute, t).result()
            with lock:
                results[t["taskId"]] = r
                if r["status"] not in ("ok", "degraded"):
                    print(f"  !! {t['taskId']} {r['status']}: {r['error']['message'][:300]}", flush=True)

    nloc = max(1, jobs)
    with ProcessPoolExecutor(nloc) as pool:
        # spawn every worker NOW, before remote threads start ssh: workers created concurrently with ssh calls
        # could inherit their pipe handles (Windows) and keep them open
        list(pool.map(abs, range(nloc)))
        # remote slots start first so they are not starved when slices are few
        threads = [threading.Thread(target=slot, args=(None,)) for _ in range(rjobs)]
        threads += [threading.Thread(target=slot, args=(pool,)) for _ in range(nloc)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()
    hosts: dict[str, int] = {}
    for r in results.values():
        h = r.get("metrics", {}).get("host", "local")
        hosts[h] = hosts.get(h, 0) + 1
    print(f"  slices by host: {hosts}", flush=True)
    # join: each scene task concatenates its slices (or re-renders in full if a slice failed)
    return [execute({**t, "cmd": {**t.get("cmd", {}), "segments": nseg[t["taskId"]]}}) for t in tasks]


def cmd_produce(a) -> int:
    from motionbrief.agent.executor import execute
    from motionbrief.ir.models import load
    ir_ref = _rel(a.ir)
    ir = load(REPO_ROOT / ir_ref)
    out = a.out or f"work/{ir.video.id}"
    scenes = a.scenes.split(",") if a.scenes else [s.id for s in ir.scenes]
    full = not a.scenes
    plan = [("tts_narration", None, {})]
    plan += [("render_scene", sid, {"pngEvery": a.png_every}) for sid in scenes]
    plan += [("mix_audio", None, {})]
    if full:
        plan += [("assemble", None, {}), ("qa_g1", None, {})]
    else:
        plan += [("qa_g1", sid, {}) for sid in scenes]
    # render_scene tasks are independent: fan them out over processes (cairo raster is CPU-bound)
    jobs = max(1, a.jobs if a.jobs else int(os.environ.get("MOTIONBRIEF_JOBS", 0)) or (os.cpu_count() or 2) - 2)
    rc, i = 0, 0
    while i < len(plan) and rc == 0:
        k = plan[i][0]
        group = [plan[i]]
        if k == "render_scene":
            while i + len(group) < len(plan) and plan[i + len(group)][0] == k:
                group.append(plan[i + len(group)])
        i += len(group)
        # tasks are built only now so each idempotency key sees the outputs of the previous step
        tasks = [_task(kk, ir_ref, out, sid, **cmd) for kk, sid, cmd in group]
        if k == "render_scene":
            from motionbrief.render.backend import plan_scene
            gpu = frozenset(s.id for s in ir.scenes if "three" in plan_scene(s).choices.values())
            results = _run_renders(tasks, {s.id: s.tEnd - s.tStart for s in ir.scenes}, ir.video.fps, jobs, gpu)
        else:
            results = [execute(t) for t in tasks]
        for t, r in zip(tasks, results):
            if not _report(t, r):
                rc = 1
    if rc == 0:
        print(f"bundle: {out}")
    return rc


def cmd_storyboard(a) -> int:
    """Script (+ optional shot list) -> shot plan (LLM) -> Scene IR (voice-measured) -> G1 + animatic."""
    import time

    from motionbrief.content import storyboard as sb
    from motionbrief.content.shots import compile_plan, estimate_voice, measure_voice
    from motionbrief.quality.deterministic import check_ir
    from motionbrief.render.animatic import render_sheet
    script = Path(a.script).read_text(encoding="utf-8")
    shotlist = Path(a.shotlist).read_text(encoding="utf-8") if a.shotlist else None
    vid = a.id or Path(a.script).stem
    bundle = REPO_ROOT / "work" / vid
    t0 = time.time()
    res = sb.run(script, shotlist, video_id=vid, title=a.title or "", ref=a.ref, repairs=a.repairs)
    sb.write(res, bundle / "plan.json")
    print(f"storyboard: {len(res.plan['shots'])} shots by {res.model} in {time.time() - t0:.0f}s; "
          f"repair rounds {res.rounds}")
    for sec, errs in res.errors.items():
        print(f"  unresolved in {sec}: {errs[:5]}")
    lines = {s["id"]: s["narration"] for s in res.plan["shots"]}
    dur = measure_voice(lines, bundle / "voice_durations.json") if a.measure else estimate_voice(lines)
    ir = compile_plan(res.plan, dur)
    out = Path(a.out) if a.out else REPO_ROOT / "fixtures" / f"{vid}.json"
    out.write_text(json.dumps(ir, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _, rep = check_ir(ir)
    print(rep.summary())
    if rep.passed:
        from motionbrief.ir.models import load
        render_sheet(load(out), bundle / "animatic.png")
        print(f"IR: {_rel(str(out))}  duration={ir['scenes'][-1]['tEnd']:.1f}s  animatic: work/{vid}/animatic.png")
    return 0 if rep.passed and not res.errors else 1


def cmd_inbox(a) -> int:
    from motionbrief.apps import inbox
    if a.action == "status":
        for d in sorted(inbox.OUTBOX.iterdir()) if inbox.OUTBOX.exists() else []:
            st = inbox.status(d.name)
            if st:
                print(f"{d.name:28} {st['state']:18} {st.get('durationSec', '')!s:>6}s  {st.get('message', '')[:90]}")
        return 0
    if a.action == "publish":
        from motionbrief.apps.publish import write_publish
        rc = 0
        for vid in a.ids:
            try:
                for p in write_publish(vid):
                    print(p)
            except Exception as e:
                print(f"{vid}: publish failed: {str(e)[:300]}")
                rc = 1
        return rc
    if a.action == "approve":
        for vid in a.ids:
            if inbox.status(vid).get("state") != "awaiting_approval":
                print(f"{vid}: not awaiting approval ({inbox.status(vid).get('state')})")
                continue
            (inbox.OUTBOX / vid / "APPROVE").write_text(inbox._now(), encoding="utf-8")
            print(f"{vid}: approved")
        return 0
    if a.watch:
        inbox.watch(a.interval, a.auto_produce)
        return 0
    n = inbox.run_once(a.auto_produce)
    print(f"[inbox] processed {n} item(s)")
    return 0


def cmd_animatic(a) -> int:
    from motionbrief.ir.models import load
    from motionbrief.render.animatic import render_sheet
    ir = load(a.ir)
    out = Path(a.out or f"work/{ir.video.id}/animatic.png")
    render_sheet(ir, out)
    print(f"animatic: {out}")
    return 0


def cmd_qa(a) -> int:
    from motionbrief.quality.gates import run_all
    reps = run_all(Path(a.ir), Path(a.bundle), a.author_family, a.scenes.split(",") if a.scenes else None)
    for r in reps:
        print(r.summary())
    return 0 if all(r.passed for r in reps) else 1


def cmd_route(a) -> int:
    from motionbrief.llm.router import CapabilityRouter
    r = CapabilityRouter.from_file().chat(a.capability, [{"role": "user", "content": a.prompt}],
                                          exclude_family=a.exclude_family)
    print(json.dumps({"provider": r.provider, "family": r.family, "text": r.text, "fallbacks": r.attempts},
                     indent=2, ensure_ascii=False))
    return 0


def cmd_run_task(a) -> int:
    from motionbrief.agent.executor import execute
    r = execute(a.task)
    print(json.dumps(r, indent=2, ensure_ascii=False))
    return 0 if r["status"] in ("ok", "degraded") else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser("motionbrief")
    sp = p.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("validate"); s.add_argument("ir"); s.set_defaults(f=cmd_validate)
    s = sp.add_parser("export-schema"); s.add_argument("--check", action="store_true"); s.set_defaults(f=cmd_export_schema)
    s = sp.add_parser("probe"); s.set_defaults(f=cmd_probe)
    s = sp.add_parser("produce"); s.add_argument("ir"); s.add_argument("--out"); s.add_argument("--scenes")
    s.add_argument("--png-every", type=int, default=15)
    s.add_argument("--jobs", type=int, default=0, help="parallel scene renders (default: MOTIONBRIEF_JOBS or cpus-2)")
    s.set_defaults(f=cmd_produce)
    s = sp.add_parser("storyboard", help="script -> shot plan (LLM) -> Scene IR + animatic")
    s.add_argument("script"); s.add_argument("--shotlist", help="optional shot-list markdown (### sNN blocks)")
    s.add_argument("--id"); s.add_argument("--title"); s.add_argument("--out")
    s.add_argument("--ref", help="pin one provider:model from the capabilities file (model comparisons)")
    s.add_argument("--repairs", type=int, default=2)
    s.add_argument("--measure", action="store_true", help="time shots with real TTS (slower, final)")
    s.set_defaults(f=cmd_storyboard)
    s = sp.add_parser("inbox", help="process scripts dropped into inbox/ (results in outbox/<id>/)")
    s.add_argument("action", nargs="?", default="run", choices=["run", "status", "approve", "publish"])
    s.add_argument("ids", nargs="*"); s.add_argument("--watch", action="store_true")
    s.add_argument("--interval", type=float, default=20.0)
    s.add_argument("--auto-produce", action="store_true", help="render without waiting for APPROVE")
    s.set_defaults(f=cmd_inbox)
    s = sp.add_parser("animatic"); s.add_argument("ir"); s.add_argument("--out"); s.set_defaults(f=cmd_animatic)
    s = sp.add_parser("qa"); s.add_argument("ir"); s.add_argument("--bundle", required=True)
    s.add_argument("--scenes"); s.add_argument("--author-family"); s.set_defaults(f=cmd_qa)
    s = sp.add_parser("route"); s.add_argument("capability"); s.add_argument("prompt")
    s.add_argument("--exclude-family"); s.set_defaults(f=cmd_route)
    s = sp.add_parser("run-task"); s.add_argument("task"); s.set_defaults(f=cmd_run_task)
    a = p.parse_args(argv)
    return a.f(a)


if __name__ == "__main__":
    sys.exit(main())
