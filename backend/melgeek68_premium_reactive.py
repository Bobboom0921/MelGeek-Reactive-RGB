from __future__ import annotations

import argparse
import ctypes
import json
import math
import subprocess
import sys
import threading
import time
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))

from melgeek68_direct_hid import DirectHidSender, LAMP_COUNT
from melgeek_native_pressure_probe import (
    QUERY_PACKET,
    PressureNormalizer,
    choose_device,
    decode_pressure_report,
    open_device as open_pressure_device,
    send_init as send_pressure_init,
    write_command as write_pressure_command,
)

ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class LampPosition:
    lamp_id: int
    x: int
    y: int
    z: int


@dataclass
class ActiveRipple:
    key_id: int
    started_at: float
    strength: float
    max_radius: float
    duration: float
    charge_until: float
    hold_factor: float = 0.0


def load_params_from_cache() -> tuple[list[LampPosition], int]:
    base_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    candidates = [
        ROOT / "melgeek_keyboard_params.json",
        ROOT / "work" / "melgeek_keyboard_params.json",
        base_dir / "melgeek_keyboard_params.json",
        base_dir / "work" / "melgeek_keyboard_params.json",
        Path(__file__).resolve().parent / "melgeek_keyboard_params.json",
    ]
    path = next((candidate for candidate in candidates if candidate.exists()), None)
    if path is None:
        raise FileNotFoundError("melgeek_keyboard_params.json not found in: " + ", ".join(str(c) for c in candidates))
    data = json.loads(path.read_text(encoding="utf-8"))
    source = data.get("data", data)
    positions = [
        LampPosition(item["lampId"], item["x"], item["y"], item["z"])
        for item in source.get("lampPositions", [])
    ]
    positions.sort(key=lambda item: item.lamp_id)
    lamp_count = int(source.get("ledCount") or len(positions) or LAMP_COUNT)
    return positions, lamp_count

KEY_LAMP_COUNT = 70
REAR_TOP = range(70, 133)
REAR_MID = range(133, 196)
REAR_BOTTOM = range(196, 259)
LEFT_SIDE = range(259, 272)
RIGHT_SIDE = range(272, 285)
BACKPLATE_COLUMNS = 63
BLACK = (0, 0, 0)
SPACE_LAMP_IDS = (61, 62, 63)
SPACE_EFFECT_IDS = (60, 61, 62, 63, 64)

VK_TO_LAMP = {
    0x1B: 0,
    0x31: 1, 0x32: 2, 0x33: 3, 0x34: 4, 0x35: 5, 0x36: 6, 0x37: 7, 0x38: 8, 0x39: 9, 0x30: 10,
    0xBD: 11, 0xBB: 12, 0x08: 13, 0x24: 14,
    0x09: 15,
    0x51: 16, 0x57: 17, 0x45: 18, 0x52: 19, 0x54: 20, 0x59: 21, 0x55: 22, 0x49: 23, 0x4F: 24, 0x50: 25,
    0xDB: 26, 0xDD: 27, 0xDC: 28, 0x2E: 29,
    0x14: 30,
    0x41: 31, 0x53: 32, 0x44: 33, 0x46: 34, 0x47: 35, 0x48: 36, 0x4A: 37, 0x4B: 38, 0x4C: 39,
    0xBA: 40, 0xDE: 41, 0x0D: 42, 0x21: 43,
    0xA0: 44, 0x10: 44,
    0x5A: 45, 0x58: 46, 0x43: 47, 0x56: 48, 0x42: 49, 0x4E: 50, 0x4D: 51,
    0xBC: 52, 0xBE: 53, 0xBF: 54, 0xA1: 55, 0x26: 56, 0x22: 57,
    0xA2: 58, 0x11: 58, 0x5B: 59, 0x5C: 59, 0xA4: 60, 0x12: 60, 0x20: 61,
    0xA5: 64, 0xA3: 66, 0x25: 67, 0x28: 68, 0x27: 69,
}


@dataclass(frozen=True)
class Theme:
    name: str
    base_hsv: tuple[float, float, float]
    outer_base_hsv: tuple[float, float, float]
    dent_levels: tuple[tuple[float, tuple[float, float, float]], ...]
    outer_low_hsv: tuple[float, float, float]
    outer_high_hsv: tuple[float, float, float]
    bass_pulse_hsv: tuple[float, float, float]


THEMES: tuple[Theme, ...] = (
    Theme(
        name="Noir Cyberpunk",
        base_hsv=(250, 0.40, 0.25),
        outer_base_hsv=(248, 0.36, 0.10),
        dent_levels=(
            (0.08, (195, 0.54, 0.42)),
            (0.38, (292, 0.72, 0.68)),
            (1.00, (332, 0.88, 0.92)),
        ),
        outer_low_hsv=(330, 0.80, 0.70),
        outer_high_hsv=(190, 0.75, 0.78),
        bass_pulse_hsv=(330, 0.80, 0.70),
    ),
    Theme(
        name="Void Luxury",
        base_hsv=(0, 0.10, 0.18),
        outer_base_hsv=(35, 0.24, 0.09),
        dent_levels=(
            (0.08, (45, 0.48, 0.42)),
            (0.38, (34, 0.72, 0.68)),
            (1.00, (20, 0.92, 0.92)),
        ),
        outer_low_hsv=(38, 0.78, 0.74),
        outer_high_hsv=(210, 0.24, 0.70),
        bass_pulse_hsv=(42, 0.78, 0.78),
    ),
    Theme(
        name="Arctic Phantom",
        base_hsv=(210, 0.35, 0.22),
        outer_base_hsv=(210, 0.30, 0.10),
        dent_levels=(
            (0.08, (190, 0.46, 0.48)),
            (0.38, (172, 0.62, 0.72)),
            (1.00, (200, 0.34, 0.98)),
        ),
        outer_low_hsv=(220, 0.72, 0.50),
        outer_high_hsv=(185, 0.36, 0.96),
        bass_pulse_hsv=(200, 0.24, 0.98),
    ),
    Theme(
        name="Midnight Ember",
        base_hsv=(260, 0.25, 0.20),
        outer_base_hsv=(260, 0.30, 0.09),
        dent_levels=(
            (0.08, (30, 0.42, 0.42)),
            (0.38, (14, 0.66, 0.66)),
            (1.00, (0, 0.86, 0.88)),
        ),
        outer_low_hsv=(5, 0.78, 0.68),
        outer_high_hsv=(260, 0.72, 0.72),
        bass_pulse_hsv=(8, 0.88, 0.76),
    ),
    Theme(
        name="Pure Eclipse",
        base_hsv=(0, 0.00, 0.15),
        outer_base_hsv=(210, 0.08, 0.065),
        dent_levels=(
            (0.08, (210, 0.18, 0.42)),
            (0.38, (210, 0.14, 0.68)),
            (1.00, (200, 0.10, 0.98)),
        ),
        outer_low_hsv=(200, 0.28, 0.48),
        outer_high_hsv=(190, 0.18, 0.84),
        bass_pulse_hsv=(200, 0.20, 0.76),
    ),
)


def load_json_config(path: str | None) -> dict:
    if not path:
        return {}
    config_path = Path(path)
    if not config_path.exists():
        print(f"config: not found {config_path}, using defaults", flush=True)
        return {}
    try:
        return json.loads(config_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"config: failed to read {config_path}: {exc}", flush=True)
        return {}


def hsv_from_config(value, fallback: tuple[float, float, float]) -> tuple[float, float, float]:  # noqa: ANN001
    if isinstance(value, (list, tuple)) and len(value) == 3:
        try:
            return (float(value[0]), float(value[1]), float(value[2]))
        except (TypeError, ValueError):
            return fallback
    return fallback


def theme_with_overrides(theme: Theme, config: dict) -> Theme:
    colors = config.get("colors") or {}
    light_hsv = hsv_from_config(colors.get("press_light_hsv"), theme.dent_levels[0][1])
    mid_hsv = hsv_from_config(colors.get("press_mid_hsv"), theme.dent_levels[1][1])
    deep_hsv = hsv_from_config(colors.get("press_deep_hsv"), theme.dent_levels[2][1])
    return Theme(
        name=theme.name,
        base_hsv=hsv_from_config(colors.get("base_hsv"), theme.base_hsv),
        outer_base_hsv=hsv_from_config(colors.get("outer_base_hsv"), theme.outer_base_hsv),
        dent_levels=((theme.dent_levels[0][0], light_hsv), (theme.dent_levels[1][0], mid_hsv), (theme.dent_levels[2][0], deep_hsv)),
        outer_low_hsv=hsv_from_config(colors.get("outer_low_hsv"), theme.outer_low_hsv),
        outer_high_hsv=hsv_from_config(colors.get("outer_high_hsv"), theme.outer_high_hsv),
        bass_pulse_hsv=hsv_from_config(colors.get("bass_pulse_hsv"), theme.bass_pulse_hsv),
    )


def cfg_float(config: dict, section: str, key: str, default: float) -> float:
    try:
        return float((config.get(section) or {}).get(key, default))
    except (TypeError, ValueError):
        return default


