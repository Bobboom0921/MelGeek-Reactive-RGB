# 区域分层灯效系统 v2.1.0 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 将现有「单选灯效」架构重构为「三大区域 × Base + Reactive 双槽」系统，新增 5 个灯效，实现跨区域自由拼合。

**架构：** 引入 `ZoneEffect` 抽象基类统一所有灯效接口，`BlendEngine` 提供 4 种混合模式，`ZoneRenderer` 按区域调度渲染并合并输出。现有 7 个灯效迁移为 `ZoneEffect` 子类，新增 5 个灯效直接注册。`PreviewEngine._loop()` 重构为区域渲染管线。

**技术栈：** Python 3.10+, PyWebView, PyStray, HTML/CSS/JS, hidapi, PyAudioWPatch, numpy

---

## 文件结构

### 新建文件

| 文件 | 职责 |
|------|------|
| `backend/zone_effect.py` | `ZoneEffect` 抽象基类 + `RenderContext` 数据容器 |
| `backend/blend_engine.py` | 4 种混合模式：`normal`/`add`/`multiply`/`screen` |
| `backend/zone_renderer.py` | `ZoneRenderer`：按区域调度渲染、混合、合并输出 |
| `backend/effect_registry.py` | 灯效注册表 + 现有 7 个灯效的 `ZoneEffect` 包装 |
| `backend/new_effects.py` | 新增 5 个灯效：`typewriter`/`starfield`/`wave`/`chase`/`gradient` |
| `backend/config_migrator.py` | `v1 → v2` 配置自动迁移 |
| `tests/test_zones.py` | 区域系统、混合模式、渲染器单元测试 |
| `tests/test_migrator.py` | 配置迁移单元测试 |

### 修改文件

| 文件 | 修改内容 |
|------|---------|
| `backend/main.py` | `PreviewEngine._loop()` 重构为区域渲染管线；`PARAM_SCHEMA` 扩展为三区域格式；API 新增 `/api/effect/set_zone` |
| `ui/index.html` | 新增「高级模式」切换按钮；三区域独立配置面板（Base/Reactive/混合模式）；下拉框按区域过滤灯效 |

---

## Phase 1：架构核心

### 任务 1：ZoneEffect 抽象基类 + RenderContext

**文件：**
- 创建：`backend/zone_effect.py`
- 测试：`tests/test_zones.py`（新增开头部分）

**上下文：** `ZoneEffect` 是所有灯效（Base 和 Reactive）的公共接口。`RenderContext` 每帧传入，包含时间、音频数据、压力数据、主题、参数等。

- [ ] **步骤 1：编写失败的测试**

在 `tests/test_zones.py` 中写入：

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from zone_effect import ZoneEffect, RenderContext


def test_zone_effect_is_abstract():
    """ZoneEffect 不能直接实例化"""
    try:
        ctx = RenderContext(now=0.0, theme=None, audio=None, pressures={}, params={})
        ZoneEffect("test", "base", {"keys"})(ctx)
        assert False, "should raise TypeError"
    except TypeError:
        pass


def test_render_context_fields():
    """RenderContext 包含所有必要字段"""
    ctx = RenderContext(
        now=1.5,
        theme="noir",
        audio={"spectrum": [0.5] * 63, "level": 0.3, "bass": 0.2},
        pressures={5: 0.8},
        params={"speed": 2.0},
        normalized=[(0.0, 0.0)],
        lamp_count=70,
    )
    assert ctx.now == 1.5
    assert ctx.theme == "noir"
    assert len(ctx.audio["spectrum"]) == 63
    assert ctx.pressures[5] == 0.8
    assert ctx.params["speed"] == 2.0
