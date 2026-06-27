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
        """
        初始化区域灯效。

        :param name: 灯效名称
        :param effect_type: 灯效类型，"base" 或 "reactive"
        :param applicable_zones: 该灯效可适用的区域集合
        """
        self.name = name
        self.effect_type = effect_type  # "base" 或 "reactive"
        self.applicable_zones = applicable_zones

    @abstractmethod
    def render(self, ctx: RenderContext) -> list[tuple[int, int, int]]:
        """
        渲染一帧。
        返回该区域所有灯珠的 RGB 值列表，长度必须等于 ctx.lamp_count。
        """

    def param_schema(self) -> list[dict[str, Any]]:
        """返回该灯效的 UI 参数定义。子类可覆盖。"""
        return []
