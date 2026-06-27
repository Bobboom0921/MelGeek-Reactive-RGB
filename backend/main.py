"""
MelGeek Reactive RGB - WebView2 Desktop App
"""

import math
import os
import sys
import threading
import json
import time
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler
import socketserver
import logging
from logging.handlers import RotatingFileHandler

from config_migrator import migrate_v1_to_v2
from effect_registry import create_effect
from zone_effect import RenderContext
from zone_renderer import ZoneRenderer
from new_effects import *  # 确保新灯效类被加载到注册表

# ── Logging ──
_LOG_DIR = Path(__file__).resolve().parents[1] / "outputs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)
_log_handler = RotatingFileHandler(
    _LOG_DIR / "melgeek_reactive.log",
    maxBytes=10 * 1024 * 1024,
    backupCount=3,
    encoding="utf-8",
)
_log_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
logger = logging.getLogger("melgeek")
logger.setLevel(logging.INFO)
logger.addHandler(_log_handler)

# ── Paths ──
if getattr(sys, 'frozen', False):
    # PyInstaller: 静态资源在临时解压目录，配置文件在 EXE 旁边
    BASE_DIR = Path(sys.executable).resolve().parent
    UI_DIR = Path(sys._MEIPASS) / "ui"
else:
    BASE_DIR = Path(__file__).resolve().parents[1]
    UI_DIR = BASE_DIR / "ui"

CONFIG_PATH = BASE_DIR / "reactive_config.json"

# ── Config ──
HOST = "127.0.0.1"
PORT = 0  # auto-assign

# ── HTTP Server for UI ──
class NoCacheHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(UI_DIR), **kwargs)

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
        super().end_headers()

    def log_message(self, format, *args):
        pass  # suppress logs

    def send_json(self, data: dict):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

def find_free_port() -> int:
    with socketserver.TCPServer((HOST, 0), None) as s:
        return s.server_address[1]

def start_server(engine_instance=None) -> str:
    port = find_free_port()

    class _Handler(NoCacheHandler):
        def do_GET(self):
            if self.path == "/api/frame":
                if engine_instance:
                    self.send_json({"colors": engine_instance.get_frame()})
                else:
                    self.send_json({"colors": [[0, 0, 0]] * 70})
                return
            elif self.path == "/api/full_frame":
                if engine_instance:
                    self.send_json({"colors": engine_instance.get_full_frame()})
                else:
                    self.send_json({"colors": [[0, 0, 0]] * 285})
                return
            elif self.path == "/api/config":
                cfg = load_config()
                self.send_json(cfg)
                return
            elif self.path == "/api/schema":
                if engine_instance:
                    from effect_registry import list_effects
                    self.send_json({
                        "params": PreviewEngine.PARAM_SCHEMA,
                        "colors": PreviewEngine.COLOR_SCHEMA,
                        "theme_defaults": PreviewEngine._build_theme_colors(),
                        "effects": {
                            "keys": list_effects("keys"),
                            "backplate": list_effects("backplate"),
                            "sides": list_effects("sides"),
                        },
                    })
                else:
                    self.send_json({"params": {}, "colors": {}, "theme_defaults": {}, "effects": {}})
                return
            elif self.path == "/api/status":
                if engine_instance:
                    self.send_json(engine_instance.get_status())
                else:
                    self.send_json({"core": "stopped", "pressure": "off", "audio": "off", "keyboard": "disconnected", "fps": 0})
                return
            super().do_GET()

        def do_POST(self):
            if self.path.startswith("/api/"):
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length) if content_length > 0 else b"{}"
                try:
                    payload = json.loads(body)
                except json.JSONDecodeError:
                    payload = {}

                if self.path == "/api/effect/start":
                    if engine_instance:
                        engine_instance.start()
                    self.send_json({"ok": True})
                elif self.path == "/api/effect/stop":
                    if engine_instance:
                        engine_instance.stop()
                    self.send_json({"ok": True})
                elif self.path == "/api/effect/set":
                    if engine_instance:
                        engine_instance.set_params(
                            effect=payload.get("effect"),
                            theme=payload.get("theme"),
                            brightness=payload.get("brightness"),
                            radius=payload.get("radius"),
                        )
                    self.send_json({"ok": True})
                elif self.path == "/api/effect/inject":
                    if engine_instance:
                        engine_instance.inject_key(
                            payload.get("key_id", 0),
                            payload.get("pressure", 0.85),
                        )
                    self.send_json({"ok": True})
                elif self.path == "/api/config/update":
                    if engine_instance:
                        engine_instance.update_config(payload)
                    self.send_json({"ok": True})
                elif self.path == "/api/effect/set_zone":
                    if engine_instance:
                        engine_instance.set_zone_config(payload)
                    self.send_json({"ok": True})
                else:
                    self.send_error(404)
                return
            self.send_error(404)

    httpd = HTTPServer((HOST, port), _Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return f"http://{HOST}:{port}"

# ── API Bridge (WebView2 -> Python) ──
api_callbacks = {}

def register_api(name: str):
    def decorator(fn):
        api_callbacks[name] = fn
        return fn
    return decorator

def handle_api_call(payload: dict) -> dict:
    method = payload.get("method")
    args = payload.get("args", {})
    if method in api_callbacks:
        try:
            return {"ok": True, "data": api_callbacks[method](**args)}
        except Exception as e:
            return {"ok": False, "error": str(e)}
    return {"ok": False, "error": f"Unknown method: {method}"}

# ── Load / Save Config ──
def load_config() -> dict:
    try:
        if CONFIG_PATH.exists():
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}

