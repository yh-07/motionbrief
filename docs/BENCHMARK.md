# Benchmark — mature explainer-video pipelines, and what MotionBrief adopts

Purpose: the review should absorb proven practice instead of inventing process. Each source below
is a pipeline that demonstrably ships high-quality explainers at scale. Only lessons that map to a
concrete mechanism in this repo are listed. Adoption IDs refer to `docs/REVIEW.md` (R-18 … R-25).

## 1. Sources reviewed

| # | Pipeline | Type | Why it is a good reference |
|---|---|---|---|
| A | **Kurzgesagt** (studio, ~70 people) | Hand-made 2D flat vector + 3D accents | Closest to the Cartoon Tech target look; published process: research → script (≈ a dozen drafts) → sketch/illustration → voiceover & animation → custom music/SFX; publishes a source sheet per video; ≈ 1,200 h/video (https://kurzgesagt.org/what-we-do) |
| B | **3Blue1Brown / Manim** | Code-driven animation | Proves "animation as code" for technical explanation; scene = class, reusable mobjects, iterate on one scene with checkpoints, render clips then edit (https://github.com/3b1b/videos, https://www.3blue1brown.com/lessons/manim-demo/) |
| C | **Commercial explainer studios** (Animation Explainers, Vidico, Creamy Animation) | Agency pipeline | Stage gates with sign-off: brief → script lock → storyboard + style frames → voiceover → animation → delivery; "a board change costs minutes, an animation change costs days" (https://animationexplainers.com/explainer-video-production-process/, https://vidico.com/explainer-video-production/explainer-video-storyboard/) |
| D | **Vox-style explainers** | Editorial explainer format | Script is a sequence of boards: one visual idea + one narration line + one on-screen label per board; label complements, not duplicates, narration (https://videoai.me/blog/vox-style-explainer-scripts-2026) |
| E | **Motion Canvas** | Code animation + editor | Voice/animation sync via named *time events* instead of hard-coded waits; changing the voiceover shifts later events automatically (https://motioncanvas.io/docs/time-events) |
| F | **Code2Video** (NUS Show Lab, ICML 2026, MIT) | Agentic code→video research | Planner → Coder (scoped auto-fix: line → block → regenerate) → Critic (VLM with a 6×6 **visual-anchor grid**); evaluated by aesthetics + **TeachQuiz** knowledge transfer (https://github.com/showlab/Code2Video) |
| G | **TheoremExplainAgent** (ACL 2025) | Agentic Manim explainer | Planner/coder split is essential; main residual defect class = **layout** issues (https://arxiv.org/abs/2502.19400) |
| H | **Remotion TikTok template** | Short-form captions | Word-level captions from Whisper word timestamps (`Caption{text,startMs,endMs}`), page-grouped (https://github.com/remotion-dev/template-tiktok) |
| I | **Short-form retention practice** (YouTube Shorts / Douyin creator guidance) | Platform craft | Hook in the first frame (no intro), a beat every few seconds, endings that loop back to the opening, compare against your own baseline (no official benchmark); Shorts accept up to 3 min (https://prepublish.ai/guides/youtube-shorts-retention, https://kompozy.io/how-to/youtube-shorts-optimization-tips) |

Note on source quality: A, B, E–H are primary (studio/official/paper/repo). C, D, I are practitioner
guides; they are used only for widely-agreed craft rules, never for numeric thresholds.

## 2. Common pattern across successful pipelines

```
research+sources ─▶ script LOCK ─▶ boards/animatic LOCK ─▶ voice ─▶ animate TO the voice ─▶ music/SFX ─▶ review ─▶ ship
        (A,C)          (A,C,D)          (B,C,F)            (A,E)        (A,E)                  (A)        (C,F,G)
```

Five invariants show up everywhere:
1. **Facts and sources first**, published with the video (A).
2. **Cheap preview before expensive render**: boards/animatic in studios (C), per-scene iteration in Manim (B), planner-before-coder in agents (F, G).
3. **Voice sets the clock**: animation is timed to the recorded narration, not the other way round (A, E).
4. **Unit of writing = one idea per board** with paired narration + label (D).
5. **Layout is the dominant residual defect** for code-generated video → needs a dedicated critic (F, G).

## 3. Gap analysis vs. our v1.0 handoff → adoptions

| Lesson | Before (v1.0 handoff) | Adopted now | Status |
|---|---|---|---|
| Duration follows content; Shorts allow up to 3 min (I) | Hard 20–120 s + tier ranges as errors | Tiers advisory (warning); hard bounds 15–180 s in `tokens.json`; new `extended` tier (R-18) | ✅ code + test |
| Voice sets timing (A, E) | Fixed `tStart/tEnd`; voice squeezed with `atempo` up to 1.35× | `timing.retime()`: scenes extend to fit narration, beats keep offsets, later scenes shift; voice never stretched; `scene_ir.timed.json` drives rendering (R-19) | ✅ code + test |
| Animatic before render (B, C) | Storyboard stage only an LLM stub; first visual check was the full render | `motionbrief animatic` → keyframe contact sheet per beat in ~5 s; it already found a near-empty frame in s07 (fixed) (R-20) | ✅ code + test |
| Critic with visual anchors (F, G) | G2 asked for free-text defects | Frames sent with a 6×6 A1–F6 anchor grid; defects must cite a cell and a fix (R-21) | ✅ code + test |
| Stage sign-offs (C) | G3 = one final approval | G3 requires `script_lock → animatic_lock → final` records (R-22) | ✅ code + test |
| One idea per board; loop endings (D, I) | Not checked | Advisory G1 checks `one_idea_per_board`, `loop_callback_ending` (non-blocking) (R-23) | ✅ code |
| Scoped auto-fix for generated code (F) | "Escalate to strong model" only | Phase 2: when the LLM emits IR, repair by scope: field → scene → regenerate scene, before full escalation (R-24) | 📝 planned |
| Comprehension eval (F: TeachQuiz) | G2 judges looks and facts, not learning | Phase 2: G2 adds a quiz check: a model that sees only frames + subtitles must answer 3 key questions (R-24) | 📝 planned |
| Word-level captions (H) | Phrase captions with proportional timing | Needs per-word timestamps from the TTS (or forced alignment); Phase 2 with neural TTS (R-25) | 📝 planned |
| Custom score per video (A) | One procedural bed | Keep procedural (license-clean); add per-pillar motifs in Phase 4 | 📝 planned |

## 3b. Round 3: craft lessons applied to the v02 cut

| Lesson (source) | Applied as |
|---|---|
| Flat vector + soft gradients + saturated palette on dark space-blue, no or thin outlines (Kurzgesagt style analyses) | Cartoon Tech v2 primitives (`prims.py`) |
| Quirky, relatable characters turn abstract things into actors (Kurzgesagt) / personification works in Chinese sci-pop (芳斯塔芙) | Mascot 小光, a photon with eyes, carries the story |
| Secondary action, overlapping action, fake 3D depth (Kurzgesagt motion course syllabus); 12 principles (squash & stretch, anticipation, follow-through) | Overshoot entrances, squash & stretch, idle blink/bob, staggered pops, parallax + drift |
| Dramatic question, moments of change, emotional arousal correlate with popularity (Huang & Grant 2020); ABT structure; curiosity gap | v02 script structure (hook → guide → But → Therefore → payoff → callback) |
| Start from everyday life, beauty first, then the knowledge (CAS Physics team) | Hook on "your own photos"; sunset/city/candle imagery |
| Voiceover sets the timing (Kurzgesagt) | Fixture built from measured voice durations |

## 3c. Round 4: procedural-video skill collection (opus-video-skills, MIT; ideas only, clean-room)

A Claude Code skill set that, like us, renders every frame as a pure function of time with procedural
sound. Its sound notes matched a measured defect in v02 (13 noise whooshes in 83 s, 14 full impacts).

| Lesson | Applied as | Measured on isp_v02 (before → after) |
|---|---|---|
| No noise whooshes on transitions; in-key swell/bell/glide instead; never the same cue twice in a row | `audio/sound_design.py` maps cue + `transitionIn` to an in-key cue from the bed chord at that time (`sfx.TONAL`); repeats are dropped | transition flatness 0.225 → 0.000 (noise → tonal) |
| About half the cuts silent (downbeat + next shot's own sounds carry them) | `match_cut`/`cut` stay silent | audible transition cues 12/13 → 7/13 |
| Full impact only for ~5 structural moments | rank hero > hook/reveal > first payoff > callback; others `soft_impact` | full impacts 14 → 5; the others 8 dB lower, no click |
| You can't listen: verify with a spectrum picture + per-section RMS; guard NaN (silences the mix) | `mix.analyze()` → `audio/analysis.json`, `logs/spectrum.png`; non-finite stems raise; G1 checks every planned cue is audible in its stem; advisory `transition_sound_variety` | — |
| Audio-only changes: remux, don't re-render | `assemble` caches `frames/_video.mp4` keyed by scene hashes + grain + encoder | assemble 54 s → 2.4 s on an audio-only change |

Decisions per cue are recorded in `audio/sound_design.json`; the authored IR is never rewritten.
Not taken: its renderer (Chrome canvas per frame), watercolour/no-text style, 16:9 layout, Google Fonts at
render time, and agent-only image self-review (we keep deterministic G1 + cross-family G2).

## 4. Deliberately not adopted

- **Kurzgesagt-level hand illustration / 1,200 h per video**: conflicts with semi-automatic scale; we take the *process* (gates, sources, voice-first) and not the labor model.
- **Engagement-bait endings** common in Douyin guides ("关注/点赞"): still forbidden by REQUIREMENTS §7 (G1 `no_cta_ending`). We take the loop/callback ending instead.
- **Pixel-space video generation** (F compares against Veo/Wan and finds them weak for precise technical diagrams): consistent with our non-goal.
- **Numeric "retention benchmarks"** from marketing posts: not published by platforms; Review Gates stay relative to our own baseline (REQUIREMENTS §5).
