# 横屏改造 第一阶段：画布参数化 Implementation Plan

> **For agentic workers:** Steps use checkbox (`- [ ]`) syntax for tracking. Source spec: `docs/superpowers/specs/2026-11-17-landscape-longform-design.md`.

**Goal:** 把渲染画布从写死的 1080×1920 改为由 `aspect` 决定，9:16 的输出逐帧不变，16:9 画布能流过整条 SVG 渲染链路。

**Architecture:** 新增一个不可变的 `Canvas(w, h)` 值对象，由 IR 的 `video.aspect` 推导。`Ctx` 与 `frame_svg` 通过它拿到宽高和中心点，取代模块级常量 `W, H` 和 `CX, CY`。组件内部坐标仍按各自画幅的设计空间书写（竖屏 1080×1920），16:9 的版面留到第二阶段。

**Tech Stack:** Python 3.13（`.venv`），pydantic v2，pytest。

## Global Constraints

- 9:16 输出必须与改动前逐帧一致：`work/svg_snapshot.py` 的 114 个哈希全部相同。
- 中心点用整数除法（`w // 2`），保证 SVG 文本中的数字仍是 `540`、`960`，不变成 `540.0`。
- 不改 `render/ffmpeg.py`、`render/backend.py` 的逻辑；`render/svg_canvas` 的改动会让缓存全部失效，因此这一阶段只渲染一次（快照脚本，不渲染视频）。
- 不写旋转元数据，不提交 git（用户未要求）。
- 测试：`pytest -q -m "not render"`（约 10 秒），`motionbrief validate` 通过。

---

## 文件结构

- Create: `motionbrief/render/svg_canvas/canvas.py` — `Canvas` 值对象与 `canvas_for(aspect)`。
- Modify: `motionbrief/ir/models.py:53-58` — `Video.aspect` 允许 `16:9`，`w`/`h` 改为由 `aspect` 校验。
- Modify: `motionbrief/render/svg_canvas/scene.py:17` 与 `frame_svg`、`_background`、`_transition_wrap` 等函数 — 去掉 `W, H` 常量，改取 `canvas`。
- Modify: `motionbrief/render/svg_canvas/components*.py`（共 5 个文件，约 150 处 `W`/`H`/`CX`/`CY`）— 通过 `c.canvas` 取值。
- Modify: `motionbrief/render/svg_canvas/prims.py:20` — `CX, CY` 常量删除，调用方改用 canvas。
- Test: `tests/test_canvas.py`（新建）。

## Task 1: Canvas 值对象

**Files:**
- Create: `motionbrief/render/svg_canvas/canvas.py`
- Test: `tests/test_canvas.py`

**Interfaces:**
- Produces: `Canvas(w: int, h: int)`，属性 `cx`、`cy`（整数）；`canvas_for(aspect: str) -> Canvas`。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_canvas.py
import pytest

from motionbrief.render.svg_canvas.canvas import Canvas, canvas_for


def test_portrait_canvas_keeps_legacy_integers():
    c = canvas_for("9:16")
    assert (c.w, c.h, c.cx, c.cy) == (1080, 1920, 540, 960)
    assert isinstance(c.cx, int) and isinstance(c.cy, int)


def test_landscape_canvas():
    c = canvas_for("16:9")
    assert (c.w, c.h, c.cx, c.cy) == (1920, 1080, 960, 540)


