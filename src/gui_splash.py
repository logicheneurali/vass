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


