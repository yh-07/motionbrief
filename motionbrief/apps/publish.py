# SPDX-License-Identifier: Apache-2.0
"""Publish package for a finished video: platform copy (B站 / 抖音), chapter list and designed covers.

  outbox/<id>/publish.md          copy per platform, chapter timestamps, cover text
  outbox/<id>/cover_16x9.png      1920x1080 (B站 / YouTube)
  outbox/<id>/cover_3x4.png       1200x1600 (B站 portrait)
  outbox/<id>/cover_9x16.png      1080x1920 (抖音)

Copy comes from the fast_text capability. Anything the LLM returns that is missing or invalid falls back to
deterministic copy, so the package never fails because of the LLM.
"""
from __future__ import annotations

import json
import os
import re
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from motionbrief.apps import inbox
from motionbrief.paths import REPO_ROOT  # noqa: F401  (loads .env for the font setting)

COVER_SIZES = {"cover_16x9.png": (1920, 1080), "cover_3x4.png": (1200, 1600), "cover_9x16.png": (1080, 1920)}
TEXT_MAIN, TEXT_SUB, PILL, INK, STROKE = "#F8FAFC", "#FACC15", "#FACC15", "#0B0F1A", "#0B0F1A"
AI_LABEL = "本视频旁白含 AI 生成内容。"
_SENT = re.compile(r"[^。！？!?\n]+[。！？!?]?")
_NOTE_KEYS = re.compile(r"简化|并非|非真实|仅供|示意|Benchmark|disclaim|AI", re.I)
_NUMERAL = re.compile(r"^[一二三四五六七八九十百]+[、.．]\s*")
_PROMPT = """You write platform publishing copy for a short Chinese explainer video.
Output strict JSON only, no prose, exactly this shape:
{"bilibili": {"title": str, "desc": str, "tags": [str]},
 "douyin": {"title": str, "desc": str, "hashtags": [str]},
 "cover": {"main": str, "sub": str, "tag": str}}
Rules:
- Simplified Chinese. bilibili.title <= 40 characters; douyin.title <= 30 characters.
- bilibili.desc: 3-6 short lines separated by newline characters. bilibili.tags: at most 10 short tags.
- douyin.desc: at most 2 short lines, no hashtags inside it. douyin.hashtags: 3-6 entries starting with '#'.
- cover.main <= 8 characters, cover.sub <= 14 characters, cover.tag <= 10 characters.
- No clickbait the video does not deliver. No invented numbers or facts: use only the narration and the fact table.
- Keep every disclaimer that appears in the fact table (for example: a simplified model, not a real benchmark).
- No calls to action such as 关注, 点赞 or 三连."""


def _json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _inputs(d: Path) -> tuple[dict, str]:
    """front-matter (or plan video/meta) and the narration body of the original inbox file."""
    src = next((p for p in sorted(d.glob("input.*"))), None)
    if src is None:
        return {}, ""
    text = src.read_text(encoding="utf-8")
    if src.name.endswith(".plan.json"):
        plan = json.loads(text)
        return {**plan.get("video", {}), **plan.get("meta", {})}, ""
    return inbox.front_matter(text)


def _chapters(scenes: list[dict]) -> list[tuple[float, str]]:
    out: list[tuple[float, str]] = []
    last = None
    for s in scenes:
        ch = s.get("chapter")
        if ch and ch != last:
            out.append((float(s.get("tStart", 0.0)), _NUMERAL.sub("", str(ch)).strip()))
        last = ch
    return out


def _mmss(t: float) -> str:
    m, s = divmod(int(t), 60)
    return f"{m:02d}:{s:02d}"


def _chapter_lines(chs: list[tuple[float, str]]) -> list[str]:
    if not chs:
        return ["00:00 开场"]
    first = chs[0][1] if chs[0][0] < 1 else "开场"
    rest = chs[1:] if chs[0][0] < 1 else chs
    return [f"00:00 {first}"] + [f"{_mmss(t)} {title}" for t, title in rest]


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT.findall(text) if s.strip()]


def _notes(sources: str) -> tuple[list[str], bool]:
    """Disclaimer lines of the fact table that must survive into the description; and whether AI is disclosed."""
    must, ai = [], False
    for line in (x.strip() for x in sources.splitlines()):
        if not line or line.startswith(("#", "-", "*", ">", "|")) or not _NOTE_KEYS.search(line):
            continue
        if "AI" in line:
            ai = True
        else:
            must.append(line)
    return must, ai


def _ask_llm(router: Any, title: str, narr: str, sources: str) -> dict:
    try:
        if router is None:
            from motionbrief.llm.router import CapabilityRouter
            router = CapabilityRouter.from_file()
        user = f"Script title: {title}\n\nNarration:\n{narr[:3000]}\n\nFact table:\n{sources[:3000]}"
        res = router.chat("fast_text", [{"role": "system", "content": _PROMPT}, {"role": "user", "content": user}])
        text = res if isinstance(res, str) else str(getattr(res, "text", ""))
        a, b = text.find("{"), text.rfind("}")
        data = json.loads(text[a:b + 1]) if a >= 0 and b > a else {}
        return data if isinstance(data, dict) else {}
    except Exception as e:  # the package must not fail because of the LLM
        print(f"[publish] LLM copy unavailable, using deterministic copy: {str(e)[:200]}", file=sys.stderr)
        return {}


