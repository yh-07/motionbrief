# Scene IR v1.2.0

Authoritative definition: `motionbrief/ir/models.py` (pydantic). JSON Schema: `schemas/scene_ir.schema.json`
(generated; `motionbrief export-schema --check` in CI). Example: `fixtures/isp_v01.json`.

## Top level
| field | type | notes |
|---|---|---|
| `irVersion` | `"1.2.0"` | v1.1.0 accepted and migrated by `migrate()` |
| `video` | object | `id, title, aspect 9:16, w 1080, h 1920, fps 30, visualIP cartoon-tech-v1, durationTier micro\|core\|deep, productionLevel hero\|standard\|fast` |
| `palette` | object | `primary` (1–2 hex), `accent` (1 hex). Neutrals come from tokens. |
| `scenes[]` | array | contiguous, no gaps/overlaps; total 20–120 s and inside the tier range |

## Scene
| field | notes |
|---|---|
| `id`, `tStart`, `tEnd` | absolute seconds |
| `role` | `hook, context, reveal, mechanism, payoff, callback` (first scene must be `hook`) |
| `narration`, `isFactual`, `citations[]` | factual + narration ⇒ ≥1 `https://` public citation |
| `styleProfile`, `assetStyle`, `renderQuality`, `cameraProjection`, `depthLayers` | Cartoon Tech extensions; `blender_cel` ⇒ `hero` |
| `camera{move, from, to, easing}` | `push_in, pull_out, pan, static, orbit` |
| `typography[]{text, style, safeArea, at?, until?}` | style ∈ tokens; box must fit the safe area |
| `visualObjects[]{id, component, renderer, props, depth, materialStyle?, outline?, lightingPreset?}` | component ∈ registry; renderer ∈ component.renderers; bands 2–5 |
| `motionGrammar[]{target, grammar, at}` | `entrance, reveal, impact, exit`; target = object id or typography text |
| `soundCues[]{sfx, at, gainDb}` | `bass_hit` must align (±50 ms) with an impact/reveal beat |
| `transitionIn{type}` | schema allows `cut, zoom_through, mask_reveal, whip, match_cut, morph_fuse`; cartoon-tech-v1 forbids `whip` |
| `fallback2D`, `rendererHints` | 3D renderers require `fallback2D=true` |
