# AI 技术短视频变现引擎 — 产品需求文档（PRD / Requirements Baseline）

- 文档性质：Requirements Baseline（v1.0 冻结；v1.0.1 = 实现评审修订，见 `docs/REVIEW.md`）
- 适用仓库：全新公开仓（clean-room，可上 GitHub）
- 产品代号：MotionBrief（公开中性名，上仓前做同名检索）
- 优先级图例：P0 = MVP 必须 ｜ P1 = 第二阶段 ｜ P2 = 未来

## 1. Product Vision & Positioning

- **不是**课程/PPT 视频生成器，而是面向技术内容创作者的 **AI Technical Short-Video / Motion Storytelling Engine**。
- 内容方向（公开技术主题）：Camera / ISP / Sensor / AI / Transformer / Agent / GPU / CPU / XR / Robot / Perception。
- 定位：**工程师视角的 20–120 秒科技微纪录片**——技术准确、高信息密度、高质感、可规模化。
- **质量优先于自动化率**：宁可 70–80% 自动化，也不牺牲 hook、镜头运动、视觉隐喻、motion timing、sound design、typography、统一 Visual IP 与事实准确性。

## 2. Target Users & Value Proposition

| 用户 | 角色 | 核心诉求 |
|---|---|---|
| 工程师型创作者 | 主用户 | 低门槛、半自动、高质感、不翻车 |
| 技术团队 / 开发者关系 | 次用户 | 批量、风格统一、可复用 |
| 技术受众 | 定义内容体验 | 看得懂、够硬核、够好看 |

核心价值：复杂技术讲清楚 · 高质感 · 半自动规模化 · 事实可追溯 · 内容资产可复用。

## 3. Monetization / Business Validation

- 内容漏斗：免费技术短视频 → 受众沉淀 → 低门槛产品 → 核心付费 → 高价值服务。
- 产品化路径：内容 IP → 可复用生产引擎 → 工具/AI Agent → SaaS/服务。
- Phase-1 的 30 条是**赛道验证数据集**，非单纯运营排期。
- **不做任何收益承诺或财务预测**；目标是可控动作 + 验证指标。

## 4. Duration Strategy

引擎**不锁死时长**（v1.0.1，REVIEW R-18）：时长由内容与配音决定，档位只是建议目标；硬边界 15–180s 仅用于拦截异常 IR（Shorts 上限 3 分钟）。导演阶段输出 `durationTier`（视频级），缺省 **core**。

| 档位 | 区间 | 适用 | 优先级 |
|---|---|---|---|
| Micro Hook | 20–40s | 单概念/反常识，完播优先 | P0 |
| **Core Short（默认）** | 45–75s | 一个完整技术问题 | P0 |
| Deep Short | 75–120s | 2–3 机制串联，主要用于 Hero | P1 |
| Extended | 120–180s | 内容确需时（建议另出长视频版） | P1 |

**节奏硬规则（P0，全档位，G1 可机检 — 定义见 REVIEW R-05）**：前 3 秒必须出现 impact/reveal beat；任意两次显著视觉变化间隔 ≤ 5s；平均切点间隔 2–4s（切点 = 场景切换或 `reveal` beat）；烧录字幕必选；禁用口播式结尾（关注/点赞/下期…）。70s ISP 属 Core 上沿，是 Hero acceptance test，产品不得硬编码 60–90s。

## 5. Phase-1 Validation Content Plan — 30 Videos

三批次验证：**Batch A (1–10) 影像/感知**——强视觉是否最易建立辨识度；**Batch B (11–20) AI/计算**——是否扩大受众；**Batch C (21–30) XR/Robot/跨域**——是否形成差异化护城河。组合：Micro≈37% / Core≈50% / Deep≈13%；Hero 5 / Standard 15 / Fast 10。

