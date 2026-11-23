# Architecture (mental model for agents)

```
             ┌──────────── strong LLM (via llm/router, capability names only) ────────────┐
 topic ──▶ research ─▶ director ─▶ storyboard ─▶ visual ─▶ motion  ══▶  Scene IR v1.2 ─▶ animatic (lock)
             (fact_db)  (tier)                                             │
                                                                           ▼  task.json (allow-listed)
 ┌──────────────────────── local agent: agent/executor.py ────────────────────────────────────┐
 │ tts_narration+retime ─▶ render_scene × N ─▶ mix_audio ─▶ assemble ─▶ qa_g1                        │
 │   (subs/SRT)     (plan_scene: probe → degrade ladder → SVG/cairo → FFmpeg)                 │
 │ retries · degrade · checkpoint(hash) · idempotency(fingerprint) · escalate · fatal         │
 └────────────────────────────────────────────────────────────────────────────────────────────┘
                                                                           │
                       G1 deterministic ──▶ G2 vision_review (other family) ──▶ G3 human ──▶ publish (manual)
```

Dependency direction (one-way):

```
apps ─▶ content ─┐
     └▶ agent ───┴─▶ { render, audio, tts, quality, llm } ─▶ { ir, motion/*.json } ─▶ stores
```

Invariants
1. Renderer never imports `content`; business code never contains model IDs.
2. Generators compose only `motion/registry.json` components; unknown component ⇒ IR invalid ⇒ ESCALATE.
3. Same IR + tokens + registry + subtitles + engine version ⇒ byte-identical frames.
4. WebGL/3D absence is never fatal when `fallback2D=true`; it is recorded as a degradation.
5. G3 is never automated.
