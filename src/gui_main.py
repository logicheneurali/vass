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
from gui_splash import SplashScreen
from gui_widgets import WaveformPlayer, VolumeTopBar, MemoryBar, _ChatLineEdit, _CompactWidget
from gui_infopanel import InfoPanel
from gui_plugins import PluginManagerDialog, PluginUiDialog


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
    mic_pressed = Signal()
    tool_indicator_signal = Signal(str, str)
    compact_mode_signal = Signal(bool)
    debug_border_signal = Signal()
    splash_progress_signal = Signal(int, int, str)
 
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
        if _is_wayland():
            self.setGeometry(x, y, width, height)
            self.setFixedSize(width, height)
        else:
            self.setGeometry(x, y, width, height)

        ico_path = os.path.join(BASE, "vass.ico")
        if os.path.exists(ico_path):
            self.setWindowIcon(QIcon(ico_path))
            QApplication.setWindowIcon(QIcon(ico_path))

        self._font_family = font_family
        self._font_size = font_size

        self._splash = SplashScreen()
        self._splash.show()
        self.splash_progress_signal.connect(self._on_splash_progress)

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
        self.stacked.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)

        self._left_spacer = QSpacerItem(0, 0, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
        self._right_spacer = QSpacerItem(0, 0, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)

        # ── Left-side widgets ──────────────────────────────────────────
        # To add a new left-side component:
        #   1. Create the widget above
        #   2. Add it to the row layout: row.addWidget(widget)
        #   3. Append it to self._left_side for automatic balancing
        self._left_side = []
        self._right_side = []

        self._bell_btn = QPushButton()
        self._bell_btn.setIcon(icon("bell", "#3f3f3f", 16, 1))
        self._bell_btn.setStyleSheet(
            "QPushButton { background-color: transparent; color: #3f3f3f; "
            "border: none; font-size: 10px; padding: 2px 4px; }"
            "QPushButton:hover { color: #dddddd; }"
        )
        self._bell_btn.setFixedWidth(35)
        self._bell_btn.setToolTip(self._t("gui.notifications"))
        self._bell_btn.clicked.connect(lambda: self._show_info_panel("all"))
        self._bell_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        row.addWidget(self._bell_btn)
        self._left_side.append(self._bell_btn)

        self._tool_indicator = QPushButton()
        self._tool_indicator.setFlat(True)
        self._tool_indicator.setFixedSize(20, 20)
        self._tool_indicator.setIconSize(QSize(16, 16))
        self._tool_indicator.setVisible(False)
        self._tool_indicator.setToolTip("")
        self._tool_indicator.setStyleSheet(
            "QPushButton { background-color: transparent; border: none; padding: 0; }"
            "QPushButton:hover { background-color: rgba(255,255,255,0.08); }"
        )
        row.addWidget(self._tool_indicator)
        self._left_side.append(self._tool_indicator)

        self._mic_btn = QPushButton()
        self._mic_btn.setIcon(icon("mic", "#f1c40f", 16, 1))
        self._mic_btn.setIconSize(QSize(16, 16))
        self._mic_btn.setFixedSize(22, 22)
        self._mic_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #f1c40f; border: none; }"
            "QPushButton:hover { color: #f9e79f; }"
        )
        self._mic_btn.setVisible(False)
        self._mic_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mic_btn.setToolTip(self._t("gui.mic_btn_tooltip"))
        self._mic_btn.clicked.connect(lambda: self.mic_pressed.emit())
        row.addWidget(self._mic_btn)
        self._left_side.append(self._mic_btn)

        row.addSpacerItem(self._left_spacer)
        row.addWidget(self.stacked)
        row.addSpacerItem(self._right_spacer)

        self.replay_btn = QPushButton()
        self.replay_btn.setIcon(icon("refresh-cw", "#ffffff", 16, 1))
        self.replay_btn.setIconSize(QSize(16, 16))
        self.replay_btn.setStyleSheet(
            "QPushButton { background-color: transparent; color: #ffffff; "
            "border: none; padding: 2px; }"
            "QPushButton:hover { color: #dddddd; }"
        )
        self.replay_btn.setFixedWidth(22)
        self.replay_btn.setVisible(False)
        self.replay_btn.clicked.connect(self._on_replay)
        self.replay_btn._right_click_cb = self.open_history
        self.replay_btn.mousePressEvent = self._replay_btn_press
        self.replay_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        row.addWidget(self.replay_btn)
        self._right_side.append(self.replay_btn)

        # Menu button with popup
        # Right-side widget — automatically balanced by _rebalance_spacers()
        self._menu_btn = QPushButton()
        self._menu_btn.setIcon(icon("menu", "#ffffff", 16, 1))
        self._menu_btn.setIconSize(QSize(16, 16))
        self._menu_btn.setStyleSheet(
            "QPushButton { background-color: transparent; color: #888888; "
            "border: none; padding: 2px; }"
            "QPushButton:hover { color: #dddddd; }"
        )
        self._menu_btn.setFixedWidth(22)
        self._menu_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._menu = QMenu()
        self._menu.setStyleSheet(
            "QMenu { background-color: #2d2d2d; color: #e0e0e0; "
            "border: 1px solid #3c3c3c; padding: 4px; }"
            "QMenu::item { padding: 6px 20px; }"
            "QMenu::item:selected { background-color: #0d7377; }"
        )
        self._mail_queue_action = self._menu.addAction("")
        self._mail_queue_action.setVisible(False)
        self._mail_queue_action.triggered.connect(self.open_mail_queue)

        self._menu.addAction(self._t("gui.menu.history"), self.open_history)
        self._menu.addAction(self._t("gui.menu.memory_editor"), self.open_memory_editor)
        self._menu.addAction(self._t("gui.menu.events"), self.open_events)

        self._plugins_ui_menu = self._menu.addMenu(self._t("gui.menu.plugins_ui"))
        self._plugins_ui_menu.menuAction().setVisible(False)
        self._menu.aboutToShow.connect(self._update_plugins_ui_menu)

        self._settings_menu = self._menu.addMenu(self._t("gui.menu.settings"))
        self._settings_menu.addAction(self._t("gui.menu.settings_general"), self.open_settings)
        self._settings_menu.addAction(self._t("gui.menu.commands"), self.open_commands)
        self._settings_menu.addAction(self._t("gui.menu.scripts"), self.open_scripts)
        self._settings_menu.addAction(self._t("gui.menu.sources"), self.open_sources)
        self._settings_menu.addAction(self._t("gui.menu.plugins"), self.open_plugins)
        self._settings_menu.addSeparator()
        self._settings_menu.addAction(self._t("gui.menu.mail"), self.open_mail_editor)
        self._settings_menu.addAction(self._t("gui.menu.contacts"), self.open_contacts_editor)
        self._settings_menu.addAction(self._t("gui.menu.notifications"), self.open_notifications_editor)

        self._menu.aboutToShow.connect(self._update_mail_queue_menu)

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

        self._chat_btn = QPushButton()
        self._chat_btn.setIcon(icon("sparkles", "#ffffff", 16, 1))
        self._chat_btn.setIconSize(QSize(16, 16))
        self._chat_btn.setStyleSheet(
            "QPushButton { background-color: transparent; color: #ffffff; "
            "border: none; padding: 2px; }"
            "QPushButton:hover { color: #dddddd; }"
        )
        self._chat_btn.setFixedWidth(22)
        self._chat_btn.setCheckable(True)
        self._chat_btn.setCursor(Qt.CursorShape.PointingHandCursor)
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
        row.addWidget(self._chat_input)

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

        # Layout size enforce (restore width/height if a widget altered them)
        self._layout_enforce_timer = QTimer()
        self._layout_enforce_timer.setSingleShot(True)
        self._layout_enforce_timer.setInterval(0)
        self._layout_enforce_timer.timeout.connect(self._enforce_layout_size)

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

    def save_layout(self, x, y, width=None, height=None):
        import configparser
        path = os.path.join(BASE, "config", "layout.ini")
        try:
            layout = configparser.ConfigParser()
            if os.path.exists(path):
                layout.read(path, encoding="utf-8")
            w = str(width) if width is not None else layout.get("window", "width", fallback="200")
            h = str(height) if height is not None else layout.get("window", "height", fallback="32")
            layout["window"] = {"x": str(x), "y": str(y), "width": w, "height": h}
            with open(path, "w", encoding="utf-8") as f:
                layout.write(f)
        except Exception as e:
            print(f"[Layout] Could not save: {e}")

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
        if _is_wayland():
            return
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

        self.setGeometry(x, y, self.width(), self.height())

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
                if _is_wayland():
                    self.setFixedSize(self.width(), self.height())
                else:
                    self.setGeometry(center_x - 18, self.y(), self.width(), self.height())
                if self.app:
                    x, y = _get_window_pos(self)
                    if x or y:
                        self.save_layout(x, y, self.width(), self.height())
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
            self.volume_top_bar.show()
            self.memory_bar.show()
            self.stacked.show()
            for w in self._left_side:
                w.show()
            for w in self._right_side:
                w.show()
            # Apply size exclusively from layout.ini (do NOT clear fixed constraints)
            if self._normal_geometry:
                x, y = self._normal_geometry[0], self._normal_geometry[1]
            else:
                x, y = self.x(), self.y()
            self._apply_window_size()
            if not _is_wayland():
                self.move(x, y)
            if self.app:
                gx, gy = _get_window_pos(self)
                if gx or gy:
                    self.save_layout(gx, gy, self.width(), self.height())
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
        self.btn.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)

    def _btn_press(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self._exit_app()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            if _try_system_move(self):
                return
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
                    x, y = _get_window_pos(self)
                    if x or y:
                        self._pending_pos = (x, y, self.width(), self.height())
                        self._pos_debounce.start()
        self._drag_pos = None
        self._drag_start = None

    def _save_position_debounced(self):
        if self._pending_pos:
            x, y, w, h = self._pending_pos
            self.save_layout(x, y)
        self._pending_pos = None

    def _btn_release(self, event):
        self._ui_release(event)

    def moveEvent(self, event):
        super().moveEvent(event)
        if self.app and not self._compact_mode and sys.platform != "linux":
            x, y = _get_window_pos(self)
            if x or y:
                self._pending_pos = (x, y, self.width(), self.height())
                self._pos_debounce.start()

    def _apply_window_size(self):
        """Apply window size exclusively from layout.ini (single source of truth)."""
        import configparser
        path = os.path.join(BASE, "config", "layout.ini")
        layout = configparser.ConfigParser()
        if os.path.exists(path):
            layout.read(path, encoding="utf-8")
        w = layout.getint("window", "width", fallback=240)
        h = layout.getint("window", "height", fallback=32)
        self.setFixedSize(w, h)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self._compact_mode and hasattr(self, '_layout_enforce_timer'):
            self._layout_enforce_timer.start()

    def _enforce_layout_size(self):
        """Network of safety: if any widget altered the window size, restore it."""
        if self._compact_mode:
            return
        # Skip when chat is expanded (width intentionally doubled)
        if self._chat_btn.isChecked() or self._chat_input.isVisible():
            return
        import configparser
        path = os.path.join(BASE, "config", "layout.ini")
        layout = configparser.ConfigParser()
        if os.path.exists(path):
            layout.read(path, encoding="utf-8")
        w = layout.getint("window", "width", fallback=240)
        h = layout.getint("window", "height", fallback=32)
        if self.width() != w or self.height() != h:
            self.setFixedSize(w, h)

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
        if state in ("listening", "paused"):
            self.hide_tool_indicator()
        if state == "listening":
            self.hide_link_panel()
        if not self._compact_mode:
            self.stacked.setCurrentWidget(self.btn)
            if state == "listening":
                path = os.path.join(BASE, "Allowed_root", "last_response.txt")
                self.replay_btn.setVisible(os.path.exists(path) and os.path.getsize(path) > 0)
                self._chat_btn.setVisible(self._current_mode != "transcription")
                self._mic_btn.setVisible(self._current_mode in ("chat", "transcription"))
            else:
                self.replay_btn.setVisible(False)
                self._chat_btn.setVisible(False)
                self._mic_btn.setVisible(False)
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
            if not _is_wayland():
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
        if _is_wayland():
            return
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
        if mode != "transcription":
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
            self._bell_btn.setIcon(icon("bell", color, 16, 1))
            self._bell_btn.setText(str(count))
            self._bell_btn.setStyleSheet(
                f"QPushButton {{ background-color: transparent; color: {color}; "
                "border: none; font-size: 10px; padding: 2px 4px; font-weight: bold; }"
                f"QPushButton:hover {{ color: #dddddd; }}"
            )
        else:
            self._bell_btn.setIcon(icon("bell", "#3f3f3f", 16, 1))
            self._bell_btn.setText("0")
            self._bell_btn.setStyleSheet(
                "QPushButton { background-color: transparent; color: #3f3f3f; "
                "border: none; font-size: 10px; padding: 2px 4px; }"
                "QPushButton:hover { color: #dddddd; }"
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
        self._chat_btn.setChecked(False)
        self._chat_input.setVisible(False)
        self._chat_input.clear()
        self.stacked.setVisible(True)
        vis = getattr(self, '_left_side_visibility', {})
        for w in self._left_side:
            w.setVisible(vis.get(w, True))
        self._left_side_visibility = {}
        w = self._restore_from_layout() or self.width()
        self._rebalance_spacers(force_width=w)
        self._enforce_layout_size()

    def _restore_from_layout(self):
        import configparser
        path = os.path.join(BASE, "config", "layout.ini")
        try:
            layout = configparser.ConfigParser()
            if os.path.exists(path):
                layout.read(path, encoding="utf-8")
            x = layout.getint("window", "x", fallback=self.x())
            y = layout.getint("window", "y", fallback=self.y())
            w = layout.getint("window", "width", fallback=200)
            h = layout.getint("window", "height", fallback=32)
            self.move(x, y)
            self.setFixedWidth(w)
            self.setFixedHeight(h)
            #QTimer.singleShot(0, lambda: self.setFixedWidth(16777215))
            return w
        except Exception:
            pass

    def _rebalance_spacers(self, force_width=None):
        """Keep the stacked widget (button / waveform) horizontally centred.

        Calculates the total visible width of widgets placed to the left
        and right of the centred area, then pads the shorter side with a
        spacer so the centre widget stays balanced.

        If force_width is given, spacers are sized so the total layout
        fits exactly within that width.

        To make a new widget participate in balancing, append it to
        self._left_side or self._right_side.  No other changes needed.
        """
        left_w = sum(w.width() for w in self._left_side if w.isVisible())
        right_w = sum(w.width() for w in self._right_side if w.isVisible())

        if self._chat_input.isVisible():
            right_w += max(self._chat_input.width(),
                           self._chat_input.sizeHint().width())

        if force_width is not None:
            center_w = self.stacked.sizeHint().width() if self.stacked.isVisible() else 0
            total_side = left_w + right_w
            remaining = max(0, force_width - total_side - center_w)
            half = remaining // 2
            self._left_spacer.changeSize(half, half,
                QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
            self._right_spacer.changeSize(half, half,
                QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
        else:
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
            original_width = self.width()
            self._left_side_visibility = {w: w.isVisible() for w in self._left_side}
            for w in self._left_side:
                w.setVisible(False)
            self.stacked.setVisible(False)
            self.setFixedWidth(original_width * 2)
            self.setFixedHeight(self.height())
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
            self.splash_progress_signal.emit(value, maximum, detail)
        # also update compact loading label for when splash is gone
        if hasattr(self, 'loading_label') and detail:
            try:
                self.loading_label.setText(detail)
                self.loading_label.setWordWrap(True)
            except Exception:
                pass

    def _on_splash_progress(self, value, maximum, detail):
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

    def request_auth(self, script_name, func_name, timeout=None):
        import threading
        self._auth_result = None
        self._auth_timeout = timeout
        self._auth_event = threading.Event()
        self.auth_requested_signal.emit(script_name, func_name)
        if timeout:
            self._auth_event.wait(timeout)
            if self._auth_result is None:
                return "deny"
        else:
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
        timeout = getattr(self, "_auth_timeout", None)
        if timeout:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(int(timeout * 1000),
                              lambda: self._finish_auth("deny", dlg))
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
                    "mail": "vass - account di posta",
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

    def _update_plugins_ui_menu(self):
        """Populate the dynamic 'Plugin' submenu with registered declarative UIs."""
        self._plugins_ui_menu.clear()
        server = getattr(self.app, '_plugin_server', None) if self.app else None
        if server is None:
            self._plugins_ui_menu.menuAction().setVisible(False)
            return
        uis = server.get_plugin_uis()
        if not uis:
            self._plugins_ui_menu.menuAction().setVisible(False)
            return
        self._plugins_ui_menu.menuAction().setVisible(True)
        for name, entry in sorted(uis.items()):
            schema = entry.get("schema", {})
            title = (schema.get(f"title_{self.language}")
                     or schema.get("title") or name)
            action = self._plugins_ui_menu.addAction(title)
            if schema.get("launcher"):
                # One-click plugins: send the action directly, no dialog window
                action.triggered.connect(
                    lambda checked=False, n=name, s=server:
                        s.send_ui_action(n, {"key": "open", "event": "button"}))
            else:
                action.triggered.connect(lambda checked=False, n=name: self._open_plugin_ui(n))

    def _open_plugin_ui(self, name):
        if not self.app or not hasattr(self.app, '_plugin_server'):
            return
        server = self.app._plugin_server
        uis = server.get_plugin_uis()
        entry = uis.get(name)
        if not entry:
            return
        dlg = PluginUiDialog(server, name, entry.get("schema", {}),
                             self._t, self.language, self)
        dlg.exec()

    def open_mail_editor(self):
        self._open_unique_window("mail", os.path.join(SRC, "mail_editor.py"), "--lang", self.language)

    def open_contacts_editor(self):
        def _show():
            from mail.contacts_editor import ContactsDialog
            dlg = ContactsDialog(self, lang=self.language)
            dlg.exec()
        self.schedule_signal.emit(_show)

    def open_notifications_editor(self):
        def _show():
            from notifications_editor import NotificationsEditor
            dlg = NotificationsEditor(lang=self.language, parent=self)
            dlg.exec()
        self.schedule_signal.emit(_show)

    def open_mail_queue(self):
        def _show():
            from mail.queue_viewer import QueueViewerDialog
            dlg = QueueViewerDialog(self.language)
            dlg.exec()
        self.schedule_signal.emit(_show)

    def open_mail_queue_with_id(self, qid):
        def _show():
            from mail.queue_viewer import QueueViewerDialog
            dlg = QueueViewerDialog(self.language, select_id=qid)
            dlg.exec()
        self.schedule_signal.emit(_show)

    def _update_mail_queue_menu(self):
        try:
            from mail.queue import count
            n = count()
            if n > 0:
                self._mail_queue_action.setText(
                    self._t("gui.menu.mail_pending").replace("{n}", str(n)))
                self._mail_queue_action.setVisible(True)
            else:
                self._mail_queue_action.setVisible(False)
        except Exception:
            self._mail_queue_action.setVisible(False)

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
        if _is_wayland():
            return
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
        "model_advice": "#00bcd4", "generate_svg": "#e67e22",
        "readinfo": "#f1c40f", "read_info": "#f1c40f", "writeinfo": "#f1c40f", "write_info": "#f1c40f", "savetags": "#ff5722", "save_tags": "#ff5722",
        "getidle": "#95a5a6", "get_idle": "#95a5a6",
        "security_scan": "#e74c3c", "security_check_cve": "#e74c3c",
        "security_status": "#e74c3c", "security_remediate": "#c0392b",
        "evaluate_image": "#8e44ad", "evaluate_svg": "#8e44ad",
    }
    _TOOL_ICONS = {
        "browse": "globe", "webfetch": "globe", "websearch": "globe",
        "search_places": "globe", "search_nearby": "globe",
        "read_file": "scroll-text", "write_file": "scroll-text",
        "readinfo": "scroll-text", "read_info": "scroll-text",
        "writeinfo": "scroll-text", "write_info": "scroll-text",
        "html_to_pdf": "scroll-text",
        "interact": "bot", "script": "bot",
        "calendar_add": "calendar", "calendar_list": "calendar", "calendar_search": "calendar",
        "addevent": "calendar", "add_event": "calendar", "nextevent": "calendar",
        "listevents": "calendar", "list_events": "calendar", "find_free_slot": "calendar",
        "delevent": "x", "delete_event": "x",
        "clipboardget": "clipboard-list", "clipboard_get": "clipboard-list",
        "clipboardset": "clipboard-list", "clipboard_set": "clipboard-list",
        "current_time": "clock", "to_timestamp": "clock",
        "calculate": "sparkles",
        "model_advice": "sparkles", "generate_svg": "sparkles",
        "langcheck": "message-circle",
        "savetags": "pin", "save_tags": "pin", "search_tags": "pin",
        "getidle": "eye", "get_idle": "eye",
        "read_news": "rss", "read_news_range": "rss", "search_news": "rss",
        "search_emails": "mail", "send_email": "mail", "reply_email": "mail",
        "forward_email": "mail", "search_contacts": "user",
        "browser_open": "globe", "browser_read": "globe", "browser_click": "globe",
        "browser_fill": "globe", "browser_submit": "globe", "browser_download": "globe",
        "browser_back": "globe", "browser_show": "globe", "browser_check_auth": "globe",
        "security_scan": "key", "security_check_cve": "key",
        "security_status": "key", "security_remediate": "key",
        "evaluate_image": "eye", "evaluate_svg": "eye",
    }

    def show_tool_indicator(self, tool_name):
        from tool_groups import load_tool_name
        name, desc = load_tool_name(tool_name, self.language)
        color = self._TOOL_COLORS.get(tool_name, "#95a5a6")
        tip = f'<font color="{color}"><b>{name}</b></font><br><font color="#aaaaaa">{desc}</font>'
        self.tool_indicator_signal.emit(tool_name, tip)

    def hide_tool_indicator(self):
        self.tool_indicator_signal.emit("", "")

    def show_links(self, text, file_paths=None):
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
        if clean or file_paths:
            self._link_panel._t = self._t
            self.schedule_signal.emit(
                lambda urls=clean, f=file_paths: self._link_panel.set_links(urls, self, f))

    def hide_link_panel(self):
        self.schedule_signal.emit(lambda: self._link_panel.hide_if_auto())

    def show_ai_responses(self):
        if not self.app:
            return
        history = self.app.conversation_history
        self._link_panel._t = self._t
        self._link_panel.set_ai_responses(list(history), self)

    def _show_info_panel(self, tab="all"):
        if not self.app:
            return
        lp = self._link_panel
        # Bell click toggles OFF only a panel the user opened on this same tab.
        # An auto-opened panel is never closed by the bell: it gets upgraded to
        # a manual (sticky) open, so it can no longer auto-close.
        if lp.isVisible() and lp._user_opened and lp._tab == tab:
            lp._close_panel()
            return
        nm = self.app.notification_manager
        self.schedule_signal.emit(lambda: (
            setattr(lp, '_t', self._t),
            setattr(lp, '_nm', nm),
            setattr(lp, '_update_bell_cb', self._update_bell),
            setattr(lp, '_open_queue_cb', lambda qid: self.open_mail_queue_with_id(qid)),
            lp.show_panel(tab, self, user_opened=True)
        ))

    def set_mcp_status(self, ok):
        if ok:
            self.hide_tool_indicator()
        else:
            self.tool_indicator_signal.emit("__mcp_down__", "")

    def _on_tool_indicator(self, tool_name, tooltip):
        if tool_name == "__mcp_down__":
            self._compact_dot.set_tool("#e74c3c")
            if not self._compact_mode:
                self._tool_indicator.setIcon(icon("x", "#e74c3c", 16))
                self._tool_indicator.setToolTip(self._t("gui.mcp_down_tooltip"))
                self._tool_indicator.setVisible(True)
            return
        if tool_name == "__transcription__":
            self._compact_dot.set_tool("#95a5a6")
            if not self._compact_mode:
                self._tool_indicator.setIcon(icon("mic", "#95a5a6", 16))
                self._tool_indicator.setToolTip(self._t("gui.transcription_mode"))
                self._tool_indicator.setVisible(True)
            return
        if not tool_name:
            self._tool_indicator.setVisible(False)
            self._compact_dot.set_tool()
            return
        icon_name = self._TOOL_ICONS.get(tool_name, "bell")
        color = self._TOOL_COLORS.get(tool_name, "#95a5a6")
        self._compact_dot.set_tool(color)
        if not self._compact_mode:
            self._tool_indicator.setIcon(icon(icon_name, color, 16))
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
        elif event.button() == Qt.MouseButton.LeftButton:
            if _try_system_move(self):
                super().mousePressEvent(event)
                return
            # fallback: allow drag on empty window area (X11)
            self._drag_start = event.globalPosition().toPoint()
            self._drag_pos = self._drag_start
            self._drag_started = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if hasattr(self, "_drag_pos") and self._drag_pos is not None:
            self._ui_move(event)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if hasattr(self, "_drag_pos") and self._drag_pos is not None:
            self._ui_release(event)
        super().mouseReleaseEvent(event)


