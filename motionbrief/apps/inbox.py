# SPDX-License-Identifier: Apache-2.0
"""Drop-folder intake: scripts written by people or other agents go to inbox/, results appear in outbox/<id>/.

  inbox/<anything>.md          script (front-matter + narration sections), see inbox/README.md
  inbox/<anything>.plan.json   ready shot plan (skips the LLM storyboard)
  outbox/<id>/status.json      queued -> storyboarding -> awaiting_approval -> rendering -> done | failed
  outbox/<id>/animatic.png     review this, then create outbox/<id>/APPROVE (empty file) to render
  outbox/<id>/final.mp4        the video (+ cover.png, subtitles.srt, sources.md)

`motionbrief inbox` processes once; `--watch` keeps polling. Front-matter `produce: auto` skips the approval stop.
"""
from __future__ import annotations

import json
import re
import shutil
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import yaml

from motionbrief.paths import REPO_ROOT
from motionbrief.render.svg_canvas.canvas import canvas_for

INBOX = REPO_ROOT / "inbox"
OUTBOX = REPO_ROOT / "outbox"
_FM = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)
_ID = re.compile(r"[^a-z0-9_]+")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def front_matter(text: str) -> tuple[dict, str]:
    m = _FM.match(text)
    if not m:
        return {}, text
    meta = yaml.safe_load(m.group(1)) or {}
    return (meta if isinstance(meta, dict) else {}), text[m.end():]


def video_id(meta: dict, path: Path) -> str:
    raw = str(meta.get("id") or path.name.split(".")[0])
    if not meta.get("id") and re.search(r"[一-鿿]", raw):  # Chinese file names -> pinyin ids
        from pypinyin import lazy_pinyin
        raw = "_".join(lazy_pinyin(raw))
    raw = raw.lower()
    vid = re.sub(r"_+", "_", _ID.sub("_", raw)).strip("_")
    return vid if vid and vid[0].isalpha() else f"v_{vid or 'video'}"


def status(vid: str) -> dict:
    p = OUTBOX / vid / "status.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _set(vid: str, state: str, **kw) -> dict:
    d = OUTBOX / vid
    d.mkdir(parents=True, exist_ok=True)
    st = {**status(vid), "id": vid, "state": state, "updated": _now(), **kw}
    st.setdefault("history", []).append([st["updated"], state])
    (d / "status.json").write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[inbox] {vid}: {state}" + (f" — {kw['message']}" if kw.get("message") else ""), flush=True)
    return st


