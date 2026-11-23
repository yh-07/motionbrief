# Layer B — three.js toon (GPU, via headless Edge/Chromium)

Implemented for `ChipReveal` (`chip.html` + `toon.py`); `vendor/three.module.js` is three.js r170 (MIT,
`vendor/LICENSE-three.txt`).

How it composes: only the object's *body* is drawn in WebGL, on a transparent canvas; `SvgBackend` embeds
that PNG as an `<image>` where the 2.5D body would be. Rays/glows/shockwave/contact shadow, camera moves,
drop/bob/squash transforms, labels and subtitles stay in SVG, so layer order and timing are unchanged.
Per-frame state comes from Python (`components.LAYER_B_STATE`), the same beats as the 2.5D version.

Where it runs: a host whose browser has WebGL. This laptop has none in the probe, so the planner keeps
`three` only when `MOTIONBRIEF_RENDER_WEBGL=1` declares the LAN render host GPU-capable; those scenes are
routed to remote slots only. If the remote fails, the scene is rendered locally with the 2.5D body and the
`three -> svg` / `remote -> local` degradations are recorded (separate checkpoint hashes, never mixed).

Look (Cartoon Tech v2, not v1 hard toon):
- `MeshToonMaterial` patched to sample the gradient map's **RGB** (stock three.js reads only `.r`), so the
  Scene IR `gradientRamp` colours are the shading colours. Soft mode (default): smoothstep blends between
  dark/mid/light on N·L thresholds, `LinearFilter`. `soft: false` gives classic hard bands (`NearestFilter`).
- No ambient light: added white light lifts dark colours toward grey in linear space; the ramp's dark colour
  is the shadow. One key `DirectionalLight` at intensity ≈ π (toon BRDF is Lambert/π).
- Inverted-hull outline kept thin (0.35 × IR width); none on small parts (pins), where it reads as jagged.
- MSAA only; 2× supersampling measured no visible gain.

Browser: `MOTIONBRIEF_BROWSER_CHANNEL=msedge` on the PC; default flags `--headless=new --use-angle=d3d11
--force_high_performance_gpu` give `ANGLE (NVIDIA … RTX 3060 … Direct3D11)`. A cold browser can fail its
first WebGL context; `ToonRenderer` retries.
