# Host profile — Windows 11 ARM64 laptop (Snapdragon X Elite)

Measured adaptation of the Linux-sandbox build to this laptop (2026-11-16). Values live in the
gitignored `.env`; `motionbrief/hostenv.py` loads it (real env vars win; `MOTIONBRIEF_NO_DOTENV=1` skips it).

## Stack

| Piece | Choice on this host | Why |
|---|---|---|
| Main venv | `.venv`, **x64** Python 3.13 (emulated) | only a win-64 cairo build is readily available (conda-forge) |
| cairo | conda-forge 1.18.6 DLLs, dir on `MOTIONBRIEF_BIN_DIRS` | cffi's dlopen searches PATH, not `add_dll_directory` |
| ffmpeg/ffprobe | BtbN n9.0 **native ARM64** static build | separate process, so it runs native |
| HW encoders | probe now test-encodes one frame | the ARM64 build *lists* nvenc/amf though no such GPU exists |
| TTS | Kokoro v1.0 in a **native ARM64** venv (onnxruntime win_arm64) → SAPI Huihui → espeak-ng | best Chinese quality offline; SAPI is the zero-install fallback |
| G2P | misaki[zh] 0.7.4 | newest for py3.13 (≥0.7.10 needs <3.13); `g2p_zh` accepts both return shapes |
| Font | `C:/Windows/Fonts/NotoSansSC-VF.ttf`, family `Noto Sans SC` | replaces Linux `fc-match` "Noto Sans CJK SC" |
| LLM | `config/capabilities.qgenie.yaml`: one gateway, three families (claude/gemini/gpt) | keeps G2 cross-family review meaningful |

## Measurements (fixture `isp_v02`, 14 scenes, 82.7 s, 1080×1920@30)

Per-frame raster cost (same SVG frames, ms): cairo-x64-emulated 55–228, skia-CPU-ARM64 158–622,
resvg-ARM64 231–1820 (pixel diff vs cairo tiny for both). Frames are fill-rate heavy (full-screen
gradients/glows), so cairo stays. 85–90 % of frame time is cairosvg draw+raster; SVG build is ~5 ms.

| Stage | before | after | change |
|---|---|---|---|
| mix_audio | 257 s | 30 s | ducking envelope: O(n·win) `np.convolve` → prefix-sum moving average |
| render 14 scenes | ~4 min | ~4.5 min | parallel processes (`--jobs`, default cpus−2), longest scene first; sustained all-core load throttles to ~9 fps |
| assemble | 65 s | 26 s | |
| **total** | 10 m 49 s | 7 m 29 s | |

Tried and rejected: capping libx264 threads (slower); `h264_mf` (Adreno MF) for intermediates —
faster alone, slower with 10 concurrent sessions. Still selectable via `MOTIONBRIEF_INTERMEDIATE_ENCODER`.

## Remote render worker (LAN PC, i7-10870H 8C/16T + RTX 3060)

`motionbrief/render/remote.py` + `remote_worker.py`. `produce` drains one longest-first scene queue with
local processes (`--jobs`) and `MOTIONBRIEF_RENDER_JOBS` remote slots; if the PC is unreachable a scene
falls back to local rendering and records a `remote -> local` degradation.

- Remote layout (`MOTIONBRIEF_RENDER_ROOT`): `venv/` (offline wheels, built from the PC's conda python,
  conda env untouched), `cairo/bin` (same conda-forge 1.18.6 DLLs), `host.env` (the PC's own `.env`,
  passed via `MOTIONBRIEF_ENV_FILE`), `engine/<content-hash>/` (auto-uploaded), `jobs/` (temporary).
- Pixel parity: identical font file (sha256), Pillow/cairosvg/cairocffi versions, libx264 intermediates →
  sampled frames are byte-identical to local renders (verified on s03). NVENC is deliberately not used for
  intermediates (quality first); the final encode stays on the laptop.
- Auth: SSH key, `BatchMode=yes`; never a password.

## Layer B on the PC GPU (three.js toon, `render/three/README.md`)

`MOTIONBRIEF_RENDER_WEBGL=1` (laptop) + `MOTIONBRIEF_BROWSER_CHANNEL=msedge` (PC `host.env`): scenes with
`renderer: three` objects (v02: s06 `chip`) render their body in Edge WebGL on the RTX 3060 and are routed
to remote slots only. Measured on `isp_v02` s06 (139 frames):

| | 2.5D SVG (before) | 3D GPU toon (now) |
|---|---|---|
| s06 alone | 32 s on laptop | 48 s on PC (≈10 s is ssh/browser start/transfer) |
| per frame under full load | ≈0.65 s (PC) | ≈0.85 s (PC); WebGL draw+readback ≈14 ms, rest is PNG embed in cairo |
| whole film wall time | — | unchanged: s06 runs on PC slots in parallel with the other scenes |
| blind review (Claude, 4 frames, A/B order swapped) | wins 2 | wins 2; better depth (7.5 vs 7.0), slightly lower style/edge |

Iterations that mattered (each judged blind): hard toon bands lost 0/4 (v2 is soft-gradient), grey die from
ambient light, jagged pin outlines.

## Open options
- Native ARM64 cairo (MSYS2 clangarm64 packages) to drop x64 emulation in the hot loop.
