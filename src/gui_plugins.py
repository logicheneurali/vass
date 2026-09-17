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
        close_btn = QPushButton(self._t("gui.close"))
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

        cfg_btn = QPushButton()
        cfg_btn.setIcon(icon("settings", "#cccccc", 16))
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

            elif ft == "note":
                note = QLabel(str(f.get("note", "")))
                note.setWordWrap(True)
                note.setStyleSheet(
                    "color: #aaa; font-size: 11px; background: #2a2a2a; border-radius: 3px; "
                    "padding: 6px 8px;")
                layout.addWidget(note)
                continue

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


_PLUGIN_UI_EXTRA_STYLE = (
    "QDialog { background-color: #1e1e1e; color: #e0e0e0; }"
    "QLabel { color: #e0e0e0; }"
    "QCheckBox { color: #e0e0e0; }"
    "QLineEdit { background: #333; border: 1px solid #555; border-radius: 3px; "
    "padding: 3px 6px; color: #e0e0e0; }"
    "QComboBox { background: #333; border: 1px solid #555; border-radius: 3px; "
    "padding: 3px 6px; color: #e0e0e0; }"
    "QSlider::groove:horizontal { height: 4px; background: #444; border-radius: 2px; }"
    "QSlider::handle:horizontal { background: #2ecc71; width: 12px; "
    "margin: -4px 0; border-radius: 6px; }"
)