| # | 题目 / Hook | 支柱 | 时长档 | 视觉隐喻 | 为什么做 | 来源类型 | Batch | 标记 |
|---|---|---|---|---|---|---|---|---|
| 1 | 四个摄像头？讲清 ISP | Camera | Core 70s | ISP 四级流水线 | 开篇代表作 | 影像教科书 | A | Hero |
| 2 | 夜景是拍还是算 | Camera | Core 50s | 多帧堆叠对齐 | 计算摄影颠覆 | 公开博客 | A | Std |
| 3 | 照片发群里为何糊 | Camera | Micro 30s | 压缩伪影 | 日常痛点 | JPEG 标准 | A | Fast |
| 4 | Bayer：相机是色盲 | Sensor | Core 60s | 去马赛克插值 | 反常识 | 公开资料 | A | Std |
| 5 | 防抖防谁的抖 OIS/EIS | Camera | Core 55s | 光轴补偿 | 实用 | 技术文档 | A | Std |
| 6 | HDR 天空人脸都清楚 | Camera | Micro 40s | 双曝光融合 | 单机制爽点 | HDR imaging | A | Fast |
| 7 | 拍月亮像贴图 | Camera | Micro 35s | AI 增强对比 | 争议传播 | 公开报道 | A | Fast |
| 8 | 像素越多越好吗 | Sensor | Micro 30s | pixel binning | 破误区 | 公开资料 | A | Fast |
| 9 | 自动对焦到 PDAF | Camera | Core 60s | 相位差对焦 | 演进叙事 | 技术资料 | A | Std |
| 10 | 光子到 JPEG 的旅程 | Camera | Deep 100s | 全链路 flythrough | 招牌集大成 | 教科书/标准 | A | Hero |
| 11 | 大模型怎么猜下一个字 | LLM | Core 65s | 概率分布采样 | AI 核心入口 | 公开论文 | B | Std |
| 12 | AI 为何一本正经胡说 | LLM | Micro 40s | 自信填空 | 高热痛点 | 公开论文 | B | Fast |
| 13 | 一张图看懂注意力 | Transformer | Deep 110s | 注意力热力图 | 深度信任招牌 | 注意力论文 | B | Hero |
| 14 | 什么是 Token | LLM | Micro 30s | 文字切块 | 入门 | tokenization | B | Fast |
| 15 | 推理为何烧显存 KV cache | 计算 | Core 60s | 缓存增长条 | 工程硬核 | 技术博客 | B | Std |
| 16 | GPU 和 CPU 差在哪 | 计算 | Core 55s | 单车道 vs 并行 | 泛受众 | 架构资料 | B | Std |
| 17 | 什么是 AI Agent | Agent | Core 60s | 规划-工具-记忆环 | 热点 | 框架文档 | B | Std |
| 18 | RAG 查资料再回答 | Agent | Core 60s | 检索→拼接→生成 | 实用热点 | RAG 论文 | B | Std |
| 19 | 端侧大模型难在量化 | 计算 | Micro 40s | 权重压缩位宽 | 工程视角 | quantization | B | Fast |
| 20 | 一次 AI 对话背后 | LLM | Deep 95s | 推理全链路 | 集成叙事 | 公开文档 | B | Std |
| 21 | 具身智能=身体的大脑 | 具身 | Micro 35s | 大脑+身体 | 概念入口 | 公开综述 | C | Std |
| 22 | VLA：看懂再动手 | 具身 | Core 70s | 视觉-语言-动作汇合 | 差异化护城河 | VLA 论文 | C | Hero |
| 23 | 机器人为何倒水难 | Robot | Micro 35s | 反馈控制抖动 | 反差共鸣 | 控制教科书 | C | Fast |
| 24 | Sim2Real 虚拟练一万次 | Robot | Core 60s | 仿真→现实迁移 | 认知新鲜 | 公开论文 | C | Std |
| 25 | 人形机器人的手难在哪 | Robot | Micro 40s | 自由度+触觉 | 话题热点 | 公开资料 | C | Fast |
| 26 | VR 怎么骗过眼睛 | XR | Core 55s | 双目视差 | 原理爽点 | stereopsis | C | Std |
| 27 | 什么是 6DoF | XR | Core 60s | 6 自由度+SLAM | 实用 | SLAM/6DoF | C | Std |
| 28 | AR 怎么贴在桌上 | XR | Core 60s | 平面检测+锚点 | 直观魔法 | AR 文档 | C | Std |
| 29 | 机器人怎么看深度 | 感知 | Micro 35s | 双目/ToF 深度图 | 感知入门 | depth sensing | C | Fast |
| 30 | 感知-决策-动作全链路 | 具身 | Deep 105s | 全链 flythrough | 跨域护城河 | 公开综述 | C | Hero |