def cfg_effect_float(config: dict, effect: str, key: str, default: float) -> float:
    try:
        return float(((config.get("effects") or {}).get(effect) or {}).get(key, default))
    except (TypeError, ValueError):
        return default


def cfg_effect_str(config: dict, effect: str, key: str, default: str) -> str:
    value = ((config.get("effects") or {}).get(effect) or {}).get(key, default)
    return str(value)


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def clamp_channel(value: float) -> int:
    return max(0, min(255, int(round(value))))


def hsv_to_rgb(h: float, s: float, v: float) -> tuple[int, int, int]:
    h = h % 360.0
    s = clamp01(s)
    v = clamp01(v)
    c = v * s
    x = c * (1 - abs((h / 60.0) % 2 - 1))
    m = v - c
    if h < 60:
        r, g, b = c, x, 0
    elif h < 120:
        r, g, b = x, c, 0
    elif h < 180:
        r, g, b = 0, c, x
    elif h < 240:
        r, g, b = 0, x, c
    elif h < 300:
        r, g, b = x, 0, c
    else:
        r, g, b = c, 0, x
    return (clamp_channel((r + m) * 255), clamp_channel((g + m) * 255), clamp_channel((b + m) * 255))


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * clamp01(t)


def smoothstep(t: float) -> float:
    t = clamp01(t)
    return t * t * (3.0 - 2.0 * t)


def lerp_rgb(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return (clamp_channel(lerp(a[0], b[0], t)), clamp_channel(lerp(a[1], b[1], t)), clamp_channel(lerp(a[2], b[2], t)))


def lerp_hsv(a: tuple[float, float, float], b: tuple[float, float, float], t: float) -> tuple[float, float, float]:
    t = clamp01(t)
    h1, s1, v1 = a
    h2, s2, v2 = b
    delta = ((h2 - h1 + 180.0) % 360.0) - 180.0
    return ((h1 + delta * t) % 360.0, lerp(s1, s2, t), lerp(v1, v2, t))


def scale_rgb(rgb: tuple[int, int, int], level: float) -> tuple[int, int, int]:
    return (clamp_channel(rgb[0] * level), clamp_channel(rgb[1] * level), clamp_channel(rgb[2] * level))


def add_rgb(dst: list[float], rgb: tuple[int, int, int], level: float = 1.0) -> None:
    dst[0] += rgb[0] * level
    dst[1] += rgb[1] * level
    dst[2] += rgb[2] * level


def max_rgb(base: tuple[int, int, int], overlay: tuple[int, int, int]) -> tuple[int, int, int]:
    return (max(base[0], overlay[0]), max(base[1], overlay[1]), max(base[2], overlay[2]))


def normalize_positions(positions: list[LampPosition], lamp_count: int) -> list[tuple[float, float]]:
    usable = positions[: min(lamp_count, len(positions))]
    min_x = min(item.x for item in usable)
    max_x = max(item.x for item in usable)
    min_y = min(item.y for item in usable)
    max_y = max(item.y for item in usable)
    x_span = max(1, max_x - min_x)
    y_span = max(1, max_y - min_y)
    scale = 100.0 / max(x_span, y_span)
    normalized: list[tuple[float, float]] = []
    for lamp_id in range(lamp_count):
        if lamp_id >= len(positions):
            normalized.append((0.0, 0.0))
            continue
        item = positions[lamp_id]
        normalized.append(((item.x - min_x) * scale, (item.y - min_y) * scale))
    return normalized


def build_distance_cache(normalized: list[tuple[float, float]], key_count: int, lamp_count: int, max_radius: float) -> dict[int, list[tuple[int, float]]]:
    cache: dict[int, list[tuple[int, float]]] = {}
    for key_id in range(min(key_count, len(normalized))):
        x1, y1 = normalized[key_id]
        neighbors: list[tuple[int, float]] = []
        for lamp_id in range(min(lamp_count, len(normalized))):
            x2, y2 = normalized[lamp_id]
            dist = math.hypot(x2 - x1, y2 - y1)
            if dist <= max_radius:
                neighbors.append((lamp_id, dist))
        cache[key_id] = neighbors
    return cache


def pressure_curve(p: float) -> float:
    # True analog mapping: pressure percentage maps directly to visual percentage.
    return clamp01(p)


def dent_color(theme: Theme, intensity: float) -> tuple[int, int, int]:
    intensity = clamp01(intensity)
    return hsv_to_rgb(*lerp_hsv(theme.base_hsv, theme.dent_levels[-1][1], intensity))


class PressureState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.pressures: dict[int, float] = {}
        self.last_seen: dict[int, float] = {}
        self.flash: dict[int, float] = {}
        self.rows = 0
        self.press_rows = 0
        self.errors: list[str] = []
        self.input_deadzone = 0.012
        self.jitter_deadzone = 0.018
        self.attack = 0.26
        self.release = 0.18
        self.small_change_attack = 0.06

    def configure(self, config: dict) -> None:
        self.input_deadzone = cfg_effect_float(config, "pressure_dent", "input_deadzone", self.input_deadzone)
        self.jitter_deadzone = cfg_effect_float(config, "pressure_dent", "jitter_deadzone", self.jitter_deadzone)
        self.attack = cfg_effect_float(config, "pressure_dent", "attack", self.attack)
        self.release = cfg_effect_float(config, "pressure_dent", "release", self.release)
        self.small_change_attack = cfg_effect_float(config, "pressure_dent", "small_change_attack", self.small_change_attack)

    def update_from_row(self, row: dict) -> None:
        now = time.time()
        samples_by_key: dict[int, float] = {}
        for source_name in ("all", "active", "top", "watch"):
            for entry in row.get(source_name) or []:
                try:
                    key_id = int(entry["keyId"])
                    pressure = clamp01(float(entry.get("pressure", 0.0)))
                except (KeyError, TypeError, ValueError):
                    continue
                if key_id < 0 or key_id >= KEY_LAMP_COUNT:
                    continue
                samples_by_key[key_id] = max(samples_by_key.get(key_id, 0.0), pressure)
        with self.lock:
            self.rows += 1
            if row.get("type") == "press" or samples_by_key:
                self.press_rows += 1
            seen: set[int] = set()
            for key_id, pressure in samples_by_key.items():
                previous = self.pressures.get(key_id, 0.0)
                if pressure <= self.input_deadzone:
                    if previous <= 0.0:
                        continue
                    pressure = 0.0
                diff = pressure - previous
                if abs(diff) < self.jitter_deadzone:
                    # Tiny changes follow slowly instead of freezing entirely; this keeps
                    # the effect responsive while still damping hand tremor.
                    attack = self.small_change_attack
                else:
                    attack = self.attack if diff > 0 else self.release
                self.pressures[key_id] = previous + diff * attack
                if self.pressures[key_id] < 0.0015 and pressure <= 0.0:
                    self.pressures.pop(key_id, None)
                    self.last_seen.pop(key_id, None)
                    continue
                self.last_seen[key_id] = now
                seen.add(key_id)
                if pressure > previous + 0.48:
                    self.flash[key_id] = max(self.flash.get(key_id, 0.0), min(0.18, pressure * 0.12))
            for key_id in list(self.pressures.keys()):
                if key_id not in seen and now - self.last_seen.get(key_id, 0.0) > 0.18:
                    self.pressures[key_id] *= 0.80
                    if self.pressures[key_id] < 0.0015:
                        self.pressures.pop(key_id, None)
                        self.last_seen.pop(key_id, None)
            for key_id in list(self.flash.keys()):
                self.flash[key_id] *= 0.82
                if self.flash[key_id] < 0.02:
                    self.flash.pop(key_id, None)

    def inject_key(self, key_id: int, pressure: float = 0.85, flash: bool = True) -> None:
        now = time.time()
        if key_id < 0 or key_id >= KEY_LAMP_COUNT:
            return
        pressure = clamp01(pressure)
        with self.lock:
            previous = self.pressures.get(key_id, 0.0)
            self.pressures[key_id] = previous + (pressure - previous) * 0.30
            self.last_seen[key_id] = now
            if flash:
                self.flash[key_id] = max(self.flash.get(key_id, 0.0), min(0.42, pressure * 0.30))

    def tick_decay(self) -> tuple[dict[int, float], dict[int, float]]:
        now = time.time()
        with self.lock:
            for key_id in list(self.pressures.keys()):
                if now - self.last_seen.get(key_id, 0.0) > 0.12:
                    self.pressures[key_id] *= 0.82
                    if self.pressures[key_id] < 0.0015:
                        self.pressures.pop(key_id, None)
                        self.last_seen.pop(key_id, None)
            for key_id in list(self.flash.keys()):
                self.flash[key_id] *= 0.84
                if self.flash[key_id] < 0.02:
                    self.flash.pop(key_id, None)
            return dict(self.pressures), dict(self.flash)


def start_pressure_bridge(args: argparse.Namespace) -> subprocess.Popen | None:
    if args.no_pressure:
        return None
    bridge_path = Path(__file__).resolve().parent / "melgeek_webhid_bridge_launcher.py"
    command = [
        sys.executable,
        str(bridge_path),
        "--min-delta",
        str(args.pressure_min_delta),
        "--min-interval-ms",
        str(args.pressure_interval_ms),
        "--full-delta",
        str(args.full_delta),
    ]
    if args.pressure_status_ms > 0:
        command.extend(["--status-interval-ms", str(args.pressure_status_ms)])
    return subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        cwd=str(bridge_path.parent),
    )