def _str(v: Any, limit: int) -> str:
    return str(v).strip()[:limit] if isinstance(v, str) and v.strip() else ""


def _lines(v: Any, limit: int) -> list[str]:
    raw = v.splitlines() if isinstance(v, str) else (v if isinstance(v, list) else [])
    return [str(x).strip() for x in raw if str(x).strip()][:limit]


def _tags(v: Any, limit: int) -> list[str]:
    raw = re.split(r"[,，、]", v) if isinstance(v, str) else (v if isinstance(v, list) else [])
    out = [re.sub(r"[#\s]+", "", str(x)) for x in raw]
    return list(dict.fromkeys(x[:20] for x in out if x))[:limit]  # Bilibili tags take up to 20 characters


def _copy(vid: str, title: str, meta: dict, narr: str, chs: list[tuple[float, str]], llm: dict,
          must: list[str], ai: bool) -> dict:
    sents = _sentences(narr)
    intro = sents[:2] or [title]
    tags = list(dict.fromkeys(t[:20] for _, t in chs if t))[:10] or ["科普"]
    b = {"title": title[:40], "desc": intro, "tags": tags}
    d = {"title": title[:30], "desc": intro[:2], "hashtags": ["#" + re.sub(r"\s+", "", t) for t in tags[:4]]}
    c = {"main": title.rstrip("？?！!。.，,")[:8], "sub": (sents[0] if sents else title)[:14], "tag": tags[0][:10]}

    lb = llm.get("bilibili") if isinstance(llm.get("bilibili"), dict) else {}
    ld = llm.get("douyin") if isinstance(llm.get("douyin"), dict) else {}
    lc = llm.get("cover") if isinstance(llm.get("cover"), dict) else {}
    b["title"] = _str(lb.get("title"), 40) or b["title"]
    b["desc"] = _lines(lb.get("desc"), 6) or b["desc"]
    b["tags"] = _tags(lb.get("tags"), 10) or b["tags"]
    d["title"] = _str(ld.get("title"), 30) or d["title"]
    d["desc"] = _lines(ld.get("desc"), 2) or d["desc"][:2]
    d["hashtags"] = [h if h.startswith("#") else "#" + h for h in _tags(ld.get("hashtags"), 6)] or d["hashtags"]
    c["main"] = _str(lc.get("main"), 8) or c["main"]
    c["sub"] = _str(lc.get("sub"), 14) or c["sub"]
    c["tag"] = _str(lc.get("tag"), 10) or c["tag"]

    if meta.get("publish_title"):
        b["title"] = d["title"] = str(meta["publish_title"])
    for key, field in (("cover_main", "main"), ("cover_sub", "sub"), ("cover_tag", "tag")):
        if meta.get(key):
            c[field] = str(meta[key])

    # disclaimers from the fact table and the AI label always make it into the B站 description
    compact = lambda s: re.sub(r"\s+", "", s)  # noqa: E731
    out = b["desc"][:6]
    for _ in range(7):
        miss = [n for n in must if compact(n) not in compact("".join(out))]
        if ai and "AI" not in "".join(out):
            miss.append(AI_LABEL)
        if not miss:
            break
        out = out[:max(0, 6 - len(miss))] + miss
    b["desc"] = out[:6]
    return {"bilibili": b, "douyin": d, "cover": c, "vid": vid}


def _publish_md(copy: dict, title: str, chs: list[tuple[float, str]]) -> str:
    b, d, c = copy["bilibili"], copy["douyin"], copy["cover"]
    lines = [f"# 发布包：{title}", f"视频 ID：{copy['vid']}", "", "## B站", "",
             f"标题：{b['title']}", "", "简介：", *b["desc"], "", "章节：", *_chapter_lines(chs), "",
             f"标签：{', '.join(b['tags'])}", "", "## 抖音", "", f"标题：{d['title']}", "", "简介：",
             *d["desc"], " ".join(d["hashtags"]), "", "## 封面文字", "",
             f"主标题：{c['main']}", f"副标题：{c['sub']}", f"标签：{c['tag']}", ""]
    return "\n".join(lines)


# ----------------------------------------------------------------- covers
@lru_cache(maxsize=None)
def _font_path() -> str:
    env = os.environ.get("MOTIONBRIEF_FONT_FILE", "")
    for cand in (env, "C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf"):
        if cand and Path(cand).exists():
            return cand
    raise FileNotFoundError("no CJK font: set MOTIONBRIEF_FONT_FILE in .env")