# ----------------------------------------------------------------- stages
def storyboard(src: Path) -> str:
    """inbox file -> plan + IR + animatic in outbox/<id>/; returns the video id."""
    from motionbrief.content import storyboard as sb
    from motionbrief.content.shots import compile_plan, measure_voice
    from motionbrief.ir.models import load
    from motionbrief.quality.deterministic import check_ir
    from motionbrief.render.animatic import render_sheet

    text = src.read_text(encoding="utf-8")
    if src.name.endswith(".plan.json"):
        plan = json.loads(text)
        meta = {**plan.get("video", {}), **plan.get("meta", {})}
    else:
        meta, body = front_matter(text)
        plan = None
    vid = video_id(meta, src)
    out = OUTBOX / vid
    out.mkdir(parents=True, exist_ok=True)
    (out / "APPROVE").unlink(missing_ok=True)  # an approval belongs to one animatic; a re-drop needs a new review
    shutil.copy2(src, out / ("input" + "".join(src.suffixes)))
    aspect = str(meta.get("aspect", "9:16"))
    if aspect not in ("9:16", "16:9"):  # unquoted 16:9 is read by YAML as sexagesimal 969
        raise ValueError(f"aspect must be 9:16 or 16:9, got {aspect!r}; quote it in the front-matter")
    _set(vid, "storyboarding", source=src.name, title=meta.get("title", ""), produce=meta.get("produce", "approve"),
         aspect=aspect, also=list(meta.get("also", [])))
    t0 = time.time()
    if plan is None:
        shotlist = None
        if meta.get("shotlist"):  # a *.shots.md file in the inbox (never processed on its own)
            p = INBOX / str(meta["shotlist"])
            if not p.exists():
                raise FileNotFoundError(f"shotlist {meta['shotlist']} not found in inbox/")
            shotlist = p.read_text(encoding="utf-8")
        res = sb.run(body, shotlist, video_id=vid, title=meta.get("title", ""), ref=meta.get("model"), aspect=aspect,
                     visual_style=str(meta.get("visualStyle", "neon")))
        plan = res.plan
        if res.errors:
            sb.write(res, out / "plan.json")
            raise RuntimeError(f"storyboard left errors: {json.dumps(res.errors, ensure_ascii=False)[:1500]}")
    plan.setdefault("video", {}).update({"id": vid, "title": meta.get("title", plan["video"].get("title", ""))})
    (out / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    lines = {s["id"]: s["narration"] for s in plan["shots"]}
    dur = measure_voice(lines, out / "voice_durations.json")
    ir = compile_plan(plan, dur)
    ir_path = REPO_ROOT / "fixtures" / f"{vid}.json"
    ir_path.write_text(json.dumps(ir, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _, rep = check_ir(ir)
    (out / "g1_ir.txt").write_text(rep.summary(), encoding="utf-8")
    if not rep.passed:
        raise RuntimeError("G1 (IR) failed:\n" + rep.summary())
    render_sheet(load(ir_path), out / "animatic.png")
    _set(vid, "awaiting_approval", ir=str(ir_path.relative_to(REPO_ROOT)), shots=len(plan["shots"]),
         durationSec=round(ir["scenes"][-1]["tEnd"], 1), storyboardSec=round(time.time() - t0),
         message=f"review outbox/{vid}/animatic.png, then create outbox/{vid}/APPROVE")
    return vid


def produce(vid: str) -> None:
    from motionbrief.apps.cli import main as cli
    st = _set(vid, "rendering")
    t0 = time.time()
    rc = cli(["produce", str(REPO_ROOT / st["ir"]), "--out", f"work/{vid}"])
    bundle = REPO_ROOT / "work" / vid
    for name in ("final.mp4", "cover.png", "subs/subtitles.srt", "sources.md", "metrics.json"):
        if (bundle / name).exists():
            shutil.copy2(bundle / name, OUTBOX / vid / Path(name).name)
    if rc != 0 or not (bundle / "final.mp4").exists():
        raise RuntimeError(f"produce exited {rc}; see work/{vid}/logs")
    # extra aspects reuse the same shot plan and voice: only the canvas changes (files: final_9x16.mp4 etc.)
    for other in st.get("also", []):
        if other == st.get("aspect", "9:16"):
            continue
        tag = other.replace(":", "x")
        ir = json.loads((REPO_ROOT / st["ir"]).read_text(encoding="utf-8"))
        size = canvas_for(other)
        ir["video"].update(aspect=other, w=size.w, h=size.h)
        alt_ir = REPO_ROOT / "work" / f"{vid}_{tag}" / "scene_ir.json"
        alt_ir.parent.mkdir(parents=True, exist_ok=True)
        alt_ir.write_text(json.dumps(ir, ensure_ascii=False, indent=1), encoding="utf-8")
        if cli(["produce", str(alt_ir), "--out", f"work/{vid}_{tag}"]) != 0 or not (alt_ir.parent / "final.mp4").exists():
            raise RuntimeError(f"produce {other} failed; see work/{vid}_{tag}/logs")
        shutil.copy2(alt_ir.parent / "final.mp4", OUTBOX / vid / f"final_{tag}.mp4")
    extra: dict = {}
    try:  # publish package: copy, chapters, covers (never blocks the video)
        from motionbrief.apps.publish import write_publish
        extra["publish"] = [f"outbox/{vid}/{Path(p).name}" for p in write_publish(vid)]
    except Exception as e:
        extra["publishError"] = str(e)[:500]
    _set(vid, "done", renderSec=round(time.time() - t0), video=f"outbox/{vid}/final.mp4", **extra)


# ----------------------------------------------------------------- loop
def pending_inputs() -> list[Path]:
    if not INBOX.exists():
        return []
    return sorted(p for p in INBOX.iterdir() if p.is_file() and not p.name.startswith((".", "_"))
                  and not p.name.lower().startswith(("readme", "template"))  # docs and templates (TEMPLATE_rich.md, ...)
                  and not p.name.endswith(".shots.md")
                  and (p.suffix == ".md" or p.name.endswith(".plan.json")))


def run_once(auto_produce: bool = False) -> int:
    INBOX.mkdir(exist_ok=True)
    OUTBOX.mkdir(exist_ok=True)
    done_dir, work_dir = INBOX / "_processed", INBOX / "_processing"
    done_dir.mkdir(exist_ok=True)
    work_dir.mkdir(exist_ok=True)
    n = 0
    for new in pending_inputs():  # new scripts
        vid = None
        src = work_dir / new.name
        try:  # claim it: a concurrent watcher loses the rename race and skips the file
            new.rename(src)
        except OSError:
            continue
        try:
            if src.name.endswith(".plan.json"):
                pl = json.loads(src.read_text(encoding="utf-8"))
                meta = {**pl.get("video", {}), **pl.get("meta", {})}
            else:
                meta = front_matter(src.read_text(encoding="utf-8"))[0]
            vid = video_id(meta, src)
            _set(vid, "queued", source=src.name)
            storyboard(src)
            n += 1
        except Exception as e:
            _set(vid or src.stem, "failed", message=str(e)[:2000], trace=traceback.format_exc()[-3000:])
        finally:
            shutil.move(str(src), str(done_dir / f"{datetime.now():%Y%m%d-%H%M%S}_{src.name}"))
    for d in sorted(OUTBOX.iterdir()) if OUTBOX.exists() else []:  # approved storyboards
        st = status(d.name)
        if st.get("state") == "awaiting_approval" and (
                (d / "APPROVE").exists() or auto_produce or st.get("produce") == "auto"):
            try:
                produce(d.name)
                n += 1
            except Exception as e:
                _set(d.name, "failed", message=str(e)[:2000], trace=traceback.format_exc()[-3000:])
    return n


def watch(interval: float = 20.0, auto_produce: bool = False) -> None:
    print(f"[inbox] watching {INBOX} every {interval:g}s (Ctrl+C to stop)", flush=True)
    while True:
        run_once(auto_produce)
        time.sleep(interval)
