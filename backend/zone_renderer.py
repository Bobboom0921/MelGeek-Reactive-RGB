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
                flashes=ctx.flashes,
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
