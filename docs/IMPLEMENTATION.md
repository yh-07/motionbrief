# MotionBrief — 实现与架构设计（Implementation Plan / Agent Handoff）

- 配套文档：`docs/REQUIREMENTS.md`（需求基线）、`docs/REVIEW.md`（评审修订，本文件已吸收）
- 读者：从零实现/继续本仓的 coding agent
- 性质：clean-room；不复制任何私有代码；技术依据仅用公开官方文档
- 状态：**First Sprint（§21）全部 8 步已实现**；ISP 70s Hero 已在 Layer A + 降级路径上端到端出片并通过 G1

## 1. Implementation Principles

clean-room from scratch · single repo · video-first · deterministic rendering · provider-neutral · weak-hardware-first · graceful degradation · quality before automation · no diffusion/video-generation dependency.

## 2. Repository Tree（实际）

```
motionbrief/
├── README.md LICENSE CONTRIBUTING.md SECURITY.md CODE_OF_CONDUCT.md
├── .env.example pyproject.toml package.json .gitignore
├── motionbrief/                 # Python 包（命名空间化，见 REVIEW R-15）
│   ├── apps/cli.py              # 出片入口
│   ├── content/                 # pipeline / director / research (+ LLM stage stubs)
│   ├── ir/models.py             # pydantic Scene IR v1.2 + validate + migrate
│   ├── llm/router.py capabilities.example.yaml clients/{openai_compat,anthropic,stub}.py
│   ├── render/backend.py probe.py ffmpeg.py svg_canvas/{scene,components,easing}.py
│   │          remotion/ three/ blender/        # 可选后端（skeleton + 官方要点）
│   ├── audio/sfx.py mix.py      # 程序化原创音效/音乐、字幕、多轨混音、响度
│   ├── tts/provider.py adapters/
│   ├── quality/deterministic.py multimodal_review.py gates.py
│   └── agent/executor.py taxonomy.py actions.py
├── motion/tokens.json registry.json tokens.ts registry.ts components/
├── schemas/scene_ir.schema.json(生成) task.schema.json result.schema.json
├── fixtures/isp_v01.json legacy_v1_1_s03.json
├── examples/isp_short/sources.md
├── stores/{asset_db,fact_db,ir_versions,metrics_db}/
├── tools/sanitize/sensitive_scan.py denylist.example.txt
├── tests/
├── docs/REQUIREMENTS.md IMPLEMENTATION.md REVIEW.md architecture.md scene-ir.md
└── .github/workflows/ci.yml release-guard.yml
```

## 3. Module Responsibilities & Dependency Rules

单向依赖（修订版，见 REVIEW R-03）：

```
apps ─▶ content ─┐
     └▶ agent ───┴─▶ { render, audio/tts, quality, llm } ─▶ { ir, motion tokens/registry } ─▶ stores
```

硬规则：renderer 禁止依赖 content；业务代码禁止出现具体模型 ID（测试 `test_no_model_ids_in_business_code` 守护）；本地 agent 只执行 allow-list 动作（`agent/actions.py`），`cmd` 只能是类型化参数，不是 shell 字符串。

## 4. Scene IR v1.2.0

见 `docs/scene-ir.md`。相对 v1.1 的变更：`palette` 必填；`durationTier`/`productionLevel` 移到 `video`；`isFactual`；`role` 枚举化；`renderer` 增加 `blender`；所有 `at` 为**绝对秒**且必须落在场景内。`migrate()` 把 v1.1 升到 v1.2（`fixtures/legacy_v1_1_s03.json` 即原文档片段）。
`schemas/scene_ir.schema.json` 由 pydantic 生成（`motionbrief export-schema`），CI `--check` 防漂移。

## 5. Capability Router

`router.chat(capability, messages, images=None, exclude_family=None)`；每能力有序 candidates、timeout、ban、`cross_family`。所有失败记录到 `attempts`（`not_configured` / `provider_error`），全部失败抛 `AllProvidersFailed`。`vision_review` 在 `cross_family: true` 时**必须**传 `exclude_family`。`stub` provider 让无凭据环境（CI）跑通；生产用 `MOTIONBRIEF_ALLOW_STUB=0` 关闭。

## 6. Content Pipeline

13 阶段（`content/pipeline.py`）。`director.decide_tier` 先判时长档（单概念→micro；一个完整问题→core；多机制且 Hero→deep）。`research.record_fact` 只接受 https 公开来源写 `fact_db`。storyboard/visual/motion 为 Phase 2（强 LLM 只能输出 registry 内组件，IR 必须过 `validate`）。

## 7. Cartoon Tech v1 Design System

`motion/tokens.json` 为单一事实源（TS 与 Python 共用）。`motion/registry.json` 声明组件 `status`（implemented/planned）、`layer`、`renderers`、`fallback2D`。
已实现（Layer A，SVG）：TitleCard、ColorSweep、ParticleStream（photons/converge/denoise）、ChipReveal（Layer B 的 2.5D 降级版）、RawFramePlate（bayer/demosaic）、ExposureMerge、PipelineFlythrough、LensArray。Planned：LensSpread、MultiFrameFusion、Diagram primitives（每 10 条复盘后再扩）。

## 8. Renderer Architecture

`RendererBackend{name, probe(), can_render(obj), render_frames(...)}`。后端：**SVG（默认 Layer A：SVG → cairo raster → raw BGRA → FFmpeg）**、Remotion（可选，许可见 R-01）、Three（Layer B skeleton）、Blender（Layer C 可选）。
降级阶梯：`blender → three → remotion → svg(2.5D) → canvas/static`，由 `plan_scene()` 依 `probe()` 结果逐对象决定并记录 `degradations`；`fallback2D=false` 时拒绝降级。FFmpeg：硬件编码器可用则用，否则显式 `libx264`；grain 用 `noise` 滤镜在拼接时统一加（确定性）。

