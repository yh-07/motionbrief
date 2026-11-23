# Handoff Review — REQUIREMENTS v1.0 / IMPLEMENTATION v0 → v1.0.1

Scope: review of the two handoff documents before/while implementing First Sprint §21.
Every finding below is either **fixed in code** (with the guarding test) or turned into an **open decision**.

Overall verdict: the requirements are unusually implementable — duration tiers, the 30-video plan
(ratios check out: Micro 11/30 ≈ 37%, Core 15/30 = 50%, Deep 4/30 ≈ 13%, Hero 5, Fast 10), the
Layer A/B/C split and the G1/G2/G3 gates all translate directly into code. The issues are mostly
internal inconsistencies in the Scene IR, a licensing risk in the default renderer, and several
"acceptance" rules that were not yet machine-checkable.

| ID | Sev | Finding | Resolution | Guard |
|---|---|---|---|---|
| R-01 | **High** | Remotion is the implied default Layer A renderer, but it is source-available under its own license: free only for individuals / for-profit orgs ≤ 3 people; larger orgs need a paid company license, and automated video products fall under a usage-priced "Automators" tier (https://www.remotion.dev/docs/license/pricing). This conflicts with "license clear / public GitHub / productisation path" and D4. | Default Layer A is a pure-Python **SVG → cairo → FFmpeg** backend (CairoSVG is LGPL-3.0-or-later, used as an unmodified library; FFmpeg invoked as an external binary). Remotion becomes an optional backend; new open decision **D9**. | `render/probe.py`, `render/remotion/README.md` |
| R-02 | **High** | Scene IR contradictions: (a) `transition` enum contains `whip` but §8 forbids it; (b) `renderer` enum lacks `blender` though `assetStyle=blender_cel` exists; (c) snippet `role:"信"` undefined; (d) `durationTier` is per-scene but is a video property; (e) top-level `palette` mentioned, never defined; (f) "fact scene" undefined so the citation rule is not checkable; (g) time base of `motionGrammar.at` / `soundCues.at` ambiguous. | **IR v1.2.0**: `whip` stays legal in the schema but `cartoon-tech-v1` rejects it in G1; `blender` added; `role` enum; `video.durationTier` + `productionLevel`; `palette{primary≤2, accent}` required; `isFactual`; all `at` are absolute seconds and must fall inside the scene. `migrate()` upgrades v1.1 (the doc snippet is kept as `fixtures/legacy_v1_1_s03.json`). | `tests/test_ir.py`, `test_forbidden_transition` |
| R-03 | Med | Dependency rule `apps → content → {ir,llm,render,quality,motion} → {tts} → stores` puts TTS *below* render/quality and omits the agent. | `apps → content|agent → {render, audio/tts, quality, llm} → {ir, motion} → stores`. | `docs/architecture.md` |
| R-04 | Med | `motion/tokens.ts` as source of truth, but the Python renderer and G1 also need tokens → drift risk. | `motion/tokens.json` is the single source; `tokens.ts` imports it. | — |
| R-05 | Med | "Average 2–4 s per cut" and "visual change every 3–5 s" were not machine-checkable. | Defined: *cut* = scene start or `reveal` beat; *visual event* = any beat / typography entrance. G1 `cadence_hook`: impact/reveal ≤ 3 s, max event gap ≤ 5 s, avg cut 2–4 s. ISP fixture: 25 cuts → 2.8 s avg, max gap 2.5 s. | `test_hook_must_land_in_3s` |
| R-06 | Med | Safe area unspecified. With right-side platform UI, a *centred* line may only be `2 × min(left, right)` wide. G1 immediately caught the first token set (16 chars × 54 px = 920 px > 760 px). | `tokens.safeArea = {top 150, bottom 380, left 72, right 160}`; subtitles 13 chars × 52 px; smart line breaking (never splits numbers / ASCII words). | `test_safe_area_violation`, `test_subtitles.py` |
| R-07 | Med | "Narration −14 LUFS" ambiguous (narration stem vs master). | Master integrated loudness −14 ± 2 LUFS, true peak ≤ −1 dBFS (two-pass `loudnorm`); narration presence checked per scene on the voice stem. | G1 `audio_presence_loudness` |
| R-08 | Med | Router sketch `except Exception: continue` swallows errors; no timeout; no family metadata, so four-eye can't be enforced. | Attempts recorded (`not_configured` / `provider_error`); per-capability timeout; provider `family`; `vision_review` refuses to run without `exclude_family`. | `tests/test_router.py` |
| R-09 | Med | "Idempotency = key + artifacts exist → skip" goes stale when tokens/registry/subtitles change but the key doesn't. | Key = fingerprint of IR + tokens + registry + subtitles + engine version; plus per-scene content hash checkpoint (`frames/<sid>.hash`). | `test_s03_layer_a_acceptance` (2nd run) |
| R-10 | Med | `task.cmd` as a free-form command is a shell-injection surface for the weak agent. | `type` is an allow-list of actions; `cmd` is a closed object of typed args (`additionalProperties:false`). | `test_invalid_task_escalates` |
| R-11 | Low | "Hero = A + B 点睛, Fast = pure A" not enforced. | G1 `style_profile` enforces both from `video.productionLevel`. | — |
| R-12 | Low | #20 is Deep but Standard, while §4 says Deep is mainly Hero and D7 is open. | Left as is; flagged for **D7**. | — |
| R-13 | Low | G3 human gate could be "auto-passed" by an agent. | G3 only passes with a signed `approval.json` (reviewer, timestamp, AI-content label, facts checked). | `quality/gates.py` |
| R-14 | Low | TTS default (D3) unspecified. | espeak-ng adapter for CI / weak hardware (robotic — **not publish quality**); neural local + cloud adapters stubbed. | — |
| R-15 | Low | Proposed tree puts `ir/`, `llm/`, `render/`, `agent/` as top-level packages → import collisions. | Namespaced under `motionbrief/`; non-Python assets (motion, schemas, fixtures) stay top-level. | — |
| R-16 | Low | "Fact scene must cite" didn't say *where* sources appear. | `sources.md` is auto-generated from IR and G1 checks every citation is listed. | G1 `bundle_complete` |
| R-17 | Info | Music / SFX licensing not covered. | All SFX and the music bed are procedurally generated (original, deterministic). | — |

## Round 2: benchmark against mature pipelines (see `docs/BENCHMARK.md`)

| ID | Sev | Finding (source) | Resolution | Guard |
|---|---|---|---|---|
| R-18 | **High** | Duration was hard-locked (20–120 s, tier ranges as errors). Mature pipelines let content set length, and Shorts accept up to 3 min. | Tiers are advisory warnings; hard bounds 15–180 s live in `tokens.json`; added `extended` tier (120–180 s). | `test_duration_not_hard_locked` |
| R-19 | **High** | The timeline was authored first and the voice squeezed to fit (`atempo` ≤ 1.35×). Studios and Motion Canvas time the animation to the voiceover. | `timing.retime()` after TTS: extend scenes, keep beat offsets, shift later scenes, never stretch voice; `scene_ir.timed.json` is the render source; only > hard max escalates. | `tests/test_timing.py` |
| R-20 | Med | No cheap preview: the first visual check was a ~10 min full render. Studios lock boards/animatic first. | `motionbrief animatic` keyframe sheet (~5 s). It immediately exposed a near-empty frame mid-merge in s07 → fixed in `ExposureMerge`. | `test_animatic_keyframes_cover_every_scene` |
| R-21 | Med | Agentic explainers' main residual defect is layout (TheoremExplainAgent); Code2Video's critic uses visual anchors. | G2 frames get a 6×6 anchor grid; defects must cite a cell + fix. | `test_anchor_overlay_returns_png` |
| R-22 | Med | One final human approval only; studios sign off per stage. | G3 = `script_lock → animatic_lock → final` (+ AI label, facts checked). | `test_g3_needs_all_stages` |
| R-23 | Low | No craft checks for "one idea per board" or loop/callback endings. | Advisory (non-blocking △) G1 checks. | — |
| R-24 | Low | Escalation is all-or-nothing; no learning-outcome evaluation. | Phase 2: scoped IR auto-repair; quiz-based comprehension check in G2. | planned |
| R-25 | Low | Captions are phrase-level with proportional timing. | Phase 2: word-level captions from TTS word timestamps / forced alignment. | planned |

## Round 3: quality review of the first cut (user feedback: 画质粗糙、配音机械、内容不生动)

Root causes found by comparing the v1 output with mature works (Kurzgesagt, CAS Physics / 芳斯塔芙, Huang & Grant 2020 on
popular science videos, classic animation principles):

| ID | Sev | Finding | Resolution | Evidence |
|---|---|---|---|---|
| R-26 | **High** | Voice was espeak-ng (formant synth). The bundled Kokoro wrapper hard-codes `lang="en-us"`, so Chinese was read through an English phonemizer. | `tts/g2p_zh.py`: misaki-zh G2P (the phoneme set Kokoro's zh voices were trained on) + English-run IPA; `tts/adapters/kokoro.py` batches sentences; auto-selected when available. | Pitch range p5–p95: espeak 4.2 st vs Kokoro 12.6 st; rate 5.7 chars/s |
| R-27 | **High** | v1 visual language (thick black ink outlines, flat fills, film grain) read as crude. | Cartoon Tech v2: no ink outlines; volume from gradients, highlight/shade bands, colored glows, soft contact shadows; deep-navy background with parallax bokeh + stars; grain removed; final CRF 17. | animatic + frame sheets |
| R-28 | **High** | Motion was mostly fade/scale; nothing alive between beats. | Animation principles: overshoot entrances (anticipation/follow-through), squash & stretch on impacts and fast moves, idle bob/blink/shimmer, staggered pops, always-on camera drift. | `components.py` |
| R-29 | **High** | Script listed steps (lecture tone): no dramatic question, no character, no emotional turn. | v02 script: counter-intuitive hook ("2/3 of your photo's colour is guessed"), personified guide 小光, And/But/Therefore turns (colour-blind sensor → filters → chip must compute), concrete comparison payoff (one blink ≈ 3–12 frames), callback that loops to the hook. | `examples/isp_short/build_v02.py` |
| R-30 | Med | Subtitles timed by character count; no emphasis. | Sentence-level synthesis; chunk boundaries snapped to detected pauses in the real audio; keywords/numbers highlighted in accent colour. | `audio/mix.py: align_chunks` |
| R-31 | Med | Music was a thin sine bed; voice unprocessed. | Original score bed (detuned pads, plucked arpeggio, sub, soft pulse) + synthetic hall reverb; voice chain HPF → compressor → presence EQ → small room. | `audio/sfx.py`, `audio/mix.py` |
| R-32 | Med | Layout collisions only visible after full render. | Caught on the animatic: WB slider vs. label, JPEG/33 ms vs. pipeline; fixed before rendering. | animatic |

Still open (honest limits): Kokoro is good but not studio voice talent; voice cloning or a hired narrator is the next
step for flagship videos. Visuals are code-drawn 2.5D, not hand illustration; Layer B (three.js) remains a skeleton.
