# MotionBrief

**AI technical short-video / motion storytelling engine** — engineer-grade 20–120 s vertical
explainers (Camera / ISP / AI / XR / Robot …) with a unified *Cartoon Tech v1* visual IP,
deterministic rendering, multitrack sound design and machine-checked quality gates.

> Clean-room, provider-neutral, weak-hardware-first. No diffusion / video-generation dependency.

## Quick start

```bash
# system deps: ffmpeg, cairo, a CJK font (e.g. Noto Sans CJK), espeak-ng (reference TTS)
pip install -e .[dev]

motionbrief probe                                   # what this host can render (WebGL? HW encoder?)
motionbrief validate fixtures/isp_v01.json          # Scene IR + G1 (IR level)
motionbrief animatic fixtures/isp_v01.json          # keyframe board for animatic_lock (~5 s)
motionbrief produce fixtures/isp_v01.json --scenes s03   # sprint acceptance: s03 Layer A + G1
motionbrief produce fixtures/isp_v01.json           # full 70 s ISP hero → work/isp_v01/final.mp4
motionbrief route code_generation "hello"           # capability router (stub when no creds)
pytest -q                                           # unit + render smoke + s03 acceptance
python tools/sanitize/sensitive_scan.py --root .    # clean-room gate
```

Output bundle `work/<id>/`: `final.mp4, cover.png, audio/narration.wav, audio/narration_mix.wav,
audio/stems/*.wav, subs/subtitles.srt, scene_ir.json, sources.md, metrics.json, frames/, logs/`.

## Everyday use: drop folder, no agent needed

```bash
.venv/Scripts/python.exe -m motionbrief.apps.cli inbox --watch   # keep running (polls inbox/ every 20 s)
# 1. drop <name>.md into inbox/ (format: inbox/README.md, template: inbox/TEMPLATE.md)
# 2. review outbox/<id>/animatic.png
# 3. approve:  motionbrief inbox approve <id>    -> outbox/<id>/final.mp4
motionbrief inbox status                                         # table of all videos
```
Routine videos need no Claude Code session; open one only to change the engine. Agent rules (token budget,
delegation to haiku, caching) are in `CLAUDE.md`.

## Script in, video out

```bash
motionbrief storyboard my_script.md [--shotlist my_shots.md] --id my_video --measure   # LLM -> plan -> IR + animatic
motionbrief produce fixtures/my_video.json                                             # render (after checking the animatic)
```
The LLM (capability `deep_reasoning`) writes only a shot plan (`work/<id>/plan.json`) using registry components
(`motion/registry.json` → `llm` catalog); `content/shots.py` compiles it deterministically (voice-first timing,
beats, sound cues). Every section is validated (verbatim narration, components/modes, text limits, G1) and repaired
with the concrete errors; whole-video rules are re-verified after merging. `InfoCards` / `StatBars` cover beats no
topic component fits. Measured on the ISP v3 script (prose only, no shot list): Claude 4.8 Opus 56 shots in 63 s,
no repairs, G1 pass; Gemini 3.1 Pro 50 shots in ~350 s, G1 pass after repairs.

## How it works

Scene IR (validated, versioned) → local agent executes allow-listed tasks
(`tts_narration → render_scene × N → mix_audio → assemble → qa_g1`) with retries, degradation,
checkpoints and idempotency → G1 deterministic gate → G2 cross-family vision review → G3 human.

Rendering: Layer A is SVG → cairo → FFmpeg (no GPU/WebGL needed). Layer B (three.js toon) and
Layer C (Blender cel) are optional; when unavailable, objects degrade to their 2.5D fallback and the
degradation is recorded.

## Docs
- `docs/REQUIREMENTS.md` — what & why
- `docs/IMPLEMENTATION.md` — how, status, next sprint
- `docs/REVIEW.md` — review findings and how each was resolved
- `docs/BENCHMARK.md` — mature pipelines studied (Kurzgesagt, 3Blue1Brown, studios, Code2Video …) and what was adopted
- `docs/architecture.md`, `docs/scene-ir.md`

## Voice
Default TTS is **Kokoro v1.0** (offline neural) with `misaki[zh]` G2P (`pip install "misaki[zh]"`); point
`MOTIONBRIEF_KOKORO_PYTHON/MODEL/VOICES` at a Kokoro-onnx install. espeak-ng is only a CI fallback.

## Status
Phase 0–1 complete; Phase 2 (ISP hero end-to-end) renders and passes G1. v02 adds Cartoon Tech v2 visuals, a mascot-led script and Kokoro narration (see REVIEW round 3).

License: Apache-2.0 (see D4 in REQUIREMENTS).
