# SPDX-License-Identifier: Apache-2.0
"""Check an inbox script before dropping it into inbox/.

    .venv/Scripts/python.exe tools/check_inbox_script.py inbox/<id>.md

Three layouts are accepted:
  * one document with inline shots: '## 章节' headings with '### sNN' blocks (template A, single file)
  * the same, with the shots in a separate file named by front-matter 'shotlist:' (older template A)
  * narration only: '## 3. 完整旁白' with '### 章节' sections (template B)

Prints ERROR (the engine would reject it) and WARN (it will run, but quality may suffer), then OK or the count.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import motionbrief.paths  # noqa: E402,F401  (loads .env)
from motionbrief.content.storyboard import _NARR, _shot_blocks, parse_beat_line, parse_pins  # noqa: E402

ASPECTS = ("9:16", "16:9")
WS = re.compile(r"\s+")


def front_matter(text: str) -> dict:
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.lstrip().startswith("#"):
            k, v = line.split(":", 1)
            out[k.strip()] = v.split("#", 1)[0].strip().strip('"')
    return out


def body_of(text: str) -> str:
    m = re.match(r"^---\n.*?\n---\n", text, re.S)
    return text[m.end():] if m else text


def narration_sections(text: str) -> dict[str, str]:
    """'### title' blocks under '## 3. 完整旁白' -> narration text (whitespace removed)."""
    m = re.search(r"^##\s*\d*\.?\s*完整旁白.*?\n(.*?)(?=^##\s|\Z)", text, re.M | re.S)
    body = m.group(1) if m else ""
    out = {}
    for h in re.finditer(r"^###\s+(.+?)\s*$\n(.*?)(?=^###\s|^##\s|\Z)", body, re.M | re.S):
        out[h.group(1)] = WS.sub("", h.group(2))
    return out


def check_shots(sl: str, msgs: list[str]) -> list[str]:
    try:
        parse_pins(sl)  # raises on unknown components or bad JSON props
    except ValueError as e:
        msgs.append(f"ERROR {e}")
    blocks = _shot_blocks(sl)
    for k, (sid, _) in enumerate(blocks, 1):
        if sid != f"s{k:02d}":
            msgs.append(f"ERROR shot ids must run s01, s02, … in order; found {sid} at position {k}")
            break
    for sid, body in blocks:
        beats = parse_beat_line(body)
        if not beats:
            msgs.append(f"WARN {sid}: no 节拍 line; a default cut is used")
        elif any(not 0 <= v <= 1 for v in beats.values()):
            msgs.append(f"ERROR {sid}: 节拍 values must be between 0 and 1")
        narr = "".join(_NARR.findall(body)).strip()
        if beats and all(0 <= v <= 1 for v in beats.values()):
            dur = max(3.0, len(narr) / 5)  # about 5 characters per second of speech
            marks = [0.0] + sorted(beats.values()) + [1.0]
            worst = max(b - a for a, b in zip(marks, marks[1:])) * dur
            if worst > 4.0:
                msgs.append(f"WARN {sid}: about {worst:.1f} s without a visual change (shot about {dur:.1f} s); "
                            f"move imp or rev closer together")
        if narr and len(narr) > 40:
            msgs.append(f"WARN {sid}: {len(narr)} characters of narration in one shot; split it (3–6 s each)")
    return msgs


def check(path: Path) -> list[str]:
    msgs: list[str] = []
    text = path.read_text(encoding="utf-8")
    fm = front_matter(text)
    if not fm:
        return ["ERROR front-matter (--- ... ---) is missing"]
    vid = fm.get("id", "")
    if not re.fullmatch(r"[a-z0-9_]+", vid):
        msgs.append(f"ERROR id {vid!r} must be lowercase letters, digits and _")
    if fm.get("aspect", "9:16") not in ASPECTS:
        msgs.append(f"ERROR aspect must be 9:16 or 16:9 (quote it), got {fm.get('aspect')!r}")
    if fm.get("produce", "approve") not in ("approve", "auto"):
        msgs.append("ERROR produce must be approve or auto")
    if fm.get("aspect") == "16:9" and fm.get("visualStyle", "neon") == "neon":
        msgs.append("WARN 16:9 video without visualStyle: graphite (the flat technical background)")
    if not re.search(r"^##\s*\d*\.?\s*事实核对", text, re.M):
        msgs.append("WARN no '## 事实核对' table: factual claims will have no citations")

    body = body_of(text)
    shotlist = fm.get("shotlist")
    if shotlist:  # shots in a separate file: its narration must match the script's chapters
        sl_path = path.parent / shotlist
        if not sl_path.exists():
            return msgs + [f"ERROR shotlist {shotlist!r} is not next to the script"]
        sl = sl_path.read_text(encoding="utf-8")
        check_shots(sl, msgs)
        secs = narration_sections(text)
        for m in re.finditer(r"^##\s+(.+?)\s*$\n(.*?)(?=^##\s|\Z)", sl, re.M | re.S):
            title, block = m.group(1), m.group(2)
            got = WS.sub("", "".join(_NARR.findall(block)))
            want = secs.get(title)
            if want is None and not got:
                continue  # a silent chapter (picture only) needs no script section
            if want is None:
                msgs.append(f"ERROR shot-list chapter {title!r} has no matching '### {title}' in the script")
            elif got != want:
                msgs.append(f"ERROR chapter {title!r}: the narration in the shot list differs from the script "
                            f"(copy the 旁白 lines verbatim, in order)")
        return msgs

    if _shot_blocks(body):  # one document: the shots are inline
        check_shots(body, msgs)
        return msgs

    secs = narration_sections(text)  # narration only: the storyboard model writes the shots
    if not secs:
        msgs.append("ERROR no '## 3. 完整旁白' section with '### 章节' headings (or inline '### sNN' shots)")
    for title, narr in secs.items():
        if not narr:
            msgs.append(f"ERROR chapter {title!r} has no narration")
        for sent in re.split(r"[。！？]", narr):
            if len(sent) > 60:
                msgs.append(f"WARN chapter {title!r}: a sentence of {len(sent)} characters, split it at a comma")
    total = sum(len(n) for n in secs.values())
    if secs and not 150 <= total <= 3000:
        msgs.append(f"WARN narration is {total} characters (about {total // 5} s); check the target length")
    return msgs


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    msgs = check(Path(sys.argv[1]))
    for m in msgs:
        print(m)
    errors = [m for m in msgs if m.startswith("ERROR")]
    print("OK" if not errors else f"{len(errors)} error(s): fix them before dropping the file into inbox/")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
