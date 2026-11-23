# SPDX-License-Identifier: Apache-2.0
"""Storyboard stage: script (+ optional shot list) -> shot plan, by a strong LLM, registry components only.

The model writes only the shot plan (content/shots.py); every section is validated deterministically
(verbatim narration, registry components and modes, typography limits, cue/beat rules, then G1 IR checks on the
compiled section) and repaired with the concrete errors, up to `repairs` rounds. Sections run in parallel.
"""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from motionbrief.content.shots import PlanError, compile_plan, estimate_voice
from motionbrief.paths import REPO_ROOT, load_registry

ROLES = ["hook", "context", "reveal", "mechanism", "payoff", "callback"]
TRANSITIONS = ["cut", "zoom_through", "mask_reveal", "match_cut", "morph_fuse", "whip"]
LIMITS = ("headline", "label", "impact_reveal")  # widths are measured with the real font (_too_wide)
EXAMPLE_SHOTS = ("s07", "s13", "s19", "s29")
_WS = re.compile(r"[\s　]+")


@dataclass
class Section:
    title: str
    body: str
    narration: str = ""  # expected verbatim narration (concatenated), when it can be parsed
    shots: int = 0       # author's shot count for this chapter, when a shot table gives it
    topics: Optional[set] = None  # script topics (None = unrestricted catalog)
    no_mascot: bool = False       # the script forbids the mascot (无吉祥物)


@dataclass
class Result:
    plan: dict
    errors: dict[str, list[str]] = field(default_factory=dict)  # section title -> unresolved problems
    rounds: dict[str, int] = field(default_factory=dict)
    model: str = ""


# ----------------------------------------------------------------- script parsing
def _parse_sections(text: str, storyboard: Optional[str] = None) -> tuple[list[Section], str]:
    """Sections to storyboard + shared context (facts, production notes). Shot lists win over prose scripts."""
    src = storyboard or text
    context = _facts(text)  # facts / production notes live in the full script
    if re.search(r"^###\s*s\d{2,3}\b", src, re.M):  # shot list: '## 段落' > '### sNN' blocks with **旁白**
        secs = []
        for m in re.finditer(r"^##\s+(.+?)\n(.*?)(?=^##\s|\Z)", src, re.M | re.S):
            title, body = m.group(1).strip(), m.group(2)
            if not re.search(r"^###\s*s\d{2,3}\b", body, re.M):
                continue
            narr = "".join(re.findall(r"\*\*旁白\*\*[：:]\s*(.+)", body))
            secs.append(Section(title, body.strip(), narr))
        return secs, context
    m = re.search(r"^##\s*\d*\.?\s*完整旁白.*?\n(.*?)(?=^##\s|\Z)", src, re.M | re.S)
    part = m.group(1) if m else src
    # chapter headings: '### 一、…' or a line that is only bold text ('**一、冷开场**')
    hs = list(re.finditer(r"^(?:###\s+(.+?)|\*\*([^*\n]+)\*\*)\s*$", part, re.M))
    secs = []
    for i, h in enumerate(hs):
        body = part[h.end():hs[i + 1].start() if i + 1 < len(hs) else len(part)].strip()
        if body:
            secs.append(Section((h.group(1) or h.group(2)).strip(), body, _WS.sub("", body)))
    _attach_shot_table(secs, src)
    if not secs:  # plain prose: one section per paragraph group of ~300 chars
        buf, secs = "", []
        for para in [p.strip() for p in part.split("\n\n") if p.strip()]:
            buf += para
            if len(buf) > 300:
                secs.append(Section(f"part {len(secs) + 1}", buf, _WS.sub("", buf)))
                buf = ""
        if buf:
            secs.append(Section(f"part {len(secs) + 1}", buf, _WS.sub("", buf)))
    return secs, context


def parse_script(text: str, storyboard: Optional[str] = None) -> tuple[list[Section], str]:
    """Sections to storyboard + shared context (the script's preamble = global requirements, facts, notes)."""
    secs, context = _parse_sections(text, storyboard)
    pre = text.split("\n## ", 1)[0].strip() if "\n## " in text else ""
    if pre:
        context = "SCRIPT-WIDE REQUIREMENTS (obey them):\n" + pre[:2500] + "\n\n" + context
    topics, no_mascot = topics_of(text + (storyboard or "")), "无吉祥物" in text or "no mascot" in text.lower()
    for sec in secs:
        sec.topics, sec.no_mascot = topics, no_mascot
    return secs, context