def bridge_stderr_reader(proc: subprocess.Popen) -> None:
    if proc.stderr is None:
        return
    for line in iter(proc.stderr.readline, ""):
        line = line.strip()
        if line:
            print(f"bridge: {line}", flush=True)


def pressure_reader(proc: subprocess.Popen, state: PressureState) -> None:
    assert proc.stdout is not None
    for line in iter(proc.stdout.readline, ""):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            print(f"bridge-json-skip: {line[:160]}", flush=True)
            continue
        state.update_from_row(row)
    print(f"bridge stdout ended returncode={proc.poll()}", flush=True)


def start_local_webhid_server(args: argparse.Namespace, jsonl_path: Path, log_path: Path) -> subprocess.Popen | None:
    if args.no_pressure or args.pressure_source != "webhid":
        return None
    if getattr(sys, "frozen", False):
        command = [
            sys.executable,
            "--pressure-server",
            "--port",
            str(args.pressure_port),
            "--jsonl",
            str(jsonl_path),
            "--log",
            str(log_path),
        ]
    else:
        server_path = Path(__file__).resolve().parent / "melgeek_local_webhid_pressure_server.py"
        command = [
            sys.executable,
            str(server_path),
            "--port",
            str(args.pressure_port),
            "--jsonl",
            str(jsonl_path),
            "--log",
            str(log_path),
        ]
    if args.no_open_pressure_page:
        command.append("--no-open")
    return subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        cwd=str(Path(__file__).resolve().parents[1]),
    )


def process_log_reader(proc: subprocess.Popen, prefix: str) -> None:
    if proc.stdout is None:
        return
    for line in iter(proc.stdout.readline, ""):
        line = line.strip()
        if line:
            print(f"{prefix}: {line}", flush=True)
    print(f"{prefix} ended returncode={proc.poll()}", flush=True)


def tail_pressure_jsonl(path: Path, state: PressureState, stop_event: threading.Event) -> None:
    position = 0
    while not stop_event.is_set() and not path.exists():
        time.sleep(0.05)
    while not stop_event.is_set():
        try:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                handle.seek(position)
                while not stop_event.is_set():
                    line = handle.readline()
                    if not line:
                        position = handle.tell()
                        time.sleep(0.02)
                        continue
                    position = handle.tell()
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    state.update_from_row(row)
        except OSError:
            time.sleep(0.1)


def native_pressure_reader(args: argparse.Namespace, state: PressureState, stop_event: threading.Event) -> None:
    normalizer = PressureNormalizer(args.full_delta)
    rows = 0
    press_rows = 0
    last_emit = 0.0
    last_query = 0.0
    try:
        dev_info = choose_device()
        handle = open_pressure_device(dev_info)
    except Exception as exc:
        print(f"pressure-native: failed to open native HID pressure source: {exc}", flush=True)
        return
    try:
        ok, total = send_pressure_init(handle, 0.025)
        print(f"pressure-native: init ok={ok}/{total}", flush=True)
        while not stop_event.is_set():
            now = time.time()
            if now - last_query >= 1.0:
                try:
                    write_pressure_command(handle, *QUERY_PACKET)
                except OSError as exc:
                    print(f"pressure-native: query failed: {exc}", flush=True)
                last_query = now
            try:
                report = handle.read(65, 50)
            except OSError as exc:
                print(f"pressure-native: read failed: {exc}", flush=True)
                time.sleep(0.05)
                continue
            if not report:
                continue
            samples = decode_pressure_report(report, args.full_delta)
            if samples is None:
                continue
            normalizer.enrich(samples)
            if now - last_emit < args.pressure_interval_ms / 1000.0:
                continue
            ranked = normalizer.ranked()
            active = [
                item
                for item in ranked
                if abs(float(item.get("delta", 0))) >= args.pressure_min_delta
                or float(item.get("pressure", 0.0)) >= 0.001
            ]
            row = {
                "ts": now,
                "type": "press" if active else "status",
                "active": active[:80],
                "top": ranked[:80],
                "all": ranked,
            }
            state.update_from_row(row)
            rows += 1
            if active:
                press_rows += 1
            last_emit = now
    finally:
        try:
            handle.close()
        except Exception:
            pass
        print(f"pressure-native: ended rows={rows} press_rows={press_rows}", flush=True)


def keyboard_fallback_reader(state: PressureState, stop_event: threading.Event) -> None:
    if sys.platform != "win32":
        return
    user32 = ctypes.windll.user32
    pressed: set[int] = set()
    while not stop_event.is_set():
        for vk, lamp_id in VK_TO_LAMP.items():
            is_down = bool(user32.GetAsyncKeyState(vk) & 0x8000)
            if is_down:
                state.inject_key(lamp_id, 0.88, flash=vk not in pressed)
                pressed.add(vk)
            else:
                pressed.discard(vk)
        time.sleep(0.012)


@dataclass
class AudioSnapshot:
    spectrum: list[float]
    level: float
    bass: float


