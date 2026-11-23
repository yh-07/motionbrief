# MotionBrief inbox: hand over a script, get a video

Drop ONE file per video into this folder (`inbox/` at the repo root). People and other
agents use the same contract. A watcher (`motionbrief inbox --watch`), or a one-shot `motionbrief inbox`,
picks it up. Results go to `outbox/<id>/`.

**Templates for other agents** (copy one, fill it in, then run `tools/check_inbox_script.py` on it before dropping it in):
- `TEMPLATE_rich.md`: one file. The agent writes the chapters, the shots (narration, visuals, component pins, beats, footnotes) and the facts in it. Best quality.
- `TEMPLATE_minimal.md`: the agent writes only the narration by chapter and facts. The engine plans the shots.

## Accepted inputs

| File | Meaning |
|---|---|
| `<name>.md` | Script in Markdown (format below). The storyboard LLM turns it into shots. |
| `<name>.shots.md` | Optional shot list referenced from a script's front-matter (`shotlist:`). Never processed on its own. |
| `<name>.plan.json` | A finished shot plan (schema in `motionbrief/content/shots.py`). Skips the LLM step. |

Write the file atomically: write `<name>.md.tmp`, then rename it to `<name>.md`. Files starting with `.` or `_`
are ignored.

## Shot list (`<name>.shots.md`)

Optional, named by the script's `shotlist:` field. One `## 段落` per chapter, one `### sNN` block per shot:

- `**旁白**：…` the narration, copied verbatim from the script (required).
- `**画面**：…` free-form visual notes for the storyboard (optional).
- `**组件**：<ComponentName> {json props}` pins the shot's visual to that registry component. Enforced in code: the
  LLM's objects for that shot are replaced by this one component (texts, beats and cues are kept). Unknown names fail.
- `**注释**：…` a small corner footnote on every frame of the shot (≤ 40 characters, e.g. a simplification disclaimer).

```markdown
## 一、开场：100 TOPS 的错觉

### s02
**旁白**：一秒钟，一百万亿次运算。
**画面**：镜头穿过屏幕进入内部 PCB，只高亮 SoC。
**组件**：PhoneSoc {"mode": "soc_zoom", "zoom": 0.3}
**注释**：简化理论上限模型，并非真实 Benchmark
```

## Script format (`<name>.md`)

```markdown
---
id: isp_ep2_night          # required: a-z, 0-9, _ ; becomes outbox/<id>/ and fixtures/<id>.json
title: 夜景是拍出来的，还是算出来的   # shown in metadata
produce: approve           # approve (default: stop at the animatic) | auto (render right away)
aspect: "9:16"            # optional: "9:16" (default, Shorts <= 180 s) | "16:9" (long-form, 480-900 s, chapter cards). Quote it.
also: ["9:16"]             # optional: extra render of the same plan in another aspect -> final_9x16.mp4 (fails if the duration is outside that aspect's bounds)
shotlist: isp_ep2.shots.md # optional
model:                     # optional: pin provider:model from config/capabilities.qgenie.yaml
---

## 3. 完整旁白

### 一、冷开场（钩子）
你手机的夜景，其实是十几张照片叠出来的。

### 二、……
……

## 4. 事实核对
| 说法 | 依据 | 处理 |
|---|---|---|
| 叠 N 张噪点降为 1/√N | [Shot noise](https://en.wikipedia.org/wiki/Shot_noise) | 事实 |
```

The spoken text is taken verbatim. Write it exactly as it should be read, with Chinese punctuation, because the
pauses follow the punctuation. Rules that keep the result good:

- **Sections**: use `###` headings under a "完整旁白" `##` heading. One section is one chapter, 1–8 sentences.
  Sections are storyboarded in parallel.
- **Length**: about 5 Chinese characters per second of speech. 300 characters ≈ 1 min. The hard limit is
  15–300 s; Shorts are ≤ 180 s.
- **Hook**: the first sentence is the hook. Do not end with "关注/点赞" calls to action, which the gate
  rejects. Ending by echoing the hook works best.
- **Facts**: every factual claim should have a public source (Wikipedia or https) in the 事实核对 table.
  The storyboard puts them on the shots as citations.
- **Visual hints are welcome**: a line like `（画面：……）` or a shot list helps the storyboard pick
  components. Components available: `motion/registry.json`, field `llm`.
- **English terms**: spoken letter by letter (ISP, JPEG, HDR) unless listed in `motionbrief/tts/g2p_zh.py`.
  RAW is read as "肉".

## Lifecycle (`outbox/<id>/status.json`, field `state`)

`queued` → `storyboarding` → `awaiting_approval` → `rendering` → `done` | `failed`

- **awaiting_approval**: review `outbox/<id>/animatic.png` (one keyframe per beat). To approve, create an
  empty file `outbox/<id>/APPROVE`, or run `motionbrief inbox approve <id>`.
- **done**: `outbox/<id>/final.mp4`, `cover.png`, `subtitles.srt`, `sources.md`, `metrics.json`.
- **failed**: `message` explains why (unresolved storyboard errors, G1 failures, render errors). Fix the script
  and drop it again; the same `id` overwrites.

Agents can poll `status.json`, or run `motionbrief inbox status` for a table of all videos.

## Running the intake

```bash
.venv/Scripts/python.exe -m motionbrief.apps.cli inbox --watch            # keep watching (20 s polls)
.venv/Scripts/python.exe -m motionbrief.apps.cli inbox                    # process once
.venv/Scripts/python.exe -m motionbrief.apps.cli inbox --auto-produce     # render without approval stops
```