def _attach_shot_table(secs: list[Section], text: str) -> None:
    """A shot table ('| e01 | time | 旁白 | 画面 | 屏幕文字 | 音效 | 来源 |', chapter rows '| | **一、…** |') is the
    author's intent: give each chapter its rows so the storyboard follows them."""
    rows = re.findall(r"^\|.*\|\s*$", text, re.M)
    header = next((r for r in rows if "旁白" in r and "画面" in r), "")
    cur, by_title = None, {}
    for r in rows:
        cells = [c.strip() for c in r.strip().strip("|").split("|")]
        chap = next((c.strip("*") for c in cells if re.fullmatch(r"\*\*[^*]+\*\*", c)), None)
        if chap:
            cur = chap
        elif cur and cells and re.fullmatch(r"[a-z]?\d{2,3}", cells[0]):
            by_title.setdefault(cur, []).append(r)
    for sec in secs:
        key = next((k for k in by_title if k == sec.title or k.split("、")[-1] in sec.title
                    or sec.title.split("、")[-1] in k), None)
        if key:
            sec.body += ("\n\nAUTHOR'S SHOT LIST for this chapter (follow its shot split, visuals, on-screen text and "
                         "sound; map the visuals onto catalog components):\n" + header + "\n" + "\n".join(by_title[key]))
            sec.shots = len(by_title[key])


def _facts(text: str) -> str:
    """Shared context: fact checks, production / voice notes, the story spine."""
    pat = r"^##\s*\d*\.?\s*(事实核对|制作要点|配音与制作提示|叙事结构|Facts)[^\n]*\n.*?(?=^##\s|\Z)"
    return "\n".join(m.group(0) for m in re.finditer(pat, text, re.M | re.S))[:9000]


# ----------------------------------------------------------------- prompt
def catalog(topics: Optional[set[str]] = None, landscape: bool = False) -> dict:
    """LLM-facing component catalog; topic-specific entries only when the script is about that topic
    (topics=None: everything). landscape=True (16:9) marks every entry `landscape: true|false`: true when the
    catalog entry says so or the component is drawn natively for the 16:9 frame."""
    from motionbrief.render.svg_canvas.components import COMPONENTS
    out = {}
    for k, v in load_registry()["components"].items():
        if not (v.get("status") == "implemented" and "llm" in v
                and (topics is None or v["llm"].get("topic") in (None, "general", *topics))):
            continue
        entry = {f: x for f, x in v["llm"].items() if f != "landscape"}  # 9:16 catalog stays unchanged
        if landscape:
            entry["landscape"] = bool(v["llm"].get("landscape")) or bool(
                getattr(COMPONENTS.get(k), "native_landscape", False))
        out[k] = entry
    return out


def _modes(entry: dict) -> Optional[set[str]]:
    if "modes" in entry:
        return set(entry["modes"])
    spec = (entry.get("props") or {}).get("mode")
    if isinstance(spec, str) and "|" in spec:
        return {re.match(r"\s*([a-z_0-9]+)", p).group(1) for p in spec.split("|") if re.match(r"\s*[a-z_]", p)}
    return None


def _example() -> str:
    p = REPO_ROOT / "examples" / "isp_v3" / "plan_full.json"
    if not p.exists():
        return ""
    shots = [s for s in json.loads(p.read_text(encoding="utf-8"))["shots"] if s["id"] in EXAMPLE_SHOTS]
    return json.dumps({"shots": shots}, ensure_ascii=False, indent=1)


