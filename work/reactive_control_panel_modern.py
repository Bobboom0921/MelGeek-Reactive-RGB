from __future__ import annotations

import colorsys
import json
import math
import queue
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QPainter, QPen, QBrush, QPalette, QAction, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QSystemTrayIcon,
    QMenu,
    QStyle,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
    WEBENGINE_AVAILABLE = True
except Exception:
    QWebEngineView = None
    WEBENGINE_AVAILABLE = False

ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "reactive_config.json"
CORE = ROOT / "work" / "melgeek68_premium_reactive.py"

EFFECTS = [
    ("static", "静态", "日常常亮底色"),
    ("breathing", "呼吸", "缓慢亮暗与色彩呼吸"),
    ("rainbow", "彩虹", "多种彩虹流动样式"),
    ("ripple", "涟漪", "按键压力触发水波"),
    ("pressure_dent", "压力热力", "磁轴深度热力凹陷"),
    ("audio_ambient", "音频氛围", "背板氛围 + 侧边 VU"),
    ("premium_reactive", "综合", "压力 + 音频综合效果"),
]
THEMES = ["noir", "void", "arctic", "ember", "eclipse"]
THEME_LABELS = {
    "noir": "Noir Cyberpunk",
    "void": "Void Luxury",
    "arctic": "Arctic Phantom",
    "ember": "Midnight Ember",
    "eclipse": "Pure Eclipse",
}
DEFAULT_CONFIG = {
    "theme": "noir",
    "effect": "premium_reactive",
    "ui": {"appearance": "system"},
    "global": {"brightness": 1.0, "radius": 16.0, "fps": 60},
    "audio": {"mode": "loopback", "sensitivity": 1.0, "bass_sensitivity": 1.0, "side_vu_strength": 1.0, "backplate_ambience_strength": 1.0, "backplate_shockwave_strength": 1.0},
    "effects": {
        "breathing": {"speed": 1.0, "depth": 1.0},
        "rainbow": {"style": "diagonal", "speed": 1.0, "saturation": 0.68, "value": 0.62},
        "ripple": {"trigger_threshold": 0.08, "retrigger_gap_ms": 45, "charge_ms": 180, "min_radius": 8.0, "max_radius": 95.0, "min_duration": 0.75, "max_duration": 2.35, "brightness": 1.0, "width": 1.0},
        "pressure_dent": {"input_deadzone": 0.008, "jitter_deadzone": 0.012, "attack": 0.42, "release": 0.28, "small_change_attack": 0.12, "color_floor": 0.22, "space_color_floor": 0.26},
        "audio_ambient": {"silence_gate": 0.0045, "side_vu_curve": 0.62, "backplate_motion": 1.0},
    },
    "colors": {"base_hsv": None, "outer_base_hsv": None, "press_light_hsv": None, "press_mid_hsv": None, "press_deep_hsv": None, "outer_low_hsv": None, "outer_high_hsv": None, "bass_pulse_hsv": None},
    "startup": {"pressure_source": "native", "pressure_port": 8766, "open_pressure_page": False, "keyboard_fallback": False},
}


