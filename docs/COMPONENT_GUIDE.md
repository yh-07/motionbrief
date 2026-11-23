# Writing a MotionBrief component (Cartoon Tech v2)

A component is a pure function `def name(c: Ctx) -> str` that returns an SVG fragment for ONE frame of a
1080×1920 (9:16) video. It must depend only on `c` (time, props, beats). Use no global state, no wall clock, and
no unseeded randomness; use `random.Random(seed)` with a fixed seed. Read these files first:
`motionbrief/render/svg_canvas/components_v3.py` (the reference: same style, same helpers),
`motionbrief/render/svg_canvas/prims.py` (drawing primitives), `motionbrief/render/svg_canvas/components.py`
(the `Ctx` class, around line 23).

## Ctx (what you get)
- `c.t`: current time in seconds. `c.t0`, `c.t1`: shot start and end. `c.frame`: frame number.
- `c.props`: the dict from the storyboard. Always use `.get(key, default)`.
- `c.ent()`: entrance time. `c.beats.at("reveal")` / `c.beats.at("impact")` / `c.beats.at("exit")`: time or None.
  `c.beats.since("impact", c.t)`: seconds since it, or -1.
- `c.p1` (violet #7C5CFF), `c.p2` (teal #22D3B6), `c.accent` (amber #FFB547).
- `c.pop(delay, dur)`: back-out pop 0→1 after the entrance. `c.impact()` returns `(sx, sy)` squash on impact.
  Wrap your whole output in `g(..., sx=isx, sy=isy, oy=<centre y>)`.

## Helpers (import them)
- From `prims`: `body(x,y,w,h,r,base,shine=,shade=,rim=)` (soft rounded volume), `ball(cx,cy,r,col)`,
  `glow(cx,cy,r,col,a)`, `contact_shadow(cx,cy,rx,ry,a)`, `text(x,y,s,size,weight,fill,anchor,opacity=)`,
  `pill(cx,cy,label,size,base)`, `g(inner, tx,ty,s,ox,oy,opacity,rot,sx,sy)` (transform group), `lin(stops,x1,y1,x2,y2)`
  / `rad(...)` (return `(defs, url)`), `mix(a,b,t)`, `lighten`, `darken`, `back_out`, `ease_io`, `wobble(t,freq,amp)`,
  `CX=540`, `CY=960`.
- From `easing`: `clamp`, `lerp`, `progress(t,start,dur)`, `ease_out_expo`.
- From `components_v3`: `mark(x,y,ok,k,r)` (green ✓ / red ✗ badge popping with k), `_k(c,at,dur)` (pop progress
  from a time), `_u(c,at,dur)` (linear 0→1 from a time), `_clip(id,x,y,w,h,r,inner)` (rounded clip + rim),
  `RED`, `GREEN`, `CYAN`.

## Style rules (Cartoon Tech v2)
- Flat vector shapes with soft gradients for volume: use `body`/`ball`/`glow`. No thick black outlines, no photos,
  no emoji. The dark blue starfield background is already drawn, so never paint a full-screen background.
- Palette: violet / teal / amber, plus white text. Red #FF4D6A means failure, green #3EE08F means success.
- Layout: keep content inside **x 72–970, y 420–1400**. Subtitles sit at y≈1480. A headline may occupy
  y 330–470, so start at y ≥ 480 when your props say there is a top text (default to starting at ~500).
- Text inside a component: ≤ 46 px for labels, ≤ 72 px for big numbers, font weight 800–900, Chinese allowed.
- Motion grammar: **entrance** = parts pop in (stagger 0.06–0.15 s); **reveal** = the shot's visual change (the
  key thing happens); **impact** = slam / ✓ / ✗ / number lands. Something should move all the time (wobble,
  flowing dots). Every mode must look complete and readable at the reveal; the **first frame must not be empty**
  (show the static set immediately and animate details).
- Unique ids: every `clipPath`/gradient id must be unique per call (include the mode and an index).
- Performance: ≤ ~400 SVG elements per frame.

## 16:9 native components (long-form)
Copy the structure of `components_explainer.py` / `components_compare.py`: author in a 1920×1080 design space,
wrap with `_fit(c, inner)`, keep the main visual in **x 120–1800, y 120–760** (subtitles sit at y ~916–996).
The `graphite` background is flat: no starfield, so never paint glows, particles or grids. Fixed colour meaning:
compute blue #3B82F6, memory orange #F59E0B, data green #22C55E, bottleneck red #EF4444, highlight #FACC15.
At the module bottom set `fn.native_landscape = True` (the scene skips the portrait mapping; with a top
headline it squeezes y 120–760 into 270–800) and, if it always moves, `fn.continuous_motion = True` (no
visual-gap errors). Add `"landscape": true` to its catalog entry. Preview with `--aspect 16:9`.

## Self-check (required)
For EVERY mode, render a contact sheet and LOOK at it with the Read tool, then fix what looks wrong
(overlaps, out of band, unreadable text, empty frames, nothing happening between times):
```
PYTHONUTF8=1 .venv/Scripts/python.exe tools/preview_component.py <module>:<function> --props '{"mode": "..."}' \
   --dur 5 --rev 0.4 --imp 0.8 --out work/_preview/<name>_<mode>.png
```
Also run `.venv/Scripts/python.exe -m ruff check --isolated --line-length 125 --select E,F <your file>`.

## Deliverables
1. Your module file, ending with `COMPONENTS = {"ComponentName": function, ...}`. Do NOT edit other source files;
   the integrator registers your module.
2. `<your module>.catalog.json` next to it, one entry per component, in this format:
   `{"ComponentName": {"use": "...", "props": {"mode": "a (what it shows) | b (...)", "other": "meaning / range"},
   "beats": "what reveal / impact do", "topic": "robotics"}}`. The storyboard LLM reads it to choose components,
   so describe each mode precisely and briefly.
3. The preview PNGs under work/_preview/.
