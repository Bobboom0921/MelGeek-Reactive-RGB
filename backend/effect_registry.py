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
