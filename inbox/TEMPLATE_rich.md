# 模板 A：完整素材（外部 agent 尽量多写）

**只交一个文件**：复制这份模板，改名为 `inbox/<id>.md`，把 `<id>` 换成你的视频 id。front-matter、各章镜头块、事实核对都在这一个文件里，引擎负责解析。

交稿前运行检查：`.venv/Scripts/python.exe tools/check_inbox_script.py inbox/<id>.md`，输出 `OK` 再交。

---

## 给外部 agent 的规则（必读）

1. **旁白是唯一的台词来源**：每个镜头的 `**旁白**` 逐字写好，不增不减，标点保留（中文标点决定停顿）。
2. **一个镜头 = 一句或两句旁白，约 15–30 个汉字（3–6 秒）**。没有旁白的镜头省略 `**旁白**` 行。
3. **每个镜头都写节拍**：`**节拍**：rev 0.3，imp 0.7`。`rev` 是画面变化点，`imp` 是重点落地点，取值 0–1。两个节拍之间不能超过 4 秒，所以镜头长的话多写一对节拍。
4. **镜头 id** 从 `s01` 开始连续编号，不跳号、不重号。章节标题用 `## 章节名`，镜头用 `### sNN`。
5. **组件**：只能用下表里的组件名和参数名。参数名写错或缺少必填参数，交稿检查会直接报错（组件会忽略不认识的参数，退回别的视频里的演示数字）。不确定就不写 `**组件**`，由引擎选。`{json}` 里的值要和本镜头的旁白一致。

