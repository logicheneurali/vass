import os
import subprocess
import sys
import time
from utils import get_project_root

from PySide6.QtCore import Qt, QTimer, QEvent, QPropertyAnimation, Signal, QPoint
from PySide6.QtGui import QPainter, QColor, QFont, QFontMetrics, QIcon, QPainterPath, QPen
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QPushButton, QLabel,
    QVBoxLayout, QHBoxLayout, QStackedWidget, QMenu, QMessageBox,
    QLineEdit, QSpacerItem, QSizePolicy, QDialog,
    QFrame, QScrollArea, QSlider, QCheckBox, QComboBox, QTextEdit, QTextBrowser,
    QAbstractScrollArea,
    QProgressBar,
)
from theme import BG, BTN_BG, BTN_FG, LABEL_FG, BTN_DEL_BG, BTN_DEL_FG, ENTRY_BG, DESCRIPTION_FG, FRAME_BORDER, FG
from activity_tracker import get_tracker, CATEGORY_COLORS

BASE = get_project_root()
SRC = os.path.join(BASE, "src")
SVG_PATH = os.path.join(BASE, "vass.svg")
VERSION_PATH = os.path.join(BASE, "VERSION")


class SplashScreen(QWidget):
    """Splash screen shown during app initialization."""

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.SplashScreen
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setFixedSize(300, 110)
        self.setStyleSheet(f"background-color: {BG}; border-radius: 8px;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(4)

        title_lbl = QLabel("VASS")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_font = QFont("Segoe UI", 16)
        title_font.setBold(True)
        title_lbl.setFont(title_font)
        title_lbl.setStyleSheet(f"color: {FG}; background: transparent;")
        layout.addWidget(title_lbl)

        self._version_lbl = QLabel(self._load_version())
        self._version_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._version_lbl.setStyleSheet(f"color: {DESCRIPTION_FG}; font-size: 10px; background: transparent;")
        layout.addWidget(self._version_lbl)

        self._detail = QLabel("Starting...")
        self._detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._detail.setStyleSheet(f"color: {LABEL_FG}; font-size: 11px; background: transparent;")
        layout.addWidget(self._detail)

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(4)
        self._bar.setStyleSheet(
            f"QProgressBar {{ background-color: {ENTRY_BG}; border: none; border-radius: 2px; }}"
            f"QProgressBar::chunk {{ background-color: #2ecc71; border-radius: 2px; }}")
        layout.addWidget(self._bar)

        self._center_on_screen()

    def _load_version(self):
        try:
            with open(VERSION_PATH) as f:
                return f"v{f.read().strip()}"
        except Exception:
            return ""

    def _center_on_screen(self):
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = geo.left() + (geo.width() - self.width()) // 2
            y = geo.top() + (geo.height() - self.height()) // 2
            self.move(x, y)

    def set_progress(self, value, maximum=100, detail=""):
        self._bar.setRange(0, maximum)
        self._bar.setValue(value)
        if detail:
            self._detail.setText(detail)
        QApplication.processEvents()

    def finish(self):
        self.hide()
        self.deleteLater()


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
                        win._pending_pos = (win.x(), win.y(), win.width(), win.height())
                        win._pos_debounce.start()
        self._drag_pos = None
        self._drag_start = None


class InfoPanel(QFrame):
    """Floating panel: dynamic tabs for notifications by type, AI links, AI responses."""

    _TYPE_ICONS = {
        "rss": "\U0001f4f0", "timer": "\u23f0", "event": "\U0001f4c5",
        "schedule": "\U0001f4cb", "mail": "\U0001f4e7", "auth": "\U0001f511",
        "script": "\U0001f4dc", "agent": "\U0001f916",
        "profile": "\U0001f9d1", "world_event": "\U0001f30d",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._t = lambda k: k
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_AlwaysShowToolTips, True)
        self.setStyleSheet(
            "InfoPanel { background-color: #0d1117; border: 1px solid #0f3460; "
            "border-radius: 6px; }"
        )
        self._links = []
        self._ai_responses = []
        self._tab = "all"
        self._expanded = False
        self._user_opened = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)
        self._parent_window = None

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(4, 4, 4, 4)
        self._layout.setSpacing(2)

        self._tab_row = QHBoxLayout()
        self._tab_row.setSpacing(2)
        self._tab_buttons = {}

        self._overflow_menu = QMenu()
        self._overflow_btn = QPushButton("+")
        self._overflow_btn.setFixedSize(20, 20)
        self._overflow_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #888; border: none; "
            "font-size: 14px; font-weight: bold; }"
            "QPushButton:hover { color: #e0e0e0; }")
        self._overflow_btn.setMenu(self._overflow_menu)
        self._overflow_btn.hide()
        self._tab_row.addWidget(self._overflow_btn)

        self._tab_row.addStretch()
        self._expand_btn = QPushButton("\u2194")
        self._expand_btn.setFixedSize(20, 20)
        self._expand_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #888; border: none; "
            "font-size: 14px; font-weight: bold; }"
            "QPushButton:hover { color: #e0e0e0; }"
        )
        self._expand_btn.setToolTip("Expand")
        self._expand_btn.clicked.connect(self._toggle_expand)
        self._tab_row.addWidget(self._expand_btn)
        close_btn = QPushButton("x")
        close_btn.setFixedSize(20, 20)
        close_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #888; border: none; "
            "font-size: 14px; font-weight: bold; }"
            "QPushButton:hover { color: #e94560; }"
        )
        close_btn.clicked.connect(self._close_panel)
        self._tab_row.addWidget(close_btn)
        self._layout.addLayout(self._tab_row)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self._scroll_widget = QWidget()
        self._scroll_widget.setStyleSheet("background: transparent;")
        self._scroll_layout = QVBoxLayout(self._scroll_widget)
        self._scroll_layout.setContentsMargins(2, 2, 2, 2)
        self._scroll_layout.setSpacing(2)
        self._scroll.setWidget(self._scroll_widget)
        self._layout.addWidget(self._scroll)

        self._mark_btn = QPushButton(self._t("gui.mark_all_read"))
        self._mark_btn.setStyleSheet(
            "QPushButton { background-color: #16213e; color: #888; border: none; "
            "border-radius: 3px; padding: 3px 8px; font-size: 11px; }"
            "QPushButton:hover { background-color: #1a5276; color: #e0e0e0; }"
        )
        self._mark_btn.clicked.connect(self._mark_all_read)
        self._mark_btn.hide()
        self._layout.addWidget(self._mark_btn)

        self.setMouseTracking(True)
        self.hide()

    def _tab_style(self, active):
        c = "#e94560" if active else "#888"
        return (
            f"QPushButton {{ background: transparent; color: {c}; border: none; "
            f"font-size: 11px; font-weight: bold; padding: 2px 6px; }}"
            f"QPushButton:hover {{ color: #e94560; }}"
        )

    def _build_toolbar(self, active_tab):
        self._overflow_menu.clear()

        # Remove old tab buttons but keep stretch, expand, close
        for btn in list(self._tab_buttons.values()):
            self._tab_row.removeWidget(btn)
            btn.deleteLater()
        self._tab_buttons.clear()

        self._overflow_menu.clear()
        self._overflow_btn.hide()

        # Compute notification type counts (unread)
        type_counts = {}
        if hasattr(self, '_nm') and self._nm:
            for n in self._nm.list_all():
                d = n.get("data")
                if isinstance(d, dict):
                    t = d.get("type") or "other"
                else:
                    t = "other"
                type_counts[t] = type_counts.get(t, 0) + (0 if n.get("read") else 1)

        # Build ordered list: all first, then special tabs, then type tabs by unread count
        all_label = self._t("gui.all_notifications")
        ordered = [("all", "all", all_label if self._expanded else "\U0001f4cb", all_label)]

        if self._links:
            links_label = self._t("gui.links")
            ordered.append(("links", "links", links_label if self._expanded else "\U0001f517", links_label))
        if self._ai_responses:
            ai_label = self._t("gui.ai_responses")
            ordered.append(("ai", "ai", ai_label if self._expanded else "\U0001f4ac", ai_label))

        for t in sorted(type_counts, key=lambda t: -type_counts[t]):
            icon = self._TYPE_ICONS.get(t, "\U0001f514")
            count = type_counts[t]
            label = self._t(f"notification_types.{t}")
            badge = f"({count})" if count > 0 else ""
            if self._expanded:
                full_label = f"{icon} {label} {badge}".strip()
            else:
                full_label = f"{icon}{badge}" if badge else icon
            ordered.append((t, t, full_label, f"{icon} {label}"))

        # Calculate available width based on parent window geometry
        if self._parent_window:
            geo = self._parent_window.geometry()
            panel_w = int(geo.width() * (3.0 if self._expanded else 1.25))
        else:
            panel_w = 275
        available = panel_w - 60  # expand + close + overflow + margins

        for t_id, t_type, display_text, tooltip_text in ordered:
            btn = QPushButton(display_text)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(tooltip_text)
            btn.clicked.connect(lambda checked=None, tab=t_type: self._switch_tab(tab))
            btn.setStyleSheet(self._tab_style(t_type == active_tab))
            btn_w = btn.sizeHint().width() + 8

            # Always add the first tab (ALL), rest only if they fit
            if len(self._tab_buttons) == 0 or available - btn_w >= 0:
                available -= btn_w
                self._tab_buttons[t_id] = btn
                # Insert at position 0 (leftmost, before overflow/stretch/expand/close)
                self._tab_row.insertWidget(0, btn)
            else:
                self._overflow_btn.show()
                action = self._overflow_menu.addAction(label)
                action.triggered.connect(lambda checked=None, tab=t_type: self._switch_tab(tab))

    def _switch_tab(self, tab):
        self._tab = tab
        self._build_toolbar(tab)
        self._mark_btn.setVisible(tab in ("all", "notifications", "other") or tab not in ("links", "ai"))
        if tab == "links":
            self._build_links()
        elif tab == "ai":
            self._build_ai_responses()
        else:
            filter_type = "all" if tab in ("all", "notifications") else tab
            self._build_notifications(filter_type)
        self._scroll.verticalScrollBar().setValue(0)

    def _reset_timer(self):
        if self.isVisible() and not self._user_opened:
            self._timer.start(30000)

    def _close_panel(self):
        self._user_opened = False
        self.hide()

    def mouseMoveEvent(self, event):
        self._reset_timer()
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        self._reset_timer()
        super().mousePressEvent(event)

    def show_panel(self, tab, parent_window, user_opened=False):
        self._parent_window = parent_window
        self._user_opened = user_opened
        self._mark_btn.setText(self._t("gui.mark_all_read"))
        self._switch_tab(tab)
        self._position(parent_window)
        self.show()
        self.raise_()
        if not user_opened:
            self._timer.start(30000)

    def set_links(self, urls, parent_window):
        self._links = urls
        if not urls:
            return
        self._parent_window = parent_window
        self._switch_tab("links")
        self._position(parent_window)
        self.show()
        self.raise_()
        self._timer.start(30000)

    def set_ai_responses(self, responses, parent_window):
        self._ai_responses = responses
        self._parent_window = parent_window
        if self.isVisible() and self._tab == "ai":
            self._build_ai_responses()
        else:
            self._switch_tab("ai")
        self._position(parent_window)
        self.show()
        self.raise_()
        self._timer.start(30000)

    def _clear_scroll(self):
        while self._scroll_layout.count():
            item = self._scroll_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _fs(self, base):
        return base + (2 if self._expanded else 0)

    def _build_links(self):
        self._clear_scroll()
        if not self._links:
            return
        from urllib.parse import urlparse
        for url in self._links:
            domain = urlparse(url).netloc or url
            display = url if len(url) <= 50 else url[:47] + "..."
            btn = QPushButton(f"{domain}\n{display}")
            btn.setStyleSheet(
                f"QPushButton {{ background-color: #16213e; color: #aaaaaa; "
                f"border: none; border-radius: 3px; padding: 4px 8px; "
                f"text-align: left; font-size: {self._fs(11)}px; }}"
                f"QPushButton:hover {{ background-color: #1a5276; color: #e0e0e0; }}"
            )
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(url)
            btn.clicked.connect(lambda checked, u=url: (self._reset_timer(), self._open_url(u)))
            self._scroll_layout.addWidget(btn)
        self._scroll_layout.addStretch()

    def _build_notifications(self, filter_type="all"):
        self._clear_scroll()
        if not hasattr(self, '_nm') or self._nm is None:
            return
        notifs = self._nm.list_all()
        if filter_type != "all":
            notifs = [n for n in notifs if (n.get("data", {}).get("type") or "other") == filter_type]
        if not notifs:
            lbl = QLabel(self._t("gui.no_notifications"))
            lbl.setStyleSheet(f"color: #888; font-size: {self._fs(11)}px; padding: 8px;")
            self._scroll_layout.addWidget(lbl)
            return
        for n in notifs:
            icon = self._TYPE_ICONS.get(n.get("data", {}).get("type", ""), "\U0001f514")
            dot = "\u25cf" if not n.get("read", False) else "\u25cb"
            prio = n.get("priority", 1)
            if prio >= 8:
                dot_color = "#e74c3c"
            elif prio >= 4:
                dot_color = "#f1c40f"
            else:
                dot_color = "#3498db"
            txt = n.get("text", "")
            if n.get("data", {}).get("type") == "rss":
                tags = n.get("data", {}).get("tags", [])
                if tags:
                    txt += f' <span style="color:#666;font-size:9px;">[{", ".join(tags)}]</span>'
            # Top row: dot, icon, timestamp
            top_row = QHBoxLayout()
            dot_lbl = QLabel(dot)
            dot_lbl.setStyleSheet(f"color: {dot_color}; font-size: {self._fs(10)}px; background: transparent;")
            dot_lbl.setFixedWidth(14)
            top_row.addWidget(dot_lbl)
            icon_lbl = QLabel(icon)
            icon_lbl.setStyleSheet(f"font-size: {self._fs(12)}px; background: transparent;")
            icon_lbl.setFixedWidth(22)
            top_row.addWidget(icon_lbl)
            ts_lbl = QLabel(n.get("ts", ""))
            ts_lbl.setStyleSheet(f"color: #666; font-size: {self._fs(10)}px; background: transparent;")
            top_row.addWidget(ts_lbl)
            top_row.addStretch()
            # Bottom row: full-width text
            text_lbl = QLabel(txt)
            text_lbl.setStyleSheet(f"color: #aaa; font-size: {self._fs(11)}px; background: transparent;")
            text_lbl.setWordWrap(True)
            # Container
            container = QWidget()
            container.setStyleSheet("background: transparent;")
            container_layout = QVBoxLayout(container)
            container_layout.setContentsMargins(4, 3, 4, 3)
            container_layout.setSpacing(1)
            container_layout.addLayout(top_row)
            container_layout.addWidget(text_lbl)
            container.setCursor(Qt.CursorShape.PointingHandCursor)
            nid = n["id"]
            link = n.get("data", {}).get("link", "")
            container.mousePressEvent = lambda e, nid=nid, link=link: self._on_notif_click(nid, link)
            self._scroll_layout.addWidget(container)
        self._scroll_layout.addStretch()

    def _on_notif_click(self, nid, link):
        self._reset_timer()
        if hasattr(self, '_nm') and self._nm is not None:
            for n in self._nm.list_all():
                if n["id"] == nid:
                    n["read"] = True
                    break
            if hasattr(self, '_update_bell_cb'):
                self._update_bell_cb()
            filter_type = "all" if self._tab in ("all", "notifications") else self._tab
            scroll_val = self._scroll.verticalScrollBar().value()
            self._build_notifications(filter_type)
            self._scroll.verticalScrollBar().setValue(scroll_val)
        if link:
            import webbrowser
            webbrowser.open(link)

    def _mark_all_read(self):
        if hasattr(self, '_nm') and self._nm is not None:
            self._nm.mark_all_read()
            if hasattr(self, '_update_bell_cb') and self._update_bell_cb:
                self._update_bell_cb()
            self.hide()

    def _build_ai_responses(self):
        self._clear_scroll()
        assistant_msgs = [r for r in self._ai_responses if r.get("role") == "assistant"]
        if not assistant_msgs:
            lbl = QLabel(self._t("gui.ai_no_responses"))
            lbl.setStyleSheet(f"color: #888; font-size: {self._fs(11)}px; padding: 8px;")
            self._scroll_layout.addWidget(lbl)
            return
        last = None
        for msg in assistant_msgs[-10:]:
            text = msg.get("content", "")
            container = QWidget()
            container.setStyleSheet("background: transparent;")
            c_layout = QVBoxLayout(container)
            c_layout.setContentsMargins(4, 3, 4, 3)
            c_layout.setSpacing(1)
            browser = QTextBrowser()
            browser.setMarkdown(text)
            browser.setOpenExternalLinks(True)
            browser.setReadOnly(True)
            browser.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            browser.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            browser.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents)
            browser.setStyleSheet(
                f"color: #aaa; font-size: {self._fs(11)}px; background: transparent; "
                "padding: 4px; border: 1px solid #16213e; border-radius: 3px; "
                "selection-background-color: #1a5276; "
                "QScrollBar { width: 0px; }"
            )
            browser.document().setDocumentMargin(0)
            browser.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
            browser.setToolTip(self._t("gui.click_to_copy"))
            browser.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextBrowserInteraction | Qt.TextInteractionFlag.TextSelectableByKeyboard
            )
            c_layout.addWidget(browser)
            self._scroll_layout.addWidget(container)
            last = container
        self._scroll_layout.addStretch()
        if last:
            QTimer.singleShot(0, lambda c=last: self._scroll.verticalScrollBar().setValue(
                c.mapTo(self._scroll_widget, QPoint(0, 0)).y()))

    def _copy_text(self, text):
        QApplication.clipboard().setText(text)

    def _toggle_expand(self):
        self._expanded = not self._expanded
        self._expand_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #e94560; border: none; "
            "font-size: 14px; font-weight: bold; }"
            "QPushButton:hover { color: #e0e0e0; }"
        ) if self._expanded else self._expand_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #888; border: none; "
            "font-size: 14px; font-weight: bold; }"
            "QPushButton:hover { color: #e0e0e0; }"
        )
        self._expand_btn.setToolTip("Reduce" if self._expanded else "Expand")
        self._switch_tab(self._tab)
        if self._parent_window:
            self._position(self._parent_window)

    def _position(self, parent):
        geo = parent.geometry()
        screen = QApplication.primaryScreen().availableGeometry()

        if self._expanded:
            panel_w = int(geo.width() * 3.0)
            mid_x = screen.left() + screen.width() // 2
            if geo.center().x() < mid_x:
                px = geo.left()
            else:
                px = geo.right() - panel_w
        else:
            panel_w = int(geo.width() * 1.25)
            px = geo.center().x() - panel_w // 2

        if self._tab == "links":
            count = len(self._links)
            panel_h = min(count * 38 + 52, 280)
        elif self._tab == "ai":
            count = len([r for r in self._ai_responses if r.get("role") == "assistant"])
            panel_h = min(count * 120 + 52, 500)
        else:
            count = 5
            panel_h = min(count * 38 + 52, 280)

        panel_w = min(panel_w, screen.width() - 20)
        panel_h = min(panel_h, screen.height() - 20)

        if self._expanded:
            mid_x = screen.left() + screen.width() // 2
            if geo.center().x() < mid_x:
                px = geo.left()
            else:
                px = geo.right() - panel_w
        else:
            px = geo.center().x() - panel_w // 2

        mid_y = screen.top() + screen.height() // 2
        if geo.center().y() < mid_y:
            py = geo.bottom() + 8
        else:
            py = geo.top() - panel_h - 8
        px = max(screen.left(), min(px, screen.right() - panel_w))
        py = max(screen.top(), min(py, screen.bottom() - panel_h))
        self.setGeometry(px, py, panel_w, panel_h)

    def _open_url(self, url):
        import webbrowser
        webbrowser.open(url)