def _round_floats(obj):
    if isinstance(obj, float):
        return round(obj, 6)
    if isinstance(obj, dict):
        return {k: _round_floats(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_round_floats(v) for v in obj]
    return obj


def save_config(cfg: dict):
    CONFIG_PATH.write_text(
        json.dumps(_round_floats(cfg), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

# ── API Implementations ──
@register_api("config.load")
def api_config_load():
    return load_config()

@register_api("config.save")
def api_config_save(**kwargs):
    save_config(kwargs.get("config", {}))
    return {"saved": True}

@register_api("effect.start")
def api_effect_start(**kwargs):
    if _engine_instance is not None:
        _engine_instance.start()
    return {"started": True}

@register_api("effect.stop")
def api_effect_stop(**kwargs):
    if _engine_instance is not None:
        _engine_instance.stop()
    return {"stopped": True}

@register_api("effect.set")
def api_effect_set(**kwargs):
    if _engine_instance is not None:
        _engine_instance.set_params(
            effect=kwargs.get("effect"),
            theme=kwargs.get("theme"),
            brightness=kwargs.get("brightness"),
            radius=kwargs.get("radius"),
        )
    return {"set": True}

@register_api("effect.inject")
def api_effect_inject(**kwargs):
    if _engine_instance is not None:
        _engine_instance.inject_key(
            kwargs.get("key_id", 0),
            kwargs.get("pressure", 0.85),
        )
    return {"injected": True}

@register_api("effect.status")
def api_effect_status(**kwargs):
    if _engine_instance is None:
        return {"running": False}
    return {
        "running": _engine_instance.running,
        "effect": _engine_instance.effect,
        "theme": _engine_instance.theme_name,
        "brightness": _engine_instance.brightness,
        "radius": _engine_instance.radius,
    }

@register_api("system.info")
def api_system_info(**kwargs):
    return {
        "version": "2.1.0",
        "platform": sys.platform,
        "webview": True,
    }

# ── Preview Engine ──
class PreviewEngine:
    """完整灯效引擎：压力读取 + 音频捕获 + 渲染 + HID 发送到键盘 + UI 预览

    支持配置热重载：每 0.5s 检查 reactive_config.json，变化时自动重新加载。
    支持 API 动态更新任意参数，变更即时生效。
    """

    # 每个 effect 对应的参数分组定义（供 UI 渲染用）
    # 原则：只放该灯效 render 函数真正读取的参数
    PARAM_SCHEMA = {
        "breathing": [
            {"key": "effects.breathing.speed", "label": "呼吸速度", "min": 0.2, "max": 3, "step": 0.05, "fmt": "{:.2f}", "section": "effects"},
            {"key": "effects.breathing.depth", "label": "呼吸幅度", "min": 0, "max": 1, "step": 0.02, "fmt": "{:.0%}", "section": "effects"},
        ],
        "rainbow": [
            {"key": "effects.rainbow.style", "label": "彩虹样式", "type": "select", "options": ["diagonal", "horizontal", "vertical", "radial", "dual", "pastel"], "section": "effects"},
            {"key": "effects.rainbow.speed", "label": "流动速度", "min": 0.05, "max": 5, "step": 0.05, "fmt": "{:.2f}", "section": "effects"},
            {"key": "effects.rainbow.saturation", "label": "色彩饱和度", "min": 0, "max": 1, "step": 0.02, "fmt": "{:.0%}", "section": "effects"},
            {"key": "effects.rainbow.value", "label": "彩虹亮度", "min": 0, "max": 1, "step": 0.02, "fmt": "{:.0%}", "section": "effects"},
        ],
        "ripple": [
            {"key": "effects.ripple.trigger_threshold", "label": "触发阈值", "min": 0.01, "max": 0.8, "step": 0.01, "fmt": "{:.2f}", "section": "effects"},
            {"key": "effects.ripple.retrigger_gap_ms", "label": "连击间隔 ms", "min": 0, "max": 300, "step": 5, "fmt": "{:.0f}", "section": "effects"},
            {"key": "effects.ripple.charge_ms", "label": "蓄力时间 ms", "min": 0, "max": 500, "step": 10, "fmt": "{:.0f}", "section": "effects"},
            {"key": "effects.ripple.brightness", "label": "涟漪亮度", "min": 0, "max": 3, "step": 0.05, "fmt": "{:.2f}", "section": "effects"},
            {"key": "effects.ripple.width", "label": "涟漪宽度", "min": 0.2, "max": 4, "step": 0.05, "fmt": "{:.2f}", "section": "effects"},
            {"key": "effects.ripple.min_radius", "label": "最小半径", "min": 1, "max": 40, "step": 1, "fmt": "{:.0f}", "section": "effects", "advanced": True},
            {"key": "effects.ripple.max_radius", "label": "最大半径", "min": 5, "max": 140, "step": 1, "fmt": "{:.0f}", "section": "effects", "advanced": True},
            {"key": "effects.ripple.min_duration", "label": "最短时长", "min": 0.1, "max": 3, "step": 0.05, "fmt": "{:.2f}", "section": "effects", "advanced": True},
            {"key": "effects.ripple.max_duration", "label": "最长时长", "min": 0.2, "max": 5, "step": 0.05, "fmt": "{:.2f}", "section": "effects", "advanced": True},
        ],
        "pressure_dent": [
            {"key": "global.radius", "label": "压力扩散", "min": 4, "max": 30, "step": 0.5, "fmt": "{:.1f}", "section": "global"},
            {"key": "effects.pressure_dent.attack", "label": "按下跟手", "min": 0.01, "max": 1, "step": 0.01, "fmt": "{:.0%}", "section": "effects"},
            {"key": "effects.pressure_dent.release", "label": "释放回弹", "min": 0.01, "max": 1, "step": 0.01, "fmt": "{:.0%}", "section": "effects"},
            {"key": "effects.pressure_dent.color_floor", "label": "周边染色", "min": 0, "max": 1, "step": 0.01, "fmt": "{:.0%}", "section": "effects"},
            {"key": "effects.pressure_dent.space_color_floor", "label": "空格染色", "min": 0, "max": 1, "step": 0.01, "fmt": "{:.0%}", "section": "effects", "advanced": True},
            {"key": "effects.pressure_dent.input_deadzone", "label": "输入死区", "min": 0, "max": 0.1, "step": 0.001, "fmt": "{:.3f}", "section": "effects", "advanced": True},
            {"key": "effects.pressure_dent.jitter_deadzone", "label": "细抖过滤", "min": 0, "max": 0.1, "step": 0.001, "fmt": "{:.3f}", "section": "effects", "advanced": True},
            {"key": "effects.pressure_dent.small_change_attack", "label": "微变化跟随", "min": 0, "max": 0.5, "step": 0.005, "fmt": "{:.3f}", "section": "effects", "advanced": True},
        ],
        "audio_ambient": [
            {"key": "audio.sensitivity", "label": "音频灵敏度", "min": 0, "max": 3, "step": 0.05, "fmt": "{:.2f}", "section": "audio"},
            {"key": "audio.bass_sensitivity", "label": "低频灵敏度", "min": 0, "max": 3, "step": 0.05, "fmt": "{:.2f}", "section": "audio"},
            {"key": "audio.backplate_shockwave_strength", "label": "低频冲击", "min": 0, "max": 3, "step": 0.05, "fmt": "{:.2f}", "section": "audio"},
            {"key": "audio.side_vu_strength", "label": "侧边 VU", "min": 0, "max": 3, "step": 0.05, "fmt": "{:.2f}", "section": "audio", "advanced": True},
            {"key": "audio.backplate_ambience_strength", "label": "背板氛围", "min": 0, "max": 3, "step": 0.05, "fmt": "{:.2f}", "section": "audio", "advanced": True},
            {"key": "effects.audio_ambient.silence_gate", "label": "静音门限", "min": 0, "max": 0.03, "step": 0.0005, "fmt": "{:.4f}", "section": "effects", "advanced": True},
            {"key": "effects.audio_ambient.side_vu_curve", "label": "VU 曲线", "min": 0.25, "max": 1.5, "step": 0.01, "fmt": "{:.2f}", "section": "effects", "advanced": True},
            {"key": "effects.audio_ambient.backplate_motion", "label": "背板运动", "min": 0, "max": 2, "step": 0.05, "fmt": "{:.2f}", "section": "effects", "advanced": True},
        ],
        "premium_reactive": [
            # 基础 - global
            {"key": "global.brightness", "label": "整体亮度", "min": 0, "max": 1, "step": 0.01, "fmt": "{:.0%}", "section": "global"},
            {"key": "global.radius", "label": "压力扩散", "min": 4, "max": 30, "step": 0.5, "fmt": "{:.1f}", "section": "global"},
            # 基础 - 压力
            {"key": "effects.pressure_dent.attack", "label": "按下跟手", "min": 0.01, "max": 1, "step": 0.01, "fmt": "{:.0%}", "section": "effects"},
            {"key": "effects.pressure_dent.release", "label": "释放回弹", "min": 0.01, "max": 1, "step": 0.01, "fmt": "{:.0%}", "section": "effects"},
            {"key": "effects.pressure_dent.color_floor", "label": "压力染色", "min": 0, "max": 1, "step": 0.01, "fmt": "{:.0%}", "section": "effects"},
            # 基础 - 音频
            {"key": "audio.sensitivity", "label": "音频灵敏度", "min": 0, "max": 3, "step": 0.05, "fmt": "{:.2f}", "section": "audio"},
            {"key": "audio.bass_sensitivity", "label": "低频灵敏度", "min": 0, "max": 3, "step": 0.05, "fmt": "{:.2f}", "section": "audio"},
            {"key": "audio.backplate_shockwave_strength", "label": "低频冲击", "min": 0, "max": 3, "step": 0.05, "fmt": "{:.2f}", "section": "audio"},
            # 高级 - 压力
            {"key": "effects.pressure_dent.input_deadzone", "label": "输入死区", "min": 0, "max": 0.1, "step": 0.001, "fmt": "{:.3f}", "section": "effects", "advanced": True},
            {"key": "effects.pressure_dent.jitter_deadzone", "label": "细抖过滤", "min": 0, "max": 0.1, "step": 0.001, "fmt": "{:.3f}", "section": "effects", "advanced": True},
            {"key": "effects.pressure_dent.small_change_attack", "label": "微变化跟随", "min": 0, "max": 0.5, "step": 0.005, "fmt": "{:.3f}", "section": "effects", "advanced": True},
            {"key": "effects.pressure_dent.space_color_floor", "label": "空格染色", "min": 0, "max": 1, "step": 0.01, "fmt": "{:.0%}", "section": "effects", "advanced": True},
            # 高级 - 音频
            {"key": "audio.side_vu_strength", "label": "侧边 VU", "min": 0, "max": 3, "step": 0.05, "fmt": "{:.2f}", "section": "audio", "advanced": True},
            {"key": "audio.backplate_ambience_strength", "label": "背板氛围", "min": 0, "max": 3, "step": 0.05, "fmt": "{:.2f}", "section": "audio", "advanced": True},
            {"key": "effects.audio_ambient.silence_gate", "label": "静音门限", "min": 0, "max": 0.03, "step": 0.0005, "fmt": "{:.4f}", "section": "effects", "advanced": True},
            {"key": "effects.audio_ambient.side_vu_curve", "label": "VU 曲线", "min": 0.25, "max": 1.5, "step": 0.01, "fmt": "{:.2f}", "section": "effects", "advanced": True},
            {"key": "effects.audio_ambient.backplate_motion", "label": "背板运动", "min": 0, "max": 2, "step": 0.05, "fmt": "{:.2f}", "section": "effects", "advanced": True},
        ],
        "static": [],
    }

    # 主题默认颜色（HEX，供前端色卡显示）
    @staticmethod
    def _hsv_to_hex(h: float, s: float, v: float) -> str:
        h = h % 360.0
        s = max(0.0, min(1.0, s))
        v = max(0.0, min(1.0, v))
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
        return f"#{int((r + m) * 255):02x}{int((g + m) * 255):02x}{int((b + m) * 255):02x}"

    THEME_DEFAULT_COLORS = {}

    @classmethod
    def _build_theme_colors(cls):
        if cls.THEME_DEFAULT_COLORS:
            return cls.THEME_DEFAULT_COLORS
        from melgeek68_premium_reactive import THEMES
        for theme in THEMES:
            name_key = theme.name.split()[0].lower()
            if name_key in ("noir", "cyberpunk"):
                alias = "noir"
            elif name_key in ("void", "luxury"):
                alias = "void"
            elif name_key in ("arctic", "phantom"):
                alias = "arctic"
            elif name_key in ("midnight", "ember"):
                alias = "ember"
            elif name_key in ("pure", "eclipse"):
                alias = "eclipse"
            else:
                alias = name_key
            light_hsv = theme.dent_levels[0][1]
            mid_hsv = theme.dent_levels[1][1]
            deep_hsv = theme.dent_levels[2][1]
            cls.THEME_DEFAULT_COLORS[alias] = {
                "base_hsv": cls._hsv_to_hex(*theme.base_hsv),
                "outer_base_hsv": cls._hsv_to_hex(*theme.outer_base_hsv),
                "press_light_hsv": cls._hsv_to_hex(*light_hsv),
                "press_mid_hsv": cls._hsv_to_hex(*mid_hsv),
                "press_deep_hsv": cls._hsv_to_hex(*deep_hsv),
                "outer_low_hsv": cls._hsv_to_hex(*theme.outer_low_hsv),
                "outer_high_hsv": cls._hsv_to_hex(*theme.outer_high_hsv),
                "bass_pulse_hsv": cls._hsv_to_hex(*theme.bass_pulse_hsv),
            }
        return cls.THEME_DEFAULT_COLORS

    # 每个 effect 对应的颜色配置项
    COLOR_SCHEMA = {
        "static": ["base_hsv", "outer_base_hsv", "press_deep_hsv", "outer_low_hsv", "outer_high_hsv"],
        "breathing": ["base_hsv", "press_deep_hsv", "outer_base_hsv", "bass_pulse_hsv"],
        "rainbow": [],
        "ripple": ["base_hsv", "press_deep_hsv"],
        "pressure_dent": ["base_hsv", "press_light_hsv", "press_mid_hsv", "press_deep_hsv"],
        "audio_ambient": ["outer_base_hsv", "bass_pulse_hsv", "outer_low_hsv", "outer_high_hsv"],
        "premium_reactive": ["base_hsv", "press_light_hsv", "press_mid_hsv", "press_deep_hsv", "outer_base_hsv", "bass_pulse_hsv", "outer_low_hsv", "outer_high_hsv"],
    }

    def __init__(self, config: dict | None = None, config_path: Path | None = None):
        self.lock = threading.Lock()
        self.frame = [(0, 0, 0)] * 70
        self.full_frame = [(0, 0, 0)] * 285
        self.running = False
        self.thread = None
        self._stop_event = threading.Event()

        # 配置
        self.config = config or {}
        self.config_path = config_path
        self._config_mtime = 0.0
        self._config_version = 0  # 每次配置更新递增，供 _loop 检测
        self._live_config_version = 0
        if self.config_path and self.config_path.exists():
            self._config_mtime = self.config_path.stat().st_mtime

        # 运行时可调参数（可被 API 直接修改，每帧被 _loop 读取）
        self.effect = self.config.get("effect", "premium_reactive")
        self.theme_name = self.config.get("theme", "noir")
        self.brightness = float(self.config.get("global", {}).get("brightness", 1.0))
        self.radius = float(self.config.get("global", {}).get("radius", 13.0))

        # 状态信息（供 UI 轮询）
        self.status_info = {
            "core": "stopped",
            "pressure": "off",
            "audio": "off",
            "keyboard": "disconnected",
            "fps": 0,
        }

        self.has_engine = False
        self._sender = None
        self._pressure_state = None
        self._audio_state = None

    def start(self):
        if self.running:
            return
        self._start()
        self.running = True
        self._stop_event.clear()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        self._stop_event.set()

    def set_params(self, effect=None, theme=None, brightness=None, radius=None):
        """API 入口：即时更新简单参数。"""
        with self.lock:
            if effect is not None:
                self.effect = effect
                self.config["effect"] = effect
            if theme is not None:
                self.theme_name = theme
                self.config["theme"] = theme
            if brightness is not None:
                self.brightness = max(0.0, min(1.0, float(brightness)))
                self.config.setdefault("global", {})["brightness"] = self.brightness
            if radius is not None:
                self.radius = max(1.0, float(radius))
                self.config.setdefault("global", {})["radius"] = self.radius
            self._bump_config_version()

    def set_zone_config(self, zones_config: dict):
        """API 入口：批量更新区域配置。"""
        with self.lock:
            self.config.setdefault("zones", {})
            for zone_name, zone_cfg in zones_config.items():
                self.config["zones"][zone_name] = zone_cfg
            self._bump_config_version()
        if self.config_path:
            try:
                self.config_path.write_text(
                    json.dumps(self.config, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except Exception as exc:
                logger.warning(f"Engine: failed to save zone config: {exc}")

    def update_config(self, updates: dict):
        """API 入口：批量更新配置（支持嵌套 key 如 effects.pressure_dent.attack）。"""
        with self.lock:
            self._deep_update(self.config, updates)
            # 同步顶层快捷属性
            self.effect = self.config.get("effect", self.effect)
            self.theme_name = self.config.get("theme", self.theme_name)
            self.brightness = float(self.config.get("global", {}).get("brightness", self.brightness))
            self.radius = float(self.config.get("global", {}).get("radius", self.radius))
            self._bump_config_version()
        # 保存到文件
        if self.config_path:
            try:
                self.config_path.write_text(
                    json.dumps(self.config, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                self._config_mtime = self.config_path.stat().st_mtime
            except Exception as exc:
                logger.warning(f"Engine: failed to save config: {exc}")

    def _bump_config_version(self):
        self._config_version += 1

    def _deep_update(self, base: dict, override: dict):
        for k, v in override.items():
            if isinstance(v, dict) and isinstance(base.get(k), dict):
                self._deep_update(base[k], v)
            else:
                base[k] = v

    @staticmethod
    def _config_changed(old: dict, new: dict) -> bool:
        """递归对比两个字典，忽略浮点精度差异（6位小数）。"""
        if type(old) != type(new):
            return True
        if isinstance(old, dict):
            if set(old.keys()) != set(new.keys()):
                return True
            return any(PreviewEngine._config_changed(old[k], new[k]) for k in old)
        if isinstance(old, list):
            if len(old) != len(new):
                return True
            return any(PreviewEngine._config_changed(a, b) for a, b in zip(old, new))
        if isinstance(old, float):
            return not math.isclose(old, new, rel_tol=1e-6, abs_tol=1e-6)
        return old != new

    def _check_config_reload(self):
        """检查外部文件是否被修改，如果是则重新加载（仅当值真正变化时）。"""
        if not self.config_path or not self.config_path.exists():
            return
        try:
            mtime = self.config_path.stat().st_mtime
            if mtime != self._config_mtime:
                new_config = json.loads(self.config_path.read_text(encoding="utf-8"))
                if not self._config_changed(self.config, new_config):
                    self._config_mtime = mtime
                    return
                self._config_mtime = mtime
                with self.lock:
                    self.config = new_config
                    self.effect = self.config.get("effect", self.effect)
                    self.theme_name = self.config.get("theme", self.theme_name)
                    self.brightness = float(self.config.get("global", {}).get("brightness", self.brightness))
                    self.radius = float(self.config.get("global", {}).get("radius", self.radius))
                    self._bump_config_version()
                logger.info(f"Engine: config reloaded from {self.config_path}")
        except Exception as exc:
            logger.warning(f"Engine: config reload failed: {exc}")

    def inject_key(self, key_id: int, pressure: float = 0.85):
        if self._pressure_state is not None:
            self._pressure_state.inject_key(key_id, pressure, flash=True)

    def get_frame(self):
        with self.lock:
            return [list(rgb) for rgb in self.frame]

    def get_full_frame(self):
        with self.lock:
            return [list(rgb) for rgb in self.full_frame]

    def get_status(self):
        with self.lock:
            return dict(self.status_info)

    def _start(self):
        try:
            import hid
        except ImportError:
            raise RuntimeError(
                "缺少 hidapi 依赖。\n\n"
                "请先安装依赖：\n"
                "  pip install hidapi\n\n"
                "或者运行 install_deps.bat"
            )
        try:
            from melgeek68_premium_reactive import (
                select_theme, PressureState, AudioState, KEY_LAMP_COUNT, LAMP_COUNT,
            )
            from melgeek68_direct_hid import DirectHidSender
            sender = DirectHidSender()
            sender.open()
            sender.close()
            self.has_engine = True
        except Exception as exc:
            raise RuntimeError(
                f"当前设备不兼容：无法加载灯效引擎或找不到 MelGeek 键盘。\n\n"
                f"错误详情：{exc}\n\n"
                f"请确认：\n"
                f"1. 已连接 MelGeek 键盘（通过 USB，不是蓝牙）\n"
                f"2. 已安装 hidapi 驱动"
            ) from exc

    def _fallback_positions(self):
        try:
            from melgeek68_premium_reactive import LampPosition
        except Exception:
            return []
        positions = []
        for i in range(15):
            positions.append(LampPosition(i, i * 19000, 0, 3950))
        for i in range(15):
            positions.append(LampPosition(15 + i, i * 19000, 19000, 5610))
        for i in range(14):
            positions.append(LampPosition(30 + i, i * 19000 + 9500, 38000, 7270))
        for i in range(14):
            positions.append(LampPosition(44 + i, i * 19000 + 9500, 57000, 8930))
        for i in range(10):
            positions.append(LampPosition(58 + i, i * 19000 + 9500, 76000, 10590))
        for i in range(70, 285):
            positions.append(LampPosition(i, i * 1000, 90000, 830))
        return positions

    def _read_cfg_value(self, config: dict, key_path: str, default):
        """读取嵌套配置值，如 'effects.pressure_dent.attack'。"""
        keys = key_path.split(".")
        val = config
        for k in keys:
            if isinstance(val, dict):
                val = val.get(k)
            else:
                return default
        return val if val is not None else default

    def _build_renderer(self, zones_cfg: dict, theme) -> ZoneRenderer:
        """根据 zones 配置构建 ZoneRenderer。"""
        def get_effect(zone_name: str, slot: str):
            cfg = zones_cfg.get(zone_name, {})
            slot_cfg = cfg.get(slot)
            if slot_cfg is None:
                return None
            name = slot_cfg.get("effect", "")
            eff = create_effect(name)
            if eff is not None:
                # 注入 params
                eff._params = slot_cfg.get("params", {})
            return eff

        return ZoneRenderer(
            keys_base=get_effect("keys", "base"),
            keys_reactive=get_effect("keys", "reactive"),
            keys_blend=zones_cfg.get("keys", {}).get("blend_mode", "normal"),
            backplate_base=get_effect("backplate", "base"),
            backplate_reactive=get_effect("backplate", "reactive"),
            backplate_blend=zones_cfg.get("backplate", {}).get("blend_mode", "normal"),
            sides_base=get_effect("sides", "base"),
            sides_reactive=get_effect("sides", "reactive"),
            sides_blend=zones_cfg.get("sides", {}).get("blend_mode", "normal"),
        )

    def _loop(self):
        from melgeek68_premium_reactive import (
            load_params_from_cache, normalize_positions, build_distance_cache,
            PressureState, AudioState, AudioSnapshot, ActiveRipple,
            select_theme, theme_with_overrides,
            render_static, render_breathing, render_rainbow,
            render_ripple_effect, render_audio_ambient, compose_frame,
            render_keys, render_backplate, render_sides,
            clamp01, scale_frame, BLACK, KEY_LAMP_COUNT, LAMP_COUNT, BACKPLATE_COLUMNS,
            ripple_params, cfg_float, cfg_effect_float,
            native_pressure_reader, keyboard_fallback_reader,
            hsv_to_rgb,
        )
        from melgeek68_direct_hid import DirectHidSender

        class _Args:
            pressure_min_delta = 12.0
            pressure_interval_ms = 12.0
            full_delta = 1100.0
        args = _Args()

        config = self.config

        # 加载灯位参数
        try:
            positions, lamp_count = load_params_from_cache()
        except Exception as exc:
            logger.warning(f"Engine: failed to load params: {exc}")
            positions = []
        if not positions:
            positions = self._fallback_positions()

        normalized = normalize_positions(positions, LAMP_COUNT)
        distance_cache = build_distance_cache(
            normalized, KEY_LAMP_COUNT, LAMP_COUNT, max_radius=max(18.0, self.radius + 4.0)
        )
        peak_hold = [0.0] * BACKPLATE_COLUMNS

        # 压力
        self._pressure_state = PressureState()
        self._pressure_state.configure(config)
        self._stop_event.clear()
        threading.Thread(
            target=native_pressure_reader,
            args=(args, self._pressure_state, self._stop_event),
            daemon=True,
        ).start()
        threading.Thread(
            target=keyboard_fallback_reader,
            args=(self._pressure_state, self._stop_event),
            daemon=True,
        ).start()

        # 音频
        audio_mode = str((config.get("audio") or {}).get("mode", "loopback"))
        audio_silence_gate = cfg_effect_float(config, "audio_ambient", "silence_gate", 0.0045)
        self._audio_state = AudioState(enabled=True, mode=audio_mode, silence_gate=audio_silence_gate)
        self._audio_state.start()

        # HID
        self._sender = DirectHidSender()

        # 运行时变量（每帧可能因配置更新而变化）
        theme = select_theme(self.theme_name)
        theme = theme_with_overrides(theme, config)

        active_ripples = []
        previous_pressures = {}
        last_ripple_at = {}

        frame_time = 1.0 / 30.0
        last_frame = 0.0
        frames = 0
        fps_timer = time.time()
        next_config_check = 0.0
        last_config_version = -1

        try:
            self._sender.send_frame(
                scale_frame([hsv_to_rgb(*theme.base_hsv)] * LAMP_COUNT, self.brightness),
                include_begin=True,
            )
            with self.lock:
                self.status_info["keyboard"] = "connected"
        except Exception as exc:
            logger.warning(f"Engine: failed to send initial frame: {exc}")

        while self.running and not self._stop_event.is_set():
            now = time.time()

            # 定期外部配置文件检查
            if now >= next_config_check:
                next_config_check = now + 0.5
                self._check_config_reload()

            # 检测配置版本变化（API 更新或文件重载）
            with self.lock:
                current_version = self._config_version
                effect = self.effect
                theme_name = self.theme_name
                brightness = self.brightness
                radius = self.radius
                live_config = dict(self.config)  # 浅拷贝供本帧使用

            if current_version != last_config_version:
                last_config_version = current_version
                # 配置变化时重新应用
                try:
                    theme = select_theme(theme_name)
                    theme = theme_with_overrides(theme, live_config)
                except Exception:
                    pass
                # 重新配置压力状态
                if self._pressure_state is not None:
                    self._pressure_state.configure(live_config)
                # 更新距离缓存（radius 可能变了）
                try:
                    distance_cache = build_distance_cache(
                        normalized, KEY_LAMP_COUNT, LAMP_COUNT,
                        max_radius=max(18.0, radius + 4.0)
                    )
                except Exception:
                    pass
                logger.info(f"Engine: config applied v{current_version} effect={effect} theme={theme_name}")

            if now - last_frame < frame_time:
                time.sleep(0.005)
                continue
            last_frame = now
            frames += 1

            # FPS 统计
            if now - fps_timer >= 1.0:
                with self.lock:
                    self.status_info["fps"] = round(frames / (now - fps_timer))
                frames = 0
                fps_timer = now

            # 从 live_config 读取所有参数（支持热更新）
            effects_cfg = live_config.get("effects") or {}
            rainbow_cfg = effects_cfg.get("rainbow") or {}
            breathing_cfg = effects_cfg.get("breathing") or {}
            breathing_speed = float(breathing_cfg.get("speed", 1.0))
            breathing_depth = float(breathing_cfg.get("depth", 1.0))
            rainbow_style = str(rainbow_cfg.get("style", "diagonal"))
            rainbow_speed = float(rainbow_cfg.get("speed", 1.0))
            rainbow_saturation = float(rainbow_cfg.get("saturation", 0.68))
            rainbow_value = float(rainbow_cfg.get("value", 0.62))
            ripple_trigger = self._read_cfg_value(live_config, "effects.ripple.trigger_threshold", 0.08)
            ripple_retrigger_gap = self._read_cfg_value(live_config, "effects.ripple.retrigger_gap_ms", 45) / 1000.0
            ripple_charge = self._read_cfg_value(live_config, "effects.ripple.charge_ms", 180) / 1000.0
            ripple_min_radius = self._read_cfg_value(live_config, "effects.ripple.min_radius", 8.0)
            ripple_max_radius = self._read_cfg_value(live_config, "effects.ripple.max_radius", 95.0)
            ripple_min_duration = self._read_cfg_value(live_config, "effects.ripple.min_duration", 0.75)
            ripple_max_duration = self._read_cfg_value(live_config, "effects.ripple.max_duration", 2.35)
            ripple_brightness = self._read_cfg_value(live_config, "effects.ripple.brightness", 1.0)
            ripple_width = self._read_cfg_value(live_config, "effects.ripple.width", 1.0)
            pressure_color_floor = self._read_cfg_value(live_config, "effects.pressure_dent.color_floor", 0.22)
            pressure_space_color_floor = self._read_cfg_value(live_config, "effects.pressure_dent.space_color_floor", 0.26)

            audio_sensitivity = float(live_config.get("audio", {}).get("sensitivity", 1.0))
            bass_sensitivity = float(live_config.get("audio", {}).get("bass_sensitivity", 1.0))
            side_vu_strength = float(live_config.get("audio", {}).get("side_vu_strength", 1.0))
            backplate_ambience_strength = float(live_config.get("audio", {}).get("backplate_ambience_strength", 1.0))
            backplate_shockwave_strength = float(live_config.get("audio", {}).get("backplate_shockwave_strength", 1.0))
            audio_side_curve = self._read_cfg_value(live_config, "effects.audio_ambient.side_vu_curve", 0.62)
            backplate_motion = self._read_cfg_value(live_config, "effects.audio_ambient.backplate_motion", 1.0)

            # 更新状态
            with self.lock:
                self.status_info["core"] = "running"
                self.status_info["pressure"] = "native"
                self.status_info["audio"] = self._audio_state.mode

            # 压力衰减
            pressures, flashes = self._pressure_state.tick_decay()

            # 涟漪触发
            for key_id, pressure in pressures.items():
                prev = previous_pressures.get(key_id, 0.0)
                if pressure >= ripple_trigger and (
                    prev < ripple_trigger * 0.72
                    or now - last_ripple_at.get(key_id, -999.0) >= ripple_retrigger_gap
                ):
                    strength = clamp01(pressure)
                    max_r, duration = ripple_params(
                        strength, ripple_min_radius, ripple_max_radius,
                        ripple_min_duration, ripple_max_duration,
                    )
                    active_ripples.append(
                        ActiveRipple(
                            key_id=key_id,
                            started_at=now,
                            strength=strength,
                            max_radius=max_r,
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
                            ripple.hold_factor = max(
                                ripple.hold_factor,
                                clamp01((now - ripple.started_at) / charge_total),
                            )
                            if pressure > ripple.strength:
                                ripple.strength = clamp01(pressure)
                                ripple.max_radius, ripple.duration = ripple_params(
                                    ripple.strength, ripple_min_radius, ripple_max_radius,
                                    ripple_min_duration, ripple_max_duration,
                                )
                            break
                previous_pressures[key_id] = pressure

            for key_id in list(previous_pressures.keys()):
                if key_id not in pressures:
                    previous_pressures[key_id] *= 0.82
                    if previous_pressures[key_id] < 0.02:
                        previous_pressures.pop(key_id, None)

            active_ripples = [r for r in active_ripples if now - r.started_at < r.duration]

            # 音频
            audio = self._audio_state.snapshot()
            audio = AudioSnapshot(
                [clamp01(v * audio_sensitivity) for v in audio.spectrum],
                clamp01(audio.level * audio_sensitivity),
                clamp01(audio.bass * bass_sensitivity),
            )

            # 确保配置是 v2 格式
            live_config = migrate_v1_to_v2(live_config)

            # 构建 ZoneRenderer
            zones_cfg = live_config.get("zones", {})
            renderer = self._build_renderer(zones_cfg, theme)

            # 构建 RenderContext
            ctx = RenderContext(
                now=now,
                theme=theme_name,
                audio={
                    "spectrum": audio.spectrum,
                    "level": audio.level,
                    "bass": audio.bass,
                },
                pressures=pressures,
                params={"_active_ripples": active_ripples, **live_config.get("effects", {})},
                normalized=normalized,
                lamp_count=285,
                distance_cache=distance_cache,
            )

            # 渲染
            try:
                frame = renderer.render_frame(ctx)
            except Exception as exc:
                logger.error(f"Engine: render error: {exc}")
                frame = [BLACK] * LAMP_COUNT

            frame = scale_frame(frame, brightness)

            # HID 发送
            try:
                self._sender.send_frame(frame, include_begin=False)
            except Exception as exc:
                logger.error(f"Engine: HID send error: {exc}")
                with self.lock:
                    self.status_info["keyboard"] = "error"

            # UI 预览
            with self.lock:
                self.frame = frame[:KEY_LAMP_COUNT]
                self.full_frame = frame

        # 清理
        self._audio_state.close()
        with self.lock:
            self.status_info["core"] = "stopped"
            self.status_info["audio"] = "off"
        try:
            self._sender.send_frame([BLACK] * LAMP_COUNT, include_begin=False)
        except Exception:
            pass
        try:
            self._sender.close()
        except Exception:
            pass
        logger.info("Engine: stopped")


# Module-level engine instance (set in main())
_engine_instance = None

# ── JS Bridge Injection ──
BRIDGE_JS = """
window.pybridge = {
  _id: 0,
  _pending: {},

  call(method, args = {}) {
    return new Promise((resolve, reject) => {
      const id = ++this._id;
      this._pending[id] = { resolve, reject };
      const msg = JSON.stringify({ id, method, args });
      if (window.chrome && window.chrome.webview) {
        window.chrome.webview.postMessage(msg);
      } else if (window.pywebview) {
        window.pywebview.api.call(method, args).then(resolve).catch(reject);
      } else {
        // Fallback: fetch to local API endpoint
        fetch('/api/' + method, {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify(args)
        })
        .then(r => r.json())
        .then(resolve)
        .catch(reject);
      }
    });
  },

  _onResponse(id, result) {
    const p = this._pending[id];
    if (p) {
      p.resolve(result);
      delete this._pending[id];
    }
  }
};

// Console redirect for debugging
const _log = console.log;
console.log = (...args) => {
  _log(...args);
  if (window.pybridge) {
    window.pybridge.call('log', { message: args.join(' ') }).catch(() => {});
  }
};
"""

# ── Tray Icon (Windows) ──
def setup_tray():
    if sys.platform != "win32":
        return
    try:
        import pystray
        from PIL import Image

        # Simple colored square icon
        from PIL import ImageDraw
        img = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle([4, 4, 60, 60], radius=14, fill=(0, 122, 255))
        draw.text((20, 18), "M", fill=(255, 255, 255), font=None)

        def on_show(icon, item):
            pass  # handled by window

        def on_quit(icon, item):
            icon.stop()
            os._exit(0)

        menu = pystray.Menu(
            pystray.MenuItem("显示控制面板", on_show),
            pystray.MenuItem("退出", on_quit),
        )
        icon = pystray.Icon("melgeek", img, "MelGeek Reactive RGB", menu)
        threading.Thread(target=icon.run, daemon=True).start()
    except ImportError:
        pass

# ── Main ──
def main():
    global _engine_instance

    # Load config
    config = load_config()

    # Start preview engine
    try:
        _engine_instance = PreviewEngine(config=config, config_path=CONFIG_PATH)
        _engine_instance.start()
    except RuntimeError as exc:
        logger.critical(f"FATAL: {exc}")
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "MelGeek Reactive RGB",
            f"{exc}\n\n请确认：\n1. 已连接 MelGeek 键盘\n2. 已安装 hidapi 驱动\n3. 已授予 USB HID 访问权限"
        )
        return 1

    # Start HTTP server
    url = start_server(engine_instance=_engine_instance)
    logger.info(f"UI server: {url}")

    # Setup tray
    setup_tray()

    # Launch WebView2 window
    try:
        import webview

        window = webview.create_window(
            "MelGeek Reactive RGB",
            url,
            width=1280,
            height=800,
            min_size=(1000, 640),
            text_select=False,
            confirm_close=False,
        )

        # Inject JS bridge on load
        def on_loaded():
            window.evaluate_js(BRIDGE_JS)

        webview.start(on_loaded, gui="edgechromium", debug=False)

    except ImportError:
        logger.error("ERROR: pywebview not installed.")
        logger.error("Run: pip install pywebview pystray pillow")
        input("Press Enter to exit...")
        return 1

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
