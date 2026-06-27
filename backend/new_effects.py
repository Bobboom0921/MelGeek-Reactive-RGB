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

    def param_schema(self) -> list[dict[str, Any]]:
        return [
            {"key": "wave_speed", "label": "扩散速度", "min": 0.5, "max": 3.0, "step": 0.1, "fmt": "{:.1f}"},
            {"key": "decay", "label": "衰减系数", "min": 0.5, "max": 0.95, "step": 0.01, "fmt": "{:.2f}"},
        ]
