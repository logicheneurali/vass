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

class InfoPanel(QFrame):
    """Floating panel: dynamic tabs for notifications by type, AI links, AI responses."""

    _TYPE_ICONS = {
        "rss": "rss", "timer": "clock", "event": "calendar",
        "schedule": "clipboard-list", "mail": "mail", "auth": "key",
        "script": "scroll-text", "agent": "bot",
        "profile": "user", "world_event": "globe",
    }

    _ACTION_HANDLERS = {
        "open_browser": lambda self, item: self._open_url((item.get("data") or {}).get("link", "")),
        "open_file": lambda self, item: self._open_file((item.get("data") or {}).get("path", "")),
        "open_queue": lambda self, item: (
            self._open_queue_cb((item.get("data") or {}).get("queue_id", ""))
            if getattr(self, "_open_queue_cb", None) else None),
        "copy_text": lambda self, item: self._copy_text((item.get("data") or {}).get("text", "")),
        "speak_text": lambda self, item: self._speak_item(item),
        "mark_read": lambda self, item: None,
        "mark_seen": lambda self, item: None,
    }

    _TYPE_ACTIONS = {
        "rss": ["open_browser", "speak_text"],
        "mail": ["open_browser", "speak_text"],
        "auth": ["open_browser", "speak_text"],
        "link": ["open_browser"],
        "file": ["open_file"],
        "ai": ["copy_text", "speak_text"],
        "mail_queue": ["open_queue"],
        "youtube": ["mark_seen", "open_browser"],
        "world_event": ["speak_text"],
        "watch": ["open_browser", "speak_text"],
    }

    _ACTION_ICONS = {
        "open_browser": "arrow-up-right",
        "open_file": "folder-open",
        "open_queue": "mail",
        "copy_text": "clipboard-list",
        "speak_text": "volume-2",
        "mark_seen": "eye",
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
        self._files = []
        self._ai_responses = []
        self._tab = "all"
        self._expanded = False
        self._user_opened = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._auto_close)
        self._parent_window = None

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(4, 4, 4, 4)
        self._layout.setSpacing(2)

        self._tab_row = QHBoxLayout()
        self._tab_row.setSpacing(2)
        self._tab_buttons = {}

        self._overflow_menu = QMenu()
        self._overflow_btn = QPushButton()
        self._overflow_btn.setIcon(icon("plus", "#888", 14))
        self._overflow_btn.setFixedSize(20, 20)
        self._overflow_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #888; border: none; "
            "font-size: 14px; font-weight: bold; }"
            "QPushButton:hover { color: #e0e0e0; }")
        self._overflow_btn.setMenu(self._overflow_menu)
        self._overflow_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._overflow_btn.hide()
        self._tab_row.addWidget(self._overflow_btn)

        self._tab_row.addStretch()
        self._expand_btn = QPushButton()
        self._expand_btn.setIcon(icon("maximize-2", "#888", 14))
        self._expand_btn.setFixedSize(20, 20)
        self._expand_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #888; border: none; "
            "font-size: 14px; font-weight: bold; }"
            "QPushButton:hover { color: #e0e0e0; }"
        )
        self._expand_btn.setToolTip("Expand")
        self._expand_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._expand_btn.clicked.connect(self._toggle_expand)
        self._tab_row.addWidget(self._expand_btn)
        close_btn = QPushButton()
        close_btn.setIcon(icon_dual("x", "#888", "#e94560", 14))
        close_btn.setFixedSize(20, 20)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #888; border: none; "
            "font-size: 14px; font-weight: bold; }"
            "QPushButton:hover { color: #e94560; }"
        )
        close_btn.clicked.connect(self._close_panel)
        self._tab_row.addWidget(close_btn)
        self._layout.addLayout(self._tab_row)

        self._scroll = SmoothScrollArea()
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
        ordered = [("all", "all", "clipboard-list",
                    all_label if self._expanded else "", all_label)]

        if self._links or self._files:
            links_label = self._t("gui.links")
            ordered.append(("links", "links", "link",
                           links_label if self._expanded else "", links_label))
        if self._ai_responses:
            ai_label = self._t("gui.ai_responses")
            ordered.append(("ai", "ai", "message-circle",
                           ai_label if self._expanded else "", ai_label))

        for t in sorted(type_counts, key=lambda t: -type_counts[t]):
            icon_name = self._TYPE_ICONS.get(t, "bell")
            count = type_counts[t]
            label = self._t(f"notification_types.{t}")
            badge = f"({count})" if count > 0 else ""
            if self._expanded:
                display_text = f"{label} {badge}".strip()
            else:
                display_text = badge if badge else ""
            ordered.append((t, t, icon_name, display_text, label))

        # Calculate available width based on parent window geometry
        if self._parent_window:
            geo = self._parent_window.geometry()
            panel_w = int(geo.width() * (3.0 if self._expanded else 1.25))
        else:
            panel_w = 275
        available = panel_w - 60  # expand + close + overflow + margins

        for t_id, t_type, icon_name, display_text, tooltip_text in ordered:
            btn = QPushButton(display_text)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(tooltip_text)
            btn.setIcon(icon(icon_name, "#e94560" if t_type == active_tab else "#888", 12))
            btn.setIconSize(QSize(12, 12))
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
                action = self._overflow_menu.addAction(tooltip_text)
                action.triggered.connect(lambda checked=None, tab=t_type: self._switch_tab(tab))

    def _switch_tab(self, tab):
        self._tab = tab
        self._build_toolbar(tab)
        self._mark_btn.setText(self._t("gui.mark_all_read"))
        self._mark_btn.setVisible(tab in ("all", "notifications", "other") or tab not in ("links", "ai"))
        if tab == "links":
            self._build_links()
        elif tab == "ai":
            self._build_ai_responses()
        else:
            filter_type = "all" if tab in ("all", "notifications") else tab
            self._build_notifications(filter_type)
        # Scroll to top: animate only when visible and after the layout has settled;
        # otherwise reset instantly (panel not yet shown / content freshly built).
        if self.isVisible():
            QTimer.singleShot(0, lambda: self._scroll.animate_to(0))
        else:
            self._scroll.verticalScrollBar().setValue(0)

    def _reset_timer(self):
        if self.isVisible() and not self._user_opened:
            self._timer.start(30000)

    def _auto_close(self):
        """Auto-close only panels the app opened (never user-opened ones)."""
        if not self._user_opened:
            self._close_panel()

    def hide_if_auto(self):
        """Hide unless the user opened the panel manually."""
        if not self._user_opened:
            self._close_panel()

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
        if user_opened:
            self._timer.stop()
        else:
            self._timer.start(30000)

    def set_links(self, urls, parent_window, files=None):
        self._links = urls
        self._files = files or []
        if not urls and not self._files:
            return
        self._parent_window = parent_window
        self._switch_tab("links")
        self._position(parent_window)
        self.show()
        self.raise_()
        if not self._user_opened:
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
        if not self._user_opened:
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
        if not self._links and not self._files:
            return
        from urllib.parse import urlparse
        for url in self._links:
            try:
                domain = urlparse(url).netloc or url
            except ValueError:
                domain = url[:50]
            display = url if len(url) <= 50 else url[:47] + "..."
            item = {"data": {"type": "link", "link": url}}
            container = QWidget()
            container.setStyleSheet("background: transparent;")
            c_layout = QVBoxLayout(container)
            c_layout.setContentsMargins(4, 3, 4, 3)
            c_layout.setSpacing(1)
            link_lbl = QLabel(f"{domain}\n{display}")
            link_lbl.setStyleSheet(
                f"color: #aaaaaa; background: transparent; font-size: {self._fs(11)}px;"
                f"padding: 4px 8px; border: 1px solid #16213e; border-radius: 3px;"
            )
            link_lbl.setWordWrap(True)
            link_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
            link_lbl.setToolTip(url)
            link_lbl.mousePressEvent = lambda e, it=item: self._on_item_click(it)
            c_layout.addWidget(link_lbl)
            action_row = QHBoxLayout()
            action_row.setSpacing(2)
            for abtn in self._build_action_icons(item):
                action_row.addWidget(abtn)
            action_row.addStretch()
            if action_row.count() > 1:
                c_layout.addLayout(action_row)
            self._scroll_layout.addWidget(container)
        for path in self._files:
            name = os.path.basename(path)
            display = path if len(path) <= 50 else path[:47] + "..."
            item = {"data": {"type": "file", "path": path}}
            container = QWidget()
            container.setStyleSheet("background: transparent;")
            c_layout = QVBoxLayout(container)
            c_layout.setContentsMargins(4, 3, 4, 3)
            c_layout.setSpacing(1)
            file_lbl = QLabel(f"{name}\n{display}")
            file_lbl.setStyleSheet(
                f"color: #8fb5d0; background: transparent; font-size: {self._fs(11)}px;"
                f"padding: 4px 8px; border: 1px solid #0f3460; border-radius: 3px;"
            )
            file_lbl.setWordWrap(True)
            file_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
            file_lbl.setToolTip(path)
            file_lbl.mousePressEvent = lambda e, it=item: self._on_item_click(it)
            c_layout.addWidget(file_lbl)
            action_row = QHBoxLayout()
            action_row.setSpacing(2)
            for abtn in self._build_action_icons(item):
                action_row.addWidget(abtn)
            action_row.addStretch()
            if action_row.count() > 1:
                c_layout.addLayout(action_row)
            self._scroll_layout.addWidget(container)
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
            icon_name = self._TYPE_ICONS.get(n.get("data", {}).get("type", ""), "bell")
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
            icon_lbl = QLabel()
            icon_lbl.setPixmap(pixmap(icon_name, "#aaaaaa", 16))
            icon_lbl.setStyleSheet("background: transparent;")
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
            # Actions row: horizontal icon buttons below the text
            action_row = QHBoxLayout()
            action_row.setSpacing(2)
            for abtn in self._build_action_icons(n):
                action_row.addWidget(abtn)
            action_row.addStretch()
            # Container
            container = QWidget()
            container.setStyleSheet("background: transparent;")
            container_layout = QVBoxLayout(container)
            container_layout.setContentsMargins(4, 3, 4, 3)
            container_layout.setSpacing(1)
            container_layout.addLayout(top_row)
            container_layout.addWidget(text_lbl)
            if action_row.count() > 1:
                container_layout.addLayout(action_row)
            container.setCursor(Qt.CursorShape.PointingHandCursor)
            container.mousePressEvent = lambda e, it=n: self._on_item_click(it)
            self._scroll_layout.addWidget(container)
        self._scroll_layout.addStretch()

    def _on_item_click(self, item):
        self._reset_timer()
        self._mark_read(item)

    def _mark_read(self, item):
        if not item or not item.get("id"):
            return
        if hasattr(self, '_nm') and self._nm is not None:
            for n in self._nm.list_all():
                if n["id"] == item["id"]:
                    n["read"] = True
                    break
            if hasattr(self, '_update_bell_cb'):
                self._update_bell_cb()
            filter_type = "all" if self._tab in ("all", "notifications") else self._tab
            scroll_val = self._scroll.verticalScrollBar().value()
            self._build_notifications(filter_type)
            self._scroll.stop_animation()
            self._scroll.verticalScrollBar().setValue(scroll_val)

    def _run_action(self, action, item):
        self._reset_timer()
        handler = self._ACTION_HANDLERS.get(action, self._ACTION_HANDLERS["mark_read"])
        try:
            handler(self, item)
        except Exception:
            pass

    def _item_actions(self, item):
        data = item.get("data", {})
        raw = data.get("action") or self._TYPE_ACTIONS.get(data.get("type"), [])
        if raw is None:
            raw = []
        return raw if isinstance(raw, list) else [raw]

    def _build_action_icons(self, item):
        """Build horizontal icon buttons for the item's actions (mark_read is implicit)."""
        buttons = []
        for act in self._item_actions(item):
            if act == "mark_read":
                continue
            btn = QPushButton()
            btn.setIcon(icon(self._ACTION_ICONS.get(act, "ellipsis"), "#888", 13, 1))
            btn.setIconSize(QSize(13, 13))
            btn.setFixedSize(18, 18)
            btn.setToolTip(self._t(f"gui.actions.{act}"))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(
                "QPushButton { background: transparent; border: none; }"
                "QPushButton:hover { background: #16213e; border-radius: 3px; }"
            )
            btn.clicked.connect(lambda checked=False, a=act, it=item: self._run_action(a, it))
            buttons.append(btn)
        return buttons

    def _mark_all_read(self):
        if hasattr(self, '_nm') and self._nm is not None:
            self._nm.mark_all_read()
            if hasattr(self, '_update_bell_cb') and self._update_bell_cb:
                self._update_bell_cb()
            self._close_panel()

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
            item = {"data": {"type": "ai", "text": text}}
            container = QWidget()
            container.setStyleSheet("background: transparent;")
            c_layout = QVBoxLayout(container)
            c_layout.setContentsMargins(4, 3, 4, 3)
            c_layout.setSpacing(1)
            text_lbl = QLabel(text)
            text_lbl.setWordWrap(True)
            text_lbl.setStyleSheet(f"color: #aaa; font-size: {self._fs(11)}px; background: transparent;"
                                   "padding: 4px; border: 1px solid #16213e; border-radius: 3px;")
            text_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
            text_lbl.setToolTip(self._t("gui.click_to_copy"))
            text_lbl.mousePressEvent = lambda e, it=item: self._on_item_click(it)
            c_layout.addWidget(text_lbl)
            action_row = QHBoxLayout()
            action_row.setSpacing(2)
            for abtn in self._build_action_icons(item):
                action_row.addWidget(abtn)
            action_row.addStretch()
            if action_row.count() > 1:
                c_layout.addLayout(action_row)
            self._scroll_layout.addWidget(container)
            last = container
        self._scroll_layout.addStretch()
        if last:
            QTimer.singleShot(0, lambda c=last: self._scroll.scroll_to_widget(c))

    def _copy_text(self, text):
        QApplication.clipboard().setText(text)

    def _speak_item(self, item):
        gui = self._parent_window
        app = getattr(gui, "app", None) if gui else None
        if not app or not getattr(app, "tts", None):
            return
        text = (item.get("data") or {}).get("text") or item.get("text", "")
        if text:
            app.tts.enqueue(text, defer_if_busy=True)

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
        # In compact mode the window is a 36x36 dot; anchor the panel to the
        # normal (non-compact) geometry so size and placement make sense.
        if getattr(parent, "_compact_mode", False) and parent._normal_geometry:
            geo_x, geo_y, geo_w, geo_h = parent._normal_geometry
        else:
            g = parent.geometry()
            geo_x, geo_y, geo_w, geo_h = g.x(), g.y(), g.width(), g.height()
        screen = QApplication.primaryScreen().availableGeometry()

        if self._expanded:
            panel_w = int(geo_w * 3.0)
            mid_x = screen.left() + screen.width() // 2
            if geo_x + geo_w // 2 < mid_x:
                px = geo_x
            else:
                px = geo_x + geo_w - panel_w
        else:
            panel_w = int(geo_w * 1.25)
            px = geo_x + geo_w // 2 - panel_w // 2

        if self._tab == "links":
            count = len(self._links) + len(self._files)
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
            if geo_x + geo_w // 2 < mid_x:
                px = geo_x
            else:
                px = geo_x + geo_w - panel_w
        else:
            px = geo_x + geo_w // 2 - panel_w // 2

        mid_y = screen.top() + screen.height() // 2
        if geo_y + geo_h // 2 < mid_y:
            py = geo_y + geo_h + 8
        else:
            py = geo_y - panel_h - 8
        px = max(screen.left(), min(px, screen.right() - panel_w))
        py = max(screen.top(), min(py, screen.bottom() - panel_h))
        self.setGeometry(px, py, panel_w, panel_h)

    def _open_url(self, url):
        import webbrowser
        webbrowser.open(url)

    def _open_file(self, path):
        if not path or not os.path.exists(path):
            return
        try:
            if sys.platform == "win32":
                os.startfile(path)  # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path], stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
            else:
                subprocess.Popen(["xdg-open", path], stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
        except Exception:
            pass