class VassGUI(QMainWindow):
    set_state_signal = Signal(str, str)
    update_memory_signal = Signal()
    start_tts_signal = Signal(object, int, int, object)
    stop_tts_signal = Signal()
    schedule_signal = Signal(object)
    auth_requested_signal = Signal(str, str)
    form_signal = Signal(str, list)
    volume_signal = Signal(float)
    noise_floor_signal = Signal(float, float)  # gain, raw_noise
    chat_text_signal = Signal(str)
    tool_indicator_signal = Signal(str, str)
    compact_mode_signal = Signal(bool)
    debug_border_signal = Signal()
 
    COLORS = {
        "listening": "#2ecc71",
        "recording": "#e67e22",
        "waiting": "#f1c40f",
        "waiting_resources": "#f39c12",
        "playing": "#3498db",
        "paused": "#e74c3c",
        "running_script": "#9b59b6",
    }

    def __init__(self, app, x=100, y=100, width=220, height=60,
                 font_family="Segoe UI", font_size=14, language="it"):
        super().__init__()
        self.app = app
        self.language = language
        from i18n import t
        self._t = lambda path: t(path, self.language)
        self._health_ok = True
        self._current_bg = "#101010"
        self._current_state = "listening"
        self._current_detail = ""
        self._current_mode = "chat"
        self._compact_mode = False

        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setStyleSheet("QMainWindow { background-color: #101010; }")
        self.setGeometry(x, y, width, height)

        ico_path = os.path.join(BASE, "vass.ico")
        if os.path.exists(ico_path):
            self.setWindowIcon(QIcon(ico_path))
            QApplication.setWindowIcon(QIcon(ico_path))

        self._font_family = font_family
        self._font_size = font_size

        self._splash = SplashScreen()
        self._splash.show()

        # --- Layout ---
        central = QWidget()
        self.setCentralWidget(central)
        central.setObjectName("_centralWidget")
        self._central = central
        self._central.installEventFilter(self)
        self._refresh_debug_border()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.volume_top_bar = VolumeTopBar()
        outer.addWidget(self.volume_top_bar)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        # Stacked: page 0 = main button, page 1 = waveform player
        self.stacked = QStackedWidget()
        self._build_main_button()
        self.stacked.addWidget(self.btn)

        self.player = WaveformPlayer()
        self.stacked.addWidget(self.player)

        self._build_loading_widget()
        self.stacked.addWidget(self.loading_widget)

        self._btn_full_text = ""
        self.stacked.installEventFilter(self)

        self._left_spacer = QSpacerItem(0, 0, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
        self._right_spacer = QSpacerItem(0, 0, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)

        # ── Left-side widgets ──────────────────────────────────────────
        # To add a new left-side component:
        #   1. Create the widget above
        #   2. Add it to the row layout: row.addWidget(widget)
        #   3. Append it to self._left_side for automatic balancing
        self._left_side = []
        self._right_side = []

        self._bell_btn = QPushButton("0")
        self._bell_btn.setStyleSheet(
            "QPushButton { background-color: transparent; color: #3f3f3f; "
            "border: none; font-size: 10px; padding: 2px 4px; }"
            "QPushButton:hover { background-color: #3d3d3d; color: #dddddd; }"
        )
        self._bell_btn.setFixedWidth(35)
        self._bell_btn.setToolTip(self._t("gui.notifications"))
        self._bell_btn.clicked.connect(lambda: self._show_info_panel("all"))
        row.addWidget(self._bell_btn)
        self._left_side.append(self._bell_btn)

        self._tool_indicator = QLabel()
        self._tool_indicator.setFixedSize(10, 10)
        self._tool_indicator.setVisible(False)
        self._tool_indicator.setToolTip("")
        row.addWidget(self._tool_indicator)
        self._left_side.append(self._tool_indicator)

        row.addSpacerItem(self._left_spacer)
        row.addWidget(self.stacked)
        row.addSpacerItem(self._right_spacer)

        self.replay_btn = QPushButton("\u21bb")
        self.replay_btn.setStyleSheet(
            "QPushButton { background-color: transparent; color: #ffffff; "
            "border: none; font-size: 10px; padding: 2px; }"
            "QPushButton:hover { background-color: #3d3d3d; color: #dddddd; }"
        )
        self.replay_btn.setFixedWidth(16)
        self.replay_btn.setVisible(False)
        self.replay_btn.clicked.connect(self._on_replay)
        self.replay_btn._right_click_cb = self.open_history
        self.replay_btn.mousePressEvent = self._replay_btn_press
        row.addWidget(self.replay_btn)
        self._right_side.append(self.replay_btn)

        # Menu button with popup
        # Right-side widget — automatically balanced by _rebalance_spacers()
        self._menu_btn = QPushButton("\u2630")
        self._menu_btn.setStyleSheet(
            "QPushButton { background-color: transparent; color: #888888; "
            "border: none; font-size: 10px; padding: 2px; }"
            "QPushButton:hover { background-color: #3d3d3d; color: #dddddd; }"
        )
        self._menu_btn.setFixedWidth(16)
        self._menu = QMenu()
        self._menu.setStyleSheet(
            "QMenu { background-color: #2d2d2d; color: #e0e0e0; "
            "border: 1px solid #3c3c3c; padding: 4px; }"
            "QMenu::item { padding: 6px 20px; }"
            "QMenu::item:selected { background-color: #0d7377; }"
        )
        self._menu.addAction(self._t("gui.menu.settings"), self.open_settings)
        self._menu.addAction(self._t("gui.menu.commands"), self.open_commands)
        self._menu.addAction(self._t("gui.menu.scripts"), self.open_scripts)
        self._menu.addAction(self._t("gui.menu.history"), self.open_history)
        self._menu.addAction(self._t("gui.menu.memory_editor"), self.open_memory_editor)
        self._menu.addAction(self._t("gui.menu.sources"), self.open_sources)
        self._menu.addAction(self._t("gui.menu.events"), self.open_events)
        self._menu.addAction(self._t("gui.menu.plugins"), self.open_plugins)
        self._help_menu = self._menu.addMenu(self._t("gui.menu.help"))
        self._help_menu.addAction(self._t("gui.menu.help_usage"), self._open_help_usage)
        self._help_menu.addAction(self._t("gui.menu.help_commands"), self._open_help_commands)
        self._help_menu.addAction(self._t("gui.menu.help_vasscript"), self._open_help_vasscript)
        self._open_windows = []
        self._menu.addSeparator()
        self._mode_chat = self._menu.addAction(self._t("gui.mode.chat"))
        self._mode_chat.setCheckable(True)
        self._mode_chat.triggered.connect(lambda: self._switch_mode("chat"))
        self._mode_transcription = self._menu.addAction(self._t("gui.mode.trascrizione"))
        self._mode_transcription.setCheckable(True)
        self._mode_transcription.triggered.connect(lambda: self._switch_mode("transcription"))
        self._menu.addSeparator()
        self._mem_full = self._menu.addAction(self._t("gui.memory_mode.full"))
        self._mem_full.setCheckable(True)
        self._mem_full.setChecked(True)
        self._mem_full.triggered.connect(lambda: self._switch_memory_mode("full"))
        self._mem_limited = self._menu.addAction(self._t("gui.memory_mode.limited"))
        self._mem_limited.setCheckable(True)
        self._mem_limited.triggered.connect(lambda: self._switch_memory_mode("limited"))
        self._mem_none = self._menu.addAction(self._t("gui.memory_mode.none"))
        self._mem_none.setCheckable(True)
        self._mem_none.triggered.connect(lambda: self._switch_memory_mode("none"))
        self._compact_toggle = self._menu.addAction(self._t("gui.menu.compact_mode"))
        self._compact_toggle.setCheckable(True)
        self._compact_toggle.triggered.connect(lambda checked: self._toggle_compact_mode(checked))
        self._menu.addSeparator()
        self._menu.addAction(self._t("gui.menu.exit"), self._exit_app)
        self._menu_btn.clicked.connect(
            lambda: self._menu.exec(self._menu_btn.mapToGlobal(
                self._menu_btn.rect().bottomLeft()))
        )
        row.addWidget(self._menu_btn)
        self._right_side.append(self._menu_btn)

        self._chat_btn = QPushButton("\u2726")
        self._chat_btn.setStyleSheet(
            "QPushButton { background-color: transparent; color: #888888; "
            "border: none; font-size: 10px; padding: 2px; }"
            "QPushButton:hover { background-color: #3d3d3d; color: #dddddd; }"
            "QPushButton:checked { background-color: transparent; color: #0d7377; }"
        )
        self._chat_btn.setFixedWidth(16)
        self._chat_btn.setCheckable(True)
        self._chat_btn.setVisible(False)
        self._chat_btn.setToolTip(self._t("gui.chat_tooltip"))
        self._chat_btn.clicked.connect(self._toggle_chat_input)
        row.addWidget(self._chat_btn)
        self._right_side.append(self._chat_btn)

        self._chat_input = _ChatLineEdit()
        self._chat_input.setMaxLength(128000)
        self._chat_input.setPlaceholderText(self._t("gui.chat_placeholder"))
        self._chat_input.setStyleSheet(
            "QLineEdit { background-color: #16213e; color: #e0e0e0; "
            "border: none; "
            "padding: 2px 6px; font-size: 12px; "
            "margin-right: 10px; }"
            "QLineEdit:focus { color: #ffffff; }"
        )
        self._chat_input.setVisible(False)
        self._chat_input.returnPressed.connect(self._send_chat_text)
        row.addWidget(self._chat_input, 1)

        self._chat_original_width = None
        self._chat_original_x = None

        outer.addLayout(row)

        # Multi-purpose bar (memory / volume / script progress)
        self.memory_bar = MemoryBar()
        outer.addWidget(self.memory_bar)

        # Compact mode dot
        self._compact_dot = _CompactWidget(self)
        self._compact_dot.setVisible(False)
        self._compact_dot.setToolTip(self._t("gui.button_tooltip"))
        self._compact_dot.set_state("#2ecc71", "listening")
        outer.addWidget(self._compact_dot, alignment=Qt.AlignmentFlag.AlignCenter)
        self._normal_geometry = None

        # Drag state
        self._drag_start = None
        self._drag_pos = None
        self._drag_started = False

        self.btn.mousePressEvent = self._btn_press
        self.btn.mouseMoveEvent = self._btn_move
        self.btn.mouseReleaseEvent = self._btn_release
        self.player.mousePressEvent = self._btn_press
        self.player.mouseMoveEvent = self._btn_move
        self.player.mouseReleaseEvent = self._btn_release

        # Position save debounce (200ms after last drag)
        self._pos_debounce = QTimer()
        self._pos_debounce.setSingleShot(True)
        self._pos_debounce.setInterval(200)
        self._pos_debounce.timeout.connect(self._save_position_debounced)
        self._pending_pos = None

        # TTS polling
        self._tts_polling = False

        # Opacity animations
        self._fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self._fade_anim.setDuration(750)
        self._pulse_anim = QPropertyAnimation(self, b"windowOpacity")
        self._pulse_anim.setDuration(1200)
        self._pulse_anim.setLoopCount(-1)
        self._pulse_anim.setKeyValueAt(0.0, 0.5)
        self._pulse_anim.setKeyValueAt(0.5, 1.0)
        self._pulse_anim.setKeyValueAt(1.0, 0.5)

        # Auth dialog state (thread-safe via signal)
        self._auth_result = None
        self._auth_event = None

        # Connect signals to main-thread slots
        self.set_state_signal.connect(self._on_set_state)
        self.update_memory_signal.connect(self._on_update_memory)
        self.start_tts_signal.connect(self._on_start_tts)
        self.stop_tts_signal.connect(self._on_stop_tts)
        self.schedule_signal.connect(lambda cb: cb(), Qt.ConnectionType.QueuedConnection)
        self.auth_requested_signal.connect(self._on_auth_requested)
        self.form_signal.connect(self._on_form_requested)
        self.volume_signal.connect(self._on_volume)
        self.noise_floor_signal.connect(self._on_noise_floor)
        self.tool_indicator_signal.connect(self._on_tool_indicator)
        self.compact_mode_signal.connect(self.set_compact_mode)
        self.debug_border_signal.connect(self._refresh_debug_border)

        self._auto_fade_enabled = True
        import threading as _th
        _th.Thread(target=self._auto_fade_loop, daemon=True).start()

        self._link_panel = InfoPanel()

        self._on_top_timer = QTimer(self)
        self._on_top_timer.timeout.connect(self._enforce_always_on_top)
        self._on_top_timer.start(30000)

        self._activity_timer = QTimer(self)
        self._activity_timer.setInterval(800)
        self._activity_timer.timeout.connect(self._poll_activity)

        self.show()
        self._clamp_to_screen()

    def showEvent(self, event):
        super().showEvent(event)
        if sys.platform == "win32":
            try:
                import ctypes
                hwnd = int(self.winId())
                GWL_EXSTYLE = -20
                WS_EX_APPWINDOW = 0x00040000
                ex = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex | WS_EX_APPWINDOW)
                ico_path = os.path.join(BASE, "vass.ico")
                if os.path.exists(ico_path):
                    hicon = ctypes.windll.user32.LoadImageW(None, ico_path, 1, 0, 0, 0x00000010)
                    if hicon:
                        GCL_HICON = -14
                        GCL_HICONSM = -34
                        ctypes.windll.user32.SetClassLongPtrW(hwnd, GCL_HICON, hicon)
                        ctypes.windll.user32.SetClassLongPtrW(hwnd, GCL_HICONSM, hicon)
            except Exception:
                pass

    def _clamp_to_screen(self):
        screen = QApplication.primaryScreen()
        if not screen:
            return
        geo = screen.availableGeometry()
        x, y = self.x(), self.y()
        w, h = self.width(), self.height()

        if w > geo.width():
            w = geo.width()
        if h > geo.height():
            h = geo.height()
        if x + w > geo.right():
            x = geo.right() - w
        if y + h > geo.bottom():
            y = geo.bottom() - h
        if x < geo.left():
            x = geo.left()
        if y < geo.top():
            y = geo.top()

        self.setGeometry(x, y, w, h)

    def _enforce_always_on_top(self):
        if sys.platform == "win32":
            try:
                import ctypes
                hwnd = int(self.winId())
                ctypes.windll.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0002 | 0x0001 | 0x0010)
            except Exception:
                pass
        else:
            self.raise_()

    def _switch_mode(self, mode):
        self._mode_chat.setChecked(mode == "chat")
        self._mode_transcription.setChecked(mode == "transcription")
        if self.app:
            self.app.set_mode(mode)

    def _switch_memory_mode(self, mode):
        self._mem_full.setChecked(mode == "full")
        self._mem_limited.setChecked(mode == "limited")
        self._mem_none.setChecked(mode == "none")
        if self.app:
            self.app.set_memory_mode(mode)

    def _exit_app(self):
        reply = QMessageBox.question(
            self, self._t("gui.dialog.exit_title"),
            self._t("gui.dialog.exit_message"),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            QApplication.quit()

    def _toggle_compact_mode(self, checked):
        self.set_compact_mode(checked)
        if self.app:
            self.app.settings["compact_mode"] = checked
            self.app._save_setting("gui", "compact_mode", "true" if checked else "false")
        self._compact_toggle.setChecked(checked)

    def set_compact_mode(self, enabled, from_restore=False):
        if enabled == self._compact_mode:
            return
        self._compact_mode = enabled
        self._compact_toggle.setChecked(enabled)
        if enabled:
            if from_restore:
                normal_x = self.x() + 18 - self.width() // 2
                self._normal_geometry = (normal_x, self.y(), self.width(), self.height())
            else:
                center_x = self.x() + self.width() // 2
                self._normal_geometry = (self.x(), self.y(), self.width(), self.height())
                self.setGeometry(center_x - 18, self.y(), self.width(), self.height())
                if self.app:
                    self.app.save_layout(self.x(), self.y(), self.width(), self.height())
            self.volume_top_bar.hide()
            self.memory_bar.hide()
            for w in self._left_side:
                w.hide()
            for w in self._right_side:
                w.hide()
            self._chat_input.hide()
            self._chat_btn.hide()
            self.stacked.hide()
            self.setAttribute(Qt.WA_TranslucentBackground, True)
            self.setStyleSheet("")
            self._central.setStyleSheet("#_centralWidget { background-color: transparent; border: none; }")
            self._compact_dot.show()
            if sys.platform == "win32":
                try:
                    import ctypes
                    hwnd = int(self.winId())
                    dwm = ctypes.windll.dwmapi
                    dwm.DwmSetWindowAttribute(
                        hwnd, 2,
                        ctypes.byref(ctypes.c_int(2)), 4)
                    ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
                        0x0027)
                except Exception:
                    pass
            self.setFixedSize(36, 36)
        else:
            self._compact_dot.hide()
            self.setAttribute(Qt.WA_TranslucentBackground, True)
            self.setStyleSheet("QMainWindow { background-color: #101010; }")
            self._refresh_debug_border()
            if sys.platform == "win32":
                try:
                    import ctypes
                    hwnd = int(self.winId())
                    dwm = ctypes.windll.dwmapi
                    dwm.DwmSetWindowAttribute(
                        hwnd, 2,
                        ctypes.byref(ctypes.c_int(1)), 4)
                    try:
                        dwm.DwmSetWindowAttribute(
                            hwnd, 33,
                            ctypes.byref(ctypes.c_int(2)), 4)
                    except Exception:
                        pass
                    ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
                        0x0027)
                except Exception:
                    pass
            self.setMinimumSize(0, 0)
            self.setMaximumSize(16777215, 16777215)
            self.volume_top_bar.show()
            self.memory_bar.show()
            self.stacked.show()
            for w in self._left_side:
                w.show()
            for w in self._right_side:
                w.show()
            if self._normal_geometry:
                x, y, w, h = self._normal_geometry
                self.setGeometry(x, y, w, h)
                if self.app:
                    self.app.save_layout(self.x(), self.y(), self.width(), self.height())
            else:
                self.setGeometry(self.x(), self.y(), 220, 60)
            self._on_set_state(self._current_state, self._current_detail)

    def _build_loading_widget(self):
        self.loading_widget = QWidget()
        self.loading_widget.setStyleSheet("background: transparent;")
        lo = QVBoxLayout(self.loading_widget)
        lo.setContentsMargins(0, 0, 0, 0)
        self.loading_label = QLabel(self._t("gui.states.loading"))
        f = QFont(self._font_family, max(8, self._font_size - 2))
        f.setBold(True)
        self.loading_label.setFont(f)
        self.loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_label.setStyleSheet(f"color: {LABEL_FG}; background: transparent;")
        lo.addWidget(self.loading_label)

    def _build_main_button(self):
        self.btn = QPushButton(self._t("gui.states.listening"))
        self.btn.setToolTip(self._t("gui.button_tooltip"))
        font = QFont(self._font_family, max(6, self._font_size - 2))
        font.setBold(True)
        self.btn.setFont(font)
        self.btn.setStyleSheet(
            "QPushButton { background-color: transparent; color: #2ecc71; "
            "border: none; border-radius: 0; text-align: center; }"
            "QPushButton:hover { color: #27ae60; }"
        )
        self.btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

    def _btn_press(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self._exit_app()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.globalPosition().toPoint()
            self._drag_pos = self._drag_start
            self._drag_started = False

    def _ui_move(self,event):
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos:
            cur = event.globalPosition().toPoint()
            if not self._drag_started and self._drag_start:
                if (cur - self._drag_start).manhattanLength() > 5:
                    self._drag_started = True
            if self._drag_started:
                self.move(
                    self.x() + cur.x() - self._drag_pos.x(),
                    self.y() + cur.y() - self._drag_pos.y(),
                )
            self._drag_pos = cur
    
    def _btn_move(self, event):
        self._ui_move(event)

    def _ui_release(self,event):
        if event.button() == Qt.MouseButton.LeftButton and self._drag_pos is not None:
            if not self._drag_started:
                if self.app:
                    self.app.handle_button_press()
            else:
                self._clamp_to_screen()
                if self.app:
                    self._pending_pos = (self.x(), self.y(), self.width(), self.height())
                    self._pos_debounce.start()
        self._drag_pos = None
        self._drag_start = None

    def _save_position_debounced(self):
        if self._pending_pos and self.app:
            x, y, w, h = self._pending_pos
            self.app.save_layout(x, y, w, h)
        self._pending_pos = None

    def _btn_release(self, event):
        self._ui_release(event)

    def moveEvent(self, event):
        super().moveEvent(event)
        if self.app and not self._compact_mode:
            self._pending_pos = (self.x(), self.y(), self.width(), self.height())
            self._pos_debounce.start()

    # ---- Thread-safe public API called from VassApp ----

    def set_state(self, state, detail=""):
        self.set_state_signal.emit(state, detail)

    def _on_set_state(self, state, detail=""):
        self._current_state = state
        self._current_detail = detail
        self.setEnabled(state != "loading")
        if state == "loading":
            self.stacked.setCurrentWidget(self.loading_widget)
            self._compact_dot.set_state("#888888", state)
            return
        if hasattr(self, '_splash') and self._splash is not None:
            self._splash.finish()
            self._splash = None
        color = self.COLORS.get(state, "#1e1e1e")
        if state == "listening" and self._current_mode == "transcription":
            color = "#85c1e9"
        self._compact_dot.set_state(color, state)
        if not self._compact_mode:
            bg = QColor(color)
            bg.setHsv(bg.hue(), bg.saturation(), max(1, int(bg.value() * 0.25)))
            self._current_bg = bg.name()
            self.setStyleSheet(
                "QMainWindow { background-color: %s; }" % self._current_bg
            )
            border = "border: 2px solid #ffcc00;" if getattr(self, '_debug_border', False) else ""
            self._central.setStyleSheet(
                f"#_centralWidget {{ background-color: {self._current_bg}; {border} }}"
            )
        text_color = "#888888" if not self._health_ok else color
        text = self._t(f"gui.states.{state}")
        if detail:
            text = f"{text} {detail}"
        self._btn_full_text = text
        self._elide_button_text()
        self.btn.setStyleSheet(
            "QPushButton { background-color: transparent; color: %s; "
            "border: none; border-radius: 0; text-align: center; }"
            "QPushButton:hover { color: %s; }"
            % (text_color, QColor(text_color).lighter(130).name())
        )
        if state == "listening":
            self.hide_tool_indicator()
            self.hide_link_panel()
        if not self._compact_mode:
            self.stacked.setCurrentWidget(self.btn)
            if state == "listening":
                path = os.path.join(BASE, "Allowed_root", "last_response.txt")
                self.replay_btn.setVisible(os.path.exists(path) and os.path.getsize(path) > 0)
                self._chat_btn.setVisible(True)
            else:
                self.replay_btn.setVisible(False)
                self._chat_btn.setVisible(False)
                if self._chat_btn.isChecked():
                    self._collapse_chat()
            self._rebalance_spacers()
        self._activity_timer.start()
        if state == "recording":
            self._activity_timer.stop()
            self.memory_bar.set_color("#69DB7C")
            self.memory_bar.set_tooltip_context(self._t("gui.bar.volume"), "")
            self.memory_bar.set_value(0, 0, 1)
        elif state == "running_script":
            self._activity_timer.stop()
            self.memory_bar.set_color("#9b59b6")
            self.memory_bar.set_tooltip_context(self._t("gui.bar.script"), self._t("gui.bar.lines"))
        else:
            self.memory_bar.set_color("#1abc9c")
            self.memory_bar.set_tooltip_context(self._t("gui.bar.activity"), "")
            self.memory_bar.set_ratio(0.0)
            self._poll_activity()
        if state in ("waiting", "waiting_resources"):
            self._fade_anim.stop()
            self._pulse_anim.start()
        else:
            self._pulse_anim.stop()
            if state == "paused":
                target = self.app.settings.get("paused_opacity", 0.5) if self.app else 0.5
            else:
                target = 1.0
            try:
                if self._is_fullscreen() and self.app and self.app.idle_tracker.get_input_idle_seconds() > 15:
                    return
            except Exception:
                pass
            self._fade_opacity(target)

    def _elide_button_text(self):
        if not self._btn_full_text:
            return
        fm = QFontMetrics(self.btn.font())
        available = max(10, self.btn.width() - 6)
        self.btn.setText(fm.elidedText(self._btn_full_text, Qt.TextElideMode.ElideRight, available))

    def _fade_opacity(self, target):
        self._fade_anim.stop()
        self._fade_anim.setStartValue(self.windowOpacity())
        self._fade_anim.setEndValue(target)
        self._fade_anim.start()

    def _on_volume(self, rms):
        level = min(1.0, rms * 50)
        self.memory_bar._tip_val = round(level, 2)
        self.memory_bar._tip_max = 1
        self.memory_bar._update_tooltip()
        self.memory_bar.set_level(level)

    def _on_noise_floor(self, gain, raw):
        self.volume_top_bar._noise_floor_ratio = gain
        self.volume_top_bar.update()
        if self._compact_dot.isVisible():
            self._compact_dot.set_noise_floor(raw)

    def set_health_status(self, ok):
        if self._health_ok != ok:
            self._health_ok = ok
            self._on_set_state(self._current_state, self._current_detail)

    def set_mode_display(self, mode):
        self._mode_chat.setChecked(mode == "chat")
        self._mode_transcription.setChecked(mode == "transcription")
        if self._current_mode != mode:
            self._current_mode = mode
            self._on_set_state(self._current_state, self._current_detail)
        if mode == "transcription":
            self.tool_indicator_signal.emit("__transcription__", "")
        else:
            self.hide_tool_indicator()

    def update_button_tooltip(self):
        """Update the main button tooltip with currently used audio devices."""
        if not self.app or not hasattr(self, 'btn'):
            return
        parts = [self._t("gui.button_tooltip")]
        try:
            import sounddevice as sd
            devs = {d["index"]: d for d in sd.query_devices()}
            default_in, default_out = sd.default.device

            inp_id = -1 if self.app.audio_handler.input_device is None else self.app.audio_handler.input_device
            if inp_id < 0:
                inp_id = default_in
            inp_dev = devs.get(inp_id)
            if inp_dev:
                parts.append(f"\nInput: {inp_dev.get('name', '?')}")
            else:
                parts.append(f"\nInput: (unknown)")

            out_id = -1 if self.app.tts.output_device is None else self.app.tts.output_device
            if out_id < 0:
                out_id = default_out
            out_dev = devs.get(out_id)
            if out_dev:
                parts.append(f"\nOutput: {out_dev.get('name', '?')}")
            else:
                parts.append(f"\nOutput: (unknown)")
        except Exception:
            pass
        self.btn.setToolTip("".join(parts))

    def _update_bell(self):
        if not self.app:
            return
        count = self.app.notification_manager.unread_count()
        if count > 0:
            max_priority = 0
            for n in self.app.notification_manager.list_all():
                if not n.get("read", False):
                    p = n.get("priority", 0)
                    if p > max_priority:
                        max_priority = p
            color = self.app.notification_manager.color_for(max_priority)
            self._bell_btn.setText(str(count))
            self._bell_btn.setStyleSheet(
                f"QPushButton {{ background-color: transparent; color: {color}; "
                "border: none; font-size: 10px; padding: 2px 4px; font-weight: bold; }"
                "QPushButton:hover { background-color: #3d3d3d; color: #dddddd; }"
            )
        else:
            self._bell_btn.setText("0")
            self._bell_btn.setStyleSheet(
                "QPushButton { background-color: transparent; color: #3f3f3f; "
                "border: none; font-size: 10px; padding: 2px 4px; }"
                "QPushButton:hover { background-color: #3d3d3d; color: #dddddd; }"
            )

    def _replay_btn_press(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self.open_history()
        else:
            QPushButton.mousePressEvent(self.replay_btn, event)

    def _on_replay(self):
        import threading
        path = os.path.join(BASE, "Allowed_root", "last_response.txt")
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    text = f.read()
                if text.strip() and self.app:
                    self.app.tts.enqueue(text)
            except Exception:
                pass

    def _collapse_chat(self):
        should_restore = self._chat_original_width is not None
        self._chat_btn.setChecked(False)
        self._chat_input.setVisible(False)
        self._chat_input.clear()
        self.stacked.setVisible(True)
        vis = getattr(self, '_left_side_visibility', {})
        for w in self._left_side:
            w.setVisible(vis.get(w, True))
        self._left_side_visibility = {}
        if should_restore:
            self.resize(self._chat_original_width, self.height())
            if self._chat_original_x is not None:
                self.move(self._chat_original_x, self.y())
            self._chat_original_width = None
            self._chat_original_x = None
        self._rebalance_spacers()

    def _rebalance_spacers(self):
        """Keep the stacked widget (button / waveform) horizontally centred.

        Calculates the total visible width of widgets placed to the left
        and right of the centred area, then pads the shorter side with a
        spacer so the centre widget stays balanced.

        To make a new widget participate in balancing, append it to
        self._left_side or self._right_side.  No other changes needed.
        """
        # ── measure visible widths ─────────────────────────────────────
        left_w = sum(w.width() for w in self._left_side if w.isVisible())
        right_w = sum(w.width() for w in self._right_side if w.isVisible())

        # _chat_input has dynamic width (not fixed), handle separately
        if self._chat_input.isVisible():
            right_w += max(self._chat_input.width(),
                           self._chat_input.sizeHint().width())

        # ── apply the difference to the shorter side ───────────────────
        diff = abs(left_w - right_w)
        if left_w > right_w:
            self._right_spacer.changeSize(diff, 0,
                QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
            self._left_spacer.changeSize(0, 0,
                QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
        else:
            self._left_spacer.changeSize(diff, 0,
                QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
            self._right_spacer.changeSize(0, 0,
                QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)

        self.centralWidget().layout().invalidate()

    def _toggle_chat_input(self):
        if self._chat_btn.isChecked():
            self._chat_original_width = self.width()
            self._chat_original_x = self.x()
            self._left_side_visibility = {w: w.isVisible() for w in self._left_side}
            for w in self._left_side:
                w.setVisible(False)
            self.stacked.setVisible(False)
            self.resize(self._chat_original_width * 2, self.height())
            self._clamp_to_screen()
            self._rebalance_spacers()
            self._chat_input.setVisible(True)
            self._chat_input.setFocus()
        else:
            self._collapse_chat()

    def _send_chat_text(self):
        text = self._chat_input.text().strip()
        if text:
            self._chat_input.add_to_history(text)
            self.chat_text_signal.emit(text)
        self._collapse_chat()

    def _refresh_debug_border(self):
        debug = getattr(self.app, 'debug_enabled', False)
        self._debug_border = debug
        bg = getattr(self, '_current_bg', '#101010')
        if hasattr(self, 'volume_top_bar'):
            self.volume_top_bar._debug_enabled = debug
            self.volume_top_bar.update()
        if self._compact_mode:
            self._central.setStyleSheet("#_centralWidget { background-color: transparent; border: none; }")
        elif debug:
            self._central.setStyleSheet(f"#_centralWidget {{ background-color: {bg}; border: 2px solid #ffcc00; }}")
        else:
            self._central.setStyleSheet(f"#_centralWidget {{ background-color: {bg}; }}")

    def _poll_activity(self):
        try:
            tracker = get_tracker()
            active = tracker.get_active()
            if not active:
                self.memory_bar.set_ratio(0.0)
                self.memory_bar.setToolTip(self._t("gui.bar.activity"))
                return
            count = len(active)
            ratio = min(0.15 + 0.17 * count, 1.0)
            self.memory_bar.set_ratio(ratio)
            names = []
            for name, info in active.items():
                cat = info.get("category", "default")
                cat_label = self._t(f"activity_categories.{cat}")
                names.append(f"{cat_label}: {name}")
            duration = int(time.time() - min(i["start"] for i in active.values()))
            tip = f"{self._t('gui.bar.activity')} ({duration}s)\n" + "\n".join(names)
            self.memory_bar.setToolTip(tip)
        except Exception:
            pass

    def set_loading_progress(self, value, maximum=100, detail=""):
        if hasattr(self, '_splash') and self._splash is not None:
            self._splash.set_progress(value, maximum, detail)

    def update_memory_bar(self):
        self.update_memory_signal.emit()

    def _on_update_memory(self):
        try:
            if self.app and hasattr(self.app, "memory_tokens"):
                path = os.path.join(BASE, "Allowed_root", "memory.json")
                mem_dir = os.path.join(BASE, "Allowed_root", "memory")
                tags_path = os.path.join(BASE, "Allowed_root", "memory_tags.json")
                total = 0
                if os.path.exists(path):
                    total += os.path.getsize(path)
                if os.path.exists(tags_path):
                    total += os.path.getsize(tags_path)
                referenced = set()
                try:
                    with open(path, encoding="utf-8") as f:
                        mem_data = json.load(f)
                    for vid in mem_data.get("history", []):
                        referenced.add(vid)
                    sid = mem_data.get("summary_id", "")
                    if sid:
                        referenced.add(sid)
                except Exception:
                    pass
                if os.path.isdir(mem_dir):
                    for fname in os.listdir(mem_dir):
                        if fname.endswith(".json"):
                            fid = fname[:-5]
                            if fid not in referenced:
                                continue
                            try:
                                total += os.path.getsize(os.path.join(mem_dir, fname))
                            except OSError:
                                pass
                max_bytes = self.app.memory_tokens * 4
                ratio = min(total / max_bytes, 1.0) if max_bytes > 0 else 0
                self.memory_bar.set_value(total, 0, max_bytes)
                self.memory_bar.set_ratio(ratio)
        except Exception:
            pass

    def schedule(self, ms, callback):
        if ms <= 0:
            self.schedule_signal.emit(callback)
        else:
            QTimer.singleShot(ms, lambda: self.schedule_signal.emit(callback))

    def start_tts_playback(self, data, samplerate, total_samples, on_complete):
        self.start_tts_signal.emit(data, samplerate, total_samples, on_complete)

    def _on_start_tts(self, data, samplerate, total_samples, on_complete):
        if getattr(self.app, 'waveform_enabled', True):
            self.player.load_data(data, samplerate)
            self.stacked.setCurrentWidget(self.player)
        self._tts_polling = True
        self._tts_total_samples = total_samples
        self._tts_on_complete = on_complete
        self._tts_last_pos = -1
        self._tts_stall_count = 0
        self._poll_tts()

    def _poll_tts(self):
        if not self._tts_polling:
            return
        pos = 0
        try:
            pos = self.app.get_tts_position() if self.app else 0
            self.player.set_pos(pos)
        except Exception:
            pass
        done = False
        if pos >= getattr(self, '_tts_total_samples', 0) and pos > 0:
            done = True
        elif pos == self._tts_last_pos and pos > 0:
            paused = False
            try:
                paused = self.app.tts._tts_paused if self.app and self.app.tts else False
            except Exception:
                pass
            if not paused:
                self._tts_stall_count += 1
                if self._tts_stall_count > 40:
                    done = True
            else:
                self._tts_stall_count = 0
        else:
            self._tts_stall_count = 0
        self._tts_last_pos = pos
        if done:
            self._tts_polling = False
            try:
                if self.app and self.app.tts:
                    self.app.tts._sd_abort.set()
            except Exception:
                pass
            cb = getattr(self, '_tts_on_complete', None)
            self._tts_on_complete = None
            if cb:
                cb()
            return
        QTimer.singleShot(80, self._poll_tts)

    def stop_tts_playback(self):
        self.stop_tts_signal.emit()

    def _on_stop_tts(self):
        self._tts_polling = False
        self.stacked.setCurrentWidget(self.btn)
        if getattr(self.app, 'waveform_enabled', True):
            self.player.data = None
            self.player.peaks = []

    def request_auth(self, script_name, func_name):
        import threading
        self._auth_result = None
        self._auth_event = threading.Event()
        self.auth_requested_signal.emit(script_name, func_name)
        self._auth_event.wait()
        return self._auth_result if self._auth_result else "deny"

    def request_form(self, title, fields):
        import threading
        self._form_result = None
        self._form_event = threading.Event()
        self.form_signal.emit(title, fields)
        self._form_event.wait()
        import json
        return json.dumps(self._form_result) if self._form_result else "{}"

    def _on_auth_requested(self, script_name, func_name):
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout
        dlg = QDialog(self)
        dlg.setWindowTitle(self._t("gui.auth.title"))
        dlg.setFixedSize(525, 300)
        dlg.setStyleSheet(
            "QDialog { background-color: #2d2d2d; color: #e0e0e0; }"
            "QLabel { color: #e0e0e0; font-size: 13px; }"
            "QPushButton { background-color: #0d7377; color: white; "
            "border: none; padding: 8px 16px; font-size: 12px; }"
            "QPushButton:hover { background-color: #0a5c5f; }"
        )
        lo = QVBoxLayout(dlg)
        msg = QLabel(
            f"<b>{script_name}</b> richiede autorizzazione per:<br>"
            f"<code>{func_name}()</code>"
        )
        msg.setWordWrap(True)
        lo.addWidget(msg)
        desc = self._t(f"gui.auth.func_descriptions.{func_name}")
        if desc and desc != func_name:
            desc_lbl = QLabel(desc)
            desc_lbl.setWordWrap(True)
            desc_lbl.setStyleSheet("color: #aaaaaa; font-size: 11px; font-style: italic; margin-top: 2px;")
            lo.addWidget(desc_lbl)
        lo.addSpacing(12)
        btn_lo = QHBoxLayout()
        btn_once = QPushButton(self._t("gui.auth.allow_once"))
        btn_once.clicked.connect(lambda: self._finish_auth("once", dlg))
        btn_func = QPushButton(self._t("gui.auth.allow_func"))
        btn_func.clicked.connect(lambda: self._finish_auth("function", dlg))
        btn_all = QPushButton(self._t("gui.auth.allow_all"))
        btn_all.clicked.connect(lambda: self._finish_auth("all", dlg))
        btn_cancel = QPushButton(self._t("gui.auth.cancel"))
        btn_cancel.setStyleSheet("QPushButton { background-color: #555555; } QPushButton:hover { background-color: #777777; }")
        btn_cancel.clicked.connect(lambda: self._finish_auth("deny", dlg))
        btn_lo.addWidget(btn_once)
        btn_lo.addWidget(btn_func)
        btn_lo.addWidget(btn_all)
        btn_lo.addWidget(btn_cancel)
        lo.addLayout(btn_lo)
        dlg.exec()
        if self._auth_result is None:
            self._finish_auth("deny", dlg)

    def _on_form_requested(self, title, fields):
        from PySide6.QtWidgets import (
            QDialog, QVBoxLayout, QFormLayout, QHBoxLayout,
            QPushButton, QLineEdit, QCheckBox, QComboBox, QSpinBox, QTextEdit,
        )
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setStyleSheet(
            "QDialog { background-color: #2d2d2d; color: #e0e0e0; }"
            "QLabel { color: #e0e0e0; font-size: 13px; }"
            "QLineEdit, QSpinBox, QComboBox, QTextEdit {"
            " background-color: #3d3d3d; color: #e0e0e0; border: 1px solid #555;"
            " padding: 4px; font-size: 13px; }"
            "QPushButton { background-color: #0d7377; color: white;"
            " border: none; padding: 8px 16px; font-size: 12px; }"
            "QPushButton:hover { background-color: #0a5c5f; }"
            "QCheckBox { color: #e0e0e0; }"
        )

        lo = QVBoxLayout(dlg)
        form = QFormLayout()
        form.setSpacing(8)
        widgets = {}

        for field_def in fields:
            parts = [p.strip() for p in field_def.split(":", 2)]
            name = parts[0]
            ftype = parts[1] if len(parts) > 1 else "text"
            default = parts[2] if len(parts) > 2 else ""

            if ftype == "text":
                w = QLineEdit(default)
            elif ftype == "number":
                w = QSpinBox()
                w.setRange(-999999, 999999)
                if default:
                    try:
                        w.setValue(int(default))
                    except ValueError:
                        pass
            elif ftype == "checkbox":
                w = QCheckBox()
                w.setChecked(default.lower() in ("si", "sì", "true", "yes", "1"))
            elif ftype == "select":
                w = QComboBox()
                for opt in default.split(","):
                    w.addItem(opt.strip())
            elif ftype == "textarea":
                w = QTextEdit(default)
                w.setFixedHeight(100)
            else:
                w = QLineEdit(default)

            form.addRow(name + ":", w)
            widgets[name] = w

        lo.addLayout(form)
        lo.addSpacing(12)

        btn_lo = QHBoxLayout()
        btn_lo.addStretch()
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(lambda: self._finish_form(
            {n: (
                w.text() if isinstance(w, QLineEdit) else
                str(w.value()) if isinstance(w, QSpinBox) else
                "true" if (isinstance(w, QCheckBox) and w.isChecked()) else
                "false" if isinstance(w, QCheckBox) else
                w.currentText() if isinstance(w, QComboBox) else
                w.toPlainText() if isinstance(w, QTextEdit) else
                ""
            ) for n, w in widgets.items()}, dlg))
        cancel_btn = QPushButton(self._t("gui.auth.cancel"))
        cancel_btn.setStyleSheet(
            "QPushButton { background-color: #555555; }"
            "QPushButton:hover { background-color: #777777; }")
        cancel_btn.clicked.connect(lambda: dlg.reject())
        btn_lo.addWidget(ok_btn)
        btn_lo.addWidget(cancel_btn)
        lo.addLayout(btn_lo)

        dlg.exec()
        if self._form_result is None:
            self._form_result = {}
        if self._form_event:
            self._form_event.set()

    def _finish_form(self, result, dlg):
        self._form_result = result
        dlg.accept()
        if self._form_event:
            self._form_event.set()

    def _finish_auth(self, result, dlg):
        self._auth_result = result
        dlg.accept()
        if self._auth_event:
            self._auth_event.set()

    def show_highlight(self, x, y, w, h, duration=1.0):
        import sys
        if sys.platform == "win32":
            import subprocess, os, ctypes
            dc = ctypes.windll.user32.GetDC(0)
            dpi = ctypes.windll.gdi32.GetDeviceCaps(dc, 88)
            ctypes.windll.user32.ReleaseDC(0, dc)
            scale = dpi / 96.0
            x = int(x / scale)
            y = int(y / scale)
            w = int(w / scale)
            h = int(h / scale)
            script = os.path.join(get_project_root(), "highlight_toast.ps1")
            subprocess.Popen(
                ["powershell", "-NoProfile", "-File", script,
                 "-x", str(x), "-y", str(y), "-w", str(w), "-h", str(h), "-dur", str(duration)],
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        else:
            def _show():
                from PySide6.QtWidgets import QWidget
                from PySide6.QtCore import Qt, QTimer
                from PySide6.QtGui import QPainter, QColor, QPen

                class _Overlay(QWidget):
                    def paintEvent(self, ev):
                        p = QPainter(self)
                        p.fillRect(self.rect(), QColor(0, 180, 255, 60))
                        p.setPen(QPen(QColor(0, 180, 255), 3))
                        p.drawRect(self.rect().adjusted(2, 2, -2, -2))

                overlay = _Overlay(None)
                overlay.setWindowFlags(
                    Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                    | Qt.WindowTransparentForInput
                )
                overlay.setAttribute(Qt.WA_TranslucentBackground)
                overlay.setAttribute(Qt.WA_ShowWithoutActivating)
                overlay.setGeometry(x, y, w, h)
                overlay.show()
                overlay.raise_()
                QTimer.singleShot(int(duration * 1000), overlay.close)

            self.schedule(0, _show)

    def _open_unique_window(self, key, script, *extra_args):
        if sys.platform == "win32":
            try:
                import ctypes
                from ctypes import wintypes
                user32 = ctypes.windll.user32
                titles = {
                    "settings": "impostazioni vass",
                    "commands": "editor comandi vass",
                    "scripts": "vasscript editor",
                    "history": "cronologia conversazioni",
                    "memory_editor": "memoria permanente",
                    "sources": "vass - fonti online",
                    "events": "vass - eventi e operazioni",
                }
                search = titles.get(key, "")
                found = []
                WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
                def _enum(hwnd, lparam):
                    buf = ctypes.create_unicode_buffer(256)
                    user32.GetWindowTextW(hwnd, buf, 256)
                    if buf.value and search in buf.value.lower():
                        found.append(hwnd)
                    return True
                user32.EnumWindows(WNDENUMPROC(_enum), 0)
                if found:
                    hwnd = found[0]
                    if user32.IsIconic(hwnd):
                        user32.ShowWindow(hwnd, 9)
                    user32.SetForegroundWindow(hwnd)
                    return
            except Exception:
                pass
        import subprocess as _sp
        cmd = [sys.executable, script] + list(extra_args)
        kwargs = {
            "stdin": _sp.DEVNULL,
            "stdout": _sp.DEVNULL,
            "stderr": _sp.DEVNULL,
        }
        if sys.platform == "win32":
            kwargs["creationflags"] = _sp.CREATE_NO_WINDOW
        _sp.Popen(cmd, **kwargs)

    def open_settings(self):
        self._open_unique_window("settings", os.path.join(SRC, "settings_editor.py"), "--lang", self.language)

    def open_commands(self):
        self._open_unique_window("commands", os.path.join(SRC, "commands_editor.py"), "--lang", self.language)

    def open_scripts(self):
        self._open_unique_window("scripts", os.path.join(SRC, "scripts_editor.py"), "--lang", self.language)

    def open_history(self):
        import json, time
        from datetime import datetime as _dt
        data_path = os.path.join(BASE, "Allowed_root", ".history_view.json")
        mem_path = os.path.join(BASE, "Allowed_root", "memory.json")
        mem_dir = os.path.join(BASE, "Allowed_root", "memory")
        entries = []
        all_ids = []
        summary_id = ""
        min_history_id = 0
        try:
            if os.path.exists(mem_path):
                with open(mem_path, encoding="utf-8") as f:
                    meta = json.load(f)
                summary_id = meta.get("summary_id", "")
                hid = meta.get("history", [])
                for vid in hid:
                    if vid not in all_ids:
                        all_ids.append(vid)
                if hid:
                    min_history_id = int(min(int(v) for v in hid if v.isdigit()))
        except Exception:
            pass

        try:
            if os.path.isdir(mem_dir):
                for fname in os.listdir(mem_dir):
                    if fname.endswith(".json"):
                        fid = fname[:-5]
                        if fid.isdigit() and fid not in all_ids:
                            all_ids.append(fid)
        except Exception:
            pass

        if summary_id and summary_id in all_ids:
            all_ids.remove(summary_id)

        all_ids.sort(reverse=True)
        capped = all_ids[:100]
        separator_inserted = False

        for vid in capped:
            if min_history_id and not separator_inserted and int(vid) < min_history_id:
                entries.append({"role": "separator", "content": "Archivio", "ts": ""})
                separator_inserted = True
            hf = os.path.join(mem_dir, f"{vid}.json")
            if os.path.exists(hf):
                try:
                    with open(hf, encoding="utf-8") as hfp:
                        info = json.load(hfp).get("info", "")
                    entry = json.loads(info)
                    try:
                        ts = _dt.fromtimestamp(int(vid) / 1000).strftime("%d/%m %H:%M")
                    except Exception:
                        ts = ""
                    entries.append({
                        "role": entry.get("role", ""),
                        "content": entry.get("content", ""),
                        "ts": ts,
                    })
                except Exception:
                    pass

        with open(data_path, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False)
        self._open_unique_window("history", os.path.join(SRC, "history_viewer.py"), "--lang", self.language)

    def open_memory_editor(self):
        self._open_unique_window("memory_editor", os.path.join(SRC, "memory_editor.py"), "--lang", self.language)

    def open_sources(self):
        self._open_unique_window("sources", os.path.join(SRC, "sources_editor.py"), "--lang", self.language)

    def open_events(self):
        self._open_unique_window("events", os.path.join(SRC, "events_editor.py"), "--lang", self.language)

    def open_plugins(self):
        if not self.app or not hasattr(self.app, '_plugin_server'):
            return
        dlg = PluginManagerDialog(self.app._plugin_server, self._t, self.language, self)
        dlg.exec()

    def _open_help_usage(self):
        import os
        readme = os.path.join(BASE, "docs", f"README_{self.language}.md")
        if not os.path.exists(readme):
            readme = os.path.join(BASE, "README.md")
        from markdown_viewer import MarkdownViewer
        v = MarkdownViewer(title=self._t("gui.menu.help_usage"), file_path=readme)
        v.destroyed.connect(lambda obj=v: self._open_windows.remove(obj) if obj in self._open_windows else None)
        v.show()
        self._open_windows.append(v)

    def _open_help_commands(self):
        import configparser, os
        content = "# Comandi disponibili\n\n"
        sections = []
        lang_path = os.path.join(BASE, "config", f"commands_{self.language}.ini")
        if os.path.exists(lang_path):
            cfg = configparser.ConfigParser()
            cfg.read(lang_path, encoding="utf-8")
            for s in cfg.sections():
                items = []
                for k, v in cfg.items(s):
                    items.append(f"- **{k}** → `{v}`")
                if items:
                    sections.append(f"## Comandi interni — {s}\n\n" + "\n".join(sorted(items)))
        user_path = os.path.join(BASE, "config", "commands.ini")
        if os.path.exists(user_path):
            cfg = configparser.ConfigParser()
            cfg.read(user_path, encoding="utf-8")
            for s in cfg.sections():
                items = []
                for k, v in cfg.items(s):
                    items.append(f"- **{k}** → `{v}`")
                if items:
                    sections.append(f"## Comandi utente — {s}\n\n" + "\n".join(sorted(items)))
        content += "\n\n".join(sections) if sections else "*Nessun comando disponibile*"
        from markdown_viewer import MarkdownViewer
        v = MarkdownViewer(title=self._t("gui.menu.help_commands"), content=content)
        v.destroyed.connect(lambda obj=v: self._open_windows.remove(obj) if obj in self._open_windows else None)
        v.show()
        self._open_windows.append(v)

    def _open_help_vasscript(self):
        import os
        path = os.path.join(BASE, "Allowed_root", "VASCRIPT_REFERENCE.md")
        from markdown_viewer import MarkdownViewer
        v = MarkdownViewer(title=self._t("gui.menu.help_vasscript"), file_path=path)
        v.destroyed.connect(lambda obj=v: self._open_windows.remove(obj) if obj in self._open_windows else None)
        v.show()
        self._open_windows.append(v)

    def _is_fullscreen(self):
        if sys.platform == "win32":
            return self._is_fullscreen_win32()
        elif sys.platform == "darwin":
            return self._is_fullscreen_darwin()
        else:
            return self._is_fullscreen_linux()

    def _is_fullscreen_win32(self):
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            dwmapi = ctypes.windll.dwmapi
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return False
            GWL_STYLE = -16
            style = user32.GetWindowLongW(hwnd, GWL_STYLE)
            no_titlebar = not (style & 0x00C00000)
            if not no_titlebar:
                return False
            r = wintypes.RECT()
            dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(r), ctypes.sizeof(r))
            w = r.right - r.left
            h = r.bottom - r.top
            mon = user32.MonitorFromWindow(hwnd, 2)
            if not mon:
                return False
            class MONITORINFO(ctypes.Structure):
                _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                            ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]
            mi = MONITORINFO()
            mi.cbSize = ctypes.sizeof(mi)
            ctypes.windll.user32.GetMonitorInfoW(mon, ctypes.byref(mi))
            work_w = mi.rcWork.right - mi.rcWork.left
            work_h = mi.rcWork.bottom - mi.rcWork.top
            return w >= work_w and h >= work_h
        except Exception:
            return False

    def _is_fullscreen_darwin(self):
        try:
            import subprocess
            script = 'tell application "System Events" to get value of attribute "AXFullScreen" of window 1 of (first process whose frontmost is true)'
            r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=5)
            return "true" in r.stdout.lower()
        except Exception:
            return False

    def _is_fullscreen_linux(self):
        try:
            import subprocess
            r = subprocess.run(["xdotool", "getactivewindow"], capture_output=True, text=True, timeout=5)
            wid = r.stdout.strip()
            if not wid:
                return False
            r2 = subprocess.run(["xprop", "-id", wid, "_NET_WM_STATE"], capture_output=True, text=True, timeout=5)
            return "FULLSCREEN" in r2.stdout
        except Exception:
            return False

    def _auto_fade_loop(self):
        import time as _time
        prev_opacity = 1.0
        fading = False
        was_compact = False
        while self._auto_fade_enabled:
            try:
                fullscreen = self._is_fullscreen()
                idle = 0
                try:
                    if self.app and hasattr(self.app, 'idle_tracker'):
                        idle = self.app.idle_tracker.get_input_idle_seconds()
                except Exception:
                    pass

                if fullscreen and idle > 15:
                    if not fading:
                        fading = True
                        prev_opacity = self.windowOpacity()
                        was_compact = self._compact_mode
                        if not was_compact:
                            self.compact_mode_signal.emit(True)
                            while not self._compact_mode:
                                _time.sleep(0.01)
                    current = self.windowOpacity()
                    target = max(0.10, current - 0.02)
                    self.setWindowOpacity(target)
                else:
                    if fading:
                        fading = False
                        self.setWindowOpacity(prev_opacity)
                        if not was_compact:
                            self.compact_mode_signal.emit(False)
                            while self._compact_mode:
                                _time.sleep(0.01)
            except Exception:
                pass
            _time.sleep(1)

    def wheelEvent(self, event):
        if self.app and self.app.tts:
            delta = event.angleDelta().y() / 120.0
            new_vol = max(0.0, min(1.0, self.app.app_volume + delta * 0.05))
            self.app.app_volume = new_vol
            self.app.tts.update_settings(new_vol)
            self.volume_top_bar.set_volume(new_vol)
            try:
                import configparser
                cfg = configparser.ConfigParser()
                settings_path = os.path.join(BASE, "config", "settings.ini")
                if os.path.exists(settings_path):
                    cfg.read(settings_path)
                cfg.set("audio", "app_volume", f"{new_vol:.2f}")
                with open(settings_path, "w") as f:
                    cfg.write(f)
            except Exception:
                pass
        super().wheelEvent(event)

    _TOOL_COLORS = {
        "browse": "#3498db", "webfetch": "#2980b9", "websearch": "#9b59b6",
        "read_file": "#f1c40f", "write_file": "#e67e22",
        "interact": "#e74c3c", "script": "#c0392b",
        "calendar_add": "#27ae60", "calendar_list": "#27ae60", "calendar_search": "#27ae60",
        "addevent": "#e67e22", "add_event": "#e67e22", "delevent": "#e67e22", "delete_event": "#e67e22", "listevents": "#e67e22", "list_events": "#e67e22", "nextevent": "#e67e22",
        "clipboardget": "#1abc9c", "clipboard_get": "#1abc9c", "clipboardset": "#1abc9c", "clipboard_set": "#1abc9c",
        "current_time": "#2ecc71", "to_timestamp": "#2ecc71",
        "calculate": "#e91e63", "langcheck": "#673ab7",
        "readinfo": "#f1c40f", "read_info": "#f1c40f", "writeinfo": "#f1c40f", "write_info": "#f1c40f", "savetags": "#ff5722", "save_tags": "#ff5722",
        "getidle": "#95a5a6", "get_idle": "#95a5a6",
    }

    def show_tool_indicator(self, tool_name):
        color = self._TOOL_COLORS.get(tool_name, "#95a5a6")
        from tool_groups import load_tool_name
        name, desc = load_tool_name(tool_name, self.language)
        tip = f'<font color="{color}"><b>{name}</b></font><br><font color="#aaaaaa">{desc}</font>'
        self.tool_indicator_signal.emit(color, tip)

    def hide_tool_indicator(self):
        self.tool_indicator_signal.emit("", "")

    def show_links(self, text):
        import re
        urls = re.findall(r'https?://[^\s<>"]+', text or "")
        clean = []
        for u in urls:
            # Remove trailing markdown/formatting artifacts only
            # Preserve URL-safe chars like ) that may be legit (Wikipedia, etc.)
            u = re.sub(r'[.,;:!?\]}>*_~`\']+$', '', u)
            # Remove one closing paren only if URL has no opening paren
            if u.endswith(')') and '(' not in u:
                u = u[:-1]
            if u not in clean:
                clean.append(u)
        if clean:
            self._link_panel._t = self._t
            self.schedule_signal.emit(lambda urls=clean: self._link_panel.set_links(urls, self))

    def hide_link_panel(self):
        self.schedule_signal.emit(lambda: self._link_panel.hide())

    def show_ai_responses(self):
        if not self.app:
            return
        history = self.app.conversation_history
        self._link_panel._t = self._t
        self._link_panel.set_ai_responses(list(history), self)

    def _show_info_panel(self, tab="all"):
        if not self.app:
            return
        if self._link_panel.isVisible() and self._link_panel._tab == tab:
            self._link_panel.hide()
            return
        nm = self.app.notification_manager
        self.schedule_signal.emit(lambda: (
            setattr(self._link_panel, '_t', self._t),
            setattr(self._link_panel, '_nm', nm),
            setattr(self._link_panel, '_update_bell_cb', self._update_bell),
            self._link_panel.show_panel(tab, self, user_opened=True)
        ))

    def set_mcp_status(self, ok):
        if ok:
            self.hide_tool_indicator()
        else:
            self.tool_indicator_signal.emit("__mcp_down__", "")

    def _on_tool_indicator(self, color, tooltip):
        if color == "__mcp_down__":
            self._compact_dot.set_tool("#e74c3c")
            if not self._compact_mode:
                self._tool_indicator.setStyleSheet(
                    "QLabel { background-color: #e74c3c; border-radius: 0px; border: none; }")
                self._tool_indicator.setToolTip(self._t("gui.mcp_down_tooltip"))
                self._tool_indicator.setVisible(True)
            return
        if color == "__transcription__":
            self._compact_dot.set_tool("#95a5a6")
            if not self._compact_mode:
                self._tool_indicator.setStyleSheet(
                    "QLabel { background-color: #95a5a6; border-radius: 0px; border: none; }")
                self._tool_indicator.setToolTip(self._t("gui.transcription_mode"))
                self._tool_indicator.setVisible(True)
            return
        if not color:
            self._tool_indicator.setVisible(False)
            self._compact_dot.set_tool()
            return
        self._compact_dot.set_tool(color)
        if not self._compact_mode:
            self._tool_indicator.setStyleSheet(
                f"QLabel {{ background-color: {color}; border-radius: 5px; }}")
            self._tool_indicator.setToolTip(tooltip)
            self._tool_indicator.setVisible(True)

    def eventFilter(self, obj, event):
        if hasattr(self, 'stacked') and obj is self.stacked and event.type() == QEvent.Type.Resize:
            self._elide_button_text()
        if (obj is self._central
                and event.type() == QEvent.Type.MouseButtonDblClick
                and event.button() == Qt.MouseButton.LeftButton
                and not self._compact_mode):
            self._toggle_compact_mode(True)
            return True
        return super().eventFilter(obj, event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self._exit_app()
        super().mousePressEvent(event)


class PluginManagerDialog(QDialog):
    STATUS_COLORS = {
        "running": "#2ecc71",
        "starting": "#f1c40f",
        "stopped": "#e67e22",
        "disabled": "#888888",
        "blocked": "#e74c3c",
        "unsupported": "#888888",
        "error": "#e74c3c",
    }

    def __init__(self, plugin_server, t_func, lang, parent=None):
        super().__init__(parent)
        self._server = plugin_server
        self._t = t_func
        self._lang = lang
        self.setWindowTitle(self._t("plugins.title"))
        self.setMinimumSize(456, 160)
        self.setStyleSheet("QDialog { background-color: #1e1e1e; color: #e0e0e0; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)

        self._list = QWidget()
        self._list_layout = QVBoxLayout(self._list)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(2)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._list)
        scroll.setStyleSheet("QScrollArea { border: 1px solid #333; border-radius: 4px; }")
        layout.addWidget(scroll, 1)

        btn_row = QHBoxLayout()
        refresh_btn = QPushButton(self._t("plugins.refresh"))
        refresh_btn.clicked.connect(self._refresh)
        close_btn = QPushButton("Chiudi")
        close_btn.clicked.connect(self.close)
        btn_row.addWidget(refresh_btn)
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self._btn_width = max(
            self._t("plugins.enable"), self._t("plugins.disable"), key=len)
        self._btn_width = max(90, QFontMetrics(self.font()).horizontalAdvance(self._btn_width) + 20)

        self._refresh()

    def _refresh(self):
        for i in reversed(range(self._list_layout.count())):
            w = self._list_layout.itemAt(i).widget()
            if w:
                w.setParent(None)

        try:
            statuses = self._server.get_plugins_status(self._lang)
        except Exception:
            return

        for p in statuses:
            row = self._build_row(p)
            self._list_layout.addWidget(row)

        self._list_layout.addStretch()

    def _build_row(self, p):
        row = QFrame()
        row.setStyleSheet("QFrame { background-color: #2a2a2a; border-radius: 4px; padding: 4px; }")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(8, 3, 8, 3)
        row_layout.setSpacing(8)

        color = self.STATUS_COLORS.get(p["status"], "#888")

        dot = QLabel()
        dot.setFixedSize(8, 8)
        dot.setStyleSheet(f"QLabel {{ background-color: {color}; border-radius: 4px; }}")
        row_layout.addWidget(dot)

        tooltip = f"{p['name']} v{p['version']}"
        desc = p.get("description", "")
        if desc:
            tooltip += f"\n{desc}"
        missing = p.get("missing_deps", [])
        if missing:
            dep_names = ", ".join(missing)
            tooltip += f"\nRequires: {dep_names}"
        name_lbl = QLabel(p["name"])
        name_lbl.setStyleSheet("font-weight: bold; font-size: 12px;")
        name_lbl.setToolTip(tooltip)
        row_layout.addWidget(name_lbl, 1)

        if p["status"] == "blocked" and missing:
            dep_names = ", ".join(missing)
            status_text = f"Dipende da: {dep_names}" if self._lang == "it" else f"Requires: {dep_names}"
        elif p["status"] == "error":
            detail = p.get("tooltip_detail", "")
            if detail == "socket_missing":
                status_text = "Senza handshake" if self._lang == "it" else "No handshake"
            elif detail == "process_missing":
                status_text = "Socket zombie" if self._lang == "it" else "Zombie socket"
            else:
                status_text = self._t("plugins.error")
            name_lbl.setToolTip(tooltip + "\n" + status_text)
        else:
            status_text = self._t(f"plugins.{p['status']}")
        status_lbl = QLabel(status_text)
        status_lbl.setStyleSheet(f"color: {color}; font-size: 11px;")
        status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row_layout.addWidget(status_lbl)

        has_cfg = self._plugin_has_config(p["name"])

        cfg_btn = QPushButton("\u2699")
        cfg_btn.setFixedSize(28, 28)
        cfg_btn.setToolTip(f"{p['name']} settings" if has_cfg else "No settings available")
        if has_cfg:
            cfg_btn.setStyleSheet(
                "QPushButton { color: #ccc; background: transparent; border: none; font-size: 16px; }"
                "QPushButton:hover { color: #fff; }")
            cfg_btn.clicked.connect(lambda checked, n=p["name"]: self._open_settings(n))
        else:
            cfg_btn.setStyleSheet(
                "QPushButton { color: #444; background: transparent; border: none; font-size: 16px; }")
        cfg_btn.setEnabled(has_cfg)
        row_layout.addWidget(cfg_btn)

        if p["status"] in ("disabled", "blocked", "unsupported"):
            btn = QPushButton(self._t("plugins.enable"))
            btn.setFixedWidth(self._btn_width)
            btn.setStyleSheet(
                "QPushButton { background-color: #2ecc71; color: #fff; border-radius: 3px; "
                "padding: 3px 10px; font-size: 11px; }"
                "QPushButton:hover { background-color: #27ae60; }")
            if p["status"] == "blocked":
                btn.setEnabled(False)
                dep_names = ", ".join(p.get("missing_deps", []))
                btn.setToolTip(f"Requires: {dep_names}" if self._lang != "it" else f"Dipende da: {dep_names}")
            elif p["status"] == "unsupported":
                btn.setEnabled(False)
                plat = p.get("platform", "?")
                btn.setToolTip(f"Requires: {plat}" if self._lang != "it" else f"Richiede: {plat}")
            else:
                btn.clicked.connect(lambda checked, n=p["name"]: self._toggle_enabled(n))
        else:
            btn = QPushButton(self._t("plugins.disable"))
            btn.setFixedWidth(self._btn_width)
            btn.setStyleSheet(
                "QPushButton { background-color: #c0392b; color: #fff; border-radius: 3px; "
                "padding: 3px 10px; font-size: 11px; }"
                "QPushButton:hover { background-color: #e74c3c; }")
            btn.clicked.connect(lambda checked, n=p["name"]: self._toggle_enabled(n))
        row_layout.addWidget(btn)

        if p["category"] == "external":
            rem_btn = QPushButton(self._t("plugins.remove"))
            rem_btn.setStyleSheet(
                "QPushButton { background-color: #a83232; color: #fff; border-radius: 3px; "
                "padding: 3px 10px; font-size: 11px; }"
                "QPushButton:hover { background-color: #c0392b; }")
            rem_btn.clicked.connect(lambda checked, n=p["name"]: self._remove_plugin(n))
            row_layout.addWidget(rem_btn)

        return row

    def _toggle_enabled(self, name):
        statuses = self._server.get_plugins_status(self._lang)
        current = next((s for s in statuses if s["name"] == name), None)
        if not current:
            return
        if current["status"] == "disabled":
            self._server.enable_plugin(name)
        else:
            dependents = [s["name"] for s in statuses
                          if s["status"] not in ("disabled", "blocked", "unsupported")
                          and name in s.get("depends_on", [])]
            if dependents:
                deps_list = ", ".join(dependents)
                msg = QMessageBox(self)
                msg.setWindowTitle(self._t("plugins.deps_warning.title"))
                msg.setText(self._t("plugins.deps_warning.text").replace("{name}", name).replace("{deps}", deps_list))
                msg.setIcon(QMessageBox.Icon.Warning)
                yes_btn = msg.addButton(self._t("plugins.deps_warning.disable_anyway"), QMessageBox.ButtonRole.YesRole)
                no_btn = msg.addButton(self._t("plugins.deps_warning.cancel"), QMessageBox.ButtonRole.NoRole)
                msg.exec()
                if msg.clickedButton() != yes_btn:
                    return
            self._server.disable_plugin(name)
        self._refresh()

    def _remove_plugin(self, name):
        msg = QMessageBox(self)
        msg.setWindowTitle(self._t("plugins.remove_confirm.title"))
        msg.setText(self._t("plugins.remove_confirm.text").replace("{name}", name))
        msg.setIcon(QMessageBox.Icon.Question)
        yes_btn = msg.addButton(self._t("plugins.remove_confirm.yes"), QMessageBox.ButtonRole.YesRole)
        no_btn = msg.addButton(self._t("plugins.remove_confirm.no"), QMessageBox.ButtonRole.NoRole)
        msg.exec()
        if msg.clickedButton() != yes_btn:
            return
        self._server.remove_plugin(name)
        self._refresh()

    def _plugin_has_config(self, name):
        try:
            cfg = self._server.get_plugin_config(name, self._lang)
            return cfg is not None and len(cfg.get("fields", [])) > 0
        except Exception:
            return False

    def _open_settings(self, name):
        cfg = self._server.get_plugin_config(name, self._lang)
        if not cfg or not cfg.get("fields"):
            return
        was_running = self._server.is_plugin_running(name)
        dlg = PluginSettingsDialog(name, cfg, self._server, self._t, self._lang, self)
        if dlg.exec() == QDialog.DialogCode.Accepted and was_running:
            self._server.stop_plugin(name)
            self._server.start_plugin(name)
        self._refresh()


class PluginSettingsDialog(QDialog):
    def __init__(self, plugin_name, config, server, t_func, lang, parent=None):
        super().__init__(parent)
        self._name = plugin_name
        self._config = config
        self._server = server
        self._t = t_func
        self._lang = lang
        self.setWindowTitle(f"{plugin_name} - Settings")
        self.setMinimumWidth(380)
        self.setStyleSheet("QDialog { background-color: #1e1e1e; color: #e0e0e0; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self._widgets = {}
        fields = config.get("fields", [])
        values = config.get("values", {})

        for f in fields:
            row = QHBoxLayout()
            lbl = QLabel(f["label"])
            lbl.setStyleSheet("font-size: 12px;")
            lbl.setFixedWidth(160)
            row.addWidget(lbl)

            ft = f["type"]
            section = f["section"]
            key = f["key"]
            current = values.get(section, {}).get(key, "")

            if ft == "toggle":
                w = QCheckBox()
                try:
                    w.setChecked(current.lower() in ("true", "1", "yes"))
                except Exception:
                    pass
                row.addWidget(w)
                row.addStretch()
                self._widgets[f["key"]] = ("toggle", w)

            elif ft == "slider":
                min_v = f.get("min_value", 0)
                max_v = f.get("max_value", 1)
                step = f.get("step", 0.01)
                decimals = f.get("decimals", 2)
                try:
                    cur_float = float(current)
                except (ValueError, TypeError):
                    cur_float = min_v

                slider = QSlider(Qt.Orientation.Horizontal)
                slider.setRange(int(min_v / step), int(max_v / step))
                slider.setValue(int(cur_float / step))
                slider.setStyleSheet(
                    "QSlider::groove:horizontal { height: 4px; background: #444; border-radius: 2px; }"
                    "QSlider::handle:horizontal { background: #2ecc71; width: 12px; "
                    "margin: -4px 0; border-radius: 6px; }")
                val_lbl = QLabel(f"{cur_float:.{decimals}f}")
                val_lbl.setFixedWidth(50)
                val_lbl.setStyleSheet("color: #aaa; font-size: 11px;")

                slider.valueChanged.connect(
                    lambda v, w=slider, l=val_lbl, s=step, d=decimals:
                    l.setText(f"{v * s:.{d}f}"))
                row.addWidget(slider)
                row.addWidget(val_lbl)
                self._widgets[f["key"]] = ("slider", slider, decimals, step)

            elif ft == "dropdown":
                w = QComboBox()
                opts = f.get("options", [])
                w.addItems(opts)
                if current in opts:
                    w.setCurrentText(current)
                w.setStyleSheet(
                    "QComboBox { background: #333; border: 1px solid #555; border-radius: 3px; "
                    "padding: 3px 6px; }")
                row.addWidget(w)
                row.addStretch()
                self._widgets[f["key"]] = ("dropdown", w)

            elif ft == "readonly":
                w = QTextEdit()
                w.setText(str(current))
                w.setReadOnly(True)
                w.setMaximumHeight(80)
                w.setStyleSheet(
                    "QTextEdit { background: #2a2a2a; border: 1px solid #444; border-radius: 3px; "
                    "padding: 3px 6px; color: #999; font-size: 11px; }")
                row.addWidget(w)
                self._widgets[f["key"]] = ("readonly", w)

            else:
                w = QLineEdit()
                w.setText(str(current))
                w.setStyleSheet(
                    "QLineEdit { background: #333; border: 1px solid #555; border-radius: 3px; "
                    "padding: 3px 6px; }")
                row.addWidget(w)
                self._widgets[f["key"]] = ("text", w)

            layout.addLayout(row)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton(self._t("plugins.cancel"))
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton(self._t("plugins.save"))
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._save)
        save_btn.setStyleSheet(
            "QPushButton { background-color: #2ecc71; color: #fff; border-radius: 3px; "
            "padding: 6px 18px; font-weight: bold; }"
            "QPushButton:hover { background-color: #27ae60; }")
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

    def _save(self):
        fields = self._config.get("fields", [])
        for f in fields:
            section = f["section"]
            key = f["key"]
            w_info = self._widgets.get(key)
            if not w_info:
                continue
            ft = w_info[0]
            if ft == "readonly":
                continue
            w = w_info[1]
            if ft == "toggle":
                val = "true" if w.isChecked() else "false"
            elif ft == "slider":
                decimals = w_info[2]
                step = w_info[3]
                val = f"{w.value() * step:.{decimals}f}"
            elif ft == "dropdown":
                val = w.currentText()
            else:
                val = w.text()
            self._server.set_plugin_value(self._name, section, key, val)
        self.accept()