SYSTEM = """You are the storyboard artist of MotionBrief, an engine for 9:16 technical explainer shorts in the
"Cartoon Tech v2" style. You turn a script section into a SHOT PLAN (JSON). The engine renders it; you only
choose components and beats. Rules:
1. One shot per narration line or clause group, 3-7 s of speech (~15-35 Chinese chars); never shorter
   than ~12 chars unless it is a one-word punchline. Narration is copied
   VERBATIM from the script, in order, nothing added or dropped; concatenated it must equal the section.
2. Use ONLY components from the catalog, with their listed modes/props. Prefer a topic component whose mode
   matches the beat; otherwise use InfoCards / StatBars (generic). Background objects ("rain" ParticleStream
   photons, depth 0) are optional atmosphere. Coordinates are 1080x1920; subtitles live at y≈1480, keep content
   between y 420 and 1400.
3. Every shot shows problem -> method -> failure -> fix where the script does; failures get a red ✗, fixes ✓
   (use modes/marks that show them).
4. beats are FRACTIONS of the shot: rev = the visual change (aligned with the key word in the line), imp = the
   slam / mark / number landing. A bass cue needs imp. cues are in order from: tick, blip, bass, riser.
   Use bass on the shot's key moment, not on every shot.
5. texts: on-screen words, short: headline ≤6 chars, label ≤14 chars, impact_reveal ≤5 Chinese chars or ≤8
   letters/digits (center only; it auto-shrinks to fit). Never cut a key term to fit: write it whole (具身智能,
   not 具身). Put the big word EITHER in a TitleCard OR in texts, never both.
   Max one headline/label at "top" per shot (+ optionally one "lower" label).
6. role: hook (first 1-2 shots), context, reveal (twists / protagonist), mechanism, payoff, callback (ending
   that loops back to the hook). transition: cut | zoom_through | mask_reveal | match_cut | morph_fuse.
   Use mask_reveal to open a new chapter, match_cut inside a chapter, zoom_through for reveals.
7. citations: Wikipedia titles or https URLs from the script/sources for factual lines; none for rhetoric.
8. hero: true only for the single protagonist reveal (ChipReveal, renderer "three").
9. note (optional): small disclaimer shown in the corner for the whole shot, e.g. "简化理论上限模型，并非真实 Benchmark",
   <= 40 chars. Only when the script needs one.
Return ONLY JSON: {"shots": [ ... ]} using the field names of the example."""


TOPICS = {"camera": ("摄像头", "相机", "传感器", "像素", "照片", "ISP", "图像", "镜头"),
          "robotics": ("机器人", "机械臂", "具身", "抓取")}


def topics_of(text: str) -> set[str]:
    """Topics a script is about (≥3 keyword hits and ≥40% of the leading topic's hits): topic-specific
    components are offered only for those, so passing mentions don't pull in another series' look."""
    hits = {t: sum(text.count(k) for k in kws) for t, kws in TOPICS.items()}
    top = max(hits.values(), default=0)
    return {t for t, h in hits.items() if h >= 3 and h >= 0.4 * top}


def _prompt(sec: Section, start: int, context: str, prev_tail: str, landscape: bool = False) -> str:
    return (f"COMPONENT CATALOG:\n{json.dumps(catalog(sec.topics, landscape), ensure_ascii=False)}\n\n"
            f"EXAMPLE (from another section, format only):\n{_example()}\n\n"
            f"SHARED CONTEXT (facts / production notes):\n{context}\n\n"
            f"Previous shot (for continuity): {prev_tail or 'none (this is the opening)'}\n\n"
            f"SECTION: {sec.title}\nShot ids start at s{start:02d}.\n{sec.body}\n\nReturn the JSON shot plan now.")


# ----------------------------------------------------------------- shot-list pins and notes
_SHOT_BLOCK = re.compile(r"^###\s*(s\d{2,3})[^\n]*\n(.*?)(?=^#{2,3}\s|\Z)", re.M | re.S)
_PIN = re.compile(r"^\*\*组件\*\*[：:]\s*(.+?)\s*$", re.M)
_NOTE = re.compile(r"^\*\*注释\*\*[：:]\s*(.+?)\s*$", re.M)
_PIN_NAME = re.compile(r"([A-Za-z_]\w*)\s*(\{.*\})?")


def _shot_blocks(text: str) -> list[tuple[str, str]]:
    """(shot id, block body) for every `### sNN` block of a shot list."""
    return [(m.group(1), m.group(2)) for m in _SHOT_BLOCK.finditer(text)]