**Review Gate（每 10 条，P0，以账号内部相对基准为锚，不编造行业阈值）**：第 10 条后判定"影像/感知是否建立辨识度"（前 3 秒留存/完播/关注转化，按支柱×hook×时长档分组）；第 20 条后判定"AI/计算是否扩大受众"；第 30 条后判定"跨域是否形成护城河"。**淘汰**：栏目连续低于均值完播即下线；时长档持续垫底降权；Hero 两条跑不过 Standard 则暂停 Deep。

## 6. End-to-End Production Pipeline

13 阶段：Topic/Script → Research & Fact Grounding → Story/Director → Storyboard（**animatic 板 + 签署**）→ Visual Design → Motion Design → Narration/TTS（**voice-first 重定时**）→ Render → Subtitles → Sound Design → QA → Package → Metrics。研究/导演/分镜/视觉/动效规划 = **强 LLM**；渲染/字幕/混轨/打包/指标 = **确定性代码 + 本地 agent**；发布 = **人工门**。

## 7. Visual Quality Requirements（可验收，非形容词）

前 3 秒 hook；每 3–5 秒显著视觉变化；镜头运动（非静止 PPT）；统一 motion timing/easing；统一 typography（≤2 主色 + 1 accent、安全区）；统一 Visual IP；技术事实必有公开 citation；帧/字幕/音频完整。
**禁止**：PPT fade、随机花哨转场、黄色描边大字、emoji 堆叠、纯 BGM+TTS 廉价音频、未标来源的"事实"、每片自创视觉语言。

## 8. Cartoon Tech v1 — Default Visual IP

原创 clean-room 风格，不复刻任何具体公开视频。渲染分层：**Layer A** 2D/2.5D flat-vector（默认，30 条全可用，不需 WebGL）；**Layer B** 轻量 3D toon（Three.js/WebGL，Hero 物体点睛）；**Layer C** Blender Eevee cel 离线预渲（极少数 Hero 资产）。WebGL 不可用必须降级 2.5D → Canvas → 静态卡。不需要专用视觉生成模型作为核心依赖。

Tokens/Grammar：色板 ≤2 主色 + 1 accent；toon 2–5 档色阶；outline（inverted-hull 或 depth+normal 后处理）；单 key 光 + ambient/hemisphere 补光；相机（图解 orthographic、hero perspective + 慢 push）；2.5D depth layers = 3；easing（进入 easeOutExpo / 强调 spring / 冲击 0.96→1.03→1）；particles（instanced toon sprite + 拖尾）；background（扁平渐变 + vignette + grain）；typography（几何无衬线 + 烧录字幕）；transition（仅 cut / zoom-through / mask-reveal / match-cut / morph-fuse）；sound cues（§9）。
机读版本：`motion/tokens.json`（单一事实源）。

## 9. Sound Design Requirements（P0）

不是 BGM+TTS。多轨：**voice + music + impact + whoosh/transition + UI/camera/digital FX**；关键 impact 与 reveal 对齐（G1：bass_hit 与 impact/reveal beat 误差 ≤ 50 ms）；**成片集成响度 −14 LUFS ± 2，true peak ≤ −1 dBFS**；音频存在、字幕时序需确定性检查。

## 10. AI / Agent Responsibilities

- **强 LLM**：research/fact grounding、story/director、storyboard、visual/motion planning、Scene IR、代码/参数生成。
- **视觉理解模型**：可选但推荐，用于 G2 画面 QA（跨 family four-eye）。
- **视觉生成模型**：非核心、可选 asset-generation adapter，不得成为出片依赖。
- **本地弱 agent**：只执行 validated task manifest、渲染、FFmpeg、收 artifacts/logs、retry/degrade/checkpoint/resume/escalate，不做高层创意决策。

