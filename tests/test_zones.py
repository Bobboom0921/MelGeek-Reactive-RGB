import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import pytest
from zone_effect import ZoneEffect, RenderContext
from blend_engine import BlendEngine


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
    # screen(a,b) = 255 - (255-a)*(255-b)//255
    # result[0]: base=(128,0,0), overlay=(128,128,0)
    #   r: 255 - 127*127//255 = 255 - 63 = 192
    #   g: 255 - 255*127//255 = 255 - 127 = 128
    #   b: 255 - 255*255//255 = 255 - 255 = 0
    # result[1]: base=(0,128,0), overlay=(128,0,128)
    #   r: 255 - 255*127//255 = 255 - 127 = 128
    #   g: 255 - 127*255//255 = 255 - 127 = 128
    #   b: 255 - 255*127//255 = 255 - 127 = 128
    assert result[0] == (192, 128, 0)
    assert result[1] == (128, 128, 128)


def test_blend_invalid_mode():
    with pytest.raises(ValueError):
        BlendEngine.blend([(0, 0, 0)], [(0, 0, 0)], "invalid")


def test_blend_length_mismatch():
    with pytest.raises(ValueError):
        BlendEngine.blend([(0, 0, 0)], [(0, 0, 0), (0, 0, 0)], "normal")