def parse_pins(text: str) -> dict[str, tuple[str, dict]]:
    """`**组件**：<ComponentName> {json props}` pins a shot's visual to that registry component (enforced in code)."""
    known = {k for k, v in load_registry()["components"].items() if v.get("status") == "implemented"}
    pins: dict[str, tuple[str, dict]] = {}
    for sid, body in _shot_blocks(text):
        m = _PIN.search(body)
        if not m:
            continue
        pm = _PIN_NAME.fullmatch(m.group(1))
        if not pm:
            raise ValueError(f"{sid}: bad 组件 line {m.group(1)!r}; expected <ComponentName> [JSON props]")
        name = pm.group(1)
        if name not in known:
            raise ValueError(f"{sid}: unknown pinned component {name!r} (known: {', '.join(sorted(known))})")
        try:
            props = json.loads(pm.group(2)) if pm.group(2) else {}
        except json.JSONDecodeError as e:
            raise ValueError(f"{sid}: 组件 {name} props are not valid JSON: {e}") from e
        if not isinstance(props, dict):
            raise ValueError(f"{sid}: 组件 {name} props must be a JSON object")
        pins[sid] = (name, props)
    problems = [f"{sid}: {p}" for sid, (name, props) in pins.items() for p in pin_problems(name, props)]
    if problems:
        raise ValueError("pinned components have props they do not take, or lack content props (fix all):\n- "
                         + "\n- ".join(problems))
    return pins


# props a pinned component must be given: without them it draws its demo values (numbers from another episode)
REQUIRED_PROPS: dict[str, tuple | dict] = {
    "Equation": {"fraction": ("num", "den", "result"), "product": ("a", "b", "result")},
    "TokenStream": {"decode": ("tokens",), "prefill": ("prompt",)},
    "SplitCompare": ("left", "right"), "HBars": ("items",), "ChipTags": ("tags",), "CodeTerminal": ("code", "output"),
    "NpuArray": ("label",), "BusCongestion": ("label",), "ModelShrink": ("bits",), "InfoCards": ("items",),
    "PipelineFlythrough": ("stages",), "TitleCard": ("text",), "StatBars": ("bars",),
}


def pin_problems(name: str, props: dict) -> list[str]:
    """Unknown prop names (the component ignores them) and missing content props, for one pinned component."""
    declared = (load_registry()["components"][name].get("llm") or {}).get("props") or {}
    out = []
    unknown = sorted(set(props) - set(declared) - {"mode"})
    if unknown:
        out.append(f"{name} does not take {', '.join(unknown)} (it takes: {', '.join(sorted(declared)) or 'no props'})")
    req = REQUIRED_PROPS.get(name, ())
    if isinstance(req, dict):
        req = req.get(props.get("mode") or next(iter(req)), ())
    missing = [k for k in req if k not in props]
    if missing:
        out.append(f"{name} needs {', '.join(missing)} (otherwise it shows demo values)")
    return out


def parse_notes(text: str) -> dict[str, str]:
    """`**注释**：<text>` sets a shot's corner footnote (overrides the LLM's note)."""
    notes = {}
    for sid, body in _shot_blocks(text):
        m = _NOTE.search(body)
        if m:
            notes[sid] = m.group(1).strip()
    return notes


_NARR = re.compile(r"\*\*旁白\*\*[：:]\s*(.+)")
_BEAT = re.compile(r"^\*\*节拍\*\*[：:]\s*(.+?)\s*$", re.M)
_BEAT_KEY = re.compile(r"(rev|imp)\s*([01](?:\.\d+)?)")


def parse_beat_line(body: str) -> dict:
    """`**节拍**：rev 0.3，imp 0.7` -> {"rev": 0.3, "imp": 0.7} (fractions of the shot; empty if absent)."""
    m = _BEAT.search(body)
    if not m:
        return {}
    return {k: float(v) for k, v in _BEAT_KEY.findall(m.group(1))}