| 组件 | 参数（只能用这些名字） | 必填 |
|---|---|---|
| `PhoneSoc` | `mode`：soc_zoom (only mode)<br>`zoom`：0..1, zooms from the whole phone into the SoC and NPU | — |
| `NpuArray` | `mode`：array (only mode)<br>`load`：0..1, fraction of compute cells active (waves of light across the array)<br>`label`：short text above the array, default 100 TOPS | label |
| `BusCongestion` | `mode`：congestion (only mode)<br>`flow`：0..1, fraction of NPU cells lit (the data-fed part); 0.25 = mostly idle NPU<br>`queue`：int 0..8, packets waiting at the bus entrance<br>`label`：optional short text (max 10 characters) above LPDDR | label |
| `ModelShrink` | `mode`：shrink (only mode)<br>`bits`：16 / 8 / 4, model block shrinks to that precision (16 = FP16 14 GB, 8 = INT8 7 GB, 4 = INT | bits |
| `MatrixArray` | `mode`：prefill / decode<br>`label`：short label above, <= 12 chars | — |
| `CodeTerminal` | `mode`：run (only mode)<br>`code`：python source shown being typed, <= 12 lines, use \n for newlines<br>`output`：its REAL printed output, <= 10 lines, use \n for newlines; keep the lines short<br>`title`：window title, default python<br>`highlight`：index (0-based) of the output line to box in yellow at impact, -1 for none | code, output |
| `Equation` | `mode`：fraction (num over den = result) / product (a x b = result)<br>`num`：fraction only: numerator value with unit, e.g. 60 GB/s<br>`den`：fraction only: denominator value with unit, e.g. ~4 GB<br>`result`：the answer shown after = (both modes), with unit, e.g. 15 token/s; keep it short<br>`a`：product only: first factor, e.g. 7B<br>`b`：product only: second factor, e.g. 2 Byte<br>`note`：optional small caption at top right, <= 16 characters | fraction：num, den, result；product：a, b, result |
| `TokenStream` | `mode`：decode (tokens appear one by one, each fed by a data packet) / prefill (whole prompt proce<br>`tokens`：decode only: list of output tokens (short strings, 1-2 characters for Chinese), default ["<br>`rate`：decode only: tokens per second, default 1.5<br>`label`：optional short text: decode shows it bottom right in orange; prefill shows it as a pill ab<br>`prompt`：prefill only: input text, one chip per character, keep it under about 20 characters | decode：tokens；prefill：prompt |
| `SplitCompare` | `mode`：pipes (left narrow vs right wide data pipe) / panels (two value panels)<br>`left`：{title, value, sub, color} for the left panel; color is blue / orange / green / red / gray<br>`right`：{title, value, sub, color} for the right panel; color is blue / orange / green / red / gra<br>`ratio`：right pipe width / left, pipes only (default 8, right gets round(2*ratio) lanes, max 24) | left, right |
| `HBars` | `mode`：bars (only mode)<br>`items`：list of up to 6 {label (str), value (number), text (str shown at bar end, default value pl<br>`unit`：str appended to the default bar-end text, for example GB<br>`highlight`：row index to highlight (default -1 for given items; with no items prop the default is 2)<br>`note`：short caption at the top right, 30 px | items |
| `ChipTags` | `mode`：tags (only mode)<br>`tags`：list of up to 8 short labels, default [KV Cache, Cache 命中率, Runtime, Kernel, 功耗, 散热]<br>`emphasis`：index of the tag to highlight with a yellow border on impact (default -1 = none) | tags |
| `InfoCards` | `items`：[{"title": ≤10 chars, "value"?: short number/text, "mark"?: "ok"/"bad", "color"?: "p1/p2/a<br>`layout`：column / row (≤3 items) / grid<br>`highlight`：index lit on impact, -1 none<br>`y`：centre ≈960 | items |
| `TitleCard` | `text`：impact_reveal: ≤5 Chinese chars or ≤8 letters/digits (auto-shrinks to fit; never cut a ter<br>`style`：impact_reveal/headline<br>`anchor`：center<br>`sub`：optional small line ≤14 chars | text |
| `PipelineFlythrough` | `stages`：list of 2-5 names (≤6 chars); camera-pipeline names get icons, others get step numbers<br>`focus`：-1 = light all in order<br>`top`：y of first capsule (≥520 if there is a top headline)<br>`budget`：bool progress bar<br>`perStage`：seconds per stage, may be {"spanFrac": f}<br>`runDelay`：seconds before lighting starts<br>`error`：bool: a red error blob grows at each stage, '!' on impact<br>`token`：bool: a photo card travels down the stages (default true only for camera-pipeline stages) | stages |
6. **数字和公式**只能来自你真实算过的结果（代码跑出的输出才能写）。不能编 benchmark、芯片参数或产品数据。
7. 凡是简化、示意、估算的画面，在 `**注释**` 写明（不超过 40 字），例如 `简化理论上限模型，并非真实 Benchmark`。
8. 事实型说法必须在"事实核对"表里给出依据（维基或 https 链接）。

---

```markdown
---
id: my_video_id                # a-z 0-9 _
title: 视频标题
produce: approve               # approve（先出 animatic，等确认）| auto
aspect: "16:9"                 # 16:9（长视频，推荐 8–15 分钟）| "9:16"（Shorts，≤180 秒）
visualStyle: graphite          # 横屏必填：深石墨、扁平技术风
publish_title: ""              # 可选：覆盖发布包里的标题
cover_main: ""                 # 可选：封面主文字（≤8 字）
cover_sub: ""                  # 可选：封面副文字（≤14 字）
cover_tag: ""                  # 可选：封面小标签（≤10 字）
---

## 章节一标题

### s01
**旁白**：第一个镜头的旁白，逐字写好。
**画面**：黑色背景，中央巨大文字 100 TOPS。
**组件**：InfoCards {"items": [{"title": "算力", "value": "100 TOPS"}], "layout": "row"}
**节拍**：rev 0.3，imp 0.7

### s02
**旁白**：第二个镜头的旁白。
**画面**：镜头推进进入手机内部，只高亮 SoC。
**组件**：PhoneSoc {"mode": "soc_zoom", "zoom": 0.3}
**注释**：简化示意，并非真实结构
**节拍**：rev 0.25，imp 0.6

## 章节二标题

### s03
**画面**：转场，无旁白。
**节拍**：rev 0.3，imp 0.7

## 事实核对
| 说法 | 依据 | 处理 |
|---|---|---|
| 说法一 | [来源名](https://en.wikipedia.org/wiki/页面) | 事实 |
| 本集的简化估算 | 本文档的示例计算 | 简化模型，并非真实 Benchmark |
```
