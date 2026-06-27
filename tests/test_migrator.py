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