def _align_to_shot_list(shots: list, sec: Section, start: int) -> list:
    """A shot-list section is cut by its `### sNN` blocks, not by the LLM: one shot per block, in order, with the
    block's narration verbatim. Each block takes the visual fields (texts, objects, beats, cues, ...) of the LLM shot
    whose narration matches it best, so merged or split replies cannot shift pins and notes onto the wrong line.
    Blocks without narration take the LLM's silent shots in order, else a minimal silent shot."""
    from difflib import SequenceMatcher

    blocks = _shot_blocks(sec.body)
    if not blocks:
        return shots
    llm = [s for s in shots if isinstance(s, dict)]
    norm = [_WS.sub("", s.get("narration") or "") for s in llm]
    silent = iter([s for s, n in zip(llm, norm) if not n])
    out = []
    for k, (_, body) in enumerate(blocks):
        narr = "".join(_NARR.findall(body)).strip()
        key = _WS.sub("", narr)
        if key:
            scores = [SequenceMatcher(None, key, n).ratio() if n else -1.0 for n in norm]
            src = llm[max(range(len(llm)), key=scores.__getitem__)] if llm and max(scores) > 0 else {}
        else:
            src = next(silent, None) or {"duration": 3.0, "beats": {"rev": 0.3, "imp": 0.7}}
        sh = json.loads(json.dumps(src))  # a merged LLM shot may serve two blocks: copy, never share
        sh.setdefault("role", "mechanism")
        sh.setdefault("objects", [])
        sh.update(id=f"s{start + k:02d}", narration=narr)
        beats = {**(sh.get("beats") or {}), **parse_beat_line(body)}  # the shot list's 节拍 line wins
        sh["beats"] = beats or {"rev": 0.3, "imp": 0.7}  # no beats at all: a default cut keeps the pacing rule
        out.append(sh)
    return out


def _fill_empty_visuals(shots: list) -> None:
    """A shot left without objects (a silent block the LLM dropped) keeps the neighbouring visual, previous first.
    Runs after pins are applied, so it continues the pinned picture."""
    for k, sh in enumerate(shots):
        if isinstance(sh, dict) and not sh.get("objects"):
            near = next((o for o in shots[:k][::-1] + shots[k + 1:] if isinstance(o, dict) and o.get("objects")), None)
            if near:
                sh["objects"] = json.loads(json.dumps(near["objects"]))
                sh.pop("target", None)


def _apply_shot_list(shots: list, start: int, pins: Optional[dict], notes: Optional[dict]) -> None:
    """Pinned shots get exactly one object (the pinned component); their texts, beats and cues are kept.
    Shot-list notes replace the LLM's note. Runs on the renumbered shots, before validation."""
    for i, sh in enumerate(shots):
        sid = f"s{start + i:02d}"
        if not isinstance(sh, dict):
            continue
        if pins and sid in pins:
            name, props = pins[sid]
            first = next((o.get("id") for o in sh.get("objects", []) if isinstance(o, dict) and o.get("id")), "pin")
            sh["objects"] = [{"id": first, "component": name, "depth": 1, "renderer": "svg", "props": dict(props)}]
            if sh.get("target", first) != first:
                sh.pop("target", None)
        if notes and sid in notes:
            sh["note"] = notes[sid]


def _has_continuous(scene: dict) -> bool:
    """A scene with a component that keeps moving (`continuous_motion`) is never a visual gap."""
    from motionbrief.render.svg_canvas.components import COMPONENTS
    return any(getattr(COMPONENTS.get(v.get("component")), "continuous_motion", False)
               for v in scene.get("visualObjects", []))


# ----------------------------------------------------------------- validation
def _too_wide(s: str, style: str) -> int:
    """Pixels by which a centred text exceeds the safe area: measured with the real font, as G1 does."""
    from motionbrief.paths import load_tokens
    from motionbrief.render.svg_canvas.components import text_width
    tok = load_tokens()
    st, sa = tok["typography"]["styles"][style], tok["safeArea"]
    half = min(540 - sa["left"], 1080 - sa["right"] - 540)
    size = st["size"]
    if style == "impact_reveal":  # drawn auto-fitted, down to MIN_FIT of its size
        from motionbrief.render.svg_canvas.prims import fit_size
        size = fit_size(s, size, 900, 2 * half)
    w = text_width(s, size) + (0 if style == "impact_reveal" else 72)
    return max(0, round(w - 2 * half))