def test_unknown_aspect_rejected():
    with pytest.raises(KeyError):
        canvas_for("1:1")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_canvas.py -q`
Expected: FAIL（`ModuleNotFoundError: canvas`）

- [ ] **Step 3: 写最小实现**

```python
# motionbrief/render/svg_canvas/canvas.py
"""Pixel canvas for one aspect ratio. Centre uses integer division so SVG text stays '540', not '540.0'."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Canvas:
    w: int
    h: int

    @property
    def cx(self) -> int:
        return self.w // 2

    @property
    def cy(self) -> int:
        return self.h // 2


_CANVASES = {"9:16": Canvas(1080, 1920), "16:9": Canvas(1920, 1080)}


def canvas_for(aspect: str) -> Canvas:
    return _CANVASES[aspect]
```

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_canvas.py -q`
Expected: PASS（3 passed）

## Task 2: IR 接受 16:9

**Files:**
- Modify: `motionbrief/ir/models.py:53-58`
- Test: `tests/test_canvas.py`（追加）

**Interfaces:**
- Consumes: `canvas_for` from Task 1.
- Produces: `Video.aspect: Literal["9:16", "16:9"]`；`w`、`h` 必须等于 `canvas_for(aspect)` 的尺寸，否则校验失败。

- [ ] **Step 1: 追加失败测试**

```python
def test_video_aspect_drives_size():
    from motionbrief.ir.models import Video

    v = Video(id="x", title="t", aspect="16:9", w=1920, h=1080)
    assert (v.w, v.h) == (1920, 1080)
    with pytest.raises(ValueError):
        Video(id="x", title="t", aspect="16:9", w=1080, h=1920)
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_canvas.py::test_video_aspect_drives_size -q`
Expected: FAIL（`aspect` 不接受 `16:9`）

- [ ] **Step 3: 改模型**

把 `aspect`、`w`、`h` 三行替换为：

```python
    aspect: Literal["9:16", "16:9"] = "9:16"
    w: int = 1080
    h: int = 1920
```

并在 `Video` 类里追加：

```python
    @model_validator(mode="after")
    def _size_matches_aspect(self):
        size = canvas_for(self.aspect)
        if (self.w, self.h) != (size.w, size.h):
            raise ValueError(f"{self.aspect} needs {size.w}x{size.h}, got {self.w}x{self.h}")
        return self
```

在文件顶部导入：`from pydantic import model_validator` 与 `from motionbrief.render.svg_canvas.canvas import canvas_for`。注意：`motionbrief/ir/` 与 `render/svg_canvas/` 的依赖方向要检查，若产生循环导入，则把 `canvas.py` 的 `_CANVASES` 尺寸表移到 `motionbrief/ir/models.py` 内，`canvas.py` 再从那里导入。

- [ ] **Step 4: 运行确认通过，并校验已有 fixtures**

Run: `.venv/Scripts/python.exe -m pytest tests/test_canvas.py tests/test_ir.py -q`
Expected: PASS
Run: `.venv/Scripts/python.exe -m motionbrief.apps.cli validate fixtures/isp_v02.json`
Expected: 无 error

## Task 3: Ctx 携带画布，scene.py 取消全局 W/H

**Files:**
- Modify: `motionbrief/render/svg_canvas/components.py:23-33`（`Ctx` 类）
- Modify: `motionbrief/render/svg_canvas/scene.py:17`, `:44`, `:59`, `:65`, `:68`, `:76-82`, `:161-193`, `:175`
- Modify: `motionbrief/render/svg_canvas/prims.py:20`

**Interfaces:**
- Consumes: `Canvas` from Task 1; `ir.video` from Task 2.
- Produces: `Ctx.canvas: Canvas`（新字段，放在 `obj_id` 之前，必须带默认值之前的位置）；`frame_svg` 不变签名，内部从 `ir.video` 取 canvas；`_background(tokens, t, cam_x, accent_glow, canvas)` 与 `_transition_wrap(scene, t, inner, bg, canvas)` 增加 `canvas` 参数。

- [ ] **Step 1: 写失败测试（9:16 画布被 Ctx 携带）**

```python
def test_ctx_carries_canvas():
    from motionbrief.render.svg_canvas.components import Ctx
    from motionbrief.render.svg_canvas.canvas import canvas_for
    from motionbrief.render.svg_canvas.easing import Beats

    c = Ctx(t=0.0, t0=0.0, t1=1.0, frame=0, props={}, beats=Beats([], 0.0), palette={}, tokens={},
            canvas=canvas_for("16:9"))
    assert c.canvas.w == 1920
```

- [ ] **Step 2: 运行确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_canvas.py::test_ctx_carries_canvas -q`
Expected: FAIL（`Ctx` 没有 `canvas` 参数）

- [ ] **Step 3: 实现**

1. `components.py` 的 `Ctx` 增加字段 `canvas: Canvas`（放在 `palette` 之后、`obj_id` 之前），并在文件顶部导入 `from motionbrief.render.svg_canvas.canvas import Canvas`。
2. `scene.py:175` 的 `Ctx(...)` 调用加上 `canvas=canvas`。
3. `frame_svg` 开头加一行 `canvas = canvas_for(ir.video.aspect)`；删除 `scene.py:17` 的 `W, H = 1080, 1920`。
4. `scene.py` 中所有 `W` 改为 `canvas.w`，`H` 改为 `canvas.h`（`:59`、`:68`、`:76-82`、`:190-193` 等）。`_background` 与 `_transition_wrap` 通过新增的 `canvas` 参数拿到它们。
5. `prims.py:20` 的 `CX, CY` 暂时保留，在 Task 4 中一并删除，避免这一步因组件仍导入它而 import 失败。

- [ ] **Step 4: 运行快速测试**

Run: `.venv/Scripts/python.exe -m pytest tests/test_canvas.py::test_ctx_carries_canvas -q`
Expected: PASS

## Task 4: 组件改用 canvas（机械替换，快照把关）

**Files:**
- Modify: `motionbrief/render/svg_canvas/components.py`（31 处 `W`/`H`/`CX`/`CY`）
- Modify: `motionbrief/render/svg_canvas/components_concepts.py`（15 处）
- Modify: `motionbrief/render/svg_canvas/components_embodied.py`（47 处）
- Modify: `motionbrief/render/svg_canvas/components_generic.py`（3 处）
- Modify: `motionbrief/render/svg_canvas/components_v3.py`（63 处）
- Modify: `motionbrief/render/svg_canvas/components_robot_arm.py`（如有）

**替换规则（每个文件内）：**
- 在函数体内有 `c`（Ctx）可用时：`W` → `c.canvas.w`，`H` → `c.canvas.h`，`CX` → `c.canvas.cx`，`CY` → `c.canvas.cy`。
- 没有 `c` 的模块级辅助函数：增加 `canvas: Canvas` 参数，由调用方传入。
- 不改数值，不改表达式结构，只换取值方式。

- [ ] **Step 1: 确认替换边界**

Run: `grep -n -E "\bW\b|\bH\b|\bCX\b|\bCY\b" motionbrief/render/svg_canvas/components*.py | cut -c1-160`
Expected: 列出所有需要替换的行。逐个文件确认变量名 `c` 在作用域内。

- [ ] **Step 2: 逐文件替换（用 Edit 工具，不用 sed）**

每个文件替换后运行一次 `.venv/Scripts/python.exe -m pyflakes motionbrief/render/svg_canvas/` 或 `python -m compileall -q motionbrief/render/svg_canvas`，确认没有未定义的名字。

- [ ] **Step 3: 快照比对（主验收）**

Run: `.venv/Scripts/python.exe work/svg_snapshot.py work/snap_after.json`
Run: `.venv/Scripts/python.exe -c "import json;a=json.load(open('work/snap_before.json'));b=json.load(open('work/snap_after.json'));d=[k for k in a if a[k]!=b.get(k)];print(len(a),len(b),'diff:',len(d),d[:5])"`
Expected: `114 114 diff: 0 []`

如有差异，停下来看那一帧的 SVG 文本差在哪里（通常是 `540` 变成 `540.0`，或者替换遗漏），修复后重跑。

## Task 5: 16:9 烟雾测试与全量测试

**Files:**
- Test: `tests/test_canvas.py`（追加）

- [ ] **Step 1: 写测试：16:9 画布能产出合法 SVG 头**

```python
def test_landscape_frame_has_landscape_viewbox():
    from motionbrief.ir.models import load
    from motionbrief.paths import REPO_ROOT
    from motionbrief.render.backend import plan_scene
    from motionbrief.render.svg_canvas.scene import frame_svg

    ir = load(REPO_ROOT / "fixtures/isp_v02.json")
    ir.video.aspect, ir.video.w, ir.video.h = "16:9", 1920, 1080
    scene = ir.scenes[0]
    svg = frame_svg(ir, scene, scene.tStart + 0.5, 15, plan_scene(scene).choices, [])
    assert 'viewBox="0 0 1920 1080"' in svg
```

注意：fixture 是共享对象，测试内修改后要用 `load` 重新读取，不要缓存。

- [ ] **Step 2: 运行**

Run: `.venv/Scripts/python.exe -m pytest tests/test_canvas.py -q`
Expected: PASS

- [ ] **Step 3: 非渲染测试全量**

Run: `.venv/Scripts/python.exe -m pytest -q -m "not render" | tail -n 20`
Expected: 与改动前相同的通过数，无新增失败。若有失败，先对比改动前（`git stash` 不可用，本仓库不是 git 仓库，改用 `work/` 下的备份）。

## Task 6: 验收记录

- [ ] **Step 1: 更新 spec 状态**

在 `docs/superpowers/specs/2026-11-17-landscape-longform-design.md` 第 11 节第 1 条后标注"已完成（画布参数化）"。

- [ ] **Step 2: 向用户报告**

报告内容：快照比对结果（114 帧，diff 0），非渲染测试结果，以及 16:9 的状态（只有 canvas 流通，组件版面未适配，第二阶段处理）。

---

## 自检

- 规格覆盖：spec §2（画幅）的画布参数化、`aspect` 字段、组件使用画布。`also`、归一化坐标、章节卡、质检、风格不在本阶段，列入第二阶段。
- 占位符：无。
- 类型一致：`Canvas(w, h)` 的属性 `cx/cy/w/h` 在 Task 1、3、4 中一致；`canvas_for(aspect)` 在 Task 1、2、3、5 中一致。