@lru_cache(maxsize=None)
def _font(size: int, bold: bool):
    from PIL import ImageFont
    f = ImageFont.truetype(_font_path(), size)
    if bold:
        try:  # variable fonts (Noto Sans SC) only; static bold files ignore this
            f.set_variation_by_name("Bold")
        except Exception:
            pass
    return f


def _fill(img, w: int, h: int):
    from PIL import Image
    s = max(w / img.width, h / img.height)
    nw, nh = max(w, round(img.width * s)), max(h, round(img.height * s))
    im = img.resize((nw, nh), Image.LANCZOS)
    left, top = (nw - w) // 2, (nh - h) // 2
    return im.crop((left, top, left + w, top + h))


def _wrap(draw, text: str, font, maxw: int) -> list[str]:
    lines: list[str] = []
    cur = ""
    for ch in text:
        if ch == "\n":
            lines.append(cur)
            cur = ""
            continue
        nxt = cur + ch
        if not cur or draw.textlength(nxt, font=font) <= maxw:
            cur = nxt
        else:
            lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    return lines


def _fit(draw, text: str, maxw: int, max_h: int, start: int, max_lines: int, bold: bool):
    """largest font size (from start down) whose wrapped text fits both the width and the height budget"""
    size = start
    while True:
        f = _font(size, bold)
        lines = _wrap(draw, text, f, maxw)
        if (len(lines) <= max_lines and len(lines) * int(size * 1.15) <= max_h) or size <= 20:
            return f, size, lines
        size -= 4


def _draw_text(im, cov: dict) -> None:
    from PIL import ImageDraw
    w, h = im.size
    short = min(w, h)
    mx, my = round(w * 0.06), round(h * 0.06)
    maxw = w - 2 * mx
    d = ImageDraw.Draw(im)

    tag_size = max(22, round(short * 0.035))
    tf = _font(tag_size, True)
    tb = d.textbbox((0, 0), cov["tag"], font=tf)
    tw, th = tb[2] - tb[0], tb[3] - tb[1]
    px, py = round(tag_size * 0.7), round(tag_size * 0.35)
    d.rounded_rectangle([mx, my, mx + tw + 2 * px, my + th + 2 * py], radius=(th + 2 * py) // 2, fill=PILL)
    d.text((mx + px - tb[0], my + py - tb[1]), cov["tag"], font=tf, fill=INK)

    y = max(my + th + 2 * py + round(h * 0.05), round(h * 0.16))
    mf, msize, mlines = _fit(d, cov["main"], maxw, round(h * 0.40), round(short * 0.17), 2, True)
    stroke = max(3, round(msize / 20))
    lh = int(msize * 1.15)
    for i, line in enumerate(mlines):
        d.text((mx, y + i * lh), line, font=mf, fill=TEXT_MAIN, stroke_width=stroke, stroke_fill=STROKE)
    y += len(mlines) * lh + round(msize * 0.2)

    sf, ssize, slines = _fit(d, cov["sub"], maxw, round(h * 0.20), round(msize * 0.5), 2, True)
    slh = int(ssize * 1.15)
    for i, line in enumerate(slines):
        d.text((mx, y + i * slh), line, font=sf, fill=TEXT_SUB, stroke_width=max(2, round(ssize / 25)),
               stroke_fill=STROKE)


def _covers(src: Path, out: Path, cov: dict) -> list[str]:
    from PIL import Image, ImageFilter
    base = Image.open(src).convert("RGB")
    paths = []
    for name, (w, h) in COVER_SIZES.items():
        im = _fill(base, w, h).filter(ImageFilter.GaussianBlur(6))
        im = Image.blend(im, Image.new("RGB", im.size, (0, 0, 0)), 0.45)
        _draw_text(im, cov)
        p = out / name
        im.save(p)
        paths.append(str(p))
    return paths


# ----------------------------------------------------------------- entry point
def write_publish(vid: str, router: Any = None, outbox: Optional[Path] = None) -> list[str]:
    """Write outbox/<vid>/publish.md and the three designed covers; returns the written file paths."""
    d = (outbox or inbox.OUTBOX) / vid
    st = _json(d / "status.json")
    meta, narr = _inputs(d)
    ir_scenes = _json(REPO_ROOT / st["ir"]).get("scenes", []) if st.get("ir") and (REPO_ROOT / st["ir"]).exists() else []
    if not narr:
        narr = "".join(str(s.get("narration", "")) for s in ir_scenes)
    sources = (d / "sources.md").read_text(encoding="utf-8") if (d / "sources.md").exists() else ""
    title = str(meta.get("title") or st.get("title") or vid)
    chs = _chapters(ir_scenes)
    must, ai = _notes(sources)
    copy = _copy(vid, title, meta, narr, chs, _ask_llm(router, title, narr, sources), must, ai)
    md = d / "publish.md"
    md.write_text(_publish_md(copy, title, chs), encoding="utf-8")
    covers = _covers(d / "cover.png", d, copy["cover"])
    return [str(md), *covers]
