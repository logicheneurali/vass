import os
import subprocess
import sys
import time
import copy
from utils import get_project_root

from PySide6.QtCore import Qt, QTimer, QEvent, QPropertyAnimation, Signal, QPoint, QSize
from PySide6.QtGui import QPainter, QColor, QFont, QFontMetrics, QIcon, QPainterPath, QPen
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QPushButton, QLabel,
    QVBoxLayout, QHBoxLayout, QStackedWidget, QMenu, QMessageBox,
    QLineEdit, QSpacerItem, QSizePolicy, QDialog,
    QFrame, QScrollArea, QSlider, QCheckBox, QComboBox, QTextEdit,
    QProgressBar, QGroupBox, QListWidget, QListWidgetItem,
)
from theme import BG, BTN_BG, BTN_FG, LABEL_FG, BTN_DEL_BG, BTN_DEL_FG, ENTRY_BG, DESCRIPTION_FG, FRAME_BORDER, FG, BASE_STYLESHEET
from activity_tracker import get_tracker, CATEGORY_COLORS
from icons import icon, icon_dual, pixmap
from smooth_scroll import SmoothScrollArea


def _is_wayland():
    if os.environ.get("QT_QPA_PLATFORM", "").lower() in ("xcb", "x11"):
        return False
    return bool(os.environ.get("WAYLAND_DISPLAY") or os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland")


def _get_window_pos(widget):
    """Get window position. Works correctly on X11/XCB. On Wayland uses mapToGlobal as best-effort."""
    if _is_wayland():
        try:
            gpos = widget.mapToGlobal(QPoint(0, 0))
            return gpos.x(), gpos.y()
        except Exception:
            return 0, 0
    return widget.x(), widget.y()


def _try_system_move(widget):
    """Try Wayland compositor-initiated move. Returns True if handled."""
    if not _is_wayland():
        return False
    try:
        wh = widget.windowHandle()
        if wh is not None and hasattr(wh, "startSystemMove"):
            wh.startSystemMove()
            return True
    except Exception:
        pass
    return False


BASE = get_project_root()
SRC = os.path.join(BASE, "src")
SVG_PATH = os.path.join(BASE, "vass.svg")
VERSION_PATH = os.path.join(BASE, "VERSION")

class WaveformPlayer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("background-color: #101010;")
        self.data = None
        self.sr = None
        self.total = 0
        self.peaks = []
        self.sample_pos = 0

    def load_data(self, data, samplerate):
        self.data = data
        self.sr = samplerate
        self.total = len(data)
        self._compute_peaks()

    def _compute_peaks(self):
        if self.data is None or self.total == 0:
            self.peaks = []
            return
        n = max(1, self.total // max(self.width(), 1))
        self.peaks = []
        for i in range(0, self.total, n):
            chunk = self.data[i:i + n]
            self.peaks.append(float(max(abs(chunk).max(), 0.001)))
        self.update()

    def set_pos(self, sample_pos):
        self.sample_pos = sample_pos
        self.update()

    def paintEvent(self, event):
        if not self.peaks:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()
        mid = h / 2
        max_h = max(h / 2 - 4, 2)
        n = len(self.peaks)
        painter.setPen(QColor("#3498db"))
        for i, p in enumerate(self.peaks):
            x = i * w / n
            amp = min(p * max_h * 2, max_h)
            painter.drawLine(int(x), int(mid - amp), int(x), int(mid + amp))
        if self.total > 0:
            px = self.sample_pos / self.total * w
            painter.setPen(Qt.GlobalColor.white)
            painter.drawLine(int(px), 0, int(px), h)


class VolumeTopBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(6)
        self._ratio = 0.50

    def set_volume(self, ratio):
        self._ratio = max(0.0, min(1.0, ratio))
        self.setToolTip(f"{int(self._ratio * 100)}%")
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()
        inset = h

        # Volume fill trapezoid, centered
        fw = int(w * self._ratio)
        if fw > 0:
            left = (w - fw) // 2
            right = left + fw
            vol = QPainterPath()
            vol.moveTo(left, 0)
            vol.lineTo(right, 0)
            vol.lineTo(right - inset, h)
            vol.lineTo(left + inset, h)
            vol.closeSubpath()
            painter.fillPath(vol, QColor("#2ecc71"))

        # Noise floor indicator (debug only)
        nf_ratio = getattr(self, '_noise_floor_ratio', 0)
        if nf_ratio > 0.001 and getattr(self, '_debug_enabled', False):
            nf_w = int(w * nf_ratio)
            if nf_w > 0:
                left = (w - nf_w) // 2
                right = left + nf_w
                bar_h = max(2, h // 3)
                bar_y = (h - bar_h) // 2
                nf = QPainterPath()
                nf.moveTo(left, bar_y)
                nf.lineTo(right, bar_y)
                nf.lineTo(right - inset, bar_y + bar_h)
                nf.lineTo(left + inset, bar_y + bar_h)
                nf.closeSubpath()
                painter.fillPath(nf, QColor("#e67e22"))


class MemoryBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(6)
        self._ratio = 0.0
        self._color = QColor(105, 219, 124, 220)
        self._tip_desc = ""
        self._tip_val = 0
        self._tip_max = 0
        self._tip_unit = ""

    def set_ratio(self, ratio):
        self._ratio = min(max(ratio, 0.0), 1.0)
        self.update()

    def set_value(self, value, min_val, max_val):
        if max_val > min_val:
            self._ratio = min(max((value - min_val) / (max_val - min_val), 0.0), 1.0)
        else:
            self._ratio = 0.0
        self._tip_val = value
        self._tip_max = max_val
        self._update_tooltip()
        self.update()

    def set_color(self, hex_color):
        c = QColor(hex_color)
        c.setAlpha(200)
        self._color = c
        self.update()

    def set_level(self, level):
        self._ratio = max(0.0, min(1.0, level))
        self.update()

    def set_tooltip_context(self, description, unit):
        self._tip_desc = description
        self._tip_unit = unit

    def _update_tooltip(self):
        if self._tip_max > 0:
            self.setToolTip(f"{self._tip_desc}: {self._tip_val}/{self._tip_max} {self._tip_unit}")
        elif self._tip_max == 0 and self._tip_unit:
            self.setToolTip(f"{self._tip_desc}: {self._tip_val:.2f}/{self._ratio:.2f}")
        elif self._tip_desc:
            self.setToolTip(f"{self._tip_desc}: {self._tip_val}/{self._tip_max} {self._tip_unit}")

    def setVisible(self, visible):
        super().setVisible(visible)
        if not visible:
            self._ratio = 0.0
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()
        inset = h

        fw = int(w * self._ratio)
        if fw > 0:
            left = (w - fw) // 2
            right = left + fw
            bar = QPainterPath()
            bar.moveTo(left + inset, 0)
            bar.lineTo(right - inset, 0)
            bar.lineTo(right, h)
            bar.lineTo(left, h)
            bar.closeSubpath()
            painter.fillPath(bar, self._color)


class _ChatLineEdit(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._history = []
        self._history_index = 0
        self._saved_text = ""

    def add_to_history(self, text):
        if text and (not self._history or self._history[-1] != text):
            self._history.append(text)
        self._history_index = len(self._history)
        self._saved_text = ""

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Up:
            if not self._history:
                return
            if self._history_index == len(self._history):
                self._saved_text = self.text()
            if self._history_index > 0:
                self._history_index -= 1
                self.setText(self._history[self._history_index])
                self.setCursorPosition(len(self.text()))
            return
        elif event.key() == Qt.Key_Down:
            if not self._history:
                return
            if self._history_index < len(self._history) - 1:
                self._history_index += 1
                self.setText(self._history[self._history_index])
                self.setCursorPosition(len(self.text()))
            elif self._history_index == len(self._history) - 1:
                self._history_index = len(self._history)
                self.setText(self._saved_text)
                self.setCursorPosition(len(self.text()))
            return
        super().keyPressEvent(event)


class _CompactWidget(QWidget):
    """Custom widget disegnato con QPainter: 3 cerchi concentrici + icona centrale."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._main_window = parent
        self.setFixedSize(36, 36)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._color = QColor("#2ecc71")
        self._state = "listening"
        self._noise_floor_raw = 0.0
        self._tool_color = None
        self._last_click_time = 0

    def set_noise_floor(self, raw):
        self._noise_floor_raw = raw
        self.update()

    def set_tool(self, color=None):
        self._tool_color = QColor(color) if color else None
        self.update()

    def set_state(self, color, state):
        self._color = QColor(color)
        self._state = state
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        r, g, b = self._color.red(), self._color.green(), self._color.blue()

        p.setPen(Qt.PenStyle.NoPen)
        raw = self._noise_floor_raw
        if raw > 0.15:
            severity = min(1.0, (raw - 0.15) / 0.45)
            nr = int(r + (231 - r) * severity)
            ng = int(g + (76 - g) * severity)
            nb = int(b + (60 - b) * severity)
            p.setBrush(QColor(nr, ng, nb, 51))
        else:
            p.setBrush(QColor(r, g, b, 51))
        p.drawEllipse(2, 2, 32, 32)

        p.setBrush(QColor(r, g, b, 127))
        p.drawEllipse(6, 6, 24, 24)

        p.setBrush(QColor(r, g, b, 255))
        p.drawEllipse(10, 10, 16, 16)

        p.setBrush(Qt.GlobalColor.white)
        p.setPen(Qt.PenStyle.NoPen)
        self._draw_icon(p)

        if self._tool_color is not None:
            p.setBrush(self._tool_color)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(15, 26, 6, 6)

    def _draw_icon(self, p):
        if self._state == "loading":
            return

        cx, cy = 18, 18

        if self._state == "recording":
            p.drawEllipse(cx - 4, cy - 4, 8, 8)
            return

        if self._state == "playing":
            path = QPainterPath()
            path.moveTo(cx - 5, cy - 6)
            path.lineTo(cx - 5, cy + 6)
            path.lineTo(cx + 6, cy)
            path.closeSubpath()
            p.drawPath(path)
            return

        if self._state == "paused":
            p.drawRect(cx - 5, cy - 6, 3, 12)
            p.drawRect(cx + 2, cy - 6, 3, 12)
            return

        if self._state in ("waiting", "waiting_resources"):
            r = 2
            for dx in (-4, 0, 4):
                p.drawEllipse(cx + dx - r, cy - r, r * 2, r * 2)
            return

        if self._state == "running_script":
            path = QPainterPath()
            s = 5
            path.moveTo(cx, cy - s)
            path.lineTo(cx + s, cy)
            path.lineTo(cx, cy + s)
            path.lineTo(cx - s, cy)
            path.closeSubpath()
            p.drawPath(path)
            return

        if self._state == "listening":
            for i, h in enumerate([5, 9, 5]):
                x = cx - 4 + i * 4 - 1
                y = cy - h // 2
                p.drawRoundedRect(x, y, 2, h, 1, 1)
            return

    def mousePressEvent(self, event):
        win = self._main_window
        if event.button() == Qt.MouseButton.RightButton:
            if win and hasattr(win, '_menu'):
                win._menu.exec(event.globalPosition().toPoint())
            return
        if event.button() == Qt.MouseButton.MiddleButton:
            if win and hasattr(win, '_exit_app'):
                win._exit_app()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            if _try_system_move(win or self):
                return
            now = time.monotonic()
            interval = QApplication.instance().doubleClickInterval() / 1000.0
            if self._last_click_time and now - self._last_click_time < interval:
                self._last_click_time = 0
                if win and hasattr(win, '_toggle_compact_mode'):
                    win._toggle_compact_mode(False)
                return
            self._last_click_time = now
            self._drag_start = event.globalPosition().toPoint()
            self._drag_pos = self._drag_start
            self._drag_started = False

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos:
            cur = event.globalPosition().toPoint()
            if not self._drag_started and self._drag_start:
                if (cur - self._drag_start).manhattanLength() > 5:
                    self._drag_started = True
            if self._drag_started:
                win = self._main_window
                if win:
                    win.move(
                        win.x() + cur.x() - self._drag_pos.x(),
                        win.y() + cur.y() - self._drag_pos.y(),
                    )
            self._drag_pos = cur

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._drag_pos is not None:
            win = self._main_window
            if not self._drag_started:
                if win and hasattr(win, 'app') and win.app:
                    win.app.handle_button_press()
            else:
                if win:
                    if hasattr(win, '_clamp_to_screen'):
                        win._clamp_to_screen()
                    if hasattr(win, 'app') and win.app:
                        x, y = _get_window_pos(win)
                        if x or y:
                            win._pending_pos = (x, y, win.width(), win.height())
                            win._pos_debounce.start()
        self._drag_pos = None
        self._drag_start = None


