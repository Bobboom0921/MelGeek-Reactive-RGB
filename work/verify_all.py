from __future__ import annotations

import ast
import json
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "work"
sys.path.insert(0, str(WORK))

hid_mock = types.ModuleType("hid")
hid_mock.enumerate = lambda *args, **kwargs: []
hid_mock.device = object
sys.modules.setdefault("hid", hid_mock)

FILES = [
    WORK / "melgeek68_premium_reactive.py",
    WORK / "reactive_control_panel_modern.py",
    WORK / "melgeek68_direct_hid.py",
    WORK / "melgeek_native_pressure_probe.py",
    WORK / "melgeek_local_webhid_pressure_server.py",
    WORK / "scan_loopback_devices.py",
]


def check_syntax() -> None:
    for path in FILES:
        ast.parse(path.read_text(encoding="utf-8"))
        print(f"OK syntax {path.name}")


def check_config() -> dict:
    config_path = ROOT / "reactive_config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    for key in ["theme", "effect", "global", "audio", "effects", "colors", "startup"]:
        assert key in config, f"config missing {key}"
    for effect in ["rainbow", "ripple", "pressure_dent", "audio_ambient"]:
        assert effect in config["effects"], f"config.effects missing {effect}"
    print("OK config structure")
    return config


def check_core_renderers() -> None:
    import melgeek68_premium_reactive as core

    positions, lamp_count = core.load_params_from_cache()
    assert lamp_count == core.LAMP_COUNT
    normalized = core.normalize_positions(positions, core.LAMP_COUNT)
    distance_cache = core.build_distance_cache(normalized, core.KEY_LAMP_COUNT, core.LAMP_COUNT, max_radius=32)
    theme = core.theme_with_overrides(core.select_theme("noir"), {})
    audio_zero = core.AudioSnapshot([0.0] * core.BACKPLATE_COLUMNS, 0.0, 0.0)
    audio_hot = core.AudioSnapshot([0.1 + 0.7 * ((i % 11) / 10) for i in range(core.BACKPLATE_COLUMNS)], 0.45, 0.55)
    pressures = {31: 0.25, 36: 0.90, 61: 0.75}
    flashes = {36: 0.1}
    ripples = [core.ActiveRipple(36, 10.0, 0.85, 95.0, 2.0, 10.18, 0.7)]
    peak = [0.0] * core.BACKPLATE_COLUMNS
    now = 10.25
    frames = {
        "static": core.render_static(theme),
        "breathing": core.render_breathing(theme, now),
        "rainbow_diagonal": core.render_rainbow(theme, normalized, now, "diagonal", 1.0, 0.68, 0.62),
        "rainbow_horizontal": core.render_rainbow(theme, normalized, now, "horizontal", 1.0, 0.68, 0.62),
        "rainbow_vertical": core.render_rainbow(theme, normalized, now, "vertical", 1.0, 0.68, 0.62),
        "rainbow_radial": core.render_rainbow(theme, normalized, now, "radial", 1.0, 0.68, 0.62),
        "rainbow_dual": core.render_rainbow(theme, normalized, now, "dual", 1.0, 0.68, 0.62),
        "rainbow_pastel": core.render_rainbow(theme, normalized, now, "pastel", 1.0, 0.68, 0.62),
        "ripple": core.render_ripple_effect(theme, normalized, ripples, now, 1.0, 1.0),
        "audio_ambient_silent": core.render_audio_ambient(theme, audio_zero, peak, now, 1.0, 1.0, 1.0, 0.62, 1.0),
        "audio_ambient_hot": core.render_audio_ambient(theme, audio_hot, peak, now, 1.0, 1.0, 1.0, 0.62, 1.0),
        "premium": core.compose_frame(theme, normalized, distance_cache, pressures, flashes, audio_hot, peak, 16.0, now, 1.0, 1.0, 1.0, 0.22, 0.26, 0.62, 1.0),
    }
    pressure_frame = core.render_static(theme)
    core.render_keys(pressure_frame, theme, normalized, distance_cache, pressures, flashes, 0.0, 16.0, 0.22, 0.26)
    frames["pressure_dent"] = pressure_frame
    for name, frame in frames.items():
        assert isinstance(frame, list), name
        assert len(frame) == core.LAMP_COUNT, f"{name} length {len(frame)}"
        for rgb in frame:
            assert isinstance(rgb, tuple) and len(rgb) == 3, f"{name} bad tuple"
            assert all(isinstance(c, int) and 0 <= c <= 255 for c in rgb), f"{name} bad rgb {rgb}"
        print(f"OK frame {name}")


def check_imports() -> None:
    import melgeek_local_webhid_pressure_server  # noqa: F401
    import melgeek_native_pressure_probe  # noqa: F401
    import scan_loopback_devices  # noqa: F401
    try:
        import reactive_control_panel_modern  # noqa: F401
        print("OK import reactive_control_panel_modern")
    except ModuleNotFoundError as exc:
        print(f"SKIP modern GUI import dependency: {exc}")
    print("OK support imports")


def main() -> int:
    check_syntax()
    check_config()
    check_core_renderers()
    check_imports()
    print("ALL_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