def validate_section(shots: list[dict], sec: Section, start: int) -> list[str]:
    cat, errs = catalog(), []
    for i, sh in enumerate(shots):
        sid = f"s{start + i:02d}"
        if sh.get("id") != sid:
            errs.append(f"shot {i}: id must be {sid}")
        if sh.get("role") not in ROLES:
            errs.append(f"{sid}: role must be one of {ROLES}")
        if sh.get("transition", "cut") not in TRANSITIONS:
            errs.append(f"{sid}: transition must be one of {TRANSITIONS}")
        if not sh.get("objects"):
            errs.append(f"{sid}: needs at least one object")
        for ob in sh.get("objects", []):
            comp = ob.get("component")
            if comp not in cat:
                errs.append(f"{sid}: unknown component {comp!r}")
                continue
            topic = cat[comp].get("topic")
            if sec.topics is not None and topic not in (None, "general") and topic not in sec.topics:
                errs.append(f"{sid}: {comp} belongs to the {topic!r} series; this script is about {sorted(sec.topics)}")
            if comp == "PhotonGuide" and sec.no_mascot:
                errs.append(f"{sid}: the script says no mascot (无吉祥物): remove PhotonGuide")
            modes = _modes(cat[comp])
            mode = (ob.get("props") or {}).get("mode")
            if modes and mode is not None and mode not in modes:
                errs.append(f"{sid}: {comp} mode {mode!r} not in {sorted(modes)}")
            if ob.get("renderer", "svg") == "three" and comp != "ChipReveal":
                errs.append(f"{sid}: renderer three is only for ChipReveal")
        titles = [(o.get("props") or {}) for o in sh.get("objects", []) if o.get("component") == "TitleCard"]
        for tx, what in [(t, "text") for t in sh.get("texts", [])] + [(t, "TitleCard text") for t in titles]:
            style = tx.get("style", "headline")
            if style not in LIMITS:
                errs.append(f"{sid}: text style must be headline|label|impact_reveal")
                continue
            over = _too_wide(str(tx.get("text", "")), style)
            if over:
                errs.append(f"{sid}: {what} {tx.get('text')!r} is {over}px too wide for style {style} "
                            f"(shorten it, or use a smaller style)")
        b = sh.get("beats", {})
        for k in ("rev", "imp", "exit", "text_at", "ent"):
            if b.get(k) is not None and not 0 <= float(b[k]) <= 1:
                errs.append(f"{sid}: beats.{k} must be a fraction 0..1")
        if "bass" in sh.get("cues", []) and b.get("imp") is None:
            errs.append(f"{sid}: cue bass needs beats.imp")
    got = _WS.sub("", "".join(s.get("narration", "") for s in shots))
    if sec.narration and got != _WS.sub("", sec.narration):
        errs.append(f"narration must equal the section verbatim. expected: {sec.narration} | got: {got}")
    if errs:
        return errs
    try:  # compile the section alone and run the scene-level G1 checks
        from motionbrief.quality.deterministic import check_ir
        # a section is not a video: whole-video rules (total length, hero object present) are checked after merge
        plan = {"video": {"id": "section", "productionLevel": "standard"}, "shots": shots}
        ir = compile_plan(plan, estimate_voice({s["id"]: s["narration"] for s in shots}))
        for sc in ir["scenes"]:  # pacing inside each shot (the whole-video cadence rule, caught early)
            span = sc["tEnd"] - sc["tStart"]
            if _has_continuous(sc):  # a continuously moving component is never a visual gap
                continue
            # gaps between events INSIDE the shot (the tail runs into the next shot's start, judged after merging)
            ev = sorted({sc["tStart"]} | {m["at"] for m in sc["motionGrammar"]} | {t["at"] for t in sc["typography"]})
            gap = max([b - a for a, b in zip(ev, ev[1:])] or [0.0])
            if gap > 5.0:  # same limit as G1 cadence (maxVisualGapSec)
                errs.append(f"{sc['id']}: {gap:.1f}s without a visual event: move beats.rev/imp so something changes "
                            f"at least every 4 s (shot is {span:.1f}s)")
        _, rep = check_ir(ir, [s["id"] for s in shots])
        errs += [d for c in rep.checks if not c.passed and not c.advisory for d in c.details
                 if "DURATION_RANGE" not in d]
    except PlanError as e:
        errs.append(str(e))
    except Exception as e:  # pydantic validation and friends: report, let the model fix it
        errs.append(f"IR does not validate: {str(e)[:600]}")
    return errs


# ----------------------------------------------------------------- driver
def _parse_json(text: str) -> dict:
    a, b = text.find("{"), text.rfind("}")
    if a < 0 or b <= a:
        raise ValueError("no JSON object in the reply")
    return json.loads(text[a:b + 1])