class AudioState:
    def __init__(self, enabled: bool, columns: int = BACKPLATE_COLUMNS, mode: str = "loopback", silence_gate: float = 0.0045) -> None:
        self.enabled = enabled
        self.columns = columns
        self.requested_mode = mode
        self.silence_gate = silence_gate
        self.lock = threading.Lock()
        self.spectrum = [0.0] * columns
        self.level = 0.0
        self.bass = 0.0
        self.agc = 0.08
        self.mode = "synthetic"
        self._stop = threading.Event()
        self._stream = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if not self.enabled:
            self.mode = "off"
            return
        if self.requested_mode == "synthetic":
            self.mode = "synthetic-forced"
            self._thread = threading.Thread(target=self._synthetic_loop, daemon=True)
            self._thread.start()
            return
        try:
            import numpy as np  # type: ignore
        except Exception:
            self.mode = "audio-off-no-numpy"
            return

        sample_rate = 44100
        block_size = 2048
        window = np.hanning(block_size)
        edges = np.geomspace(2, block_size // 2, self.columns + 1).astype(int)
        edges[0] = 1

        def process_block(data) -> float:  # noqa: ANN001
            if data is None or len(data) == 0:
                return 0.0
            arr_in = data.astype(float)
            mono = np.mean(arr_in, axis=1) if getattr(arr_in, "ndim", 1) > 1 else arr_in
            if len(mono) < block_size:
                mono = np.pad(mono, (0, block_size - len(mono)))
            elif len(mono) > block_size:
                mono = mono[:block_size]
            rms = float(np.sqrt(np.mean(mono * mono)))
            noise_gate = self.silence_gate
            if rms < noise_gate:
                # Silence/noise gate: do not let AGC amplify device noise into fake spectrum.
                with self.lock:
                    self.level *= 0.70
                    self.bass *= 0.62
                    self.spectrum = [value * 0.62 for value in self.spectrum]
                    self.agc = max(self.agc * 0.992, 0.08)
                return rms
            fft = np.abs(np.fft.rfft(mono * window))
            values = []
            for i in range(self.columns):
                start = int(edges[i])
                end = max(start + 1, int(edges[i + 1]))
                values.append(float(np.mean(fft[start:end])))
            spectrum = np.log1p(np.array(values) * 6.0)
            raw_peak = float(np.percentile(spectrum, 92)) if spectrum.size else 0.0
            with self.lock:
                self.agc = max(self.agc * 0.995, raw_peak, 0.08)
                normalized = np.clip(spectrum / max(self.agc * 1.85, 0.08), 0.0, 1.0) ** 0.90
                bass = float(np.mean(normalized[: max(4, self.columns // 7)])) if normalized.size else 0.0
                self.level = self.level * 0.68 + clamp01(rms * 5.5) * 0.32
                self.bass = self.bass * 0.68 + clamp01(bass * 0.78) * 0.32
                self.spectrum = [clamp01(self.spectrum[i] * 0.70 + float(normalized[i]) * 0.30) for i in range(self.columns)]
            return rms

        if self.requested_mode == "loopback" and sys.platform == "win32":
            try:
                import pyaudiowpatch as pyaudio  # type: ignore

                pa_format = pyaudio.paFloat32

                def open_default_loopback(pa):  # noqa: ANN001
                    device = pa.get_default_wasapi_loopback()
                    channels = max(1, min(2, int(device.get("maxInputChannels") or 2)))
                    rate = int(device.get("defaultSampleRate") or sample_rate)
                    stream = pa.open(
                        format=pa_format,
                        channels=channels,
                        rate=rate,
                        input=True,
                        input_device_index=int(device["index"]),
                        frames_per_buffer=block_size,
                    )
                    return device, stream, channels

                pa = pyaudio.PyAudio()
                initial_device, initial_stream, initial_channels = open_default_loopback(pa)

                def wasapi_loopback_loop() -> None:
                    stream = initial_stream
                    try:
                        device = initial_device
                        channels = initial_channels
                        current_index = int(device["index"])
                        current_name = str(device.get("name", "WASAPI Loopback"))
                        self.mode = f"wasapi-loopback:{current_name}"
                        print(f"audio: {self.mode}", flush=True)
                        last_device_check = 0.0
                        while not self._stop.is_set():
                            now_audio = time.time()
                            if now_audio - last_device_check >= 0.5:
                                last_device_check = now_audio
                                try:
                                    default_device = pa.get_default_wasapi_loopback()
                                    default_index = int(default_device["index"])
                                    if default_index != current_index:
                                        print(f"audio: default loopback changed {current_name} -> {default_device.get('name')}", flush=True)
                                        stream.stop_stream()
                                        stream.close()
                                        device, stream, channels = open_default_loopback(pa)
                                        current_index = int(device["index"])
                                        current_name = str(device.get("name", "WASAPI Loopback"))
                                        self.mode = f"wasapi-loopback:{current_name}"
                                        print(f"audio: {self.mode}", flush=True)
                                except Exception as exc:
                                    print(f"audio: default loopback check failed: {exc}", flush=True)
                            try:
                                raw = stream.read(block_size, exception_on_overflow=False)
                            except Exception as exc:
                                print(f"audio: loopback read failed; reopening default device: {exc}", flush=True)
                                try:
                                    stream.stop_stream()
                                    stream.close()
                                except Exception:
                                    pass
                                device, stream, channels = open_default_loopback(pa)
                                current_index = int(device["index"])
                                current_name = str(device.get("name", "WASAPI Loopback"))
                                self.mode = f"wasapi-loopback:{current_name}"
                                print(f"audio: {self.mode}", flush=True)
                                continue
                            block = np.frombuffer(raw, dtype=np.float32)
                            if channels > 1 and block.size >= channels:
                                block = block[: (block.size // channels) * channels].reshape(-1, channels)
                            process_block(block)
                    except Exception as exc:
                        print(f"audio: WASAPI loopback stopped: {exc}", flush=True)
                        self.mode = "audio-off-wasapi-loopback-failed"
                    finally:
                        try:
                            stream.stop_stream()
                            stream.close()
                        except Exception:
                            pass
                        try:
                            pa.terminate()
                        except Exception:
                            pass

                self._thread = threading.Thread(target=wasapi_loopback_loop, daemon=True)
                self._thread.start()
                return
            except Exception as exc:
                print(f"audio: PyAudioWPatch WASAPI unavailable; falling back to soundcard scan: {exc}", flush=True)

            try:
                import soundcard as sc  # type: ignore

                def measure_microphone(candidate) -> float:  # noqa: ANN001
                    try:
                        with candidate.recorder(samplerate=sample_rate, channels=2, blocksize=block_size) as recorder:
                            best = 0.0
                            for _ in range(6):
                                data = recorder.record(numframes=block_size)
                                arr = data.astype(float)
                                mono = np.mean(arr, axis=1) if getattr(arr, "ndim", 1) > 1 else arr
                                best = max(best, float(np.sqrt(np.mean(mono * mono))) if len(mono) else 0.0)
                            return best
                    except Exception:
                        return 0.0

                def select_microphone():  # noqa: ANN001
                    microphones = sc.all_microphones(include_loopback=True)
                    selected = None
                    selected_rms = 0.0
                    for candidate in microphones:
                        value = measure_microphone(candidate)
                        if value > selected_rms:
                            selected = candidate
                            selected_rms = value
                    if selected is None:
                        raise RuntimeError("no loopback microphone devices found")
                    return selected, selected_rms

                mic, selected_rms = select_microphone()
                self.mode = f"soundcard-loopback:{mic.name}"
                print(f"audio: selected loopback {mic.name} rms={selected_rms:.5f}", flush=True)

                def loopback_loop() -> None:
                    current_mic = mic
                    silence_started = None
                    last_idle_log = 0.0
                    while not self._stop.is_set():
                        try:
                            self.mode = f"soundcard-loopback:{current_mic.name}"
                            with current_mic.recorder(samplerate=sample_rate, channels=2, blocksize=block_size) as recorder:
                                print(f"audio: {self.mode}", flush=True)
                                while not self._stop.is_set():
                                    level_rms = process_block(recorder.record(numframes=block_size))
                                    now_audio = time.time()
                                    if level_rms < self.silence_gate:
                                        if silence_started is None:
                                            silence_started = now_audio
                                        elif now_audio - silence_started > 2.5:
                                            new_mic, new_rms = select_microphone()
                                            threshold = max(self.silence_gate * 1.4, 0.006)
                                            if getattr(new_mic, "name", "") != getattr(current_mic, "name", "") and new_rms > threshold:
                                                print(f"audio: switching loopback {current_mic.name} -> {new_mic.name} rms={new_rms:.5f}", flush=True)
                                                current_mic = new_mic
                                                silence_started = None
                                                break
                                            if now_audio - last_idle_log > 5.0:
                                                print(f"audio: idle, keeping current loopback {current_mic.name}; best_other_rms={new_rms:.5f}", flush=True)
                                                last_idle_log = now_audio
                                    else:
                                        silence_started = None
                        except Exception as exc:
                            print(f"audio: soundcard loopback failed; rescanning: {exc}", flush=True)
                            try:
                                current_mic, _ = select_microphone()
                            except Exception:
                                self.mode = "audio-off-loopback-failed"
                                return

                self._thread = threading.Thread(target=loopback_loop, daemon=True)
                self._thread.start()
                return
            except Exception as exc:
                print(f"audio: soundcard loopback unavailable; audio disabled: {exc}", flush=True)
                self.mode = "audio-off-loopback-unavailable"
                return

        try:
            import sounddevice as sd  # type: ignore

            def callback(indata, frames, callback_time, status):  # noqa: ANN001
                process_block(indata)

            self.mode = "live-input" if self.requested_mode == "input" else "live-input-fallback"
            self._stream = sd.InputStream(channels=1, samplerate=sample_rate, blocksize=block_size, callback=callback)
            self._stream.start()
            print(f"audio: {self.mode}", flush=True)
        except Exception as exc:
            print(f"audio: input fallback failed; audio disabled: {exc}", flush=True)
            self.mode = "audio-off-input-failed"

    def _synthetic_loop(self) -> None:
        started = time.time()
        while not self._stop.is_set():
            t = time.time() - started
            values = []
            for i in range(self.columns):
                low = math.sin(t * 1.7 + i * 0.12) * 0.5 + 0.5
                high = math.sin(t * 4.7 + i * 0.55) * 0.5 + 0.5
                envelope = 0.10 + 0.18 * (math.sin(t * 0.55) * 0.5 + 0.5)
                values.append(clamp01((low * 0.70 + high * 0.30) * envelope))
            with self.lock:
                self.spectrum = values
                self.level = clamp01(0.12 + 0.12 * math.sin(t * 1.2) ** 2)
                self.bass = clamp01(0.10 + 0.18 * math.sin(t * 1.7) ** 2)
            time.sleep(1 / 30)

    def snapshot(self) -> AudioSnapshot:
        if not self.enabled:
            return AudioSnapshot([0.0] * self.columns, 0.0, 0.0)
        with self.lock:
            return AudioSnapshot(list(self.spectrum), self.level, self.bass)

    def close(self) -> None:
        self._stop.set()
        stream = self._stream
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass


def spectrum_color(theme: Theme, column: int, value: float, bass: float) -> tuple[int, int, int]:
    t = column / max(1, BACKPLATE_COLUMNS - 1)
    hsv = lerp_hsv(theme.outer_low_hsv, theme.outer_high_hsv, t)
    if column < BACKPLATE_COLUMNS * 0.20 and bass > 0.28:
        hsv = lerp_hsv(hsv, theme.bass_pulse_hsv, clamp01((bass - 0.28) / 0.72) * 0.62)
    h, s, v = hsv
    v = clamp01(0.06 + v * (0.35 + 0.95 * clamp01(value)))
    return hsv_to_rgb(h, s, v)


def render_backplate(colors: list[tuple[int, int, int]], theme: Theme, audio: AudioSnapshot, peak_hold: list[float], now: float, ambience_strength: float = 1.0, shockwave_strength: float = 1.0, motion_strength: float = 1.0) -> None:
    base_hsv = theme.outer_base_hsv
    base = scale_rgb(hsv_to_rgb(*base_hsv), 0.42)
    rows = [REAR_BOTTOM, REAR_MID, REAR_TOP]
    for lamp_id in list(REAR_TOP) + list(REAR_MID) + list(REAR_BOTTOM):
        colors[lamp_id] = base

    spectrum = audio.spectrum or [0.0] * BACKPLATE_COLUMNS
    low_energy = clamp01(max(audio.bass, sum(spectrum[:13]) / max(1, min(13, len(spectrum)))))
    mid_slice = spectrum[13:42] if len(spectrum) >= 42 else spectrum
    high_slice = spectrum[42:] if len(spectrum) > 42 else spectrum[-12:]
    mid_energy = clamp01(sum(mid_slice) / max(1, len(mid_slice)))
    high_energy = clamp01(sum(high_slice) / max(1, len(high_slice)))
    level = clamp01(audio.level)
    energy_gate = max(level, low_energy, mid_energy, high_energy)
    if energy_gate < 0.025:
        return

    low_hsv = theme.outer_low_hsv
    mid_hsv = theme.bass_pulse_hsv
    high_hsv = theme.outer_high_hsv
    motion = clamp01(motion_strength)
    pulse = clamp01(max(level * 0.55, low_energy * 0.72) * shockwave_strength)
    body = clamp01((0.34 * level + 0.28 * mid_energy + 0.14 * low_energy) * ambience_strength)
    shimmer = clamp01(high_energy * 0.16 * ambience_strength)
    wave_phase = now * (0.12 + 0.30 * motion)

    for column in range(BACKPLATE_COLUMNS):
        x = column / max(1, BACKPLATE_COLUMNS - 1)
        broad = 0.72 + 0.28 * math.sin(wave_phase + x * math.pi * 1.6)
        center_glow = math.exp(-((x - 0.50) / 0.46) ** 2)
        edge_glow = max(math.exp(-((x - 0.12) / 0.30) ** 2), math.exp(-((x - 0.88) / 0.30) ** 2))
        amount = clamp01((body * broad + pulse * center_glow * 0.55 + shimmer * edge_glow * 0.25))
        if amount <= 0.015:
            continue
        # One coherent palette: base -> pulse color, with only slight cool shimmer.
        hsv = lerp_hsv(theme.outer_base_hsv, mid_hsv, clamp01(body * 0.55 + pulse * 0.38))
        hsv = lerp_hsv(hsv, low_hsv, clamp01(pulse * 0.30))
        hsv = lerp_hsv(hsv, high_hsv, clamp01(shimmer * 0.18))
        h, s, v = hsv
        target = hsv_to_rgb(h, s, clamp01(v * (0.20 + amount * 0.95)))

        row_levels = [
            clamp01(amount + pulse * 0.28),
            clamp01(amount * 0.90 + body * 0.16),
            clamp01(amount * 0.72 + shimmer * 0.16),
        ]
        for row_index, row in enumerate(rows):
            row_amount = clamp01(row_levels[row_index])
            if row_amount <= 0.015:
                continue
            lamp_id = list(row)[column]
            colors[lamp_id] = lerp_rgb(colors[lamp_id], target, clamp01(0.18 + row_amount * 0.82))


def render_sides(colors: list[tuple[int, int, int]], theme: Theme, level: float, bass: float, vu_strength: float = 1.0, vu_curve: float = 0.62) -> None:
    base = scale_rgb(hsv_to_rgb(*theme.outer_base_hsv), 0.55)
    strength = clamp01(vu_strength)
    raw_impact = max(level * 1.28, bass * 1.05) * strength
    if raw_impact < 0.035:
        for lamp_id in list(LEFT_SIDE) + list(RIGHT_SIDE):
            colors[lamp_id] = base
        return
    impact = clamp01(raw_impact ** max(0.25, min(1.5, vu_curve)))
    previous_peak = getattr(render_sides, "peak", 0.0)
    peak = max(impact, previous_peak * 0.92 - 0.010)
    setattr(render_sides, "peak", peak)
    fill = impact * (len(LEFT_SIDE) + 1.6)
    peak_pos = peak * (len(LEFT_SIDE) + 1.6)
    bass_mix = clamp01((bass - 0.14) / 0.86)

    def render_one_side(side: list[int], left: bool) -> None:
        n = len(side)
        for index, lamp_id in enumerate(side):
            # Physical orientation note from testing:
            # left strip index 0 is top; right strip index 0 is bottom.
            physical_from_bottom = (n - 1 - index) if left else index
            amount = clamp01((fill - physical_from_bottom) * 2.25)
            peak_amount = 0.0
            if abs(peak_pos - physical_from_bottom) < 0.55 and peak > 0.08:
                peak_amount = 0.42
            if amount <= 0 and peak_amount <= 0:
                colors[lamp_id] = base
                continue
            amount = clamp01(amount * 1.45)
            physical_from_top = (n - 1 - physical_from_bottom)
            top_t = physical_from_top / max(1, n - 1)
            # Desired color orientation: left top red / bottom cyan; right bottom red / top cyan.
            if left:
                color_t = top_t
            else:
                color_t = 1.0 - top_t
            hsv = lerp_hsv(theme.outer_low_hsv, theme.outer_high_hsv, color_t)
            hsv = lerp_hsv(hsv, theme.bass_pulse_hsv, bass_mix * (0.82 if physical_from_bottom < 5 else 0.42))
            h, s, v = hsv
            v = clamp01(v * (0.34 + 0.98 * max(amount, peak_amount)))
            colors[lamp_id] = lerp_rgb(base, hsv_to_rgb(h, s, v), 0.28 + 0.72 * max(amount, peak_amount))

    render_one_side(list(LEFT_SIDE), left=True)
    render_one_side(list(RIGHT_SIDE), left=False)


def contribution_centers(key_id: int) -> tuple[int, ...]:
    if key_id in SPACE_LAMP_IDS:
        return tuple(lamp_id for lamp_id in SPACE_EFFECT_IDS if 0 <= lamp_id < KEY_LAMP_COUNT)
    return (key_id,)


def render_keys(
    colors: list[tuple[int, int, int]],
    theme: Theme,
    normalized: list[tuple[float, float]],
    distance_cache: dict[int, list[tuple[int, float]]],
    pressures: dict[int, float],
    flashes: dict[int, float],
    bass: float,
    max_radius: float,
    color_floor_amount: float = 0.22,
    space_color_floor_amount: float = 0.26,
) -> None:
    base = hsv_to_rgb(*theme.base_hsv)
    pulse = hsv_to_rgb(*theme.bass_pulse_hsv)
    bass_mix = clamp01((bass - 0.55) / 0.45) * 0.06
    for lamp_id in range(min(KEY_LAMP_COUNT, len(colors))):
        colors[lamp_id] = lerp_rgb(base, pulse, bass_mix)

    intensities = [0.0] * min(KEY_LAMP_COUNT, len(colors))
    flash_intensities = [0.0] * min(KEY_LAMP_COUNT, len(colors))
    for key_id, pressure in pressures.items():
        if key_id < 0 or key_id >= KEY_LAMP_COUNT:
            continue
        effective = pressure_curve(pressure)
        if effective <= 0:
            continue
        is_space = key_id in SPACE_LAMP_IDS
        radius = (4.2 if is_space else 3.4) + effective * (max_radius * (1.55 if is_space else 1.35))
        centers = contribution_centers(key_id)
        for center_id in centers:
            for lamp_id, dist in distance_cache.get(center_id, []):
                if lamp_id >= KEY_LAMP_COUNT or dist > radius:
                    continue
                falloff = max(0.0, 1.0 - (dist / max(0.01, radius)) ** (0.92 if is_space else 0.98))
                color_floor = effective * (space_color_floor_amount if is_space else color_floor_amount)
                # Expansion and color now share the same pressure percentage. Low
                # pressure contributes a subtle halo instead of waiting for deep travel.
                contribution = max(effective * falloff, color_floor * (0.35 + 0.65 * falloff))
                intensities[lamp_id] = max(intensities[lamp_id], contribution)
        flash = flashes.get(key_id, 0.0)
        if flash > 0:
            flash_radius = 5.2 if is_space else 2.8
            for center_id in centers:
                for lamp_id, dist in distance_cache.get(center_id, []):
                    if lamp_id >= KEY_LAMP_COUNT or dist > flash_radius:
                        continue
                    sigma = 2.2 if is_space else 1.05
                    flash_intensities[lamp_id] = max(flash_intensities[lamp_id], flash * math.exp(-0.5 * (dist / sigma) ** 2))

    for lamp_id, intensity in enumerate(intensities):
        if intensity > 0:
            gain = 0.82 + 0.42 * clamp01(intensity)
            colors[lamp_id] = scale_rgb(dent_color(theme, intensity), gain)
        if flash_intensities[lamp_id] > 0:
            hot = hsv_to_rgb(*theme.dent_levels[-1][1])
            colors[lamp_id] = lerp_rgb(colors[lamp_id], hot, clamp01(flash_intensities[lamp_id] * 0.55))


def render_static(theme: Theme) -> list[tuple[int, int, int]]:
    colors = [hsv_to_rgb(*theme.outer_base_hsv) for _ in range(LAMP_COUNT)]
    key_base = hsv_to_rgb(*theme.base_hsv)
    for lamp_id in range(min(KEY_LAMP_COUNT, LAMP_COUNT)):
        colors[lamp_id] = key_base
    return colors


def render_breathing(theme: Theme, now: float, speed: float = 1.0, depth: float = 1.0) -> list[tuple[int, int, int]]:
    # Slow HSV breathing between the theme base and its accent color. This is
    # intentionally not a multi-color step effect.
    depth = clamp01(depth)
    t = 0.5 + 0.5 * math.sin(now * 0.82 * max(0.05, speed))
    t = smoothstep(t)
    mix = t * depth
    key_hsv = lerp_hsv(theme.base_hsv, theme.dent_levels[1][1], mix * 0.72)
    outer_hsv = lerp_hsv(theme.outer_base_hsv, theme.bass_pulse_hsv, mix * 0.62)
    key_gain = 0.42 + 0.58 * mix
    outer_gain = 0.32 + 0.55 * mix
    colors = [scale_rgb(hsv_to_rgb(*outer_hsv), outer_gain) for _ in range(LAMP_COUNT)]
    key_color = scale_rgb(hsv_to_rgb(*key_hsv), key_gain)
    for lamp_id in range(min(KEY_LAMP_COUNT, LAMP_COUNT)):
        colors[lamp_id] = key_color
    return colors


def render_rainbow(theme: Theme, normalized: list[tuple[float, float]], now: float, style: str = "diagonal", speed: float = 1.0, saturation: float = 0.68, value: float = 0.62) -> list[tuple[int, int, int]]:
    colors: list[tuple[int, int, int]] = []
    for lamp_id in range(LAMP_COUNT):
        x, y = normalized[lamp_id] if lamp_id < len(normalized) else (0.0, 0.0)
        if style == "horizontal":
            hue = x * 3.1 + now * 42.0 * speed
        elif style == "vertical":
            hue = y * 4.2 + now * 36.0 * speed
        elif style == "radial":
            hue = math.hypot(x - 50.0, y - 50.0) * 5.0 - now * 48.0 * speed
        elif style == "dual":
            hue = (x * 2.8 - y * 1.7 + math.sin(now * 0.8 * speed) * 80.0 + now * 28.0 * speed)
        elif style == "pastel":
            hue = x * 1.5 + y * 0.7 + now * 18.0 * speed
        else:
            hue = x * 2.4 + y * 0.8 + now * 42.0 * speed
        sat = saturation * (0.72 if style == "pastel" else 1.0)
        val = value * (0.90 if lamp_id < KEY_LAMP_COUNT else 0.76)
        colors.append(hsv_to_rgb(hue % 360.0, clamp01(sat), clamp01(val)))
    return colors


def render_audio_ambient(theme: Theme, audio: AudioSnapshot, peak_hold: list[float], now: float, side_vu_strength: float, backplate_ambience_strength: float, backplate_shockwave_strength: float, side_vu_curve: float = 0.62, backplate_motion: float = 1.0) -> list[tuple[int, int, int]]:
    colors = render_static(theme)
    render_backplate(colors, theme, audio, peak_hold, now, backplate_ambience_strength, backplate_shockwave_strength, backplate_motion)
    render_sides(colors, theme, audio.level, audio.bass, side_vu_strength, side_vu_curve)
    return colors


def ripple_params(strength: float, min_radius: float, max_radius: float, min_duration: float, max_duration: float) -> tuple[float, float]:
    strength = clamp01(strength)
    return min_radius + (max_radius - min_radius) * (strength ** 0.82), min_duration + (max_duration - min_duration) * strength


def render_ripple_effect(theme: Theme, normalized: list[tuple[float, float]], ripples: list[ActiveRipple], now: float, brightness: float = 1.0, width_scale: float = 1.0) -> list[tuple[int, int, int]]:
    # Match the older standalone ripple feel: dark stage, soft Gaussian ring,
    # small tap flash, and an after-shimmer. Pressure only controls width/radius/life.
    colors_float = [[0.0, 0.0, 0.0] for _ in range(LAMP_COUNT)]
    live = [r for r in ripples if now - r.started_at < r.duration]
    ripple_rgb = hsv_to_rgb(*theme.dent_levels[-1][1])
    for ripple in live:
        if ripple.key_id >= len(normalized):
            continue
        elapsed = max(0.0, now - ripple.started_at)
        progress = clamp01(elapsed / max(0.1, ripple.duration))
        eased = 1.0 - (1.0 - progress) ** 2.15
        radius = eased * ripple.max_radius
        fade = (1.0 - progress) ** 0.72 * (0.35 + 0.95 * ripple.strength) * max(0.0, brightness)
        hold = clamp01(ripple.hold_factor)
        width = max(1.0, (1.8 + hold * 8.8 + ripple.strength * 1.2) * max(0.2, width_scale))
        centers = contribution_centers(ripple.key_id)
        for center_id in centers:
            if center_id >= len(normalized):
                continue
            cx, cy = normalized[center_id]
            for lamp_id in range(LAMP_COUNT):
                x, y = normalized[lamp_id] if lamp_id < len(normalized) else (0.0, 0.0)
                dist = math.hypot(x - cx, y - cy)
                ring = math.exp(-0.5 * ((dist - radius) / width) ** 2)
                tap_flash = 0.30 * math.exp(-0.5 * (dist / max(0.01, width * 0.50)) ** 2) * (1.0 - progress) ** 4.2
                after_shimmer = 0.14 * math.exp(-0.5 * ((dist - radius * 0.68) / max(0.01, width * 1.8)) ** 2) * fade
                level = max(ring * fade, tap_flash * ripple.strength, after_shimmer)
                if level <= 0.005:
                    continue
                outer_scale = 0.58 if lamp_id >= KEY_LAMP_COUNT else 1.0
                for channel_index, channel in enumerate(ripple_rgb):
                    colors_float[lamp_id][channel_index] += channel * level * outer_scale
    return [
        (clamp_channel(rgb[0]), clamp_channel(rgb[1]), clamp_channel(rgb[2]))
        for rgb in colors_float
    ]


def compose_frame(
    theme: Theme,
    normalized: list[tuple[float, float]],
    distance_cache: dict[int, list[tuple[int, float]]],
    pressures: dict[int, float],
    flashes: dict[int, float],
    audio: AudioSnapshot,
    peak_hold: list[float],
    max_radius: float,
    now: float,
    side_vu_strength: float = 1.0,
    backplate_ambience_strength: float = 1.0,
    backplate_shockwave_strength: float = 1.0,
    pressure_color_floor: float = 0.22,
    pressure_space_color_floor: float = 0.26,
    side_vu_curve: float = 0.62,
    backplate_motion: float = 1.0,
) -> list[tuple[int, int, int]]:
    colors = [BLACK for _ in range(LAMP_COUNT)]
    render_backplate(colors, theme, audio, peak_hold, now, backplate_ambience_strength, backplate_shockwave_strength, backplate_motion)
    render_sides(colors, theme, audio.level, audio.bass, side_vu_strength, side_vu_curve)
    render_keys(colors, theme, normalized, distance_cache, pressures, flashes, audio.bass, max_radius, pressure_color_floor, pressure_space_color_floor)
    return colors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Premium interactive RGB effect for MelGeek MADE68 V2: spectrum + VU + magnetic pressure heatmap dent.")
    parser.add_argument("--seconds", type=float, default=0.0, help="Run duration. 0 means until Ctrl+C.")
    parser.add_argument("--theme", default="noir", help="Theme index/name: noir, void, arctic, ember, eclipse, or 0-4.")
    parser.add_argument("--effect", default="premium_reactive", choices=["static", "breathing", "rainbow", "ripple", "audio_ambient", "pressure_dent", "premium_reactive"], help="Lighting effect mode.")
    parser.add_argument("--config", default="", help="Optional JSON config file generated by the GUI.")
    parser.add_argument("--list-themes", action="store_true", help="Print available themes and exit.")
    parser.add_argument("--fps", type=float, default=30.0)
    parser.add_argument("--brightness", type=float, default=0.70, help="Global brightness multiplier 0-1.")
    parser.add_argument("--radius", type=float, default=13.0, help="Keyboard dent spread radius in normalized position units.")
    parser.add_argument("--pressure-min-delta", type=float, default=12.0, help="Raw ADC delta threshold for WebHID bridge events. This is not a percentage.")
    parser.add_argument("--pressure-interval-ms", type=float, default=12.0)
    parser.add_argument("--pressure-status-ms", type=float, default=1000.0)
    parser.add_argument("--full-delta", type=float, default=1100.0)
    parser.add_argument("--pressure-source", choices=["native", "webhid", "off"], default="native", help="native reads pressure through hidapi; webhid keeps the old browser bridge as fallback.")
    parser.add_argument("--pressure-port", type=int, default=8766, help="Local WebHID pressure page/server port used by the main effect.")
    parser.add_argument("--no-open-pressure-page", action="store_true", help="Do not automatically open the WebHID pressure page.")
    parser.add_argument("--no-pressure", action="store_true")
    parser.add_argument("--no-keyboard-fallback", action="store_true", help="Disable ordinary keyboard-key fallback. By default it shows dent reactions even if WebHID pressure is not working.")
    parser.add_argument("--no-audio", action="store_true")
    parser.add_argument("--audio-mode", choices=["loopback", "input", "synthetic"], default="loopback", help="loopback captures computer playback on Windows; input captures microphone; synthetic is built-in animation.")
    parser.add_argument("--no-final-black", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Do not write HID frames; useful for verifying pressure/audio parsing.")
    return parser.parse_args()


def select_theme(value: str) -> Theme:
    aliases = {
        "noir": 0,
        "cyberpunk": 0,
        "void": 1,
        "luxury": 1,
        "arctic": 2,
        "phantom": 2,
        "ember": 3,
        "midnight": 3,
        "eclipse": 4,
        "pure": 4,
    }
    key = value.strip().lower()
    if key in aliases:
        return THEMES[aliases[key]]
    try:
        return THEMES[int(key) % len(THEMES)]
    except Exception:
        valid = ", ".join(theme.name for theme in THEMES)
        raise SystemExit(f"Unknown theme {value!r}. Valid themes: {valid}")


def scale_frame(colors: Iterable[tuple[int, int, int]], brightness: float) -> list[tuple[int, int, int]]:
    # Treat brightness=1.0 as a real full-output request. Themes are intentionally
    # dark, so allow a little headroom before clamping.
    level = max(0.0, min(1.6, brightness * 1.45))
    return [(clamp_channel(r * level), clamp_channel(g * level), clamp_channel(b * level)) for r, g, b in colors]


def main() -> int:
    args = parse_args()
    if args.list_themes:
        for index, theme in enumerate(THEMES):
            print(f"{index}: {theme.name}")
        return 0
    config = load_json_config(args.config)
    if config:
        args.theme = str(config.get("theme") or args.theme)
        args.effect = str(config.get("effect") or args.effect)
        args.brightness = cfg_float(config, "global", "brightness", args.brightness)
        args.radius = cfg_float(config, "global", "radius", args.radius)
        args.fps = cfg_float(config, "global", "fps", args.fps)
        args.audio_mode = str((config.get("audio") or {}).get("mode", args.audio_mode))
        startup_cfg = config.get("startup") or {}
        args.pressure_port = int(cfg_float(config, "startup", "pressure_port", args.pressure_port))
        args.pressure_source = str(startup_cfg.get("pressure_source", args.pressure_source)).lower()
        if args.pressure_source not in ("native", "webhid", "off"):
            args.pressure_source = "native"
        args.no_pressure = args.no_pressure or args.pressure_source == "off"
        args.no_open_pressure_page = not bool((config.get("startup") or {}).get("open_pressure_page", not args.no_open_pressure_page))
        args.no_keyboard_fallback = not bool((config.get("startup") or {}).get("keyboard_fallback", not args.no_keyboard_fallback))
    theme = theme_with_overrides(select_theme(args.theme), config)
    positions, lamp_count = load_params_from_cache()
    if lamp_count != LAMP_COUNT:
        print(f"WARN cached lamp_count={lamp_count}, DirectHID lamp_count={LAMP_COUNT}; using {LAMP_COUNT}", flush=True)
    normalized = normalize_positions(positions, LAMP_COUNT)
    distance_cache = build_distance_cache(normalized, KEY_LAMP_COUNT, LAMP_COUNT, max_radius=max(18.0, args.radius + 4.0))
    peak_hold = [0.0] * BACKPLATE_COLUMNS

    audio_sensitivity = cfg_float(config, "audio", "sensitivity", 1.0)
    bass_sensitivity = cfg_float(config, "audio", "bass_sensitivity", 1.0)
    side_vu_strength = cfg_float(config, "audio", "side_vu_strength", 1.0)
    backplate_ambience_strength = cfg_float(config, "audio", "backplate_ambience_strength", 1.0)
    backplate_shockwave_strength = cfg_float(config, "audio", "backplate_shockwave_strength", 1.0)
    audio_silence_gate = cfg_effect_float(config, "audio_ambient", "silence_gate", 0.0045)
    audio_side_curve = cfg_effect_float(config, "audio_ambient", "side_vu_curve", 0.62)
    backplate_motion = cfg_effect_float(config, "audio_ambient", "backplate_motion", 1.0)
    effects_cfg = config.get("effects") or {}
    rainbow_cfg = effects_cfg.get("rainbow") or {}
    breathing_cfg = effects_cfg.get("breathing") or {}
    breathing_speed = float(breathing_cfg.get("speed", 1.0))
    breathing_depth = float(breathing_cfg.get("depth", 1.0))
    rainbow_style = str(rainbow_cfg.get("style", "diagonal"))
    rainbow_speed = float(rainbow_cfg.get("speed", 1.0))
    rainbow_saturation = float(rainbow_cfg.get("saturation", 0.68))
    rainbow_value = float(rainbow_cfg.get("value", 0.62))
    ripple_trigger = cfg_effect_float(config, "ripple", "trigger_threshold", 0.08)
    ripple_retrigger_gap = cfg_effect_float(config, "ripple", "retrigger_gap_ms", 45) / 1000.0
    ripple_charge = cfg_effect_float(config, "ripple", "charge_ms", 180) / 1000.0
    ripple_min_radius = cfg_effect_float(config, "ripple", "min_radius", 8.0)
    ripple_max_radius = cfg_effect_float(config, "ripple", "max_radius", 95.0)
    ripple_min_duration = cfg_effect_float(config, "ripple", "min_duration", 0.75)
    ripple_max_duration = cfg_effect_float(config, "ripple", "max_duration", 2.35)
    ripple_brightness = cfg_effect_float(config, "ripple", "brightness", 1.0)
    ripple_width = cfg_effect_float(config, "ripple", "width", 1.0)
    pressure_color_floor = cfg_effect_float(config, "pressure_dent", "color_floor", 0.22)
    pressure_space_color_floor = cfg_effect_float(config, "pressure_dent", "space_color_floor", 0.26)

    pressure_state = PressureState()
    pressure_state.configure(config)
    stop_event = threading.Event()
    pressure_jsonl = ROOT / "outputs" / "premium_reactive_pressure.jsonl"
    pressure_log = ROOT / "outputs" / "premium_reactive_pressure.log"
    pressure_proc = start_local_webhid_server(args, pressure_jsonl, pressure_log)
    if pressure_proc is not None:
        threading.Thread(target=process_log_reader, args=(pressure_proc, "pressure-page"), daemon=True).start()
        threading.Thread(target=tail_pressure_jsonl, args=(pressure_jsonl, pressure_state, stop_event), daemon=True).start()
    elif not args.no_pressure and args.pressure_source == "native":
        threading.Thread(target=native_pressure_reader, args=(args, pressure_state, stop_event), daemon=True).start()
    if not args.no_keyboard_fallback:
        threading.Thread(target=keyboard_fallback_reader, args=(pressure_state, stop_event), daemon=True).start()

    audio_state = AudioState(enabled=not args.no_audio, mode=args.audio_mode, silence_gate=audio_silence_gate)
    audio_state.start()

    sender = None if args.dry_run else DirectHidSender()
    frame_time = 1.0 / max(1.0, args.fps)
    deadline = None if args.seconds <= 0 else time.time() + max(0.2, args.seconds)
    next_report = 0.0
    status_log_path = ROOT / "outputs" / "premium_reactive_status.log"
    status_log_path.parent.mkdir(parents=True, exist_ok=True)
    status_log_path.write_text(f"==== {time.ctime()} ====\n", encoding="utf-8")
    frames = 0
    active_ripples: list[ActiveRipple] = []
    previous_pressures: dict[int, float] = {}
    last_ripple_at: dict[int, float] = {}

    active_pressure_source = "off" if args.no_pressure else args.pressure_source
    print(f"theme={theme.name} fps={args.fps:g} brightness={clamp01(args.brightness):.2f} audio={audio_state.mode} pressure={active_pressure_source} keyboard_fallback={'off' if args.no_keyboard_fallback else 'on'} dry_run={args.dry_run}", flush=True)
    if active_pressure_source == "webhid":
        print("按 Ctrl+C 停止。若 Edge 弹出 WebHID 授权，请选择 MADE68 V2 / MelGeek 设备。", flush=True)
    elif active_pressure_source == "native":
        print("按 Ctrl+C 停止。压力数据将通过原生 HID 读取，不需要打开浏览器连接页。", flush=True)
    else:
        print("按 Ctrl+C 停止。压力读取已关闭。", flush=True)

    config_path = Path(args.config) if args.config else None
    config_mtime = config_path.stat().st_mtime if config_path and config_path.exists() else 0.0
    next_config_check = 0.0

    try:
        if sender is not None:
            sender.send_frame(scale_frame([hsv_to_rgb(*theme.base_hsv)] * LAMP_COUNT, args.brightness), include_begin=True)
        last_frame = 0.0
        while deadline is None or time.time() < deadline:
            now = time.time()
            if config_path and now >= next_config_check:
                next_config_check = now + 0.35
                try:
                    current_mtime = config_path.stat().st_mtime
                except OSError:
                    current_mtime = config_mtime
                if current_mtime != config_mtime:
                    config_mtime = current_mtime
                    config = load_json_config(str(config_path))
                    old_radius = args.radius
                    old_audio_mode = args.audio_mode
                    args.theme = str(config.get("theme") or args.theme)
                    args.effect = str(config.get("effect") or args.effect)
                    args.brightness = cfg_float(config, "global", "brightness", args.brightness)
                    args.radius = cfg_float(config, "global", "radius", args.radius)
                    args.fps = cfg_float(config, "global", "fps", args.fps)
                    args.audio_mode = str((config.get("audio") or {}).get("mode", args.audio_mode))
                    theme = theme_with_overrides(select_theme(args.theme), config)
                    audio_sensitivity = cfg_float(config, "audio", "sensitivity", audio_sensitivity)
                    bass_sensitivity = cfg_float(config, "audio", "bass_sensitivity", bass_sensitivity)
                    side_vu_strength = cfg_float(config, "audio", "side_vu_strength", side_vu_strength)
                    backplate_ambience_strength = cfg_float(config, "audio", "backplate_ambience_strength", backplate_ambience_strength)
                    backplate_shockwave_strength = cfg_float(config, "audio", "backplate_shockwave_strength", backplate_shockwave_strength)
                    audio_silence_gate = cfg_effect_float(config, "audio_ambient", "silence_gate", audio_silence_gate)
                    audio_side_curve = cfg_effect_float(config, "audio_ambient", "side_vu_curve", audio_side_curve)
                    backplate_motion = cfg_effect_float(config, "audio_ambient", "backplate_motion", backplate_motion)
                    audio_state.silence_gate = audio_silence_gate
                    if args.audio_mode != old_audio_mode:
                        print(f"audio mode changed: {old_audio_mode} -> {args.audio_mode}; restarting audio", flush=True)
                        audio_state.close()
                        audio_state = AudioState(enabled=not args.no_audio, mode=args.audio_mode, silence_gate=audio_silence_gate)
                        audio_state.start()
                    effects_cfg = config.get("effects") or {}
                    breathing_cfg = effects_cfg.get("breathing") or {}
                    breathing_speed = float(breathing_cfg.get("speed", breathing_speed))
                    breathing_depth = float(breathing_cfg.get("depth", breathing_depth))
                    rainbow_cfg = effects_cfg.get("rainbow") or {}
                    rainbow_style = str(rainbow_cfg.get("style", rainbow_style))
                    rainbow_speed = float(rainbow_cfg.get("speed", rainbow_speed))
                    rainbow_saturation = float(rainbow_cfg.get("saturation", rainbow_saturation))
                    rainbow_value = float(rainbow_cfg.get("value", rainbow_value))
                    ripple_trigger = cfg_effect_float(config, "ripple", "trigger_threshold", ripple_trigger)
                    ripple_retrigger_gap = cfg_effect_float(config, "ripple", "retrigger_gap_ms", ripple_retrigger_gap * 1000.0) / 1000.0
                    ripple_charge = cfg_effect_float(config, "ripple", "charge_ms", ripple_charge * 1000.0) / 1000.0
                    ripple_min_radius = cfg_effect_float(config, "ripple", "min_radius", ripple_min_radius)
                    ripple_max_radius = cfg_effect_float(config, "ripple", "max_radius", ripple_max_radius)
                    ripple_min_duration = cfg_effect_float(config, "ripple", "min_duration", ripple_min_duration)
                    ripple_max_duration = cfg_effect_float(config, "ripple", "max_duration", ripple_max_duration)
                    ripple_brightness = cfg_effect_float(config, "ripple", "brightness", ripple_brightness)
                    ripple_width = cfg_effect_float(config, "ripple", "width", ripple_width)
                    pressure_color_floor = cfg_effect_float(config, "pressure_dent", "color_floor", pressure_color_floor)
                    pressure_space_color_floor = cfg_effect_float(config, "pressure_dent", "space_color_floor", pressure_space_color_floor)
                    pressure_state.configure(config)
                    frame_time = 1.0 / max(1.0, args.fps)
                    if abs(args.radius - old_radius) > 0.01:
                        distance_cache = build_distance_cache(normalized, KEY_LAMP_COUNT, LAMP_COUNT, max_radius=max(18.0, args.radius + 4.0))
                    print(f"config reloaded: effect={args.effect} theme={args.theme} brightness={args.brightness:.2f} radius={args.radius:.1f}", flush=True)
            if now - last_frame < frame_time:
                time.sleep(min(0.005, frame_time - (now - last_frame)))
                continue
            last_frame = now
            pressures, flashes = pressure_state.tick_decay()
            for key_id, pressure in pressures.items():
                prev = previous_pressures.get(key_id, 0.0)
                if pressure >= ripple_trigger and (prev < ripple_trigger * 0.72 or now - last_ripple_at.get(key_id, -999.0) >= ripple_retrigger_gap):
                    strength = clamp01(pressure)
                    max_radius, duration = ripple_params(strength, ripple_min_radius, ripple_max_radius, ripple_min_duration, ripple_max_duration)
                    active_ripples.append(
                        ActiveRipple(
                            key_id=key_id,
                            started_at=now,
                            strength=strength,
                            max_radius=max_radius,
                            duration=duration,
                            charge_until=now + ripple_charge,
                            hold_factor=0.04,
                        )
                    )
                    last_ripple_at[key_id] = now
                else:
                    for ripple in reversed(active_ripples):
                        if ripple.key_id == key_id and now <= ripple.charge_until:
                            charge_total = max(0.001, ripple.charge_until - ripple.started_at)
                            ripple.hold_factor = max(ripple.hold_factor, clamp01((now - ripple.started_at) / charge_total))
                            if pressure > ripple.strength:
                                ripple.strength = clamp01(pressure)
                                ripple.max_radius, ripple.duration = ripple_params(ripple.strength, ripple_min_radius, ripple_max_radius, ripple_min_duration, ripple_max_duration)
                            break
                previous_pressures[key_id] = pressure
            for key_id in list(previous_pressures.keys()):
                if key_id not in pressures:
                    previous_pressures[key_id] *= 0.82
                    if previous_pressures[key_id] < 0.02:
                        previous_pressures.pop(key_id, None)
            active_ripples = [r for r in active_ripples if now - r.started_at < r.duration]
            audio = audio_state.snapshot()
            audio = AudioSnapshot(
                [clamp01(value * audio_sensitivity) for value in audio.spectrum],
                clamp01(audio.level * audio_sensitivity),
                clamp01(audio.bass * bass_sensitivity),
            )
            if args.effect == "static":
                frame = render_static(theme)
            elif args.effect == "breathing":
                frame = render_breathing(theme, now, breathing_speed, breathing_depth)
            elif args.effect == "rainbow":
                frame = render_rainbow(theme, normalized, now, rainbow_style, rainbow_speed, rainbow_saturation, rainbow_value)
            elif args.effect == "ripple":
                frame = render_ripple_effect(theme, normalized, active_ripples, now, ripple_brightness, ripple_width)
            elif args.effect == "audio_ambient":
                frame = render_audio_ambient(theme, audio, peak_hold, now, side_vu_strength, backplate_ambience_strength, backplate_shockwave_strength, audio_side_curve, backplate_motion)
            elif args.effect == "pressure_dent":
                frame = render_static(theme)
                render_keys(frame, theme, normalized, distance_cache, pressures, flashes, audio.bass, args.radius, pressure_color_floor, pressure_space_color_floor)
            else:
                frame = compose_frame(
                    theme,
                    normalized,
                    distance_cache,
                    pressures,
                    flashes,
                    audio,
                    peak_hold,
                    args.radius,
                    now,
                    side_vu_strength,
                    backplate_ambience_strength,
                    backplate_shockwave_strength,
                    pressure_color_floor,
                    pressure_space_color_floor,
                    audio_side_curve,
                    backplate_motion,
                )
            frame = scale_frame(frame, args.brightness)
            if sender is not None:
                sender.send_frame(frame, include_begin=False)
            frames += 1
            if now >= next_report:
                status_line = f"frames={frames} pressure_rows={pressure_state.rows} press_rows={pressure_state.press_rows} active_keys={len(pressures)} audio_mode={audio_state.mode} audio_level={audio.level:.3f} bass={audio.bass:.3f}"
                print(status_line, flush=True)
                with status_log_path.open("a", encoding="utf-8") as status_log:
                    status_log.write(status_line + "\n")
                next_report = now + 5.0
    except KeyboardInterrupt:
        print("stopping...", flush=True)
    finally:
        stop_event.set()
        audio_state.close()
        if pressure_proc is not None:
            pressure_proc.terminate()
            try:
                pressure_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                pressure_proc.kill()
        if sender is not None:
            if not args.no_final_black:
                try:
                    sender.send_frame([BLACK] * LAMP_COUNT, include_begin=False)
                except Exception as exc:
                    print(f"WARN failed to clear lights: {exc}", flush=True)
            sender.close()
    print(f"done frames={frames} pressure_rows={pressure_state.rows} press_rows={pressure_state.press_rows}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