## 11. Technical Requirements

Versioned Scene/Director IR；provider-neutral capability routing（`fast_text` / `deep_reasoning` / `code_generation` / `vision_review`）；renderer abstraction；reusable design system / motion grammar / component registry；deterministic-first QA；local-agent task/result protocol；stores（assets/facts/IR versions/metrics）；modest hardware + graceful degradation。

## 12. Scene IR Requirements

IR 至少表达：narration、timing、durationTier、camera、typography、visualObjects、motionGrammar、soundCues、transitions、citations/provenance、rendererHints、graceful degradation。Cartoon Tech 扩展字段：`styleProfile`、`assetStyle`、`renderQuality`、`materialStyle`、`outline`、`lightingPreset`、`cameraProjection`、`depthLayers`、`fallback2D`。v1.2 增补：`palette`（必填）、`isFactual`、视频级 `durationTier` / `productionLevel`（见 `docs/scene-ir.md`）。

## 13. QA Gates

- **G1 deterministic**：schema、component registry、safe area、subtitle timing、frame completeness/black-frame、audio presence/loudness、citation、render integrity、style-profile 约束、节奏/hook、口播结尾。
- **G2 multimodal**：composition、typography、visual hierarchy、motion continuity、pacing、fact consistency；跨 provider/family four-eye。
- **G3 human**：发布终审 + AI 生成内容标识（永不自动通过）。

## 14. Outputs

final MP4、cover、narration audio、subtitles、Scene IR、sources、metrics（至少）。

## 15. Platform Adaptation

MVP 母片 **9:16 / 1080×1920 / 30fps**；P1 做抖音/小红书/Bilibili/YouTube Shorts 的标题/封面/尺寸/标签改版；**MVP 不自动发布**。

## 16. Clean-room / GitHub Requirements

新仓从零创建、无私有 git 历史、无内部资料/敏感词/凭据/私有路径；依赖/素材/字体/音乐/图片许可清晰；CI 必含 secret scan、sensitive-term scan、license/SPDX、dependency vulnerability、metadata/EXIF、schema/unit/render-smoke/public-artifact gates；**真实敏感词 denylist 不提交仓库，仅本地 gitignored 文件或 CI secret 注入**。渲染依赖许可须与公开仓/商业化路径兼容（REVIEW R-01）。

## 17. MVP Definition of Done

引擎支持 20–120s（默认 Core 45–75s）；能从一个公开技术主题/脚本端到端生成高质感竖屏短片；**ISP 70s Hero 通过全部质量门**；Phase-1 至少跑通 Batch A 前 10 条（含 ISP Hero）；产物齐全；普通硬件可复现、3D 不可用自动降级；clean-room CI 全绿、可公开 GitHub。

## 18. ISP Acceptance Test

主题 → 合法多场 IR；强 hook；视觉隐喻；组件复用；镜头/motion；多轨音效；字幕/配音对齐；公开事实来源；3D → 2D 降级；完整产物。

## 19. Non-Goals

通用商业视频编辑器/时间轴 UI；diffusion/video-generation 依赖；云渲染农场；多租户 SaaS（MVP）；自动发布（MVP）；课程/PPT 视频；私有语音/会议/ASR/企业集成；收益承诺。

## 20. Open Decisions

D1 公开产品名；D2 3D 默认（建议默认 Layer A，Hero 才 B）；D3 TTS 默认实现；D4 开源许可证（仓库暂用 Apache-2.0）；D5 P1 平台改版范围；D6 指标采集方式；D7 Deep 档是否仅限 Hero（#20 当前为 Std，需定）；D8 Batch A/B/C 是否串行（建议串行）；**D9（新增）Remotion 是否作为生产渲染器（许可）**。

## 21. Requirements Completion Status

已冻结 v1.0：产品定位、时长策略、30 条 Phase-1 backlog、Cartoon Tech v1、13 阶段流程、可验收质量标准、Scene IR 需求、QA 门、MVP DoD、ISP acceptance、clean-room 发布要求。开放（不阻塞实现）：D1–D9。延后 P2：自动发布、批量产线、SaaS、云渲染。