def _ask(router, ref: Optional[str], messages: list[dict]) -> tuple[str, str]:
    if ref:  # pin one provider:model (model comparisons)
        prov, model = ref.split(":", 1)
        timeout = float(router.caps["capabilities"]["deep_reasoning"].get("timeout_s", 600))
        return router.providers[prov].chat(model, messages, timeout=timeout), ref
    res = router.chat("deep_reasoning", messages)
    return res.text, f"{res.provider}:{res.model}"


_HOOK_TITLE = re.compile(r"开场|钩子|hook", re.I)  # sections that open the video, not chapters

SYSTEM_LANDSCAPE = (SYSTEM
                    .replace("an engine for 9:16 technical explainer shorts",
                             "an engine for 16:9 long-form technical explainer videos (8-15 minutes, chapters)")
                    .replace("Coordinates are 1080x1920;",
                             "Coordinates are the 1080x1920 design space (the engine spreads objects into landscape "
                             "columns);")
                    + "\nPACE: cut every 3-5 seconds (one shot = one visual change). "
                    "A shot never stays still for more than 5 seconds."
                    + "\nPrefer components marked landscape: true; they are drawn for the 16:9 frame and fill it. Use "
                      "portrait-only components (landscape: false) only when no landscape component fits.")


def storyboard_section(sec: Section, start: int, context: str, prev_tail: str, router, ref=None,
                       repairs: int = 2, system: str = SYSTEM, *, landscape: bool = False,
                       pins: Optional[dict] = None, notes: Optional[dict] = None) -> tuple[list[dict], list[str], int, str]:
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": _prompt(sec, start, context, prev_tail, landscape)}]
    shots, errs, used = [], ["no reply"], ""
    for rnd in range(repairs + 1):
        text, used = _ask(router, ref, messages)
        try:
            shots = _parse_json(text).get("shots", [])
            for i, sh in enumerate(shots):  # ids follow position; renumber instead of spending a repair round on it
                if isinstance(sh, dict):
                    sh["id"] = f"s{start + i:02d}"
            shots = _align_to_shot_list(shots, sec, start)  # the shot list fixes the cut: ids and narration
            _apply_shot_list(shots, start, pins, notes)  # shot-list pins / notes win over the LLM's choice
            _fill_empty_visuals(shots)
            errs = validate_section(shots, sec, start)
        except (ValueError, json.JSONDecodeError) as e:
            errs = [f"reply is not valid JSON: {e}"]
        if not errs:
            return shots, [], rnd, used
        messages += [{"role": "assistant", "content": text},
                     {"role": "user", "content": "Fix these problems and return the whole corrected JSON:\n- "
                                                 + "\n- ".join(errs[:20])}]
    return shots, errs, repairs, used


def run(script: str, storyboard: Optional[str] = None, *, video_id: str = "video", title: str = "",
        router=None, ref: Optional[str] = None, repairs: int = 2, workers: int = 4, aspect: str = "9:16",
        visual_style: str = "neon") -> Result:
    """Script text (+ optional shot-list text) -> shot plan, sections storyboarded in parallel.

    16:9 uses the long-form prompt and tags the first shot of each chapter with the chapter title.
    """
    from motionbrief.llm.router import CapabilityRouter
    router = router or CapabilityRouter.from_file()
    secs, context = parse_script(script, storyboard)
    if not secs:
        raise ValueError("no sections found in the script")
    landscape = aspect == "16:9"
    system = SYSTEM_LANDSCAPE if landscape else SYSTEM
    src = storyboard or script  # the shot list (or a shot-list script): its pins and notes are enforced
    pins, notes = parse_pins(src), parse_notes(src)
    # shot ids must be known up front for parallel sections: estimate shots per section from the script
    counts = [max(1, s.shots or len(re.findall(r"^###\s*s\d{2,3}\b", s.body, re.M)) or round(len(s.narration) / 24))
              for s in secs]
    starts = [1 + sum(counts[:i]) for i in range(len(secs))]
    with ThreadPoolExecutor(workers) as pool:
        futs = [pool.submit(storyboard_section, s, st, context, "", router, ref, repairs, system,
                            landscape=landscape, pins=pins, notes=notes)
                for s, st in zip(secs, starts)]
        outs = [f.result() for f in futs]
    shots, res = [], Result({"video": {"id": video_id, "title": title, "aspect": aspect, "visualStyle": visual_style},
                             "shots": []})
    for sec, (sh, errs, rnd, used) in zip(secs, outs):
        if aspect == "16:9" and sh and not _HOOK_TITLE.search(sec.title):  # the cold open is a hook, not a chapter
            sh[0]["chapter"] = sec.title
        shots += sh
        res.rounds[sec.title] = rnd
        res.model = used
        if errs:
            res.errors[sec.title] = errs
    for i, sh in enumerate(shots, 1):  # sections may come back with more/fewer shots than estimated
        sh["id"] = f"s{i:02d}"
    res.plan["shots"] = shots
    _video_pass(res, secs, [o[0] for o in outs], context, router, ref, pins=pins, notes=notes)
    return res