class PluginUiDialog(QDialog):
    """Renderer for declarative plugin UIs (ui_register schema).

    Widget kinds: toggle, slider, text, combo, button, label, list.
    Instant widgets (toggle/slider with instant=true) send ui_action on change;
    buffered widgets (text/combo, and non-instant toggles/sliders) are collected
    and sent with button clicks. The plugin replies with ui_state which is
    polled every second and applied to the widgets.
    """

    def __init__(self, plugin_server, name, schema, t_func, lang, parent=None):
        super().__init__(parent)
        self._server = plugin_server
        self._name = name
        self._schema = schema
        self._t = t_func
        self._lang = lang
        self._widgets = {}          # key -> widget
        self._widget_kind = {}      # key -> kind
        self._list_widgets = {}     # key -> QListWidget
        self._slider_labels = {}    # key -> QLabel (value display)
        self._last_state = None

        title = (schema.get(f"title_{lang}") or schema.get("title") or name)
        self.setWindowTitle(title)
        self.setMinimumWidth(460)
        self.setStyleSheet(BASE_STYLESHEET + _PLUGIN_UI_EXTRA_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # Content rows are wrapped in a scroll area so tall profiles scroll
        # instead of being clipped by the dialog height.
        container = QWidget()
        content_layout = QVBoxLayout(container)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(10)

        for section in schema.get("sections", []):
            sec_title = (section.get(f"title_{lang}")
                         or section.get("title") or "")
            box = QGroupBox(sec_title) if sec_title else QGroupBox()
            box.setStyleSheet("QGroupBox { border: 1px solid #333; border-radius: 4px; "
                              "margin-top: 8px; padding-top: 6px; color: #e0e0e0; }")
            sec_layout = QVBoxLayout(box)
            sec_layout.setSpacing(6)
            for row in section.get("rows", []):
                self._build_row(sec_layout, row)
            content_layout.addWidget(box)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(container)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(scroll, 1)

        # Close button stays outside the scroll area so it is always reachable.
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        close_btn = QPushButton(self._t("gui.close"))
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self._sync_state()
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._sync_state)
        self._timer.start()

    # ── helpers ──────────────────────────────────────────────────

    def _loc(self, field, key):
        return (field.get(f"label_{self._lang}")
                or field.get("label") or key)

    def _collect_values(self):
        values = {}
        for key, w in self._widgets.items():
            kind = self._widget_kind[key]
            try:
                if kind == "toggle":
                    values[key] = bool(w.isChecked())
                elif kind == "slider":
                    values[key] = w.value()
                elif kind == "combo":
                    values[key] = w.currentText()
                elif kind == "text":
                    values[key] = w.text()
                elif kind == "label":
                    values[key] = w.text()
            except Exception:
                pass
        for key, lw in self._list_widgets.items():
            item = lw.currentItem()
            values[f"{key}_selected"] = item.data(Qt.ItemDataRole.UserRole) if item else ""
        return values

    def _emit(self, key, event, extra=None):
        action = {"key": key, "event": event}
        if event != "select":
            action["values"] = self._collect_values()
        if extra:
            action.update(extra)
        self._server.send_ui_action(self._name, action)

    # ── row builders ─────────────────────────────────────────────

    def _build_row(self, layout, row):
        kind = row.get("kind", "label")
        key = row.get("key", "")
        label = self._loc(row, key)

        if kind == "toggle":
            w = QCheckBox(label)
            w.setChecked(bool(row.get("value", False)))
            if row.get("instant"):
                w.toggled.connect(lambda checked, k=key: self._emit(k, "toggle"))
            layout.addWidget(w)
            self._widgets[key] = w
            self._widget_kind[key] = "toggle"

        elif kind == "slider":
            row_l = QHBoxLayout()
            lbl = QLabel(label)
            lbl.setFixedWidth(150)
            row_l.addWidget(lbl)
            w = QSlider(Qt.Orientation.Horizontal)
            w.setRange(int(row.get("min", 0)), int(row.get("max", 100)))
            w.setValue(int(row.get("value", 0)))
            val_lbl = QLabel(str(w.value()))
            val_lbl.setFixedWidth(40)
            val_lbl.setStyleSheet("color: #aaa;")
            if row.get("instant"):
                w.valueChanged.connect(
                    lambda v, k=key: (val_lbl.setText(str(v)), self._emit(k, "slider")))
            else:
                w.valueChanged.connect(lambda v, l=val_lbl: l.setText(str(v)))
            row_l.addWidget(w)
            row_l.addWidget(val_lbl)
            layout.addLayout(row_l)
            self._widgets[key] = w
            self._widget_kind[key] = "slider"
            self._slider_labels[key] = val_lbl

        elif kind == "text":
            row_l = QHBoxLayout()
            lbl = QLabel(label)
            lbl.setFixedWidth(150)
            row_l.addWidget(lbl)
            w = QLineEdit(str(row.get("value", "")))
            row_l.addWidget(w)
            layout.addLayout(row_l)
            self._widgets[key] = w
            self._widget_kind[key] = "text"

        elif kind == "combo":
            row_l = QHBoxLayout()
            lbl = QLabel(label)
            lbl.setFixedWidth(150)
            row_l.addWidget(lbl)
            w = QComboBox()
            w.addItems([str(o) for o in row.get("options", [])])
            cur = str(row.get("value", ""))
            if cur in [str(o) for o in row.get("options", [])]:
                w.setCurrentText(cur)
            row_l.addWidget(w)
            layout.addLayout(row_l)
            self._widgets[key] = w
            self._widget_kind[key] = "combo"

        elif kind == "button":
            w = QPushButton(label)
            w.clicked.connect(lambda checked=False, k=key: self._emit(k, "button"))
            layout.addWidget(w)
            self._widgets[key] = w
            self._widget_kind[key] = "button"

        elif kind == "list":
            lbl = QLabel(label)
            layout.addWidget(lbl)
            lw = QListWidget()
            self._fill_list(lw, row.get("items", []), row)

            def _on_select(current, _prev, k=key):
                item_id = current.data(Qt.ItemDataRole.UserRole) if current else ""
                self._emit(k, "select", {"selected": item_id})

            lw.currentItemChanged.connect(_on_select)
            layout.addWidget(lw)
            self._list_widgets[key] = lw

        else:  # label
            w = QLabel(str(row.get("text", "")))
            w.setWordWrap(True)
            w.setStyleSheet("color: #aaa;")
            layout.addWidget(w)
            self._widgets[key] = w
            self._widget_kind[key] = "label"

    @staticmethod
    def _fill_list(lw, items, row):
        lw.blockSignals(True)
        lw.clear()
        columns = [c.get("key", "") for c in row.get("columns", [])]
        for item in items:
            parts = []
            for ck in columns:
                v = item.get(ck, "")
                if isinstance(v, bool):
                    v = "on" if v else "off"
                parts.append(str(v))
            li = QListWidgetItem(" — ".join(parts))
            li.setData(Qt.ItemDataRole.UserRole, item.get("id", ""))
            lw.addItem(li)
        lw.blockSignals(False)

    # ── state sync ───────────────────────────────────────────────

    def _sync_state(self):
        try:
            uis = self._server.get_plugin_uis()
            entry = uis.get(self._name)
            state = entry.get("state", {}) if entry else {}
        except Exception:
            return
        if state == self._last_state:
            return
        self._last_state = copy.deepcopy(state)

        for key, w in self._widgets.items():
            if key not in state:
                continue
            kind = self._widget_kind[key]
            try:
                if kind == "toggle":
                    w.blockSignals(True)
                    w.setChecked(bool(state[key]))
                    w.blockSignals(False)
                elif kind == "slider":
                    w.blockSignals(True)
                    w.setValue(int(state[key]))
                    w.blockSignals(False)
                    lbl = self._slider_labels.get(key)
                    if lbl:
                        lbl.setText(str(w.value()))
                elif kind == "combo":
                    txt = str(state[key])
                    if txt in [w.itemText(i) for i in range(w.count())]:
                        w.setCurrentText(txt)
                elif kind == "text":
                    w.setText(str(state[key]))
                elif kind == "label":
                    w.setText(str(state[key]))
            except Exception:
                pass

        for key, lw in self._list_widgets.items():
            items = state.get(key)
            if not isinstance(items, list):
                continue
            current_ids = [lw.item(i).data(Qt.ItemDataRole.UserRole)
                           for i in range(lw.count())]
            new_ids = [i.get("id", "") for i in items]
            if current_ids == new_ids:
                continue  # dati invariati: preserva selezione e scroll
            sel_id = (lw.currentItem().data(Qt.ItemDataRole.UserRole)
                      if lw.currentItem() else "")
            self._fill_list(lw, items, self._find_row(key))
            if not items:
                continue
            row = 0
            for i in range(lw.count()):
                if lw.item(i).data(Qt.ItemDataRole.UserRole) == sel_id:
                    row = i
                    break
            lw.setCurrentRow(row)

    def _find_row(self, key):
        for section in self._schema.get("sections", []):
            for row in section.get("rows", []):
                if row.get("key") == key:
                    return row
        return {}


