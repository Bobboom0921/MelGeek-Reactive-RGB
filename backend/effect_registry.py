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

    def param_schema(self) -> list[dict[str, Any]]:
        return [
            {"key": "speed", "label": "呼吸速度", "min": 0.2, "max": 3, "step": 0.05, "fmt": "{:.2f}"},
            {"key": "depth", "label": "呼吸幅度", "min": 0, "max": 1, "step": 0.02, "fmt": "{:.0%}"},
        ]


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

    def param_schema(self) -> list[dict[str, Any]]:
        return [
            {"key": "style", "label": "彩虹样式", "type": "select", "options": ["diagonal", "horizontal", "vertical", "radial", "dual", "pastel"]},
            {"key": "speed", "label": "流动速度", "min": 0.05, "max": 5, "step": 0.05, "fmt": "{:.2f}"},
            {"key": "saturation", "label": "色彩饱和度", "min": 0, "max": 1, "step": 0.02, "fmt": "{:.0%}"},
            {"key": "value", "label": "彩虹亮度", "min": 0, "max": 1, "step": 0.02, "fmt": "{:.0%}"},
        ]


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
        full = render_ripple_effect(theme, normalized, ripples, ctx.now, brightness, width_scale=width)
        if ctx.lamp_count == 70:
            return full[:70]
        elif ctx.lamp_count == 189:
            return full[70:259]
        else:
            return full[259:285]

    def param_schema(self) -> list[dict[str, Any]]:
        return [
            {"key": "brightness", "label": "涟漪亮度", "min": 0, "max": 3, "step": 0.05, "fmt": "{:.2f}"},
            {"key": "width", "label": "涟漪宽度", "min": 0.2, "max": 4, "step": 0.05, "fmt": "{:.2f}"},
        ]


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

    def param_schema(self) -> list[dict[str, Any]]:
        return [
            {"key": "radius", "label": "压力扩散", "min": 4, "max": 30, "step": 0.5, "fmt": "{:.1f}"},
            {"key": "color_floor", "label": "周边染色", "min": 0, "max": 1, "step": 0.01, "fmt": "{:.0%}"},
            {"key": "space_color_floor", "label": "空格染色", "min": 0, "max": 1, "step": 0.01, "fmt": "{:.0%}"},
        ]


class AudioSpectrumEffect(ZoneEffect):
    """背板音频频谱灯效（Reactive）。仅背板区。"""

    def __init__(self) -> None:
        super().__init__("audio_spectrum", "reactive", {"backplate"})

    def render(self, ctx: RenderContext) -> list[tuple[int, int, int]]:
        theme = _get_theme(str(ctx.theme))
        audio_data = ctx.audio or {"spectrum": [0.0] * 63, "level": 0.0, "bass": 0.0}
        full = [(0, 0, 0)] * 285
        # peak_hold 需要持久化状态，这里简化为空列表
        peak_hold = [0.0] * 63
        from melgeek68_premium_reactive import AudioSnapshot
        audio = AudioSnapshot(
            audio_data.get("spectrum", [0.0] * 63),
            audio_data.get("level", 0.0),
            audio_data.get("bass", 0.0),
        )
        ambience = float(ctx.params.get("ambience_strength", 1.0))
        shockwave = float(ctx.params.get("shockwave_strength", 1.0))
        motion = float(ctx.params.get("motion", 1.0))
        render_backplate(full, theme, audio, peak_hold, ctx.now, ambience, shockwave, motion)
        return full[70:259]

    def param_schema(self) -> list[dict[str, Any]]:
        return [
            {"key": "ambience_strength", "label": "背板氛围", "min": 0, "max": 3, "step": 0.05, "fmt": "{:.2f}"},
            {"key": "shockwave_strength", "label": "低频冲击", "min": 0, "max": 3, "step": 0.05, "fmt": "{:.2f}"},
            {"key": "motion", "label": "背板运动", "min": 0, "max": 2, "step": 0.05, "fmt": "{:.2f}"},
        ]