def deep_merge(base: dict, override: dict) -> dict:
    out = json.loads(json.dumps(base))
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return deep_merge(DEFAULT_CONFIG, json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except Exception:
            pass
    return json.loads(json.dumps(DEFAULT_CONFIG))


def save_config(config: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


def ensure_effect_output_streams(force: bool = False) -> None:
    if not force:
        try:
            sys.stdout.write("")
            sys.stdout.flush()
            sys.stderr.write("")
            sys.stderr.flush()
            return
        except Exception:
            pass
    log_dir = ROOT / "outputs"
    log_dir.mkdir(parents=True, exist_ok=True)
    stream = (log_dir / "run_effect_stdout.log").open("a", encoding="utf-8", buffering=1)
    sys.stdout = stream
    sys.stderr = stream


def hsv_to_qcolor(hsv):
    if not hsv:
        return QColor("#7c3aed")
    h, s, v = float(hsv[0]) / 360.0, float(hsv[1]), float(hsv[2])
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return QColor(int(r * 255), int(g * 255), int(b * 255))


def qcolor_to_hsv(color: QColor) -> list[float]:
    r, g, b = color.red() / 255.0, color.green() / 255.0, color.blue() / 255.0
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    return [round(h * 360.0, 1), round(s, 3), round(v, 3)]


class ColorButton(QPushButton):
    def __init__(self, label: str, key: str, parent):
        super().__init__(label)
        self.key = key
        self.parent_panel = parent
        self.setMinimumHeight(46)
        self.clicked.connect(self.pick)
        self.setCursor(Qt.PointingHandCursor)

    def set_color_value(self, hsv):
        self.hsv = hsv
        color = hsv_to_qcolor(hsv)
        self.setText(f"   {self.text().strip()}")
        self.setStyleSheet(f"text-align:left; padding:10px 14px; border-radius:8px; border:1px solid rgba(128,128,128,.22); background:qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {color.name()}, stop:.18 {color.name()}, stop:.19 rgba(255,255,255,.10)); color:{'#000' if color.lightness() > 150 else '#fff'}; font-weight:600;")

    def pick(self):
        start = hsv_to_qcolor(getattr(self, "hsv", None))
        color = QColorDialog.getColor(start, self, self.text())
        if color.isValid():
            self.parent_panel.set_color(self.key, qcolor_to_hsv(color))


class LabeledSlider(QWidget):
    def __init__(self, title: str, minv: float, maxv: float, step: float, suffix: str = ""):
        super().__init__()
        self.setObjectName("SettingRow")
        self.minv = minv; self.maxv = maxv; self.step = step; self.suffix = suffix
        self.label = QLabel(title)
        self.label.setObjectName("SettingLabel")
        self.value_label = QLabel()
        self.value_label.setObjectName("SettingValue")
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, int(round((maxv - minv) / step)))
        top = QHBoxLayout(); top.addWidget(self.label); top.addStretch(); top.addWidget(self.value_label)
        layout = QVBoxLayout(self); layout.setContentsMargins(14, 11, 14, 11); layout.setSpacing(8); layout.addLayout(top); layout.addWidget(self.slider)
        self.slider.valueChanged.connect(self._update_label)
        self._update_label()

    def value(self) -> float:
        return self.minv + self.slider.value() * self.step

    def setValue(self, value: float) -> None:
        index = int(round((value - self.minv) / self.step))
        self.slider.setValue(max(0, min(self.slider.maximum(), index)))
        self._update_label()

    def _update_label(self) -> None:
        self.value_label.setText(f"{self.value():.3g}{self.suffix}")

    def valueChangedConnect(self, slot):
        self.slider.valueChanged.connect(slot)


class PreviewWidget(QWidget):
    KEY_RECTS = {
        0: (0.0, 0, 1.0), 1: (1.2, 0, 1.0), 2: (2.2, 0, 1.0), 3: (3.2, 0, 1.0), 4: (4.2, 0, 1.0), 5: (5.2, 0, 1.0), 6: (6.2, 0, 1.0), 7: (7.2, 0, 1.0), 8: (8.2, 0, 1.0), 9: (9.2, 0, 1.0), 10: (10.2, 0, 1.0), 11: (11.2, 0, 1.0), 12: (12.2, 0, 1.0), 13: (13.2, 0, 1.45), 14: (14.85, 0, 1.0),
        15: (0.0, 1, 1.45), 16: (1.55, 1, 1.0), 17: (2.55, 1, 1.0), 18: (3.55, 1, 1.0), 19: (4.55, 1, 1.0), 20: (5.55, 1, 1.0), 21: (6.55, 1, 1.0), 22: (7.55, 1, 1.0), 23: (8.55, 1, 1.0), 24: (9.55, 1, 1.0), 25: (10.55, 1, 1.0), 26: (11.55, 1, 1.0), 27: (12.55, 1, 1.0), 28: (13.65, 1, 1.0), 29: (14.85, 1, 1.0),
        30: (0.0, 2, 1.7), 31: (1.8, 2, 1.0), 32: (2.8, 2, 1.0), 33: (3.8, 2, 1.0), 34: (4.8, 2, 1.0), 35: (5.8, 2, 1.0), 36: (6.8, 2, 1.0), 37: (7.8, 2, 1.0), 38: (8.8, 2, 1.0), 39: (9.8, 2, 1.0), 40: (10.8, 2, 1.0), 41: (11.8, 2, 1.0), 42: (12.9, 2, 1.65), 43: (14.85, 2, 1.0),
        44: (0.0, 3, 2.05), 45: (2.15, 3, 1.0), 46: (3.15, 3, 1.0), 47: (4.15, 3, 1.0), 48: (5.15, 3, 1.0), 49: (6.15, 3, 1.0), 50: (7.15, 3, 1.0), 51: (8.15, 3, 1.0), 52: (9.15, 3, 1.0), 53: (10.15, 3, 1.0), 54: (11.15, 3, 1.0), 55: (12.25, 3, 1.35), 56: (13.65, 3, 1.0), 57: (14.85, 3, 1.0),
        58: (0.0, 4, 1.25), 59: (1.35, 4, 1.25), 60: (2.70, 4, 1.25), 61: (4.25, 4, 5.80), 64: (10.55, 4, 1.0), 65: (11.55, 4, 1.0), 66: (12.55, 4, 1.0), 67: (13.55, 4, 1.0), 68: (14.55, 4, 1.0), 69: (15.55, 4, 1.0),
    }

    def __init__(self):
        super().__init__()
        self.config = load_config()
        self.phase = 0.0
        self.positions = self.load_positions()
        self.timer = QTimer(self); self.timer.timeout.connect(self.tick); self.timer.start(33)
        self.setMinimumHeight(360)

    def load_positions(self):
        candidates = [ROOT / "work" / "melgeek_keyboard_params.json", ROOT / "melgeek_keyboard_params.json", Path(__file__).resolve().parent / "melgeek_keyboard_params.json"]
        for path in candidates:
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                source = data.get("data", data)
                items = source.get("lampPositions", [])
                return {int(i["lampId"]): (float(i["x"]), float(i["y"])) for i in items}
        return {}

    def tick(self):
        self.phase += 0.03
        self.update()

    def set_config(self, config: dict):
        self.config = config
        self.update()

    def is_dark_mode(self) -> bool:
        appearance = self.config.get("ui", {}).get("appearance", "system")
        if appearance == "dark":
            return True
        if appearance == "light":
            return False
        return self.palette().color(QPalette.Window).lightness() < 128

    def blend_color(self, a: QColor, b: QColor, amount: float) -> QColor:
        amount = max(0.0, min(1.0, amount))
        return QColor(
            int(a.red() + (b.red() - a.red()) * amount),
            int(a.green() + (b.green() - a.green()) * amount),
            int(a.blue() + (b.blue() - a.blue()) * amount),
        )

    def key_anchor(self, lamp_id: int) -> tuple[float, float]:
        if lamp_id in self.positions:
            x, y = self.positions[lamp_id]
            return x / 42000.0, y / 42000.0
        if lamp_id in self.KEY_RECTS:
            x_units, row, width_units = self.KEY_RECTS[lamp_id]
            return (x_units + width_units * 0.5) / 16.8, row / 4.0
        return 0.5, 0.5

    def pressure_preview_level(self, lamp_id: int) -> float:
        centers = (32, 36, 38, 49, 50, 61)
        x, y = self.key_anchor(lamp_id)
        pulse = 0.58 + 0.42 * math.sin(self.phase * 2.8)
        level = 0.0
        for index, center_id in enumerate(centers):
            cx, cy = self.key_anchor(center_id)
            d = math.hypot(x - cx, y - cy)
            wave = 0.55 + 0.45 * math.sin(self.phase * 1.9 + index * 0.9)
            level = max(level, max(0.0, 1.0 - d / (0.18 + wave * 0.08)) * pulse)
        return max(0.0, min(1.0, level))

    def audio_preview_level(self) -> tuple[float, float]:
        level = 0.48 + 0.34 * math.sin(self.phase * 2.1) + 0.12 * math.sin(self.phase * 5.4)
        bass = max(0.0, math.sin(self.phase * 1.35)) ** 3.0
        return max(0.0, min(1.0, level)), max(0.0, min(1.0, bass))

    def lamp_color(self, lamp_id: int, base: QColor, accent: QColor, outer: QColor) -> QColor:
        effect = self.config.get("effect", "premium_reactive")
        t = self.phase
        colors = self.config.get("colors", {})
        press_light = hsv_to_qcolor(colors.get("press_light_hsv") or [285, .48, .72])
        press_mid = hsv_to_qcolor(colors.get("press_mid_hsv") or [310, .62, .82])
        bass_color = hsv_to_qcolor(colors.get("bass_pulse_hsv") or [248, .55, .90])
        outer_high = hsv_to_qcolor(colors.get("outer_high_hsv") or [220, .60, .86])
        audio_level, bass = self.audio_preview_level()
        is_outer = lamp_id >= 70
        if effect == "static":
            return outer if is_outer else base
        if effect == "breathing":
            breathing_cfg = (self.config.get("effects", {}) or {}).get("breathing", {}) or {}
            speed = float(breathing_cfg.get("speed", 1.0))
            depth = max(0.0, min(1.0, float(breathing_cfg.get("depth", 1.0))))
            pulse = 0.5 + 0.5 * math.sin(t * 1.7 * max(0.05, speed))
            pulse = pulse * pulse * (3.0 - 2.0 * pulse)
            amount = pulse * depth
            return self.blend_color(outer.darker(135), bass_color, amount * 0.72) if is_outer else self.blend_color(base.darker(145), accent, amount)
        if effect == "rainbow":
            x, y = self.positions.get(lamp_id, (0, 0))
            rainbow_cfg = (self.config.get("effects", {}) or {}).get("rainbow", {}) or {}
            speed = float(rainbow_cfg.get("speed", 1.0))
            sat = max(0.0, min(1.0, float(rainbow_cfg.get("saturation", 0.68))))
            val = max(0.0, min(1.0, float(rainbow_cfg.get("value", 0.62))))
            c = QColor(); c.setHsvF(((x * 0.000004 + y * 0.000006 + t * 0.15 * speed) % 1.0), sat, min(1.0, val * (1.18 if not is_outer else 0.92))); return c
        if effect == "ripple":
            x, y = self.positions.get(lamp_id, (0, 0)); cx, cy = self.positions.get(36, (x, y))
            d = math.hypot(x - cx, y - cy) / 42000.0
            ring = max(0.0, 1.0 - abs(d - (t * 2.6) % 2.0) / 0.22)
            return QColor(accent).lighter(100 + int(ring * 130)) if ring > 0 else base.darker(150)
        if effect == "pressure_dent":
            if is_outer:
                return outer.darker(120)
            heat = self.pressure_preview_level(lamp_id)
            return self.blend_color(self.blend_color(base, press_light, heat * 0.45), self.blend_color(press_mid, accent, heat), heat)
        if effect == "audio_ambient":
            if is_outer:
                pulse = 0.45 + 0.55 * math.sin(t * 1.45 + lamp_id * 0.075)
                return self.blend_color(self.blend_color(outer, outer_high, audio_level * 0.62), bass_color, bass * max(0.0, pulse))
            return self.blend_color(base.darker(120), bass_color, bass * 0.18)
        if effect == "premium_reactive":
            if is_outer:
                pulse = 0.45 + 0.55 * math.sin(t * 1.45 + lamp_id * 0.075)
                return self.blend_color(self.blend_color(outer, outer_high, audio_level * 0.55), bass_color, bass * max(0.0, pulse))
            heat = self.pressure_preview_level(lamp_id)
            pressure_color = self.blend_color(self.blend_color(base, press_light, heat * 0.45), self.blend_color(press_mid, accent, heat), heat)
            return self.blend_color(pressure_color, bass_color, bass * 0.12)
        if is_outer:
            pulse = 0.5 + 0.5 * math.sin(t * 1.3 + lamp_id * 0.05)
            return QColor(outer).lighter(95 + int(pulse * 45))
        return base

    def draw_glow_strip(self, painter: QPainter, rect: QRectF, color: QColor, radius: float = 10.0) -> None:
        painter.setPen(Qt.NoPen)
        soft = QColor(color)
        soft.setAlpha(70)
        painter.setBrush(soft)
        painter.drawRoundedRect(rect, radius, radius)
        core = QColor(color)
        core.setAlpha(160)
        inset = rect.adjusted(1.5, 1.5, -1.5, -1.5)
        painter.setBrush(core)
        painter.drawRoundedRect(inset, max(2.0, radius - 2), max(2.0, radius - 2))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(18, 18, -18, -18)
        dark = self.is_dark_mode()
        painter.setPen(Qt.NoPen)
        bg = QColor(16, 18, 24) if dark else QColor(247, 248, 251)
        deck = QColor(31, 36, 48) if dark else QColor(232, 236, 244)
        painter.setBrush(bg)
        painter.drawRoundedRect(rect, 20, 20)
        colors = self.config.get("colors", {})
        base = hsv_to_qcolor(colors.get("base_hsv") or [250, .4, .25])
        accent = hsv_to_qcolor(colors.get("press_deep_hsv") or [332, .88, .92])
        outer = hsv_to_qcolor(colors.get("outer_base_hsv") or [235, .28, .22])
        board = rect.adjusted(34, 30, -34, -30)
        board_ratio = 17.0 / 6.2
        if board.width() / max(1, board.height()) > board_ratio:
            width = board.height() * board_ratio
            board = QRectF(board.center().x() - width / 2, board.top(), width, board.height())
        else:
            height = board.width() / board_ratio
            board = QRectF(board.left(), board.center().y() - height / 2, board.width(), height)
        painter.setBrush(deck)
        painter.drawRoundedRect(board, 18, 18)

        unit = min(board.width() / 17.1, board.height() / 6.25)
        gap = unit * 0.12
        key_h = unit * 0.78
        start_x = board.left() + unit * 0.58
        start_y = board.top() + unit * 0.82
        strip_h = unit * 0.14
        for row, ids in enumerate((range(70, 133), range(133, 196), range(196, 259))):
            row_color = self.lamp_color(70 + row * 63 + int((self.phase * 12) % 40), base, accent, outer)
            y = board.top() + unit * (0.25 + row * 0.18)
            self.draw_glow_strip(painter, QRectF(board.left() + unit * 0.7, y, board.width() - unit * 1.4, strip_h), row_color, strip_h / 2)

        for index, lamp_id in enumerate(range(259, 272)):
            y = start_y + index * (key_h * 0.42)
            self.draw_glow_strip(painter, QRectF(board.left() + unit * 0.18, y, unit * 0.13, key_h * 0.25), self.lamp_color(lamp_id, base, accent, outer), 3)
        for index, lamp_id in enumerate(range(272, 285)):
            y = start_y + (12 - index) * (key_h * 0.42)
            self.draw_glow_strip(painter, QRectF(board.right() - unit * 0.31, y, unit * 0.13, key_h * 0.25), self.lamp_color(lamp_id, base, accent, outer), 3)

        key_border = QColor(255, 255, 255, 30) if dark else QColor(24, 32, 47, 34)
        cap_overlay = QColor(255, 255, 255, 18) if dark else QColor(255, 255, 255, 110)
        for lamp_id, (x_units, row, width_units) in self.KEY_RECTS.items():
            x = start_x + x_units * unit
            y = start_y + row * (key_h + gap)
            w = max(unit * width_units - gap, unit * 0.62)
            key_rect = QRectF(x, y, w, key_h)
            color = self.lamp_color(lamp_id, base, accent, outer)
            painter.setPen(QPen(key_border, 1))
            painter.setBrush(color)
            painter.drawRoundedRect(key_rect, 5, 5)
            painter.setPen(Qt.NoPen)
            painter.setBrush(cap_overlay)
            painter.drawRoundedRect(key_rect.adjusted(2, 2, -2, -key_h * 0.54), 4, 4)
        painter.end()


class ModernPanel(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MelGeek Reactive RGB")
        self.config = load_config()
        self.proc: subprocess.Popen | None = None
        self.output_queue: queue.Queue[str] = queue.Queue()
        self.controls: dict[str, LabeledSlider] = {}
        self.color_buttons: dict[str, ColorButton] = {}
        self.log_visible = False
        self.loading = False
        self.autosave = QTimer(self); self.autosave.setSingleShot(True); self.autosave.timeout.connect(self.save_silent)
        self.build_ui()
        self.apply_style()
        self.setup_tray()
        self.load_to_ui()
        self.poll = QTimer(self); self.poll.timeout.connect(self.poll_output); self.poll.start(700)

    def setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = None
            return
        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(self.style().standardIcon(QStyle.SP_ComputerIcon))
        menu = QMenu()
        show_action = QAction("显示控制面板", self); show_action.triggered.connect(self.show_window)
        start_action = QAction("启动灯效", self); start_action.triggered.connect(lambda: self.start_effect())
        stop_action = QAction("停止灯效", self); stop_action.triggered.connect(self.stop_effect)
        quit_action = QAction("退出", self); quit_action.triggered.connect(self.quit_app)
        menu.addAction(show_action); menu.addSeparator(); menu.addAction(start_action); menu.addAction(stop_action); menu.addSeparator(); menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.show_window() if reason == QSystemTrayIcon.DoubleClick else None)
        self.tray.show()

    def show_window(self):
        self.center_on_primary_screen()
        self.setWindowState((self.windowState() & ~Qt.WindowMinimized) | Qt.WindowActive)
        self.showNormal(); self.raise_(); self.activateWindow()

    def center_on_primary_screen(self):
        screen = QApplication.primaryScreen()
        if not screen:
            return
        available = screen.availableGeometry()
        frame = self.frameGeometry()
        frame.moveCenter(available.center())
        self.move(frame.topLeft())

    def quit_app(self):
        self.stop_effect()
        QApplication.instance().quit()

    def closeEvent(self, event):
        if getattr(self, "tray", None) is not None and self.tray.isVisible():
            event.ignore()
            self.hide()
            self.tray.showMessage("MelGeek Reactive RGB", "已最小化到系统托盘。右键托盘图标可退出。", QSystemTrayIcon.Information, 2000)
        else:
            self.quit_app()
            event.accept()

    def build_ui(self):
        root = QWidget(); self.setCentralWidget(root)
        root.setObjectName("AppRoot")
        shell = QHBoxLayout(root); shell.setContentsMargins(16,16,16,16); shell.setSpacing(14)
        sidebar = QFrame(); sidebar.setObjectName("Sidebar"); sidebar.setFixedWidth(268)
        sidebar_l = QVBoxLayout(sidebar); sidebar_l.setContentsMargins(14,14,14,14); sidebar_l.setSpacing(12)
        brand = QLabel("MelGeek")
        brand.setObjectName("BrandTitle")
        brand_sub = QLabel("Reactive RGB 控制台")
        brand_sub.setObjectName("BrandSubtitle")
        sidebar_l.addWidget(brand); sidebar_l.addWidget(brand_sub)
        self.effects = QListWidget(); self.effects.setObjectName("EffectsList")
        for key, name, desc in EFFECTS:
            item = QListWidgetItem(f"{name}\n{desc}"); item.setData(Qt.UserRole, key); self.effects.addItem(item)
        self.effects.currentRowChanged.connect(self.effect_changed)
        sidebar_l.addWidget(self.effects, 1)
        sidebar_note = QLabel("关闭窗口会最小化到托盘")
        sidebar_note.setObjectName("SidebarNote")
        sidebar_l.addWidget(sidebar_note)
        shell.addWidget(sidebar)
        center_frame = QFrame(); center_frame.setObjectName("MainSurface")
        shell.addWidget(center_frame, 1)
        center = QVBoxLayout(center_frame); center.setContentsMargins(18,18,18,18); center.setSpacing(14)
        header = QHBoxLayout(); header.setSpacing(10); center.addLayout(header)
        title_box = QVBoxLayout(); title_box.setSpacing(2)
        title = QLabel("Reactive RGB")
        title.setObjectName("PageTitle")
        subtitle = QLabel("原生压力 · WASAPI 音频 · 285 灯位实时控制")
        subtitle.setObjectName("PageSubtitle")
        title_box.addWidget(title); title_box.addWidget(subtitle)
        header.addLayout(title_box); header.addStretch()
        self.webhid_view = None
        self.appearance_box = QComboBox(); self.appearance_box.setObjectName("AppearanceBox")
        self.appearance_box.addItem("跟随系统", "system")
        self.appearance_box.addItem("日间", "light")
        self.appearance_box.addItem("夜间", "dark")
        self.appearance_box.setFixedWidth(104)
        self.appearance_box.currentIndexChanged.connect(self.appearance_changed)
        self.connect_btn = QPushButton("WebHID 备用"); self.connect_btn.setObjectName("SecondaryButton")
        self.browser_connect_btn = QPushButton("浏览器备用"); self.browser_connect_btn.setObjectName("SecondaryButton")
        self.start_btn = QPushButton("启动灯效"); self.start_btn.setObjectName("PrimaryButton")
        self.stop_btn = QPushButton("停止"); self.stop_btn.setObjectName("DangerButton")
        header.addWidget(self.appearance_box)
        header.addWidget(self.connect_btn)
        header.addWidget(self.browser_connect_btn)
        header.addWidget(self.start_btn); header.addWidget(self.stop_btn)
        status_bar = QFrame(); status_bar.setObjectName("StatusBar")
        status_l = QHBoxLayout(status_bar); status_l.setContentsMargins(12,10,12,10); status_l.setSpacing(8)
        self.core_pill = QLabel("核心：未启动"); self.core_pill.setObjectName("StatusPill")
        self.pressure_pill = QLabel("压力：Native") ; self.pressure_pill.setObjectName("StatusPill")
        self.audio_pill = QLabel("音频：待机") ; self.audio_pill.setObjectName("StatusPill")
        self.effect_pill = QLabel("模式：综合") ; self.effect_pill.setObjectName("StatusPill")
        for pill in (self.core_pill, self.pressure_pill, self.audio_pill, self.effect_pill):
            status_l.addWidget(pill)
        status_l.addStretch()
        center.addWidget(status_bar)
        self.preview = PreviewWidget(); self.preview.setObjectName("PreviewCard"); center.addWidget(self.preview)
        self.status_card = QLabel("状态：未启动 · 原生压力待启动 · 音频未启动")
        self.status_card.setObjectName("StatusCard")
        self.status_card.setMinimumHeight(44)
        center.addWidget(self.status_card)
        log_header = QHBoxLayout(); log_header.setSpacing(8)
        log_title = QLabel("运行日志")
        log_title.setObjectName("SectionTitle")
        self.log_toggle = QPushButton("显示")
        self.log_toggle.setObjectName("GhostButton")
        self.log_toggle.clicked.connect(self.toggle_log)
        log_header.addWidget(log_title); log_header.addStretch(); log_header.addWidget(self.log_toggle)
        center.addLayout(log_header)
        self.log = QTextEdit(); self.log.setObjectName("LogBox"); self.log.setReadOnly(True); self.log.setMaximumHeight(132); self.log.setVisible(False); center.addWidget(self.log)
        right_scroll = QScrollArea(); right_scroll.setObjectName("InspectorScroll"); right_scroll.setWidgetResizable(True); right_scroll.setFixedWidth(380)
        self.right = QWidget(); self.right.setObjectName("InspectorBody"); self.right_layout = QVBoxLayout(self.right); self.right_layout.setContentsMargins(14,14,14,14); self.right_layout.setSpacing(12); right_scroll.setWidget(self.right); shell.addWidget(right_scroll)
        self.start_btn.clicked.connect(lambda: self.start_effect()); self.stop_btn.clicked.connect(self.stop_effect); self.browser_connect_btn.clicked.connect(self.open_browser_webhid)
        self.connect_btn.clicked.connect(self.open_browser_webhid)

    def toggle_log(self):
        self.log_visible = not self.log_visible
        self.log.setVisible(self.log_visible)
        self.log_toggle.setText("隐藏" if self.log_visible else "显示")

    def appearance_changed(self, *_):
        if self.loading:
            return
        mode = self.appearance_box.currentData() or "system"
        self.config.setdefault("ui", {})["appearance"] = mode
        self.apply_style()
        self.preview.update()
        self.schedule_save()

    def rebuild_params(self):
        self.rainbow_style = None
        while self.right_layout.count():
            item = self.right_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        self.controls.clear(); self.color_buttons.clear()
        effect = self.config.get("effect", "premium_reactive")
        effect_name = next((name for key, name, _ in EFFECTS if key == effect), "参数")
        inspector_title = QLabel(effect_name)
        inspector_title.setObjectName("InspectorTitle")
        inspector_hint = QLabel("只显示当前光效真正相关的参数")
        inspector_hint.setObjectName("InspectorHint")
        self.right_layout.addWidget(inspector_title)
        self.right_layout.addWidget(inspector_hint)
        self.tabs = QTabWidget(); self.right_layout.addWidget(self.tabs)
        basic = QWidget(); basic_l = QVBoxLayout(basic)
        advanced = QWidget(); adv_l = QVBoxLayout(advanced)
        basic_l.setContentsMargins(0,12,0,0); basic_l.setSpacing(10)
        adv_l.setContentsMargins(0,12,0,0); adv_l.setSpacing(10)
        self.tabs.addTab(basic, "基础"); self.tabs.addTab(advanced, "高级")

        def add_field_label(layout, text):
            label = QLabel(text)
            label.setObjectName("FieldTitle")
            layout.addWidget(label)

        def add_color_group(layout, title, items):
            if not items:
                return
            color_group = QGroupBox(title)
            color_l = QVBoxLayout(color_group)
            color_l.setSpacing(8)
            layout.addWidget(color_group)
            for key, label in items:
                btn = ColorButton(label, key, self)
                self.color_buttons[key] = btn
                color_l.addWidget(btn)

        def add_slider_group(layout, title, items):
            if not items:
                return
            group = QGroupBox(title)
            group_l = QVBoxLayout(group)
            group_l.setSpacing(8)
            layout.addWidget(group)
            for key, label, lo, hi, step, section in items:
                self.add_slider(group_l, key, label, lo, hi, step, section)

        theme_label = QLabel("主题")
        theme_label.setObjectName("FieldTitle")
        self.theme_box = QComboBox(); self.theme_box.addItems([THEME_LABELS[k] for k in THEMES]); self.theme_box.currentIndexChanged.connect(self.schedule_save); basic_l.addWidget(theme_label); basic_l.addWidget(self.theme_box)

        self.add_slider(basic_l, "brightness", "整体亮度", 0, 1, .01, "global")

        if effect == "static":
            add_color_group(basic_l, "外观", [("base_hsv", "键区底色"), ("outer_base_hsv", "背板底色")])
            add_color_group(adv_l, "强调色", [("press_deep_hsv", "键区强调"), ("outer_low_hsv", "侧边低位"), ("outer_high_hsv", "侧边高位")])
        elif effect == "breathing":
            self.add_slider(basic_l, "breathing.speed", "呼吸速度", .2, 3, .05, "effects")
            self.add_slider(basic_l, "breathing.depth", "呼吸幅度", 0, 1, .02, "effects")
            add_color_group(basic_l, "呼吸颜色", [("base_hsv", "暗部底色"), ("press_deep_hsv", "亮部目标")])
            add_color_group(adv_l, "背板颜色", [("outer_base_hsv", "背板底色"), ("bass_pulse_hsv", "背板呼吸色")])
        elif effect == "rainbow":
            add_field_label(basic_l, "彩虹样式")
            self.rainbow_style = QComboBox(); self.rainbow_style.addItems(["diagonal", "horizontal", "vertical", "radial", "dual", "pastel"]); self.rainbow_style.currentIndexChanged.connect(self.schedule_save); basic_l.addWidget(self.rainbow_style)
            for key, title, lo, hi, step in [("speed","流动速度",.05,5,.05),("value","彩虹亮度",0,1,.02)]: self.add_slider(basic_l, f"rainbow.{key}", title, lo, hi, step, "effects")
            self.add_slider(adv_l, "rainbow.saturation", "色彩饱和度", 0, 1, .02, "effects")
        elif effect == "ripple":
            for key, title, lo, hi, step in [("max_radius","涟漪范围",5,140,1),("brightness","涟漪亮度",0,3,.05),("width","涟漪宽度",.2,4,.05)]: self.add_slider(basic_l, f"ripple.{key}", title, lo, hi, step, "effects")
            for key, title, lo, hi, step in [("trigger_threshold","触发阈值",.01,.8,.01),("retrigger_gap_ms","连击间隔 ms",0,300,5),("charge_ms","蓄力时间 ms",0,500,10),("min_radius","最小半径",1,40,1),("min_duration","最短时长",.1,3,.05),("max_duration","最长时长",.2,5,.05)]: self.add_slider(adv_l, f"ripple.{key}", title, lo, hi, step, "effects")
            add_color_group(adv_l, "涟漪颜色", [("base_hsv", "背景底色"), ("press_deep_hsv", "涟漪颜色")])
        elif effect == "pressure_dent":
            self.add_slider(basic_l, "radius", "压力扩散", 4, 30, .5, "global")
            for key, title, lo, hi, step in [("attack","按下跟手",.01,1,.01),("release","释放回弹",.01,1,.01),("color_floor","周边染色",0,1,.01),("space_color_floor","空格染色",0,1,.01)]: self.add_slider(basic_l, f"pressure_dent.{key}", title, lo, hi, step, "effects")
            for key, title, lo, hi, step in [("input_deadzone","输入死区",0,.1,.001),("jitter_deadzone","细抖过滤",0,.1,.001),("small_change_attack","微变化跟随",0,.5,.005)]: self.add_slider(adv_l, f"pressure_dent.{key}", title, lo, hi, step, "effects")
            add_color_group(adv_l, "压力颜色", [("base_hsv", "键区底色"), ("press_light_hsv", "轻压色"), ("press_mid_hsv", "中压色"), ("press_deep_hsv", "重压色")])
        elif effect == "audio_ambient":
            for key, title, lo, hi, step in [("sensitivity","音频灵敏度",0,3,.05),("bass_sensitivity","低频灵敏度",0,3,.05),("side_vu_strength","侧边 VU",0,3,.05),("backplate_ambience_strength","背板氛围",0,3,.05),("backplate_shockwave_strength","低频冲击",0,3,.05)]: self.add_slider(basic_l, key, title, lo, hi, step, "audio")
            for key, title, lo, hi, step in [("audio_ambient.silence_gate","静音门限",0,.03,.0005),("audio_ambient.side_vu_curve","VU 曲线",.25,1.5,.01),("audio_ambient.backplate_motion","背板运动",0,2,.05)]: self.add_slider(adv_l, key, title, lo, hi, step, "effects")
            add_color_group(adv_l, "音频颜色", [("outer_base_hsv", "背板底色"), ("bass_pulse_hsv", "低频冲击色"), ("outer_low_hsv", "侧边低位色"), ("outer_high_hsv", "侧边高位色")])
        elif effect == "premium_reactive":
            add_slider_group(basic_l, "压力 / 键区响应", [
                ("radius", "压力扩散", 4, 30, .5, "global"),
                ("pressure_dent.attack", "按下跟手", .01, 1, .01, "effects"),
                ("pressure_dent.release", "释放回弹", .01, 1, .01, "effects"),
                ("pressure_dent.color_floor", "压力染色", 0, 1, .01, "effects"),
            ])
            add_slider_group(basic_l, "音频 / 背板响应", [
                ("sensitivity", "音频灵敏度", 0, 3, .05, "audio"),
                ("bass_sensitivity", "低频灵敏度", 0, 3, .05, "audio"),
                ("backplate_shockwave_strength", "低频冲击", 0, 3, .05, "audio"),
            ])
            add_slider_group(adv_l, "压力高级", [
                ("pressure_dent.input_deadzone", "输入死区", 0, .1, .001, "effects"),
                ("pressure_dent.jitter_deadzone", "细抖过滤", 0, .1, .001, "effects"),
                ("pressure_dent.small_change_attack", "微变化跟随", 0, .5, .005, "effects"),
                ("pressure_dent.space_color_floor", "空格染色", 0, 1, .01, "effects"),
            ])
            add_slider_group(adv_l, "音频高级", [
                ("side_vu_strength", "侧边 VU", 0, 3, .05, "audio"),
                ("backplate_ambience_strength", "背板氛围", 0, 3, .05, "audio"),
                ("audio_ambient.silence_gate", "静音门限", 0, .03, .0005, "effects"),
                ("audio_ambient.side_vu_curve", "VU 曲线", .25, 1.5, .01, "effects"),
                ("audio_ambient.backplate_motion", "背板运动", 0, 2, .05, "effects"),
            ])
            add_color_group(adv_l, "键区颜色", [("base_hsv", "键区底色"), ("press_light_hsv", "轻压色"), ("press_mid_hsv", "中压色"), ("press_deep_hsv", "重压色")])
            add_color_group(adv_l, "音频 / 背板颜色", [("outer_base_hsv", "背板底色"), ("bass_pulse_hsv", "低频冲击色"), ("outer_low_hsv", "侧边低位色"), ("outer_high_hsv", "侧边高位色")])
        basic_l.addStretch(); adv_l.addStretch(); self.right_layout.addStretch(); self.load_to_ui_values()

    def add_slider(self, layout, key, title, lo, hi, step, section):
        w = LabeledSlider(title, lo, hi, step); w.valueChangedConnect(self.schedule_save); w.setProperty("config_key", key); w.setProperty("section", section); self.controls[key] = w; layout.addWidget(w)

    def load_to_ui(self):
        row = next((i for i,(k,_,__) in enumerate(EFFECTS) if k == self.config.get("effect")), 0); self.effects.setCurrentRow(row); self.rebuild_params()

    def load_to_ui_values(self):
        self.loading = True
        appearance = self.config.get("ui", {}).get("appearance", "system")
        for index in range(self.appearance_box.count()):
            if self.appearance_box.itemData(index) == appearance:
                self.appearance_box.setCurrentIndex(index)
                break
        self.theme_box.setCurrentIndex(max(0, THEMES.index(self.config.get("theme","noir"))))
        for key,w in self.controls.items(): w.setValue(self.get_value(key, w.property("section")))
        if self.rainbow_style is not None: self.rainbow_style.setCurrentText(self.config.get("effects",{}).get("rainbow",{}).get("style","diagonal"))
        for key,btn in self.color_buttons.items(): btn.set_color_value(self.config.get("colors",{}).get(key))
        self.preview.set_config(self.config); self.loading = False

    def get_value(self, key, section):
        if "." in key and section == "effects": a,b=key.split(".",1); return float(self.config.get("effects",{}).get(a,{}).get(b, DEFAULT_CONFIG.get("effects",{}).get(a,{}).get(b,0)))
        return float(self.config.get(section,{}).get(key, DEFAULT_CONFIG.get(section,{}).get(key,0)))

    def effect_changed(self, row):
        if row < 0: return
        self.config["effect"] = self.effects.item(row).data(Qt.UserRole); self.rebuild_params(); self.schedule_save()
        label = self.effects.item(row).text().split("\n", 1)[0]
        self.effect_pill.setText(f"模式：{label}")

    def set_color(self, key, hsv):
        self.config.setdefault("colors",{})[key]=hsv; self.color_buttons[key].set_color_value(hsv); self.schedule_save()

    def schedule_save(self, *_):
        if self.loading: return
        self.autosave.start(180)

    def save_silent(self):
        self.config["theme"] = THEMES[self.theme_box.currentIndex()]
        self.config.setdefault("ui", {})["appearance"] = self.appearance_box.currentData() or "system"
        if self.rainbow_style is not None: self.config.setdefault("effects",{}).setdefault("rainbow",{})["style"] = self.rainbow_style.currentText()
        for key,w in self.controls.items():
            sec=w.property("section"); val=w.value()
            if "." in key and sec=="effects": a,b=key.split(".",1); self.config.setdefault("effects",{}).setdefault(a,{})[b]=val
            else: self.config.setdefault(sec,{})[key]=val
        save_config(self.config); self.preview.set_config(self.config)

    def open_browser_webhid(self):
        was_source = str(self.config.get("startup", {}).get("pressure_source", "native"))
        if self.proc and self.proc.poll() is None and was_source != "webhid":
            self.log.append("正在切换到 WebHID 备用压力源...")
            self.proc.terminate()
            self.proc = None
        self.config.setdefault("startup", {})["pressure_source"] = "webhid"
        self.config.setdefault("startup", {})["open_pressure_page"] = True
        save_config(self.config)
        if not (self.proc and self.proc.poll() is None):
            self.log.append("本地 WebHID 服务未运行，正在先启动灯效核心...")
            self.start_effect("webhid", True)
            QTimer.singleShot(1200, self.open_browser_webhid)
            return
        port = int(self.config.get("startup", {}).get("pressure_port", 8766))
        url = f"http://127.0.0.1:{port}/"
        edge = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
        chrome = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
        try:
            if edge.exists():
                subprocess.Popen([str(edge), f"--app={url}", "--window-size=310,90"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            elif chrome.exists():
                subprocess.Popen([str(chrome), f"--app={url}", "--window-size=310,90"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                webbrowser.open(url)
            self.status_card.setText("状态：已打开独立 WebHID 连接窗口。连接后可最小化，不要关闭。")
        except Exception as exc:
            self.log.append(f"打开浏览器连接页失败：{exc}")
            webbrowser.open(url)

    def open_webhid_helper(self):
        if not WEBENGINE_AVAILABLE or self.webhid_view is None:
            self.log.append("未安装 PySide6-WebEngine，无法内嵌 WebHID 页面。请运行 install_gui_deps.bat。")
            return
        if not (self.proc and self.proc.poll() is None):
            self.log.append("本地 WebHID 服务未运行，正在先启动灯效核心...")
            self.start_effect()
            QTimer.singleShot(1200, self.open_webhid_helper)
            return
        port = int(self.config.get("startup", {}).get("pressure_port", 8766))
        self.webhid_view.setUrl(QUrl(f"http://127.0.0.1:{port}/"))
        self.webhid_view.show()
        self.status_card.setText("状态：请在内嵌连接页点击 Connect WebHID，连接后可隐藏窗口到托盘")

    def start_effect(self, pressure_source="native", open_pressure_page=False):
        self.save_silent()
        self.config.setdefault("startup", {})["pressure_source"] = pressure_source
        self.config.setdefault("startup", {})["open_pressure_page"] = open_pressure_page
        save_config(self.config)
        if self.proc and self.proc.poll() is None: QMessageBox.information(self,"运行中","灯效已经在运行"); return
        cmd=[sys.executable,"--run-effect",str(CONFIG_PATH)] if getattr(sys,"frozen",False) else [sys.executable,str(CORE),"--config",str(CONFIG_PATH)]
        self.proc=subprocess.Popen(cmd,cwd=str(ROOT),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
        threading.Thread(target=self.reader,args=(self.proc,),daemon=True).start(); self.log.append("已启动灯效"); self.status_card.setText("状态：灯效已启动，等待原生压力/音频状态..."); self.core_pill.setText("核心：运行中"); self.pressure_pill.setText("压力：Native")

    def stop_effect(self):
        if self.proc and self.proc.poll() is None: self.proc.terminate(); self.log.append("已停止灯效"); self.status_card.setText("状态：已停止"); self.core_pill.setText("核心：已停止"); self.audio_pill.setText("音频：待机")

    def reader(self,proc):
        if proc.stdout:
            for line in iter(proc.stdout.readline,""): self.output_queue.put(line.rstrip())

    def poll_output(self):
        for _ in range(50):
            try:
                line = self.output_queue.get_nowait()
                self.log.append(line)
                if "audio:" in line:
                    self.audio_pill.setText("音频：已连接")
                if "pressure-native: init ok" in line:
                    self.pressure_pill.setText("压力：Native 已连接")
                if "audio:" in line or "audio_mode=" in line or "pressure_rows=" in line:
                    self.status_card.setText("状态：" + line[:180])
            except queue.Empty:break

    def apply_style(self):
        appearance = self.config.get("ui", {}).get("appearance", "system")
        if appearance == "dark":
            dark = True
        elif appearance == "light":
            dark = False
        else:
            dark = self.palette().color(QPalette.Window).lightness() < 128
        if dark:
            self.setStyleSheet('''
                QMainWindow { background: #101217; }
                QWidget#AppRoot { background: #101217; }
                QFrame#Sidebar, QFrame#MainSurface, QScrollArea#InspectorScroll { background: #171a21; border: 1px solid #2b3240; border-radius: 8px; }
                QWidget#InspectorBody { background: #171a21; }
                QLabel { color: #eef2f7; font-size: 13px; }
                QLabel#BrandTitle { color: #f7f9fc; font-size: 21px; font-weight: 800; }
                QLabel#BrandSubtitle, QLabel#PageSubtitle, QLabel#InspectorHint, QLabel#SidebarNote { color: #98a2b3; font-size: 12px; }
                QLabel#PageTitle { color: #f7f9fc; font-size: 24px; font-weight: 800; }
                QLabel#SectionTitle, QLabel#InspectorTitle { color: #f7f9fc; font-size: 15px; font-weight: 750; }
                QLabel#FieldTitle, QLabel#SettingLabel { color: #d7dde8; font-weight: 650; }
                QLabel#SettingValue { color: #aab8ff; font-size: 12px; font-weight: 700; }
                QLabel#StatusPill { background: #1f2430; border: 1px solid #303848; border-radius: 8px; padding: 6px 9px; color: #cbd3df; }
                QFrame#StatusBar, QLabel#StatusCard, QTextEdit#LogBox, PreviewWidget#PreviewCard { background: #1f2430; border: 1px solid #303848; border-radius: 8px; }
                QLabel#StatusCard { padding: 9px 12px; color: #cbd3df; }
                QTextEdit#LogBox { color: #cbd3df; padding: 10px; font-family: Consolas, SF Mono, monospace; }
                QListWidget#EffectsList { background: transparent; border: 0; padding: 2px; font-size: 13px; outline: 0; }
                QListWidget#EffectsList::item { padding: 11px 10px; margin: 2px 0; border-radius: 8px; color: #a8b1c0; }
                QListWidget#EffectsList::item:selected { background: #252b43; color: #eef2ff; border-left: 3px solid #8ea2ff; }
                QListWidget#EffectsList::item:hover { background: #1f2430; color: #eef2f7; }
                QComboBox { background: #1f2430; color: #eef2f7; border: 1px solid #303848; border-radius: 8px; padding: 8px 10px; }
                QTabWidget::pane { border: 0; }
                QTabBar::tab { background: #1f2430; color: #98a2b3; border: 1px solid #303848; border-radius: 8px; padding: 7px 16px; margin-right: 6px; }
                QTabBar::tab:selected { background: #252b43; border-color: #5967b8; color: #eef2ff; }
                QGroupBox { color: #eef2f7; border: 1px solid #303848; border-radius: 8px; margin-top: 12px; padding: 12px; font-weight: 700; }
                QWidget#SettingRow { background: #1f2430; border: 1px solid #303848; border-radius: 8px; }
                QPushButton { background: #232938; color: #eef2f7; border: 1px solid #3a4356; border-radius: 8px; padding: 9px 14px; font-weight: 700; }
                QPushButton:hover { background: #2c3445; }
                QPushButton#PrimaryButton { background: #5b6ee1; border-color: #7486f4; color: #ffffff; }
                QPushButton#PrimaryButton:hover { background: #687cf0; }
                QPushButton#SecondaryButton, QPushButton#GhostButton { background: transparent; color: #cbd3df; border-color: #3a4356; }
                QPushButton#DangerButton { background: #3a2024; border-color: #704149; color: #fda29b; }
                QSlider::groove:horizontal { height: 6px; background: #303848; border-radius: 3px; }
                QSlider::sub-page:horizontal { background: #8ea2ff; border-radius: 3px; }
                QSlider::handle:horizontal { background: #f7f9fc; border: 1px solid #aab8ff; width: 18px; height: 18px; border-radius: 9px; margin: -6px 0; }
            ''')
        else:
            self.setStyleSheet('''
                QMainWindow { background: #f7f8fb; }
                QWidget#AppRoot { background: #f7f8fb; }
                QFrame#Sidebar, QFrame#MainSurface, QScrollArea#InspectorScroll { background: #ffffff; border: 1px solid #dfe3ea; border-radius: 8px; }
                QWidget#InspectorBody { background: #ffffff; }
                QLabel { color: #18202f; font-size: 13px; }
                QLabel#BrandTitle { color: #111827; font-size: 21px; font-weight: 800; }
                QLabel#BrandSubtitle, QLabel#PageSubtitle, QLabel#InspectorHint, QLabel#SidebarNote { color: #6b7280; font-size: 12px; }
                QLabel#PageTitle { color: #111827; font-size: 24px; font-weight: 800; }
                QLabel#SectionTitle, QLabel#InspectorTitle { color: #18202f; font-size: 15px; font-weight: 750; }
                QLabel#FieldTitle, QLabel#SettingLabel { color: #293244; font-weight: 650; }
                QLabel#SettingValue { color: #4f6df5; font-size: 12px; font-weight: 700; }
                QLabel#StatusPill { background: #f1f3f7; border: 1px solid #dfe3ea; border-radius: 8px; padding: 6px 9px; color: #4b5563; }
                QFrame#StatusBar, QLabel#StatusCard, QTextEdit#LogBox, PreviewWidget#PreviewCard { background: #f1f3f7; border: 1px solid #dfe3ea; border-radius: 8px; }
                QLabel#StatusCard { padding: 9px 12px; color: #4b5563; }
                QTextEdit#LogBox { color: #4b5563; padding: 10px; font-family: Consolas, SF Mono, monospace; }
                QListWidget#EffectsList { background: transparent; border: 0; padding: 2px; font-size: 13px; outline: 0; }
                QListWidget#EffectsList::item { padding: 11px 10px; margin: 2px 0; border-radius: 8px; color: #5f6877; }
                QListWidget#EffectsList::item:selected { background: #eef2ff; color: #3344a3; border-left: 3px solid #4f6df5; }
                QListWidget#EffectsList::item:hover { background: #f1f3f7; color: #18202f; }
                QComboBox { background: #ffffff; color: #18202f; border: 1px solid #ccd3de; border-radius: 8px; padding: 8px 10px; }
                QTabWidget::pane { border: 0; }
                QTabBar::tab { background: #ffffff; color: #6b7280; border: 1px solid #dfe3ea; border-radius: 8px; padding: 7px 16px; margin-right: 6px; }
                QTabBar::tab:selected { background: #eef2ff; border-color: #b9c4ff; color: #3344a3; }
                QGroupBox { color: #18202f; border: 1px solid #dfe3ea; border-radius: 8px; margin-top: 12px; padding: 12px; font-weight: 700; }
                QWidget#SettingRow { background: #f8f9fc; border: 1px solid #dfe3ea; border-radius: 8px; }
                QPushButton { background: #ffffff; color: #18202f; border: 1px solid #ccd3de; border-radius: 8px; padding: 9px 14px; font-weight: 700; }
                QPushButton:hover { background: #f1f3f7; }
                QPushButton#PrimaryButton { background: #4f6df5; border-color: #4f6df5; color: white; }
                QPushButton#PrimaryButton:hover { background: #435ee6; }
                QPushButton#SecondaryButton, QPushButton#GhostButton { background: #ffffff; color: #4b5563; border-color: #ccd3de; }
                QPushButton#DangerButton { background: #fff7f5; border-color: #f5c2bb; color: #b42318; }
                QSlider::groove:horizontal { height: 6px; background: #dfe3ea; border-radius: 3px; }
                QSlider::sub-page:horizontal { background: #4f6df5; border-radius: 3px; }
                QSlider::handle:horizontal { background: #ffffff; border: 1px solid #9aa7bb; width: 18px; height: 18px; border-radius: 9px; margin: -6px 0; }
            ''')


def main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "--run-effect":
        config = sys.argv[2] if len(sys.argv) >= 3 else str(CONFIG_PATH)
        ensure_effect_output_streams(force=getattr(sys, "frozen", False))
        import melgeek68_premium_reactive as core
        sys.argv = ["melgeek68_premium_reactive", "--config", config] + sys.argv[3:]
        return core.main()
    if len(sys.argv) >= 2 and sys.argv[1] == "--pressure-server":
        import melgeek_local_webhid_pressure_server as server
        sys.argv = ["melgeek_local_webhid_pressure_server"] + sys.argv[2:]
        return server.main()
    app = QApplication(sys.argv)
    win = ModernPanel(); win.resize(1180,760); win.center_on_primary_screen(); win.show(); QTimer.singleShot(120, win.show_window)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