## 9–11. Three.js / Remotion / Blender

官方要点保留于 `motionbrief/render/{three,remotion,blender}/README.md`：`MeshToonMaterial`+`gradientMap`（`NearestFilter` 必设）、inverted hull 描边、单 key 光 + 低强度补光；Remotion `<ThreeCanvas width height>` + `useCurrentFrame()`、`<Sequence layout="none">`、`chromiumOptions:{gl:'angle'}`；Blender Shader to RGB → ColorRamp(Constant)、View Transform=Standard。

## 12. TTS / Audio

`TTSProvider.synthesize(text, voice, out_wav)`；适配器：espeak-ng（CI/弱硬件参考，音质不足以发布）、local-neural、cloud（占位，D3）。旁白按场景放置（+0.15s），超窗则 `atempo` ≤ 1.35，否则 `NarrationTooLong` → ESCALATE。
多轨 stems：voice / music / impact / transition / fx，全部程序化原创（无第三方素材许可风险）；music 在旁白下 ducking；两遍 `loudnorm` 到 −14 LUFS、TP −1.5。

## 13. QA Architecture

`quality/gates.py`：G1 → G2 → G3，G1 失败即停（不浪费模型调用）。G1 分 IR 级与产物级、可按场景限定范围（`--scenes s03`）。G2 已接线到 router（stub 下记为 `stub_review`）。G3 需要人工签署 `approval.json`，永不自动通过。

## 14. Local Agent Protocol

`task.json`：taskId/type/idempotencyKey/irRef/sceneId/renderer/cmd/retries/degrade/checkpoint/outDir（`schemas/task.schema.json`）。`result.json`：taskId/status(ok|retryable|degraded|escalate|fatal)/artifacts/metrics/logsRef/error(+degradations, skipped)。
- 幂等：key = 所有输入指纹（IR、tokens、registry、字幕、版本）；结果缓存 + 产物存在即跳过。
- checkpoint：每场景 `frames/<sid>.hash`，内容哈希一致即复用（resume）。
- 失败分类：RETRYABLE（I/O/编码器）本地重试；DEGRADED（WebGL/3D 不可用）改用 svg；ESCALATE（IR 非法、门失败、旁白超长）回强模型；FATAL（缺依赖或未分类 bug）停报。

## 15. Stores / Artifacts

`work/<id>/{frames/(scene mp4 + 抽样 png), audio/(stems, narration.wav, narration_mix.wav), subs/subtitles.srt, final.mp4, cover.png, scene_ir.json, sources.md, metrics.json, logs/}`。

## 16. ISP Acceptance Fixture

`fixtures/isp_v01.json`：12 场、70s、Core、Hero；s03 ChipReveal 为 Layer B（three）且 `fallback2D`，在无 WebGL 主机上自动降级为 2.5D SVG，并记录在 result.json。

## 17–19. Phase-1 策略 / 测试 / Clean-room CI

全部 30 条默认 Layer A；Hero 加 Layer B；Fast 纯 A（G1 强制）。测试：schema/unit、router、registry、render smoke（确定性帧）、降级、字幕、sanitizer、s03 acceptance。`release-guard.yml`：gitleaks → 敏感词（CI secret）/公开产物/.env/SPDX/EXIF → 依赖许可 → grype → exiftool → schema/unit/render-smoke。

## 20. Implementation Phases（更新）

| Phase | 内容 | 状态 |
|---|---|---|
| 0 | clean repo + docs + CI guard | ✅ |
| 1 | Scene IR + router + Layer A + G1 + local executor | ✅ |
| 2 | ISP Hero 端到端 | ✅ 出片 + G1 通过；✅ voice-first 重定时、animatic、G2 锚点网格、G3 分阶段签署；⏳ 神经 TTS、G2 真模型、字级字幕 |
| 3 | Layer B three.js toon + 降级 | ⏳ 降级路径已通，three 后端为 skeleton |
| 4 | Batch A 10 条 + Review Gate | ⏳ 需补组件：MultiFrameFusion、LensSpread、OIS/PDAF 图元 |
| 5 | Batch B/C + 组件扩展 | — |
| 6 | 可选 Blender / P1 平台改版 / 指标自动化 | — |

## 21. Next Sprint（建议给下一个 agent，按序）

1. 接入本地神经 TTS 适配器（D3），替换 espeak-ng 作为默认；保持 espeak 作为 CI 适配器。
2. G2：实现真实 `vision_review` 提示与 JSON 解析，作者 family 写入 IR 元数据。
3. Layer B：`render/three` 用 Remotion+ThreeCanvas 输出透明 PNG 序列，SVG 场景合成；`probe_webgl.mjs` 实测 WebGL。
4. Batch A #2–#9 所需组件（每个先写 registry 条目 → SVG 实现 → golden-frame 测试）。
5. golden-frame 视觉回归（关键帧 SSIM 阈值）。

## 21b. 吸收的成熟经验（Round 2，见 BENCHMARK.md）

- 时长不锁死：tier 仅建议，硬边界 15–180s（`tokens.duration`）。
- Voice-first：TTS 后 `timing.retime()` 生成 `scene_ir.timed.json`，渲染/混音/QA 都用它。
- Animatic 先行：`motionbrief animatic` → 关键帧板，`animatic_lock` 签署后才全量渲染。
- G2 锚点网格（6×6）；G3 三段签署；G1 增加非阻塞 craft 建议项（△）。

## 22. Explicit Non-Implementation

MVP 不实现：自动发布、SaaS、多租户、云渲染、diffusion/video generation、通用编辑器、私有语音/会议/ASR、企业集成。