HINTS = {"visual gap": "a stretch with no visual event: move beats.rev earlier and/or add beats.imp, or split the"
                       " long line into two shots, so something changes at least every 4 s; "
                       "a gap at the END of a shot needs a late"
                       " beat (beats.imp ≈0.8-0.9 or a text with text_at ≈0.8)",
         "average cut interval": "shots are too short on average: merge adjacent short lines into one shot so shots"
                                 " last 3-6 s (≈15-30 Chinese characters)"}


def _video_pass(res: Result, secs: list[Section], per_sec: list[list[dict]], context: str, router, ref,
                rounds: int = 2, *, pins: Optional[dict] = None, notes: Optional[dict] = None) -> None:
    """Whole-video G1 rules (cadence, hook, ending) can only be judged after merging: map each failure to the
    section owning the shot / time it names, repair that section, and RE-VERIFY on the merged video (a section
    check cannot see cadence, so a section-level 'pass' proves nothing here)."""
    for _ in range(rounds + 1):
        fails, ir = _video_fails(res)
        if not fails:
            for sec in secs:
                res.errors.pop(sec.title, None)
            return
        if _ == rounds:
            break
        _video_round(res, secs, per_sec, context, router, ref, fails, ir, pins=pins, notes=notes)
    res.errors["(whole video)"] = fails


def _video_fails(res: Result) -> tuple[list[str], dict]:
    from motionbrief.quality.deterministic import check_ir
    ir = compile_plan(res.plan, estimate_voice({s["id"]: s["narration"] for s in res.plan["shots"]}))
    _, rep = check_ir(ir)
    return [d for c in rep.checks if not c.passed and not c.advisory for d in c.details], ir


def _video_round(res: Result, secs: list[Section], per_sec: list[list[dict]], context: str, router, ref,
                 fails: list[str], ir: dict, *, pins: Optional[dict] = None, notes: Optional[dict] = None) -> None:
    landscape = res.plan["video"].get("aspect") == "16:9"
    owner = {}  # shot id -> section index (ids after renumbering)
    k = 0
    for si, sh in enumerate(per_sec):
        for _ in sh:
            k += 1
            owner[f"s{k:02d}"] = si
    by_sec: dict[int, list[str]] = {}
    for d in fails:
        m = re.search(r"\b(s\d{2,3})\b", d)
        t = re.search(r"t=([\d.]+)s", d)
        sid = m.group(1) if m else next((s["id"] for s in ir["scenes"]
                                         if t and s["tStart"] <= float(t.group(1)) < s["tEnd"]),
                                       None)
        if sid in owner:
            by_sec.setdefault(owner[sid], []).append(d)
    for si, errs in by_sec.items():
        start = 1 + sum(len(x) for x in per_sec[:si])
        sec = secs[si]
        hints = [h for k, h in HINTS.items() if any(k in e for e in errs)]
        note = Section(sec.title, sec.body + "\n\nWHOLE-VIDEO CHECK FAILED for this section (fix it):\n- "
                       + "\n- ".join(errs + hints), sec.narration)
        shots, left, _, _ = storyboard_section(note, start, context, "", router, ref, repairs=1,
                                               system=SYSTEM_LANDSCAPE if landscape else SYSTEM, landscape=landscape,
                                               pins=pins, notes=notes)
        if shots and not left:
            per_sec[si] = shots
    res.plan["shots"] = [sh for part in per_sec for sh in part]
    for i, sh in enumerate(res.plan["shots"], 1):
        sh["id"] = f"s{i:02d}"


def write(res: Result, plan_out: Path) -> None:
    plan_out.parent.mkdir(parents=True, exist_ok=True)
    plan_out.write_text(json.dumps(res.plan, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