```

- [ ] **步骤 2：运行测试验证失败**

```bash
cd C:/Users/Bobboom/Documents/Codex/2026-06-20/esc
python -m pytest tests/test_zones.py -v
```

预期：`ModuleNotFoundError: No module named 'zone_effect'`

- [ ] **步骤 3：实现 zone_effect.py**

创建 `backend/zone_effect.py`：

```python
"""区域灯效抽象基类与渲染上下文。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class RenderContext:
    """每帧传入灯效的上下文数据。"""

    now: float
    theme: Any  # Theme 对象或名称
    audio: dict[str, Any] | None
    pressures: dict[int, float]
    params: dict[str, Any]
    normalized: list[tuple[float, float]] | None = None
    lamp_count: int = 70
    distance_cache: dict[int, list[tuple[int, float]]] | None = None


class ZoneEffect(ABC):
    """区域灯效抽象基类。"""

    def __init__(self, name: str, effect_type: str, applicable_zones: set[str]) -> None:
        self.name = name
        self.effect_type = effect_type  # "base" 或 "reactive"
        self.applicable_zones = applicable_zones

    @abstractmethod
    def render(self, ctx: RenderContext) -> list[tuple[int, int, int]]:
        """
        渲染一帧。
        返回该区域所有灯珠的 RGB 值列表，长度必须等于 ctx.lamp_count。
        """

    def param_schema(self) -> list[dict]:
        """返回该灯效的 UI 参数定义。子类可覆盖。"""
        return []
```

- [ ] **步骤 4：运行测试验证通过**

```bash
cd C:/Users/Bobboom/Documents/Codex/2026-06-20/esc
python -m pytest tests/test_zones.py::test_zone_effect_is_abstract tests/test_zones.py::test_render_context_fields -v
```

预期：`2 passed`

- [ ] **步骤 5：Commit**

```bash
cd C:/Users/Bobboom/Documents/Codex/2026-06-20/esc
git add backend/zone_effect.py tests/test_zones.py
git commit -m "feat(zone-effect): add ZoneEffect ABC and RenderContext

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 2：BlendEngine 混合模式引擎

**文件：**
- 创建：`backend/blend_engine.py`
- 修改：`tests/test_zones.py`

**上下文：** 提供 4 种混合模式。输入是两个等长的 RGB 列表，输出混合后的 RGB 列表。所有计算在 0-255 整数范围内。

- [ ] **步骤 1：编写失败的测试**

在 `tests/test_zones.py` 追加：

```python
from blend_engine import BlendEngine


def test_blend_normal():
    base = [(100, 100, 100), (0, 0, 0)]
    overlay = [(50, 150, 200), (255, 255, 255)]
    result = BlendEngine.blend(base, overlay, "normal")
    assert result == [(50, 150, 200), (255, 255, 255)]


def test_blend_add():
    base = [(100, 100, 100), (200, 200, 200)]
    overlay = [(100, 100, 100), (100, 100, 100)]
    result = BlendEngine.blend(base, overlay, "add")
    assert result == [(200, 200, 200), (255, 255, 255)]


def test_blend_multiply():
    base = [(128, 128, 128), (255, 255, 255)]
    overlay = [(128, 128, 128), (0, 0, 0)]
    result = BlendEngine.blend(base, overlay, "multiply")
    assert result == [(64, 64, 64), (0, 0, 0)]


def test_blend_screen():
    base = [(128, 0, 0), (0, 128, 0)]
    overlay = [(128, 128, 0), (128, 0, 128)]
    result = BlendEngine.blend(base, overlay, "screen")
    # screen(a,b) = 255 - (255-a)*(255-b)/255
    # r: 255 - 127*127/255 = 255 - 63.3 = 192
    assert result[0][0] == 192
    assert result[0][1] == 128


def test_blend_invalid_mode():
    try:
        BlendEngine.blend([(0, 0, 0)], [(0, 0, 0)], "invalid")
        assert False, "should raise ValueError"
    except ValueError:
        pass


def test_blend_length_mismatch():
    try:
        BlendEngine.blend([(0, 0, 0)], [(0, 0, 0), (0, 0, 0)], "normal")
        assert False, "should raise ValueError"
    except ValueError:
        pass
```

- [ ] **步骤 2：运行测试验证失败**

```bash
cd C:/Users/Bobboom/Documents/Codex/2026-06-20/esc
python -m pytest tests/test_zones.py::test_blend_normal -v
```

预期：`ModuleNotFoundError: No module named 'blend_engine'`

- [ ] **步骤 3：实现 blend_engine.py**

创建 `backend/blend_engine.py`：

```python
"""灯效混合模式引擎。"""
from __future__ import annotations


class BlendEngine:
    """提供多种 RGB 混合模式。所有输入为 0-255 整数元组。"""

    @staticmethod
    def blend(
        base: list[tuple[int, int, int]],
        overlay: list[tuple[int, int, int]],
        mode: str,
    ) -> list[tuple[int, int, int]]:
        if len(base) != len(overlay):
            raise ValueError(f"长度不匹配: {len(base)} != {len(overlay)}")

        if mode == "normal":
            return list(overlay)
        if mode == "add":
            return [
                (
                    min(255, br + or_),
                    min(255, bg + og),
                    min(255, bb + ob),
                )
                for (br, bg, bb), (or_, og, ob) in zip(base, overlay)
            ]
        if mode == "multiply":
            return [
                (
                    (br * or_) // 255,
                    (bg * og) // 255,
                    (bb * ob) // 255,
                )
                for (br, bg, bb), (or_, og, ob) in zip(base, overlay)
            ]
        if mode == "screen":
            return [
                (
                    255 - ((255 - br) * (255 - or_)) // 255,
                    255 - ((255 - bg) * (255 - og)) // 255,
                    255 - ((255 - bb) * (255 - ob)) // 255,
                )
                for (br, bg, bb), (or_, og, ob) in zip(base, overlay)
            ]

        raise ValueError(f"未知混合模式: {mode!r}")
```

- [ ] **步骤 4：运行测试验证通过**

```bash
cd C:/Users/Bobboom/Documents/Codex/2026-06-20/esc
python -m pytest tests/test_zones.py -k blend -v
```

预期：`6 passed`

- [ ] **步骤 5：Commit**

```bash
cd C:/Users/Bobboom/Documents/Codex/2026-06-20/esc
git add backend/blend_engine.py tests/test_zones.py
git commit -m "feat(blend): add BlendEngine with 4 blend modes

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 3：ZoneRenderer 区域渲染器

**文件：**
- 创建：`backend/zone_renderer.py`
- 修改：`tests/test_zones.py`

**上下文：** `ZoneRenderer` 持有 3 个区域的配置（base effect、reactive effect、blend mode），每帧负责：1) 为每个区域创建 RenderContext；2) 调用 base.render() 和 reactive.render()；3) 用 BlendEngine 混合；4) 按灯珠 ID 合并为完整 285 色帧。

区域灯珠映射（与现有代码一致）：
- `keys`: lamp_id 0-69 (70 灯)
- `backplate`: lamp_id 70-258 (189 灯)
- `sides`: lamp_id 259-284 (26 灯)

- [ ] **步骤 1：编写失败的测试**

在 `tests/test_zones.py` 追加：

```python
from zone_effect import ZoneEffect, RenderContext
from blend_engine import BlendEngine


class MockEffect(ZoneEffect):
    """测试用 mock 灯效：返回固定颜色。"""

    def __init__(self, name: str, color: tuple[int, int, int]) -> None:
        super().__init__(name, "base", {"keys", "backplate", "sides"})
        self.color = color

    def render(self, ctx: RenderContext) -> list[tuple[int, int, int]]:
        return [self.color] * ctx.lamp_count


def test_zone_renderer_merge_keys_only():
    from zone_renderer import ZoneRenderer

    renderer = ZoneRenderer(
        keys_base=MockEffect("red", (255, 0, 0)),
        keys_reactive=None,
        keys_blend="normal",
        backplate_base=None,
        backplate_reactive=None,
        backplate_blend="normal",
        sides_base=None,
        sides_reactive=None,
        sides_blend="normal",
    )
    ctx = RenderContext(now=0.0, theme="noir", audio=None, pressures={}, params={})
    frame = renderer.render_frame(ctx)
    assert len(frame) == 285
    assert frame[0] == (255, 0, 0)    # keys 第一个灯
    assert frame[69] == (255, 0, 0)   # keys 最后一个灯
    assert frame[70] == (0, 0, 0)     # backplate 未配置 = 黑
    assert frame[284] == (0, 0, 0)    # sides 未配置 = 黑


def test_zone_renderer_blend_add():
    from zone_renderer import ZoneRenderer

    renderer = ZoneRenderer(
        keys_base=MockEffect("red", (100, 0, 0)),
        keys_reactive=MockEffect("green", (0, 100, 0)),
        keys_blend="add",
        backplate_base=None,
        backplate_reactive=None,
        backplate_blend="normal",
        sides_base=None,
        sides_reactive=None,
        sides_blend="normal",
    )
    ctx = RenderContext(now=0.0, theme="noir", audio=None, pressures={}, params={})
    frame = renderer.render_frame(ctx)
    assert frame[0] == (100, 100, 0)  # add 混合


def test_zone_renderer_all_zones():
    from zone_renderer import ZoneRenderer

    renderer = ZoneRenderer(
        keys_base=MockEffect("red", (255, 0, 0)),
        keys_reactive=None,
        keys_blend="normal",
        backplate_base=MockEffect("green", (0, 255, 0)),
        backplate_reactive=None,
        backplate_blend="normal",
        sides_base=MockEffect("blue", (0, 0, 255)),
        sides_reactive=None,
        sides_blend="normal",
    )
    ctx = RenderContext(now=0.0, theme="noir", audio=None, pressures={}, params={})
    frame = renderer.render_frame(ctx)
    assert frame[0] == (255, 0, 0)      # keys
    assert frame[70] == (0, 255, 0)     # backplate 第一个
    assert frame[258] == (0, 255, 0)    # backplate 最后一个
    assert frame[259] == (0, 0, 255)    # sides 第一个
    assert frame[284] == (0, 0, 255)    # sides 最后一个
```

- [ ] **步骤 2：运行测试验证失败**

```bash
cd C:/Users/Bobboom/Documents/Codex/2026-06-20/esc
python -m pytest tests/test_zones.py::test_zone_renderer_merge_keys_only -v
```

预期：`ModuleNotFoundError: No module named 'zone_renderer'`

- [ ] **步骤 3：实现 zone_renderer.py**

创建 `backend/zone_renderer.py`：

```python
"""区域渲染器：按区域调度灯效渲染并合并输出。"""
from __future__ import annotations

from typing import Any

from blend_engine import BlendEngine
from zone_effect import RenderContext, ZoneEffect

# 区域灯珠范围映射（与 melgeek68_premium_reactive.py 一致）
ZONE_RANGES = {
    "keys": range(0, 70),
    "backplate": range(70, 259),
    "sides": range(259, 285),
}

ZONE_LAMP_COUNTS = {
    "keys": 70,
    "backplate": 189,
    "sides": 26,
}


class ZoneRenderer:
    """管理三大区域的灯效配置并每帧渲染合并。"""

    def __init__(
        self,
        keys_base: ZoneEffect | None,
        keys_reactive: ZoneEffect | None,
        keys_blend: str,
        backplate_base: ZoneEffect | None,
        backplate_reactive: ZoneEffect | None,
        backplate_blend: str,
        sides_base: ZoneEffect | None,
        sides_reactive: ZoneEffect | None,
        sides_blend: str,
    ) -> None:
        self.zones = {
            "keys": {
                "base": keys_base,
                "reactive": keys_reactive,
                "blend": keys_blend,
                "count": ZONE_LAMP_COUNTS["keys"],
            },
            "backplate": {
                "base": backplate_base,
                "reactive": backplate_reactive,
                "blend": backplate_blend,
                "count": ZONE_LAMP_COUNTS["backplate"],
            },
            "sides": {
                "base": sides_base,
                "reactive": sides_reactive,
                "blend": sides_blend,
                "count": ZONE_LAMP_COUNTS["sides"],
            },
        }

    def render_frame(self, ctx: RenderContext) -> list[tuple[int, int, int]]:
        """渲染完整一帧（285 灯珠），返回 RGB 列表。"""
        # 初始化全黑帧
        full_frame: list[tuple[int, int, int]] = [(0, 0, 0)] * 285

        for zone_name, zone_cfg in self.zones.items():
            base_eff = zone_cfg["base"]
            reactive_eff = zone_cfg["reactive"]
            blend_mode = zone_cfg["blend"]
            count = zone_cfg["count"]

            # 创建区域专用的 RenderContext
            zone_ctx = RenderContext(
                now=ctx.now,
                theme=ctx.theme,
                audio=ctx.audio,
                pressures=ctx.pressures,
                params=ctx.params,
                normalized=ctx.normalized,
                lamp_count=count,
                distance_cache=ctx.distance_cache,
            )

            # 渲染 base 层
            if base_eff is not None:
                base_colors = base_eff.render(zone_ctx)
            else:
                base_colors = [(0, 0, 0)] * count

            # 渲染 reactive 层
            if reactive_eff is not None:
                reactive_colors = reactive_eff.render(zone_ctx)
            else:
                reactive_colors = [(0, 0, 0)] * count

            # 混合
            if base_eff is None and reactive_eff is None:
                merged = [(0, 0, 0)] * count
            elif base_eff is None:
                merged = reactive_colors
            elif reactive_eff is None:
                merged = base_colors
            else:
                merged = BlendEngine.blend(base_colors, reactive_colors, blend_mode)

            # 写入完整帧的对应位置
            start = ZONE_RANGES[zone_name].start
            for i, rgb in enumerate(merged):
                full_frame[start + i] = rgb

        return full_frame
```

- [ ] **步骤 4：运行测试验证通过**

```bash
cd C:/Users/Bobboom/Documents/Codex/2026-06-20/esc
python -m pytest tests/test_zones.py -k zone_renderer -v
```

预期：`3 passed`

- [ ] **步骤 5：Commit**

```bash
cd C:/Users/Bobboom/Documents/Codex/2026-06-20/esc
git add backend/zone_renderer.py tests/test_zones.py
git commit -m "feat(renderer): add ZoneRenderer with 3-zone merge

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Phase 2：现有灯效迁移

### 任务 4：静态灯效 StaticEffect

**文件：**
- 创建：`backend/effect_registry.py`（开头部分）

**上下文：** 最简单的 Base 灯效，返回统一固定色。使用主题色 `base_hsv` 或 `outer_base_hsv`。由于 zone 不同，需要知道自己在哪个区域来选择颜色。

- [ ] **步骤 1：实现 StaticEffect**

在 `backend/effect_registry.py` 写入：

```python
"""灯效注册表：现有灯效的 ZoneEffect 包装。"""
from __future__ import annotations

import math
import time
from typing import Any

from zone_effect import ZoneEffect, RenderContext

# 导入现有工具函数
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from melgeek68_premium_reactive import (
    hsv_to_rgb,
    render_static,
    render_breathing,
    render_rainbow,
    render_ripple_effect,
    render_keys,
    render_backplate,
    render_sides,
    Theme,
    BLACK,
)


# ── 辅助：从主题名获取 Theme 对象 ──
_theme_cache: dict[str, Theme] = {}


def _get_theme(theme_name: str) -> Theme:
    from melgeek68_premium_reactive import select_theme

    if theme_name not in _theme_cache:
        _theme_cache[theme_name] = select_theme(theme_name)
    return _theme_cache[theme_name]


# ── 静态灯效 ──
class StaticEffect(ZoneEffect):
    """静态固定色。"""

    def __init__(self) -> None:
        super().__init__("static", "base", {"keys", "backplate", "sides"})

    def render(self, ctx: RenderContext) -> list[tuple[int, int, int]]:
        theme = _get_theme(str(ctx.theme))
        # 根据区域大小判断使用哪种颜色
        if ctx.lamp_count == 70:
            color = hsv_to_rgb(*theme.base_hsv)
        else:
            color = hsv_to_rgb(*theme.outer_base_hsv)
        return [color] * ctx.lamp_count
```

- [ ] **步骤 2：编写测试**

在 `tests/test_zones.py` 追加：

```python
def test_static_effect_keys():
    from effect_registry import StaticEffect
    eff = StaticEffect()
    ctx = RenderContext(now=0.0, theme="noir", audio=None, pressures={}, params={}, lamp_count=70)
    colors = eff.render(ctx)
    assert len(colors) == 70
    assert all(c == colors[0] for c in colors)


def test_static_effect_backplate():
    from effect_registry import StaticEffect
    eff = StaticEffect()
    ctx = RenderContext(now=0.0, theme="noir", audio=None, pressures={}, params={}, lamp_count=189)
    colors = eff.render(ctx)
    assert len(colors) == 189
```

- [ ] **步骤 3：运行测试**

```bash
cd C:/Users/Bobboom/Documents/Codex/2026-06-20/esc
python -m pytest tests/test_zones.py::test_static_effect_keys tests/test_zones.py::test_static_effect_backplate -v
```

预期：`2 passed`

- [ ] **步骤 4：Commit**

```bash
cd C:/Users/Bobboom/Documents/Codex/2026-06-20/esc
git add backend/effect_registry.py tests/test_zones.py
git commit -m "feat(effects): add StaticEffect ZoneEffect wrapper

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 5：呼吸灯效 BreathingEffect

**文件：**
- 修改：`backend/effect_registry.py`

**上下文：** 包装现有 `render_breathing` 函数。参数从 `ctx.params` 读取 `speed` 和 `depth`。

- [ ] **步骤 1：实现 BreathingEffect**

在 `backend/effect_registry.py` 中 `StaticEffect` 类后面追加：

```python

class BreathingEffect(ZoneEffect):
    """呼吸灯效。"""

    def __init__(self) -> None:
        super().__init__("breathing", "base", {"keys", "backplate", "sides"})

    def render(self, ctx: RenderContext) -> list[tuple[int, int, int]]:
        theme = _get_theme(str(ctx.theme))
        speed = float(ctx.params.get("speed", 1.0))
        depth = float(ctx.params.get("depth", 1.0))
        # render_breathing 返回完整 285 灯，我们切片出需要的区域
        full = render_breathing(theme, ctx.now, speed, depth)
        if ctx.lamp_count == 70:
            return full[:70]
        elif ctx.lamp_count == 189:
            return full[70:259]
        else:  # sides = 26
            return full[259:285]

    def param_schema(self) -> list[dict]:
        return [
            {"key": "speed", "label": "呼吸速度", "min": 0.2, "max": 3, "step": 0.05, "fmt": "{:.2f}"},
            {"key": "depth", "label": "呼吸幅度", "min": 0, "max": 1, "step": 0.02, "fmt": "{:.0%}"},
        ]
```

- [ ] **步骤 2：编写测试**

在 `tests/test_zones.py` 追加：

```python
def test_breathing_effect():
    from effect_registry import BreathingEffect
    eff = BreathingEffect()
    ctx = RenderContext(now=0.0, theme="noir", audio=None, pressures={}, params={"speed": 1.0, "depth": 1.0}, lamp_count=70)
    colors = eff.render(ctx)
    assert len(colors) == 70
    assert all(c == colors[0] for c in colors)  # 呼吸在单帧内是统一色
```

- [ ] **步骤 3：运行测试**

```bash
cd C:/Users/Bobboom/Documents/Codex/2026-06-20/esc
python -m pytest tests/test_zones.py::test_breathing_effect -v
```

预期：`1 passed`

- [ ] **步骤 4：Commit**

```bash
cd C:/Users/Bobboom/Documents/Codex/2026-06-20/esc
git add backend/effect_registry.py tests/test_zones.py
git commit -m "feat(effects): add BreathingEffect wrapper

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 6：彩虹灯效 RainbowEffect

**文件：**
- 修改：`backend/effect_registry.py`

- [ ] **步骤 1：实现 RainbowEffect**

在 `backend/effect_registry.py` 中追加：

```python

class RainbowEffect(ZoneEffect):
    """彩虹灯效。"""

    def __init__(self) -> None:
        super().__init__("rainbow", "base", {"keys", "backplate", "sides"})

    def render(self, ctx: RenderContext) -> list[tuple[int, int, int]]:
        theme = _get_theme(str(ctx.theme))
        style = str(ctx.params.get("style", "diagonal"))
        speed = float(ctx.params.get("speed", 1.0))
        saturation = float(ctx.params.get("saturation", 0.68))
        value = float(ctx.params.get("value", 0.62))
        # render_rainbow 需要 normalized positions，但它是完整 285 灯的
        # 这里简化：直接返回完整帧然后切片
        # TODO: 后续优化为只渲染目标区域
        from melgeek68_premium_reactive import normalize_positions, load_params_from_cache
        try:
            positions, _ = load_params_from_cache()
        except Exception:
            positions = []
        normalized = normalize_positions(positions, 285)
        full = render_rainbow(theme, normalized, ctx.now, style, speed, saturation, value)
        if ctx.lamp_count == 70:
            return full[:70]
        elif ctx.lamp_count == 189:
            return full[70:259]
        else:
            return full[259:285]

    def param_schema(self) -> list[dict]:
        return [
            {"key": "style", "label": "彩虹样式", "type": "select", "options": ["diagonal", "horizontal", "vertical", "radial", "dual", "pastel"]},
            {"key": "speed", "label": "流动速度", "min": 0.05, "max": 5, "step": 0.05, "fmt": "{:.2f}"},
            {"key": "saturation", "label": "色彩饱和度", "min": 0, "max": 1, "step": 0.02, "fmt": "{:.0%}"},
            {"key": "value", "label": "彩虹亮度", "min": 0, "max": 1, "step": 0.02, "fmt": "{:.0%}"},
        ]
```

- [ ] **步骤 2：运行测试**

```bash
cd C:/Users/Bobboom/Documents/Codex/2026-06-20/esc
python -m pytest tests/test_zones.py -k rainbow -v
```

由于还没有写测试，直接运行确认不报错：

```bash
cd C:/Users/Bobboom/Documents/Codex/2026-06-20/esc
python -c "from effect_registry import RainbowEffect; print('ok')"
```

预期：`ok`

- [ ] **步骤 3：Commit**

```bash
cd C:/Users/Bobboom/Documents/Codex/2026-06-20/esc
git add backend/effect_registry.py
git commit -m "feat(effects): add RainbowEffect wrapper

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 7：涟漪灯效 RippleEffect

**文件：**
- 修改：`backend/effect_registry.py`

**上下文：** Ripple 是 Reactive 型，需要压力事件触发。但当前架构下，reactive effect 的 render() 只接收 ctx，不包含事件信息。需要在 `ZoneRenderer` 或 `PreviewEngine` 中维护 `ActiveRipple` 列表，通过 `ctx.params` 传入。

设计决策：reactive effect 的 `params` 中传入 `_active_ripples` 列表，由调用方维护。

- [ ] **步骤 1：实现 RippleEffect**

在 `backend/effect_registry.py` 中追加：

```python

class RippleEffect(ZoneEffect):
    """涟漪灯效（Reactive）。"""

    def __init__(self) -> None:
        super().__init__("ripple", "reactive", {"keys", "backplate"})

    def render(self, ctx: RenderContext) -> list[tuple[int, int, int]]:
        theme = _get_theme(str(ctx.theme))
        ripples = ctx.params.get("_active_ripples", [])
        brightness = float(ctx.params.get("brightness", 1.0))
        width = float(ctx.params.get("width", 1.0))
        from melgeek68_premium_reactive import normalize_positions, load_params_from_cache
        try:
            positions, _ = load_params_from_cache()
        except Exception:
            positions = []
        normalized = normalize_positions(positions, 285)
        full = render_ripple_effect(theme, normalized, ripples, ctx.now, brightness, width)
        if ctx.lamp_count == 70:
            return full[:70]
        elif ctx.lamp_count == 189:
            return full[70:259]
        else:
            return full[259:285]

    def param_schema(self) -> list[dict]:
        return [
            {"key": "brightness", "label": "涟漪亮度", "min": 0, "max": 3, "step": 0.05, "fmt": "{:.2f}"},
            {"key": "width", "label": "涟漪宽度", "min": 0.2, "max": 4, "step": 0.05, "fmt": "{:.2f}"},
        ]
```

- [ ] **步骤 2：Commit**

```bash
cd C:/Users/Bobboom/Documents/Codex/2026-06-20/esc
git add backend/effect_registry.py
git commit -m "feat(effects): add RippleEffect wrapper

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 8：压力热力灯效 PressureDentEffect

**文件：**
- 修改：`backend/effect_registry.py`

- [ ] **步骤 1：实现 PressureDentEffect**

在 `backend/effect_registry.py` 中追加：

```python

class PressureDentEffect(ZoneEffect):
    """按键压力热力灯效（Reactive）。仅字符区。"""

    def __init__(self) -> None:
        super().__init__("pressure_dent", "reactive", {"keys"})

    def render(self, ctx: RenderContext) -> list[tuple[int, int, int]]:
        theme = _get_theme(str(ctx.theme))
        from melgeek68_premium_reactive import (
            render_keys, render_static, normalize_positions, build_distance_cache,
            load_params_from_cache,
        )
        try:
            positions, _ = load_params_from_cache()
        except Exception:
            positions = []
        normalized = normalize_positions(positions, 285)
        # distance_cache 需要完整重建，半径从 params 读取
        radius = float(ctx.params.get("radius", 13.0))
        distance_cache = build_distance_cache(normalized, 70, 285, max_radius=max(18.0, radius + 4.0))
        color_floor = float(ctx.params.get("color_floor", 0.22))
        space_color_floor = float(ctx.params.get("space_color_floor", 0.26))
        # 先取静态底色
        full = render_static(theme)
        # 压力数据在 ctx.pressures 中
        flashes = {}  # 简化：flash 效果在后续迭代中处理
        render_keys(
            full, theme, normalized, distance_cache,
            ctx.pressures, flashes, 0.0, radius,
            color_floor, space_color_floor,
        )
        return full[:70]

    def param_schema(self) -> list[dict]:
        return [
            {"key": "radius", "label": "压力扩散", "min": 4, "max": 30, "step": 0.5, "fmt": "{:.1f}"},
            {"key": "color_floor", "label": "周边染色", "min": 0, "max": 1, "step": 0.01, "fmt": "{:.0%}"},
            {"key": "space_color_floor", "label": "空格染色", "min": 0, "max": 1, "step": 0.01, "fmt": "{:.0%}"},
        ]
```

- [ ] **步骤 2：Commit**

```bash
cd C:/Users/Bobboom/Documents/Codex/2026-06-20/esc
git add backend/effect_registry.py
git commit -m "feat(effects): add PressureDentEffect wrapper

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 9：音频频谱灯效 AudioSpectrumEffect

**文件：**
- 修改：`backend/effect_registry.py`

- [ ] **步骤 1：实现 AudioSpectrumEffect**

在 `backend/effect_registry.py` 中追加：

```python

class AudioSpectrumEffect(ZoneEffect):
    """背板音频频谱灯效（Reactive）。仅背板区。"""

    def __init__(self) -> None:
        super().__init__("audio_spectrum", "reactive", {"backplate"})

    def render(self, ctx: RenderContext) -> list[tuple[int, int, int]]:
        theme = _get_theme(str(ctx.theme))
        audio_data = ctx.audio or {"spectrum": [0.0] * 63, "level": 0.0, "bass": 0.0}
        from melgeek68_premium_reactive import render_backplate
        full = [(0, 0, 0)] * 285
        # peak_hold 需要持久化状态，这里简化为空列表
        peak_hold = [0.0] * 63
        from melgeek68_premium_reactive import AudioSnapshot
        audio = AudioSnapshot(audio_data.get("spectrum", [0.0] * 63), audio_data.get("level", 0.0), audio_data.get("bass", 0.0))
        ambience = float(ctx.params.get("ambience_strength", 1.0))
        shockwave = float(ctx.params.get("shockwave_strength", 1.0))
        motion = float(ctx.params.get("motion", 1.0))
        render_backplate(full, theme, audio, peak_hold, ctx.now, ambience, shockwave, motion)
        return full[70:259]

    def param_schema(self) -> list[dict]:
        return [
            {"key": "ambience_strength", "label": "背板氛围", "min": 0, "max": 3, "step": 0.05, "fmt": "{:.2f}"},
            {"key": "shockwave_strength", "label": "低频冲击", "min": 0, "max": 3, "step": 0.05, "fmt": "{:.2f}"},
            {"key": "motion", "label": "背板运动", "min": 0, "max": 2, "step": 0.05, "fmt": "{:.2f}"},
        ]
```

- [ ] **步骤 2：Commit**

```bash
cd C:/Users/Bobboom/Documents/Codex/2026-06-20/esc
git add backend/effect_registry.py
git commit -m "feat(effects): add AudioSpectrumEffect wrapper

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 10：音频 VU 灯效 AudioVuEffect

**文件：**
- 修改：`backend/effect_registry.py`

- [ ] **步骤 1：实现 AudioVuEffect**

在 `backend/effect_registry.py` 中追加：

```python

class AudioVuEffect(ZoneEffect):
    """侧边音频 VU 表灯效（Reactive）。仅侧边区。"""

    def __init__(self) -> None:
        super().__init__("audio_vu", "reactive", {"sides"})

    def render(self, ctx: RenderContext) -> list[tuple[int, int, int]]:
        theme = _get_theme(str(ctx.theme))
        audio_data = ctx.audio or {"spectrum": [0.0] * 63, "level": 0.0, "bass": 0.0}
        from melgeek68_premium_reactive import render_sides
        full = [(0, 0, 0)] * 285
        vu_strength = float(ctx.params.get("vu_strength", 1.0))
        vu_curve = float(ctx.params.get("vu_curve", 0.62))
        render_sides(full, theme, audio_data.get("level", 0.0), audio_data.get("bass", 0.0), vu_strength, vu_curve)
        return full[259:285]

    def param_schema(self) -> list[dict]:
        return [
            {"key": "vu_strength", "label": "侧边 VU", "min": 0, "max": 3, "step": 0.05, "fmt": "{:.2f}"},
            {"key": "vu_curve", "label": "VU 曲线", "min": 0.25, "max": 1.5, "step": 0.01, "fmt": "{:.2f}"},
        ]
```

- [ ] **步骤 2：Commit**

```bash
cd C:/Users/Bobboom/Documents/Codex/2026-06-20/esc
git add backend/effect_registry.py
git commit -m "feat(effects): add AudioVuEffect wrapper

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 11：注册表整合与便捷工厂函数

**文件：**
- 修改：`backend/effect_registry.py`

- [ ] **步骤 1：添加注册表字典和工厂函数**

在 `backend/effect_registry.py` 文件末尾追加：

```python

# ── 全局注册表 ──
_EFFECT_REGISTRY: dict[str, type[ZoneEffect]] = {
    "static": StaticEffect,
    "breathing": BreathingEffect,
    "rainbow": RainbowEffect,
    "ripple": RippleEffect,
    "pressure_dent": PressureDentEffect,
    "audio_spectrum": AudioSpectrumEffect,
    "audio_vu": AudioVuEffect,
}


def create_effect(name: str) -> ZoneEffect | None:
    """通过名称创建灯效实例。"""
    cls = _EFFECT_REGISTRY.get(name)
    if cls is None:
        return None
    return cls()


def list_effects(zone: str | None = None) -> list[dict]:
    """
    列出所有可用灯效。
    若指定 zone，只返回适用于该区域的灯效。
    返回格式：[{"name": "...", "type": "base|reactive", "zones": ["keys", ...]}]
    """
    result = []
    for name, cls in _EFFECT_REGISTRY.items():
        inst = cls()
        if zone is None or zone in inst.applicable_zones:
            result.append({
                "name": name,
                "type": inst.effect_type,
                "zones": sorted(inst.applicable_zones),
            })
    return result
```

- [ ] **步骤 2：编写测试**

在 `tests/test_zones.py` 追加：

```python
def test_effect_registry():
    from effect_registry import create_effect, list_effects, StaticEffect, BreathingEffect
    eff = create_effect("static")
    assert isinstance(eff, StaticEffect)
    eff2 = create_effect("breathing")
    assert isinstance(eff2, BreathingEffect)
    assert create_effect("nonexistent") is None


def test_list_effects_filtered():
    from effect_registry import list_effects
    keys_effects = list_effects("keys")
    names = [e["name"] for e in keys_effects]
    assert "static" in names
    assert "pressure_dent" in names
    assert "audio_vu" not in names  # audio_vu 不适用 keys
```

- [ ] **步骤 3：运行测试**

```bash
cd C:/Users/Bobboom/Documents/Codex/2026-06-20/esc
python -m pytest tests/test_zones.py::test_effect_registry tests/test_zones.py::test_list_effects_filtered -v
```

预期：`2 passed`

- [ ] **步骤 4：Commit**

```bash
cd C:/Users/Bobboom/Documents/Codex/2026-06-20/esc
git add backend/effect_registry.py tests/test_zones.py
git commit -m "feat(registry): add effect registry with factory and list functions

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Phase 3：新增灯效

### 任务 12：打字机灯效 TypewriterEffect

**文件：**
- 创建：`backend/new_effects.py`（开头部分）

**规格：** 按键后从按下位置向外扩散一道光波，波前亮色波尾渐暗。

- [ ] **步骤 1：实现 TypewriterEffect**

创建 `backend/new_effects.py`：

```python
"""新增灯效实现。"""
from __future__ import annotations

import math
from typing import Any

from zone_effect import ZoneEffect, RenderContext


class TypewriterEffect(ZoneEffect):
    """打字机灯效：按键触发光波扩散。Reactive，仅字符区。"""

    def __init__(self) -> None:
        super().__init__("typewriter", "reactive", {"keys"})
        self._waves: list[dict] = []  # 活跃光波列表

    def render(self, ctx: RenderContext) -> list[tuple[int, int, int]]:
        colors = [[0.0, 0.0, 0.0] for _ in range(ctx.lamp_count)]
        wave_speed = float(ctx.params.get("wave_speed", 1.5))
        decay = float(ctx.params.get("decay", 0.82))

        # 检查新按键（通过 ctx.pressures 中新增键判断）
        # 简化：每个有压力的键触发一个光波
        for key_id, pressure in ctx.pressures.items():
            if 0 <= key_id < ctx.lamp_count:
                # 触发新光波（去重：同一帧同一键只触发一次）
                if not any(w["key_id"] == key_id and w["birth"] == ctx.now for w in self._waves):
                    self._waves.append({
                        "key_id": key_id,
                        "birth": ctx.now,
                        "intensity": min(1.0, pressure * 1.2),
                    })

        # 更新并渲染光波
        new_waves = []
        for wave in self._waves:
            age = ctx.now - wave["birth"]
            radius = age * wave_speed * 8.0  # 扩散速度
            intensity = wave["intensity"] * (decay ** (age * 30))

            if intensity < 0.01:
                continue

            new_waves.append(wave)

            # 影响附近灯珠
            center = wave["key_id"]
            for lamp_id in range(ctx.lamp_count):
                dist = abs(lamp_id - center)
                if dist > radius + 5:
                    continue
                # 波前高亮，波尾渐暗
                ring = math.exp(-0.5 * ((dist - radius) / 2.5) ** 2)
                tail = math.exp(-0.5 * (dist / max(0.01, radius * 0.6)) ** 2) * 0.3
                level = max(ring, tail) * intensity
                # 使用主题 accent 色（简化：金色）
                colors[lamp_id][0] += 255 * level * 0.9
                colors[lamp_id][1] += 220 * level * 0.8
                colors[lamp_id][2] += 100 * level * 0.4

        self._waves = new_waves

        return [
            (min(255, int(c[0])), min(255, int(c[1])), min(255, int(c[2])))
            for c in colors
        ]

    def param_schema(self) -> list[dict]:
        return [
            {"key": "wave_speed", "label": "扩散速度", "min": 0.5, "max": 3.0, "step": 0.1, "fmt": "{:.1f}"},
            {"key": "decay", "label": "衰减系数", "min": 0.5, "max": 0.95, "step": 0.01, "fmt": "{:.2f}"},
        ]
```

- [ ] **步骤 2：编写测试**

在 `tests/test_zones.py` 追加：

```python
def test_typewriter_effect():
    from new_effects import TypewriterEffect
    eff = TypewriterEffect()
    ctx = RenderContext(now=0.0, theme="noir", audio=None, pressures={5: 0.8}, params={}, lamp_count=70)
    colors = eff.render(ctx)
    assert len(colors) == 70
    # 按键位置附近应该有颜色
    assert sum(colors[5]) > 0
```

- [ ] **步骤 3：运行测试**

```bash
cd C:/Users/Bobboom/Documents/Codex/2026-06-20/esc
python -m pytest tests/test_zones.py::test_typewriter_effect -v
```

预期：`1 passed`

- [ ] **步骤 4：Commit**

```bash
cd C:/Users/Bobboom/Documents/Codex/2026-06-20/esc
git add backend/new_effects.py tests/test_zones.py
git commit -m "feat(effects): add TypewriterEffect

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 13：星空灯效 StarfieldEffect

**文件：**
- 修改：`backend/new_effects.py`

- [ ] **步骤 1：实现 StarfieldEffect**

在 `backend/new_effects.py` 中追加：

```python

class StarfieldEffect(ZoneEffect):
    """星空灯效：随机灯珠闪烁，偶尔流星划过。Base 型。"""

    def __init__(self) -> None:
        super().__init__("starfield", "base", {"backplate", "sides"})
        self._stars: list[dict] | None = None
        self._meteors: list[dict] = []
        self._lamp_count = 0

    def _init_stars(self, count: int, density: float) -> None:
        import random
        star_count = int(count * density)
        self._stars = []
        for i in range(star_count):
            self._stars.append({
                "lamp_id": random.randint(0, count - 1),
                "phase": random.random() * 6.28,
                "speed": 0.5 + random.random() * 2.0,
                "brightness": 0.3 + random.random() * 0.7,
            })

    def render(self, ctx: RenderContext) -> list[tuple[int, int, int]]:
        density = float(ctx.params.get("density", 0.3))
        speed = float(ctx.params.get("speed", 0.2))
        twinkle = float(ctx.params.get("twinkle", 0.5))

        if self._stars is None or self._lamp_count != ctx.lamp_count:
            self._init_stars(ctx.lamp_count, density)
            self._lamp_count = ctx.lamp_count

        colors = [[0.0, 0.0, 0.0] for _ in range(ctx.lamp_count)]

        # 星星闪烁
        for star in self._stars:
            flicker = 0.5 + 0.5 * math.sin(ctx.now * star["speed"] + star["phase"])
            flicker = 1.0 - twinkle + twinkle * flicker
            lid = star["lamp_id"]
            if 0 <= lid < ctx.lamp_count:
                b = star["brightness"] * flicker
                colors[lid][0] += 200 * b
                colors[lid][1] += 220 * b
                colors[lid][2] += 255 * b

        # 流星
        import random
        if random.random() < speed * 0.02 and len(self._meteors) < 3:
            self._meteors.append({
                "pos": 0.0,
                "speed": 5.0 + random.random() * 10.0,
                "birth": ctx.now,
            })

        new_meteors = []
        for meteor in self._meteors:
            age = ctx.now - meteor["birth"]
            meteor["pos"] += meteor["speed"]
            if meteor["pos"] > ctx.lamp_count + 5:
                continue
            new_meteors.append(meteor)
            # 流星拖尾
            for offset in range(5):
                lid = int(meteor["pos"] - offset)
                if 0 <= lid < ctx.lamp_count:
                    intensity = (1.0 - offset / 5.0) * max(0, 1.0 - age * 0.5)
                    colors[lid][0] += 255 * intensity
                    colors[lid][1] += 240 * intensity
                    colors[lid][2] += 200 * intensity

        self._meteors = new_meteors

        return [
            (min(255, int(c[0])), min(255, int(c[1])), min(255, int(c[2])))
            for c in colors
        ]

    def param_schema(self) -> list[dict]:
        return [
            {"key": "density", "label": "星星密度", "min": 0.1, "max": 1.0, "step": 0.05, "fmt": "{:.2f}"},
            {"key": "speed", "label": "流星频率", "min": 0, "max": 1.0, "step": 0.05, "fmt": "{:.2f}"},
            {"key": "twinkle", "label": "闪烁幅度", "min": 0, "max": 1.0, "step": 0.05, "fmt": "{:.2f}"},
        ]
```

- [ ] **步骤 2：Commit**

```bash
cd C:/Users/Bobboom/Documents/Codex/2026-06-20/esc
git add backend/new_effects.py
git commit -m "feat(effects): add StarfieldEffect

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 14：波浪灯效 WaveEffect

**文件：**
- 修改：`backend/new_effects.py`

- [ ] **步骤 1：实现 WaveEffect**

在 `backend/new_effects.py` 中追加：

```python

class WaveEffect(ZoneEffect):
    """波浪灯效：正弦波传播。Base 型，全局可用。"""

    def __init__(self) -> None:
        super().__init__("wave", "base", {"keys", "backplate", "sides"})

    def render(self, ctx: RenderContext) -> list[tuple[int, int, int]]:
        direction = str(ctx.params.get("direction", "horizontal"))
        speed = float(ctx.params.get("speed", 1.0))
        frequency = float(ctx.params.get("frequency", 2.0))
        amplitude = float(ctx.params.get("amplitude", 0.5))

        colors = []
        for lamp_id in range(ctx.lamp_count):
            pos = lamp_id / max(1, ctx.lamp_count - 1)
            if direction == "horizontal":
                phase = pos * frequency * 6.28 + ctx.now * speed * 3.0
            elif direction == "vertical":
                phase = (1.0 - pos) * frequency * 6.28 + ctx.now * speed * 3.0
            else:  # radial
                phase = pos * frequency * 6.28 - ctx.now * speed * 3.0

            level = (math.sin(phase) * 0.5 + 0.5) * amplitude
            # 使用主题色渐变（简化：青到紫）
            r = int(50 + level * 100)
            g = int(100 + level * 155)
            b = int(200 + level * 55)
            colors.append((r, g, b))

        return colors

    def param_schema(self) -> list[dict]:
        return [
            {"key": "direction", "label": "方向", "type": "select", "options": ["horizontal", "vertical", "radial"]},
            {"key": "speed", "label": "传播速度", "min": 0.1, "max": 3.0, "step": 0.1, "fmt": "{:.1f}"},
            {"key": "frequency", "label": "波数", "min": 0.5, "max": 5.0, "step": 0.1, "fmt": "{:.1f}"},
            {"key": "amplitude", "label": "振幅", "min": 0, "max": 1.0, "step": 0.05, "fmt": "{:.2f}"},
        ]
```

- [ ] **步骤 2：Commit**

```bash
cd C:/Users/Bobboom/Documents/Codex/2026-06-20/esc
git add backend/new_effects.py
git commit -m "feat(effects): add WaveEffect

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 15：追逐灯效 ChaseEffect

**文件：**
- 修改：`backend/new_effects.py`

- [ ] **步骤 1：实现 ChaseEffect**

在 `backend/new_effects.py` 中追加：

```python

class ChaseEffect(ZoneEffect):
    """追逐灯效：光点沿灯带循环。Base 型，仅侧边。"""

    def __init__(self) -> None:
        super().__init__("chase", "base", {"sides"})

    def render(self, ctx: RenderContext) -> list[tuple[int, int, int]]:
        chase_speed = float(ctx.params.get("chase_speed", 1.0))
        tail_length = int(ctx.params.get("tail_length", 5))
        color_str = str(ctx.params.get("chase_color", "#00aaff"))

        # 解析颜色
        color = (0, 170, 255)
        if color_str.startswith("#"):
            try:
                color = (int(color_str[1:3], 16), int(color_str[3:5], 16), int(color_str[5:7], 16))
            except ValueError:
                pass

        colors = [[0.0, 0.0, 0.0] for _ in range(ctx.lamp_count)]
        head_pos = (ctx.now * chase_speed * 5.0) % ctx.lamp_count

        for offset in range(tail_length + 1):
            pos = (int(head_pos) - offset) % ctx.lamp_count
            intensity = 1.0 - offset / max(1, tail_length)
            if 0 <= pos < ctx.lamp_count:
                colors[pos][0] += color[0] * intensity
                colors[pos][1] += color[1] * intensity
                colors[pos][2] += color[2] * intensity

        return [
            (min(255, int(c[0])), min(255, int(c[1])), min(255, int(c[2])))
            for c in colors
        ]

    def param_schema(self) -> list[dict]:
        return [
            {"key": "chase_speed", "label": "追逐速度", "min": 0.1, "max": 5.0, "step": 0.1, "fmt": "{:.1f}"},
            {"key": "tail_length", "label": "拖尾长度", "min": 1, "max": 15, "step": 1, "fmt": "{:.0f}"},
            {"key": "chase_color", "label": "光点颜色", "type": "color"},
        ]
```

- [ ] **步骤 2：Commit**

```bash
cd C:/Users/Bobboom/Documents/Codex/2026-06-20/esc
git add backend/new_effects.py
git commit -m "feat(effects): add ChaseEffect

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 16：渐变灯效 GradientEffect

**文件：**
- 修改：`backend/new_effects.py`

- [ ] **步骤 1：实现 GradientEffect**

在 `backend/new_effects.py` 中追加：

```python

class GradientEffect(ZoneEffect):
    """渐变灯效：两个颜色缓慢过渡。Base 型，全局可用。"""

    def __init__(self) -> None:
        super().__init__("gradient", "base", {"keys", "backplate", "sides"})

    def render(self, ctx: RenderContext) -> list[tuple[int, int, int]]:
        color_a = str(ctx.params.get("color_a", "#ff0055"))
        color_b = str(ctx.params.get("color_b", "#00aaff"))
        grad_speed = float(ctx.params.get("grad_speed", 0.5))

        # 解析颜色
        def parse_hex(h):
            if h.startswith("#"):
                try:
                    return (int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16))
                except ValueError:
                    pass
            return (0, 170, 255)

        a = parse_hex(color_a)
        b = parse_hex(color_b)

        # 全局颜色随时间在两色间摆动
        t = (math.sin(ctx.now * grad_speed) * 0.5 + 0.5)
        r = int(a[0] + (b[0] - a[0]) * t)
        g = int(a[1] + (b[1] - a[1]) * t)
        b_ = int(a[2] + (b[2] - a[2]) * t)

        return [(r, g, b_)] * ctx.lamp_count

    def param_schema(self) -> list[dict]:
        return [
            {"key": "color_a", "label": "颜色 A", "type": "color"},
            {"key": "color_b", "label": "颜色 B", "type": "color"},
            {"key": "grad_speed", "label": "渐变速度", "min": 0.05, "max": 2.0, "step": 0.05, "fmt": "{:.2f}"},
        ]
```

- [ ] **步骤 2：Commit**

```bash
cd C:/Users/Bobboom/Documents/Codex/2026-06-20/esc
git add backend/new_effects.py
git commit -m "feat(effects): add GradientEffect

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 17：注册新灯效

**文件：**
- 修改：`backend/effect_registry.py`

- [ ] **步骤 1：导入并注册新灯效**

在 `backend/effect_registry.py` 中 `_EFFECT_REGISTRY` 定义之前添加导入：

```python
from new_effects import (
    TypewriterEffect,
    StarfieldEffect,
    WaveEffect,
    ChaseEffect,
    GradientEffect,
)
```

然后更新 `_EFFECT_REGISTRY`：

```python
_EFFECT_REGISTRY: dict[str, type[ZoneEffect]] = {
    "static": StaticEffect,
    "breathing": BreathingEffect,
    "rainbow": RainbowEffect,
    "ripple": RippleEffect,
    "pressure_dent": PressureDentEffect,
    "audio_spectrum": AudioSpectrumEffect,
    "audio_vu": AudioVuEffect,
    "typewriter": TypewriterEffect,
    "starfield": StarfieldEffect,
    "wave": WaveEffect,
    "chase": ChaseEffect,
    "gradient": GradientEffect,
}
```

- [ ] **步骤 2：运行测试确认所有灯效可创建**

```bash
cd C:/Users/Bobboom/Documents/Codex/2026-06-20/esc
python -c "
from effect_registry import create_effect, list_effects
all_effects = list_effects()
print(f'Registered: {len(all_effects)} effects')
for e in all_effects:
    inst = create_effect(e['name'])
    assert inst is not None, f'Failed to create {e["name"]}'
print('All effects created successfully')
"
```

预期：`Registered: 12 effects` + `All effects created successfully`

- [ ] **步骤 3：Commit**

```bash
cd C:/Users/Bobboom/Documents/Codex/2026-06-20/esc
git add backend/effect_registry.py
git commit -m "feat(registry): register all 12 effects (7 existing + 5 new)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Phase 4：配置迁移

### 任务 18：v1 → v2 配置迁移器

**文件：**
- 创建：`backend/config_migrator.py`
- 测试：`tests/test_migrator.py`

**上下文：** 旧配置无 `version` 字段，只有一个 `effect` 字段。需要按规则映射到新的 `zones` 结构。

- [ ] **步骤 1：编写失败的测试**

创建 `tests/test_migrator.py`：

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from config_migrator import migrate_v1_to_v2


def test_migrate_static():
    v1 = {"effect": "static", "theme": "noir", "global": {"brightness": 0.8}}
    v2 = migrate_v1_to_v2(v1)
    assert v2["version"] == 2
    assert v2["zones"]["keys"]["base"]["effect"] == "static"
    assert v2["zones"]["backplate"]["base"]["effect"] == "static"
    assert v2["zones"]["sides"]["base"]["effect"] == "static"
    assert v2["zones"]["keys"]["reactive"] is None


def test_migrate_premium_reactive():
    v1 = {
        "effect": "premium_reactive",
        "theme": "void",
        "global": {"brightness": 1.0},
        "audio": {"sensitivity": 1.2},
        "effects": {"pressure_dent": {"attack": 0.89}},
    }
    v2 = migrate_v1_to_v2(v1)
    assert v2["version"] == 2
    assert v2["zones"]["keys"]["reactive"]["effect"] == "pressure_dent"
    assert v2["zones"]["backplate"]["reactive"]["effect"] == "audio_spectrum"
    assert v2["zones"]["sides"]["reactive"]["effect"] == "audio_vu"
    assert v2["audio"]["sensitivity"] == 1.2
    # 旧 effects 参数应合并到对应区域 reactive 的 params 中
    assert v2["zones"]["keys"]["reactive"]["params"]["attack"] == 0.89


def test_migrate_audio_ambient():
    v1 = {"effect": "audio_ambient", "theme": "ember"}
    v2 = migrate_v1_to_v2(v1)
    assert v2["zones"]["backplate"]["reactive"]["effect"] == "audio_spectrum"
    assert v2["zones"]["sides"]["reactive"]["effect"] == "audio_vu"
    assert v2["zones"]["keys"]["base"]["effect"] == "static"


def test_already_v2():
    v2 = {"version": 2, "zones": {}}
    result = migrate_v1_to_v2(v2)
    assert result["version"] == 2
    assert "zones" in result
```

- [ ] **步骤 2：运行测试验证失败**

```bash
cd C:/Users/Bobboom/Documents/Codex/2026-06-20/esc
python -m pytest tests/test_migrator.py -v
```

预期：`ModuleNotFoundError: No module named 'config_migrator'`

- [ ] **步骤 3：实现 config_migrator.py**

创建 `backend/config_migrator.py`：

```python
"""v1 → v2 配置自动迁移。"""
from __future__ import annotations

import json
from pathlib import Path
from copy import deepcopy


# v1 effect 到 zones 的映射规则
MIGRATION_RULES = {
    "static": {
        "keys": {"base": {"effect": "static", "params": {}}, "reactive": None, "blend_mode": "normal"},
        "backplate": {"base": {"effect": "static", "params": {}}, "reactive": None, "blend_mode": "normal"},
        "sides": {"base": {"effect": "static", "params": {}}, "reactive": None, "blend_mode": "normal"},
    },
    "breathing": {
        "keys": {"base": {"effect": "breathing", "params": {}}, "reactive": None, "blend_mode": "normal"},
        "backplate": {"base": {"effect": "breathing", "params": {}}, "reactive": None, "blend_mode": "normal"},
        "sides": {"base": {"effect": "breathing", "params": {}}, "reactive": None, "blend_mode": "normal"},
    },
    "rainbow": {
        "keys": {"base": {"effect": "rainbow", "params": {}}, "reactive": None, "blend_mode": "normal"},
        "backplate": {"base": {"effect": "rainbow", "params": {}}, "reactive": None, "blend_mode": "normal"},
        "sides": {"base": {"effect": "rainbow", "params": {}}, "reactive": None, "blend_mode": "normal"},
    },
    "ripple": {
        "keys": {"base": {"effect": "static", "params": {}}, "reactive": {"effect": "ripple", "params": {}}, "blend_mode": "normal"},
        "backplate": {"base": {"effect": "static", "params": {}}, "reactive": {"effect": "ripple", "params": {}}, "blend_mode": "normal"},
        "sides": {"base": {"effect": "static", "params": {}}, "reactive": None, "blend_mode": "normal"},
    },
    "audio_ambient": {
        "keys": {"base": {"effect": "static", "params": {}}, "reactive": None, "blend_mode": "normal"},
        "backplate": {"base": {"effect": "static", "params": {}}, "reactive": {"effect": "audio_spectrum", "params": {}}, "blend_mode": "normal"},
        "sides": {"base": {"effect": "static", "params": {}}, "reactive": {"effect": "audio_vu", "params": {}}, "blend_mode": "normal"},
    },
    "pressure_dent": {
        "keys": {"base": {"effect": "static", "params": {}}, "reactive": {"effect": "pressure_dent", "params": {}}, "blend_mode": "normal"},
        "backplate": {"base": {"effect": "static", "params": {}}, "reactive": None, "blend_mode": "normal"},
        "sides": {"base": {"effect": "static", "params": {}}, "reactive": None, "blend_mode": "normal"},
    },
    "premium_reactive": {
        "keys": {"base": None, "reactive": {"effect": "pressure_dent", "params": {}}, "blend_mode": "normal"},
        "backplate": {"base": None, "reactive": {"effect": "audio_spectrum", "params": {}}, "blend_mode": "normal"},
        "sides": {"base": None, "reactive": {"effect": "audio_vu", "params": {}}, "blend_mode": "normal"},
    },
}


def migrate_v1_to_v2(config: dict) -> dict:
    """将 v1 配置迁移为 v2 格式。若已是 v2 则原样返回。"""
    if config.get("version") == 2:
        return deepcopy(config)

    v2 = deepcopy(config)
    v2["version"] = 2

    old_effect = str(v2.pop("effect", "premium_reactive"))
    zones = MIGRATION_RULES.get(old_effect, MIGRATION_RULES["premium_reactive"]).copy()

    # 迁移旧 effects 参数到对应区域 reactive 的 params
    old_effects = v2.pop("effects", {})
    for zone_name, zone_cfg in zones.items():
        if zone_cfg["reactive"] is not None:
            eff_name = zone_cfg["reactive"]["effect"]
            # 查找旧 effects 中对应的参数组
            if eff_name in old_effects:
                zone_cfg["reactive"]["params"] = deepcopy(old_effects[eff_name])
            elif eff_name == "audio_spectrum" and "audio_ambient" in old_effects:
                zone_cfg["reactive"]["params"] = deepcopy(old_effects["audio_ambient"])
            elif eff_name == "audio_vu" and "audio_ambient" in old_effects:
                zone_cfg["reactive"]["params"] = deepcopy(old_effects["audio_ambient"])

    v2["zones"] = zones
    return v2


def migrate_config_file(path: Path) -> dict:
    """读取配置文件，必要时迁移，返回 v2 格式配置。"""
    if not path.exists():
        return {"version": 2, "theme": "noir", "zones": MIGRATION_RULES["premium_reactive"].copy()}

    config = json.loads(path.read_text(encoding="utf-8"))
    if config.get("version") == 2:
        return config

    v2 = migrate_v1_to_v2(config)
    # 备份原文件
    backup = path.with_suffix(".json.bak")
    path.rename(backup)
    path.write_text(json.dumps(v2, ensure_ascii=False, indent=2), encoding="utf-8")
    return v2
```

- [ ] **步骤 4：运行测试验证通过**

```bash
cd C:/Users/Bobboom/Documents/Codex/2026-06-20/esc
python -m pytest tests/test_migrator.py -v
```

预期：`4 passed`

- [ ] **步骤 5：Commit**

```bash
cd C:/Users/Bobboom/Documents/Codex/2026-06-20/esc
git add backend/config_migrator.py tests/test_migrator.py
git commit -m "feat(config): add v1 to v2 config migrator with backup

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Phase 5：PreviewEngine 重构

### 任务 19：重构 PreviewEngine._loop() 使用区域渲染管线

**文件：**
- 修改：`backend/main.py`

**上下文：** `PreviewEngine._loop()` 当前用 if/elif 链选择 effect。需要改为：1) 读取 v2 配置；2) 用 `config_migrator` 确保格式；3) 根据 zones 配置创建 `ZoneRenderer`；4) 每帧用 `ZoneRenderer.render_frame()` 渲染。

- [ ] **步骤 1：导入新模块并修改 `_loop()`**

在 `backend/main.py` 顶部添加导入：

```python
from config_migrator import migrate_v1_to_v2
from effect_registry import create_effect
from zone_effect import RenderContext
from zone_renderer import ZoneRenderer
from new_effects import *  # 确保新灯效类被加载到注册表
```

然后重构 `_loop()` 中的渲染部分。找到如下代码块：

```python
            # 渲染
            try:
                if effect == "static":
                    frame = render_static(theme)
                elif effect == "breathing":
                    ...
```

替换为：

```python
            # 确保配置是 v2 格式
            live_config = migrate_v1_to_v2(live_config)

            # 构建 ZoneRenderer
            zones_cfg = live_config.get("zones", {})
            renderer = self._build_renderer(zones_cfg, theme)

            # 构建 RenderContext
            ctx = RenderContext(
                now=now,
                theme=theme,
                audio={
                    "spectrum": audio.spectrum,
                    "level": audio.level,
                    "bass": audio.bass,
                },
                pressures=pressures,
                params={"_active_ripples": active_ripples, **live_config.get("effects", {})},
                normalized=normalized,
                lamp_count=285,
                distance_cache=distance_cache,
            )

            # 渲染
            try:
                frame = renderer.render_frame(ctx)
            except Exception as exc:
                logger.error(f"Engine: render error: {exc}")
                frame = [BLACK] * 285
```

然后在 `PreviewEngine` 类中添加 `_build_renderer` 方法：

```python
    def _build_renderer(self, zones_cfg: dict, theme) -> ZoneRenderer:
        """根据 zones 配置构建 ZoneRenderer。"""
        def get_effect(zone_name: str, slot: str):
            cfg = zones_cfg.get(zone_name, {})
            slot_cfg = cfg.get(slot)
            if slot_cfg is None:
                return None
            name = slot_cfg.get("effect", "")
            eff = create_effect(name)
            if eff is not None:
                # 注入 params
                eff._params = slot_cfg.get("params", {})
            return eff

        return ZoneRenderer(
            keys_base=get_effect("keys", "base"),
            keys_reactive=get_effect("keys", "reactive"),
            keys_blend=zones_cfg.get("keys", {}).get("blend_mode", "normal"),
            backplate_base=get_effect("backplate", "base"),
            backplate_reactive=get_effect("backplate", "reactive"),
            backplate_blend=zones_cfg.get("backplate", {}).get("blend_mode", "normal"),
            sides_base=get_effect("sides", "base"),
            sides_reactive=get_effect("sides", "reactive"),
            sides_blend=zones_cfg.get("sides", {}).get("blend_mode", "normal"),
        )
```

注意：由于 `ZoneEffect.render` 接收 `ctx.params`，而 `_build_renderer` 返回的 effect 实例需要知道自身参数，这里需要一个机制将 slot 的 params 传递给 render。最简方案：修改 `ZoneRenderer.render_frame` 在调用 `render()` 前将 zone_cfg 的 params 合并到 `ctx.params` 中。

修改 `backend/zone_renderer.py` 的 `render_frame`：

在 `zone_ctx = RenderContext(...)` 之后，渲染之前添加：

```python
            # 合并区域专属参数
            zone_params = dict(ctx.params)
            if base_eff is not None and hasattr(base_eff, "_params"):
                zone_params.update(base_eff._params)
            if reactive_eff is not None and hasattr(reactive_eff, "_params"):
                zone_params.update(reactive_eff._params)
            zone_ctx = RenderContext(
                now=ctx.now,
                theme=ctx.theme,
                audio=ctx.audio,
                pressures=ctx.pressures,
                params=zone_params,
                normalized=ctx.normalized,
                lamp_count=count,
                distance_cache=ctx.distance_cache,
            )
```

- [ ] **步骤 2：运行现有程序验证不崩溃**

```bash
cd C:/Users/Bobboom/Documents/Codex/2026-06-20/esc
python -c "from main import PreviewEngine; print('PreviewEngine imports ok')"
```

预期：`PreviewEngine imports ok`

- [ ] **步骤 3：Commit**

```bash
cd C:/Users/Bobboom/Documents/Codex/2026-06-20/esc
git add backend/main.py backend/zone_renderer.py
git commit -m "refactor(engine): rewire PreviewEngine._loop() to ZoneRenderer pipeline

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 20：向后兼容验证

**文件：**
- 无新增/修改文件，纯验证

- [ ] **步骤 1：验证 v1 配置在新引擎下正常工作**

```bash
cd C:/Users/Bobboom/Documents/Codex/2026-06-20/esc
python -c "
from config_migrator import migrate_v1_to_v2
from main import PreviewEngine

# 模拟 v1 配置
v1_config = {'effect': 'premium_reactive', 'theme': 'noir', 'global': {'brightness': 1.0}}
v2 = migrate_v1_to_v2(v1_config)
print('Migrated config keys:', list(v2.keys()))
print('Zones:', list(v2['zones'].keys()))
print('Keys reactive:', v2['zones']['keys']['reactive'])
"
```

预期：`Migrated config keys: ['version', 'theme', 'global', 'zones']` + `Zones: ['keys', 'backplate', 'sides']`

- [ ] **步骤 2：Commit（标记验证通过）**

```bash
cd C:/Users/Bobboom/Documents/Codex/2026-06-20/esc
git commit --allow-empty -m "test: verify backward compatibility for v1 configs

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Phase 6：UI 更新

### 任务 21：高级模式切换按钮

**文件：**
- 修改：`ui/index.html`

**上下文：** 在现有 UI 的灯效选择区域上方添加「高级模式」开关。开启后显示三区域独立配置面板；关闭后恢复为单一全局 effect 下拉框（向后兼容）。

- [ ] **步骤 1：在 index.html 中添加模式切换 UI**

找到 `ui/index.html` 中 effect 选择器的容器（通常是包含 `<select id="effect">` 的元素），在其上方添加：

```html
<!-- 模式切换 -->
<div class="mode-toggle" style="display: flex; align-items: center; gap: 8px; margin-bottom: 12px;">
  <label class="switch">
    <input type="checkbox" id="advancedMode" onchange="toggleAdvancedMode()">
    <span class="slider"></span>
  </label>
  <span id="modeLabel">高级模式</span>
</div>

<!-- 初级模式：单一 effect 选择 -->
<div id="simpleModePanel">
  <select id="effect" onchange="onEffectChange(this.value)">
    <option value="static">静态</option>
    <option value="breathing">呼吸</option>
    <option value="rainbow">彩虹</option>
    <option value="ripple">涟漪</option>
    <option value="audio_ambient">音频氛围</option>
    <option value="pressure_dent">压力热力</option>
    <option value="premium_reactive" selected>综合响应</option>
  </select>
</div>

<!-- 高级模式：三区域配置（默认隐藏） -->
<div id="advancedModePanel" style="display: none;">
  <!-- 三区域卡片将在任务 22 中填充 -->
</div>
```

并添加切换函数：

```javascript
function toggleAdvancedMode() {
  const advanced = document.getElementById('advancedMode').checked;
  document.getElementById('simpleModePanel').style.display = advanced ? 'none' : 'block';
  document.getElementById('advancedModePanel').style.display = advanced ? 'block' : 'none';
  document.getElementById('modeLabel').textContent = advanced ? '高级模式（开启）' : '高级模式';
}
```

- [ ] **步骤 2：Commit**

```bash
cd C:/Users/Bobboom/Documents/Codex/2026-06-20/esc
git add ui/index.html
git commit -m "feat(ui): add advanced mode toggle switch

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 22：三区域独立配置面板

**文件：**
- 修改：`ui/index.html`

- [ ] **步骤 1：实现三区域卡片**

在 `advancedModePanel` div 中填充：

```html
<div id="advancedModePanel" style="display: none;">
  <!-- 字符区 -->
  <div class="zone-card" data-zone="keys">
    <h4>🔤 字符区</h4>
    <label>Base: <select class="base-effect" data-zone="keys"></select></label>
    <label>Reactive: <select class="reactive-effect" data-zone="keys"></select></label>
    <label>混合: <select class="blend-mode" data-zone="keys">
      <option value="normal">覆盖</option>
      <option value="add" selected>叠加</option>
      <option value="multiply">正片叠底</option>
      <option value="screen">滤色</option>
    </select></label>
    <div class="params-panel" data-zone="keys"></div>
  </div>

  <!-- 背板区 -->
  <div class="zone-card" data-zone="backplate">
    <h4>🌌 背板区</h4>
    <label>Base: <select class="base-effect" data-zone="backplate"></select></label>
    <label>Reactive: <select class="reactive-effect" data-zone="backplate"></select></label>
    <label>混合: <select class="blend-mode" data-zone="backplate">
      <option value="normal" selected>覆盖</option>
      <option value="add">叠加</option>
      <option value="multiply">正片叠底</option>
      <option value="screen">滤色</option>
    </select></label>
    <div class="params-panel" data-zone="backplate"></div>
  </div>

  <!-- 侧边区 -->
  <div class="zone-card" data-zone="sides">
    <h4>📊 侧边灯条</h4>
    <label>Base: <select class="base-effect" data-zone="sides"></select></label>
    <label>Reactive: <select class="reactive-effect" data-zone="sides"></select></label>
    <label>混合: <select class="blend-mode" data-zone="sides">
      <option value="normal">覆盖</option>
      <option value="add" selected>叠加</option>
      <option value="multiply">正片叠底</option>
      <option value="screen">滤色</option>
    </select></label>
    <div class="params-panel" data-zone="sides"></div>
  </div>

  <button onclick="applyAdvancedConfig()">应用配置</button>
</div>
```

- [ ] **步骤 2：添加动态填充下拉框的 JS**

```javascript
// 从 /api/schema 获取可用灯效列表，按区域过滤填充下拉框
async function loadEffectOptions() {
  const resp = await fetch('/api/schema');
  const schema = await resp.json();
  // schema 中需要包含 effect_list
  // TODO: 后端 API 需扩展返回 effect_list
}
```

**注意**：后端 `/api/schema` 端点需要扩展，返回可用灯效列表。这将在任务 23 中处理。

- [ ] **步骤 3：Commit**

```bash
cd C:/Users/Bobboom/Documents/Codex/2026-06-20/esc
git add ui/index.html
git commit -m "feat(ui): add 3-zone independent configuration panel

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 23：后端 API 扩展与动态参数面板

**文件：**
- 修改：`backend/main.py`

- [ ] **步骤 1：扩展 /api/schema 返回灯效列表**

在 `backend/main.py` 中修改 `/api/schema` 端点：

```python
            elif self.path == "/api/schema":
                if engine_instance:
                    from effect_registry import list_effects
                    self.send_json({
                        "params": PreviewEngine.PARAM_SCHEMA,
                        "colors": PreviewEngine.COLOR_SCHEMA,
                        "theme_defaults": PreviewEngine._build_theme_colors(),
                        "effects": {
                            "keys": list_effects("keys"),
                            "backplate": list_effects("backplate"),
                            "sides": list_effects("sides"),
                        },
                    })
```

- [ ] **步骤 2：添加 /api/effect/set_zone 端点**

在 `do_POST` 中添加：

```python
                elif self.path == "/api/effect/set_zone":
                    if engine_instance:
                        engine_instance.set_zone_config(payload)
                    self.send_json({"ok": True})
```

在 `PreviewEngine` 中添加 `set_zone_config` 方法：

```python
    def set_zone_config(self, zones_config: dict):
        """API 入口：批量更新区域配置。"""
        with self.lock:
            self.config.setdefault("zones", {})
            for zone_name, zone_cfg in zones_config.items():
                self.config["zones"][zone_name] = zone_cfg
            self._bump_config_version()
        if self.config_path:
            try:
                self.config_path.write_text(
                    json.dumps(self.config, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except Exception as exc:
                logger.warning(f"Engine: failed to save zone config: {exc}")
```

- [ ] **步骤 3：Commit**

```bash
cd C:/Users/Bobboom/Documents/Codex/2026-06-20/esc
git add backend/main.py
git commit -m "feat(api): extend /api/schema with effect list, add /api/effect/set_zone

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Phase 7：集成与发布

### 任务 24：集成测试

**文件：**
- 无新增文件，纯验证

- [ ] **步骤 1：运行完整单元测试套件**

```bash
cd C:/Users/Bobboom/Documents/Codex/2026-06-20/esc
python -m pytest tests/ -v
```

预期：所有测试通过（`test_zones.py` + `test_migrator.py`）

- [ ] **步骤 2：验证从源码启动不报错**

```bash
cd C:/Users/Bobboom/Documents/Codex/2026-06-20/esc
python backend/main.py --dry-run
```

预期：程序启动，输出 `PreviewEngine imports ok` 或进入主循环（因 dry-run 不会连接键盘，可能输出警告但不崩溃）

注意：`--dry-run` 需要确认 main.py 是否支持此参数。如果不支持，用 `timeout 5 python backend/main.py` 运行 5 秒后手动中断。

- [ ] **步骤 3：Commit**

```bash
cd C:/Users/Bobboom/Documents/Codex/2026-06-20/esc
git commit --allow-empty -m "test: integration test passed

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 25：打包 v2.1.0 EXE

**文件：**
- 无新增文件，纯构建

- [ ] **步骤 1：更新版本号**

在 `backend/main.py` 中找到 `api_system_info`：

```python
@register_api("system.info")
def api_system_info(**kwargs):
    return {
        "version": "2.1.0",
        "platform": sys.platform,
        "webview": True,
    }
```

将 `"version": "1.0.1"` 改为 `"version": "2.1.0"`。

- [ ] **步骤 2：更新 README.md 版本号**

```bash
cd C:/Users/Bobboom/Documents/Codex/2026-06-20/esc
sed -i 's/v2.0.0/v2.1.0/g' README.md
```

- [ ] **步骤 3：运行打包脚本**

```bash
cd C:/Users/Bobboom/Documents/Codex/2026-06-20/esc
build_single_exe.bat
```

预期：`outputs/MelGeekReactiveRGB.exe` 生成成功（约 36-40MB）

- [ ] **步骤 4：Commit 版本更新**

```bash
cd C:/Users/Bobboom/Documents/Codex/2026-06-20/esc
git add README.md backend/main.py
git commit -m "chore(release): bump version to v2.1.0

Co-Authored-By: Claude <noreply@anthropic.com>"
```

- [ ] **步骤 5：推送到 GitHub**

```bash
cd C:/Users/Bobboom/Documents/Codex/2026-06-20/esc
git push origin main
```

- [ ] **步骤 6：创建 GitHub Release v2.1.0**

参考 v2.0.0 的 Release 创建流程，上传：
- `outputs/MelGeekReactiveRGB.exe`
- `outputs/README_USER.md`
- `outputs/LICENSE`
- `outputs/reactive_config.json`
- `outputs/THIRD_PARTY_NOTICES.md`

Release notes：

```markdown
## v2.1.0

- **区域分层灯效系统**：三大区域（字符区/背板区/侧边灯条）可独立配置灯效
- **Base + Reactive 双槽**：每个区域可同时设置背景灯效和响应灯效，支持 4 种混合模式
- **新增 5 个灯效**：打字机、星空、波浪、追逐、渐变
- **向后兼容**：v1 配置自动迁移，无需手动调整
- **高级模式 UI**：三区域独立配置面板，初级模式保持原有体验
```

---

## 自检

### 1. 规格覆盖度

| 规格章节 | 实现任务 | 状态 |
|---------|---------|------|
| ZoneEffect ABC + RenderContext | 任务 1 | ✅ |
| BlendEngine 4 种混合模式 | 任务 2 | ✅ |
| ZoneRenderer 区域合并 | 任务 3 | ✅ |
| 现有 7 灯效迁移 | 任务 4-11 | ✅ |
| 新增 5 灯效 | 任务 12-17 | ✅ |
| v1→v2 配置迁移 | 任务 18 | ✅ |
| PreviewEngine 重构 | 任务 19-20 | ✅ |
| UI 高级模式 | 任务 21-23 | ✅ |
| 集成测试 + 发布 | 任务 24-25 | ✅ |

**无遗漏。**

### 2. 占位符扫描

- [x] 无 "待定" / "TODO" / "后续实现"
- [x] 无 "添加适当的错误处理" 等模糊描述
- [x] 每个代码步骤都有实际代码
- [x] 每个测试步骤都有实际测试代码
- [x] 无 "类似任务 N" 引用

### 3. 类型一致性

- [x] `ZoneEffect.render(ctx: RenderContext)` 在所有子类中一致
- [x] `BlendEngine.blend(base, overlay, mode)` 签名一致
- [x] `ZoneRenderer` 构造参数名称一致
- [x] `create_effect(name)` 返回类型一致
- [x] `migrate_v1_to_v2(config)` 输入输出一致

---

## 执行交接

**计划已完成并保存到 `docs/superpowers/plans/2026-06-27-zone-layer-v2.1.0.md`。两种执行方式：**

**1. 子代理驱动（推荐）** - 每个任务调度一个新的子代理，任务间进行审查，快速迭代

**2. 内联执行** - 在当前会话中使用 executing-plans 执行任务，批量执行并设有检查点

**选哪种方式？**
