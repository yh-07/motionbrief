# MotionBrief — agent rules (read first)

MotionBrief turns a script into a 9:16 explainer video. Routine production needs NO agent: it runs from
the drop folder. Agents are for engine changes only. This repo's sessions default to **haiku**
(`.claude/settings.local.json`). Keep work cheap.

## Routine production: do not hand-hold it
- Intake: put the script in `inbox/` (spec in `inbox/README.md`), then run
  `.venv/Scripts/python.exe -m motionbrief.apps.cli inbox --watch` (or run `inbox` once).
- Review `outbox/<id>/animatic.png`, then run `motionbrief inbox approve <id>` and `inbox` again.
  Status lives in `outbox/<id>/status.json`; the video is `outbox/<id>/final.mp4`.
- If the user only asks to "make a video", run the commands above and report the outbox paths. Do not
  re-storyboard, re-render or inspect frames unless a step failed.

## Token budget rules
1. **One task per session.** Start a new session for each new task. State carries over through the memory
   files and `outbox/*/status.json`, not through long chats.
2. **Never poll.** Start long jobs (storyboard, voice, render: 2–20 min) with `run_in_background` and wait for
   the completion notification. Do not loop on status or sleep between checks.
3. **Small images only.** Review sheets at ≤ 800 px wide (`PIL.Image.thumbnail((800, 4000))`). Crop just the
   shot in question when you need detail. Never Read the full 1620-px animatic. Judge layout from real frames, not the animatic grid: run `tools/preview_frames.py <id>` (6 real 1920x1080 frames on one ≤800 px sheet) before approving.
4. **Terse tool output.** Pipe through `| tail -n 20`, `grep -E "FAIL|✘|error"`, or `cut -c1-300`. Do not
   dump JSON, logs or plans; extract the fields you need with a short `python -c`.
5. **Edit with the Edit tool, not shell heredocs.** In this Windows Git Bash, heredoc/sed scripts have
   repeatedly broken `\n`, `\s` and backslash continuations. Use heredocs only for files with no escapes.
6. **Delegate bulk work to haiku subagents** (`model: haiku`): new visual components (follow
   `docs/COMPONENT_GUIDE.md` and `tools/preview_component.py`), installs and downloads, surveys of other
   repos. The main session writes the spec, reviews small preview sheets once, and integrates.
7. **Do not re-run what is cached.** Renders are checkpointed per slice, and voice per sentence by text plus
   TTS code. Changing `render/svg_canvas`, `render/three`, `render/backend.py`, `render/ffmpeg.py` or `ir/`
   re-renders everything, so batch such edits and render once. Transport code (`render/remote*.py`) does
   not invalidate.
8. **Verify cheaply.** Use `motionbrief validate`, `pytest -q -m "not render"` (about 10 s) and the animatic
   (about 1 min) before any full render. Run full `pytest` (about 2 min) only before finishing.

## Engine facts (avoid re-discovering)
- Host: Windows ARM64 laptop; `.venv` is x64 Python 3.13 (emulated) because of the win-64 cairo DLLs. The
  LAN render PC is reached over SSH (key auth) per `.env`. Details are in `docs/HOST_WINDOWS_ARM64.md`.
- LLM: qgenie through `config/capabilities.qgenie.yaml`. The storyboard default is `deep_reasoning`, which is
  Claude via qgenie. That is billed by qgenie, not by this session.
- Components: `motion/registry.json` plus `render/svg_canvas/*.catalog.json` packs (topic-filtered for the
  LLM). A new pack is a module + catalog + the import line in `components.py`.
- 16:9: prefer landscape-native packs (`components_phone_interior/chip_stage/explainer/compare`, flags
  `native_landscape` + `continuous_motion`). Portrait components draw on the portrait canvas even in 16:9;
  `scene._place_landscape` fits their drawn content (bbox, measured once per shot) into the 16:9 object area. Front-matter `visualStyle: graphite` gives the flat technical background.
- Shot lists: `**组件**：Name {json}` pins a shot's visual (enforced in code, the LLM ignores free-text hints);
  `**注释**：…` adds a corner footnote (disclaimers). Every done video also gets `publish.md` and
  `cover_16x9/3x4/9x16.png`; regenerate with `motionbrief inbox publish <id>`.
- Do not put real model IDs in `motionbrief/` code (test guard). Keep `.env`/secrets out of the repo; the
  `tools/sanitize/sensitive_scan.py` check must stay at 0 findings.
- Windows pitfall: never read ssh/scp output through pipes while a process pool is spawning workers
  (`remote._run` writes to temp files for this reason).
