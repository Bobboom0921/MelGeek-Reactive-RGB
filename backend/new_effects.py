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

    def param_schema(self) -> list[dict[str, Any]]:
        return [
            {"key": "density", "label": "星星密度", "min": 0.1, "max": 1.0, "step": 0.05, "fmt": "{:.2f}"},
            {"key": "speed", "label": "流星频率", "min": 0, "max": 1.0, "step": 0.05, "fmt": "{:.2f}"},
            {"key": "twinkle", "label": "闪烁幅度", "min": 0, "max": 1.0, "step": 0.05, "fmt": "{:.2f}"},
        ]


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

    def param_schema(self) -> list[dict[str, Any]]:
        return [
            {"key": "direction", "label": "方向", "type": "select", "options": ["horizontal", "vertical", "radial"]},
            {"key": "speed", "label": "传播速度", "min": 0.1, "max": 3.0, "step": 0.1, "fmt": "{:.1f}"},
            {"key": "frequency", "label": "波数", "min": 0.5, "max": 5.0, "step": 0.1, "fmt": "{:.1f}"},
            {"key": "amplitude", "label": "振幅", "min": 0, "max": 1.0, "step": 0.05, "fmt": "{:.2f}"},
        ]
