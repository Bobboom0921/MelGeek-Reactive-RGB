"""灯效混合模式引擎。"""
from __future__ import annotations


class BlendEngine:
    """提供多种 RGB 混合模式。所有输入为 RGB 元组组成的列表，每个通道为 0-255 整数。"""

    @staticmethod
    def blend(
        base: list[tuple[int, int, int]],
        overlay: list[tuple[int, int, int]],
        mode: str,
    ) -> list[tuple[int, int, int]]:
        """对两组 RGB 列表进行混合。

        参数:
            base: 底层 RGB 列表。
            overlay: 覆盖层 RGB 列表，必须与 base 等长。
            mode: 混合模式，支持 "normal"、"add"、"multiply"、"screen"。

        返回:
            混合后的 RGB 列表。

        异常:
            ValueError: 列表长度不匹配或 mode 不受支持。
        """
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
