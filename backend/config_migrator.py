"""v1 → v2 配置自动迁移。"""
from __future__ import annotations

import json
from pathlib import Path
from copy import deepcopy


# v1 effect 到 zones 的映射规则
MIGRATION_RULES = {
    "static": {
        "keys": {"base": {"effect": "static", "params": {}}, "reactive": None, "blend_mode": "normal"},
        "backplate": {"base": {"effect": "static", "params": {}}, "reactive": None, "blend_mode": "normal"},
        "sides": {"base": {"effect": "static", "params": {}}, "reactive": None, "blend_mode": "normal"},
    },
    "breathing": {
        "keys": {"base": {"effect": "breathing", "params": {}}, "reactive": None, "blend_mode": "normal"},
        "backplate": {"base": {"effect": "breathing", "params": {}}, "reactive": None, "blend_mode": "normal"},
        "sides": {"base": {"effect": "breathing", "params": {}}, "reactive": None, "blend_mode": "normal"},
    },
    "rainbow": {
        "keys": {"base": {"effect": "rainbow", "params": {}}, "reactive": None, "blend_mode": "normal"},
        "backplate": {"base": {"effect": "rainbow", "params": {}}, "reactive": None, "blend_mode": "normal"},
        "sides": {"base": {"effect": "rainbow", "params": {}}, "reactive": None, "blend_mode": "normal"},
    },
    "ripple": {
        "keys": {"base": {"effect": "static", "params": {}}, "reactive": {"effect": "ripple", "params": {}}, "blend_mode": "normal"},
        "backplate": {"base": {"effect": "static", "params": {}}, "reactive": {"effect": "ripple", "params": {}}, "blend_mode": "normal"},
        "sides": {"base": {"effect": "static", "params": {}}, "reactive": None, "blend_mode": "normal"},
    },
    "audio_ambient": {
        "keys": {"base": {"effect": "static", "params": {}}, "reactive": None, "blend_mode": "normal"},
        "backplate": {"base": {"effect": "static", "params": {}}, "reactive": {"effect": "audio_spectrum", "params": {}}, "blend_mode": "normal"},
        "sides": {"base": {"effect": "static", "params": {}}, "reactive": {"effect": "audio_vu", "params": {}}, "blend_mode": "normal"},
    },
    "pressure_dent": {
        "keys": {"base": {"effect": "static", "params": {}}, "reactive": {"effect": "pressure_dent", "params": {}}, "blend_mode": "normal"},
        "backplate": {"base": {"effect": "static", "params": {}}, "reactive": None, "blend_mode": "normal"},
        "sides": {"base": {"effect": "static", "params": {}}, "reactive": None, "blend_mode": "normal"},
    },
    "premium_reactive": {
        "keys": {"base": None, "reactive": {"effect": "pressure_dent", "params": {}}, "blend_mode": "normal"},
        "backplate": {"base": None, "reactive": {"effect": "audio_spectrum", "params": {}}, "blend_mode": "normal"},
        "sides": {"base": None, "reactive": {"effect": "audio_vu", "params": {}}, "blend_mode": "normal"},
    },
}


def migrate_v1_to_v2(config: dict) -> dict:
    """将 v1 配置迁移为 v2 格式。若已是 v2 则原样返回。"""
    if config.get("version") == 2:
        return deepcopy(config)

    v2 = deepcopy(config)
    v2["version"] = 2

    old_effect = str(v2.pop("effect", "premium_reactive"))
    zones = deepcopy(MIGRATION_RULES.get(old_effect, MIGRATION_RULES["premium_reactive"]))

    # 迁移旧 effects 参数到对应区域 reactive 的 params
    old_effects = v2.pop("effects", {})
    for zone_name, zone_cfg in zones.items():
        if zone_cfg["reactive"] is not None:
            eff_name = zone_cfg["reactive"]["effect"]
            # 查找旧 effects 中对应的参数组
            if eff_name in old_effects:
                zone_cfg["reactive"]["params"] = deepcopy(old_effects[eff_name])
            elif eff_name == "audio_spectrum" and "audio_ambient" in old_effects:
                zone_cfg["reactive"]["params"] = deepcopy(old_effects["audio_ambient"])
            elif eff_name == "audio_vu" and "audio_ambient" in old_effects:
                zone_cfg["reactive"]["params"] = deepcopy(old_effects["audio_ambient"])

    v2["zones"] = zones
    return v2


def migrate_config_file(path: Path) -> dict:
    """读取配置文件，必要时迁移，返回 v2 格式配置。"""
    if not path.exists():
        return {"version": 2, "theme": "noir", "zones": deepcopy(MIGRATION_RULES["premium_reactive"])}

    config = json.loads(path.read_text(encoding="utf-8"))
    if config.get("version") == 2:
        return config

    v2 = migrate_v1_to_v2(config)
    # 备份原文件
    backup = path.with_suffix(".json.bak")
    path.rename(backup)
    path.write_text(json.dumps(v2, ensure_ascii=False, indent=2), encoding="utf-8")
    return v2
