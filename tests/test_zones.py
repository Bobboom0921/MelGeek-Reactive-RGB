import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import pytest
from zone_effect import ZoneEffect, RenderContext


def test_zone_effect_is_abstract():
    """ZoneEffect 不能直接实例化"""
    with pytest.raises(TypeError):
        ZoneEffect("test", "base", {"keys"})


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
    assert ctx.normalized == [(0.0, 0.0)]
    assert ctx.lamp_count == 70
    assert ctx.distance_cache is None
