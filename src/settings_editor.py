import configparser
import os
import sys
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
    QGroupBox, QMessageBox, QComboBox, QSlider, QCheckBox, QListWidget,
)
from PySide6.QtGui import QKeySequence, QShortcut
from i18n import t
from theme import (BG, FG, ENTRY_BG, ENTRY_FG, LABEL_FG, BTN_BG, BTN_FG,
                   SECTION_FG, DESCRIPTION_FG)

BASE_STYLESHEET = f"""
QMainWindow, QWidget {{ background-color: {BG}; color: {FG}; }}
QGroupBox {{
    font-weight: bold; color: {SECTION_FG};
    border: 1px solid #3c3c3c; border-radius: 4px;
    margin-top: 10px; padding-top: 14px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 6px;
}}
QLabel {{ color: {LABEL_FG}; font-size: 12px; }}
QLineEdit {{
    background-color: {ENTRY_BG}; color: {ENTRY_FG};
    border: 1px solid #3c3c3c; border-radius: 3px;
    padding: 5px 6px; font-size: 12px;
}}
QLineEdit:focus {{ border-color: {BTN_BG}; }}
QPushButton {{
    background-color: {BTN_BG}; color: {BTN_FG};
    border: none; border-radius: 3px; padding: 6px 18px;
    font-weight: bold; font-size: 12px;
}}
QPushButton:hover {{ background-color: #0a5c5e; }}
QPushButton:pressed {{ background-color: #085052; }}
QScrollArea {{ border: none; }}
QScrollBar:vertical {{
    background: {BG}; width: 10px;
}}
QScrollBar::handle:vertical {{
    background: #2d2d2d; border-radius: 4px; min-height: 20px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
QSlider::groove:horizontal {{
    background: #3c3c3c; height: 6px; border-radius: 3px;
}}
QSlider::handle:horizontal {{
    background: {BTN_BG}; width: 14px; height: 14px;
    margin: -4px 0; border-radius: 7px;
}}
QSlider::handle:horizontal:hover {{ background: #0a5c5e; }}
QSlider::sub-page:horizontal {{
    background: {BTN_BG}; border-radius: 3px;
}}
"""

BOOLEAN_KEYS = {"llama_autostart", "noise_pause", "calendar_enabled", "calendar_sync_enabled", "gmail_enabled", "google_home_enabled", "word_learning_enabled", "allow_ai_scripts", "debug_enabled"}
HIDDEN_KEYS = {"lastmode"}

COMBO_OPTIONS = {
    "overflow_strategy": {"truncate": "Truncate", "summarize": "Summarize"},
}

SLIDER_CONFIG = {
    "sensitivity": {"min": 1, "max": 20, "scale": 0.001, "default": 5},
    "similarity":  {"min": 0, "max": 100, "scale": 0.01, "default": 60},
    "input_volume":  {"min": 1, "max": 100, "scale": 0.01, "default": 100},
    "output_volume": {"min": 1, "max": 100, "scale": 0.01, "default": 100},
}



_SECTION_DEFAULTS = {
    "audio": {"input_device": "-1", "output_device": "-1", "input_volume": "1.0", "output_volume": "1.0"},
    "google": {
        "calendar_enabled": "false", "calendar_sync_enabled": "false",
        "calendar_sync_minutes": "30", "calendar_sync_days": "7",
        "gmail_enabled": "false", "gmail_sync_minutes": "5", "gmail_max_results": "10",
        "google_home_enabled": "false", "google_home_model_id": "", "google_home_device_id": "",
    },
    "debug": {"debug_enabled": "false", "debug_log_max_kb": "1024"},
}


class SettingsEditor(QMainWindow):
    def __init__(self, settings_file=None, language="en"):
        super().__init__()
        self.lang = language
        if settings_file is None:
            self.settings_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "settings.ini")
        else:
            self.settings_file = settings_file
        self.config = configparser.ConfigParser()
        self.load_config()
        self._ensure_sections()
        self.entries = {}
        self._slider_widgets = {}
        self._original_api_key = self._load_original_api_key()
        self._google_disabled = False
        self.build_ui()

    def _get_supported_languages(self):
        supported = []
        locales_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "locales")
        if os.path.isdir(locales_dir):
            for fname in os.listdir(locales_dir):
                if fname.endswith(".json"):
                    supported.append(fname[:-5])
        return sorted(supported)

    def _load_original_api_key(self):
        try:
            import keyring
            stored = keyring.get_password("vass", "api_key")
            if stored:
                return stored
        except Exception:
            pass
        return self.config.get("ai", "api_key", fallback="")

    def _add_api_key_field(self, section, group_layout, row):
        api_label = t("settings_editor.field_labels.api_key", self.lang)
        lbl = QLabel(api_label)
        group_layout.addWidget(lbl, row, 0, Qt.AlignTop)

        entry = QLineEdit()
        entry.setEchoMode(QLineEdit.Password)
        entry.setText(self._original_api_key)
        toggle_btn = QPushButton("👁")
        toggle_btn.setFixedWidth(30)
        toggle_btn.setCheckable(True)
        toggle_btn.setToolTip("Mostra/Nascondi chiave")
        toggle_btn.toggled.connect(lambda checked: entry.setEchoMode(
            QLineEdit.Normal if checked else QLineEdit.Password
        ))
        h_layout = QHBoxLayout()
        h_layout.setContentsMargins(0, 0, 0, 0)
        h_layout.setSpacing(2)
        h_layout.addWidget(entry)
        h_layout.addWidget(toggle_btn)
        container = QWidget()
        container.setLayout(h_layout)
        group_layout.addWidget(container, row, 1)

        api_desc = t("settings_editor.field_descriptions.api_key", self.lang)
        desc_lbl = QLabel(api_desc)
        desc_lbl.setStyleSheet(
            f"color: {DESCRIPTION_FG}; font-size: 11px; font-style: italic; "
            f"margin-bottom: 4px;"
        )
        desc_lbl.setWordWrap(True)
        group_layout.addWidget(desc_lbl, row + 1, 1, 1, 1)

        self.entries[(section, "api_key")] = entry

    def load_config(self):
        if os.path.exists(self.settings_file):
            self.config.read(self.settings_file, encoding="utf-8")

    def _ensure_sections(self):
        changed = False
        for section, keys in _SECTION_DEFAULTS.items():
            if not self.config.has_section(section):
                self.config.add_section(section)
            for key, default in keys.items():
                if not self.config.has_option(section, key):
                    self.config.set(section, key, default)
                    changed = True
        if changed:
            with open(self.settings_file, "w", encoding="utf-8") as f:
                self.config.write(f)

    def build_ui(self):
        self.setWindowTitle(t("settings_editor.title", self.lang))
        self.resize(800, 700)
        self.setMinimumSize(650, 400)
        self.setStyleSheet(BASE_STYLESHEET)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        sidebar = QWidget()
        sidebar.setFixedWidth(170)
        sidebar.setStyleSheet("background-color: #252525;")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(4, 8, 4, 8)

        self.section_list = QListWidget()
        self.section_list.setStyleSheet(
            "QListWidget { background: transparent; color: #e0e0e0; border: none; font-size: 12px; }"
            "QListWidget::item { padding: 8px 10px; border-radius: 3px; }"
            "QListWidget::item:selected { background-color: #0d7377; color: #ffffff; }"
            "QListWidget::item:hover { background-color: #3d3d3d; }"
        )
        sidebar_layout.addWidget(self.section_list)

        main_layout.addWidget(sidebar)

        right_panel = QVBoxLayout()
        right_panel.setContentsMargins(10, 10, 10, 10)
        right_panel.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        self._scroll.setWidget(content)
        content_layout = QVBoxLayout(content)

        self._section_widgets = {}
        section_items = []

        for section in self.config.sections():
            label = t(f"settings_editor.section_labels.{section}", self.lang)
            section_items.append((section, label))

            group = QGroupBox(label)
            group.setObjectName(f"section_{section}")
            self._section_widgets[section] = group
            group_layout = QGridLayout(group)
            group_layout.setColumnMinimumWidth(0, 140)
            group_layout.setColumnStretch(1, 1)
            group_layout.setVerticalSpacing(8)

            api_key_injected = False
            row = 0

            if section == "google":
                from setup_google import is_google_configured
                if not is_google_configured():
                    warn_text = t("settings_editor.warnings.google_not_configured", self.lang)
                    warn_lbl = QLabel(warn_text)
                    warn_lbl.setStyleSheet(
                        "color: #e74c3c; font-size: 12px; font-weight: bold; "
                        "padding: 8px; background-color: #3d1a1a; border-radius: 3px;"
                    )
                    warn_lbl.setWordWrap(True)
                    group_layout.addWidget(warn_lbl, 0, 0, 1, 2)
                    row = 2
                    self._google_disabled = True
                else:
                    self._google_disabled = False

            for i, key in enumerate(self.config.options(section)):
                if section == "ai" and key == "api_key":
                    continue
                if key in HIDDEN_KEYS:
                    continue

                field_label = t(f"settings_editor.field_labels.{key}", self.lang)
                lbl = QLabel(field_label)
                group_layout.addWidget(lbl, row, 0, Qt.AlignTop)

                if key == "language":
                    entry = QComboBox()
                    for lang_code in self._get_supported_languages():
                        entry.addItem(lang_code)
                    current_val = self.config.get(section, key)
                    idx = entry.findText(current_val)
                    if idx >= 0:
                        entry.setCurrentIndex(idx)
                    group_layout.addWidget(entry, row, 1)
                elif key in BOOLEAN_KEYS:
                    if key == "llama_autostart":
                        entry = QPushButton()
                        entry.setCheckable(True)
                        current_val = self.config.get(section, key, fallback="false")
                        entry.setChecked(current_val.lower() == "true")
                        self._update_llama_btn(entry)
                        entry.toggled.connect(lambda checked, b=entry: self._update_llama_btn(b))
                        cw = QWidget()
                        cw_layout = QHBoxLayout(cw)
                        cw_layout.setContentsMargins(0, 0, 0, 0)
                        cw_layout.setSpacing(6)
                        cw_layout.addWidget(entry)
                        start_btn = QPushButton(t("settings_editor.buttons.start_llama", self.lang))
                        start_btn.setFixedWidth(80)
                        start_btn.clicked.connect(self._start_llama_server)
                        cw_layout.addWidget(start_btn)
                        cw_layout.addStretch()
                        group_layout.addWidget(cw, row, 1)
                        entry = cw
                    else:
                        entry = QCheckBox()
                        current_val = self.config.get(section, key, fallback="false")
                        entry.setChecked(current_val.lower() == "true")
                        group_layout.addWidget(entry, row, 1)
                elif key in SLIDER_CONFIG:
                    cfg = SLIDER_CONFIG[key]
                    raw = float(self.config.get(section, key))
                    slider_val = int(round(raw / cfg["scale"]))
                    slider_val = max(cfg["min"], min(cfg["max"], slider_val))
                    slider = QSlider(Qt.Horizontal)
                    slider.setRange(cfg["min"], cfg["max"])
                    slider.setValue(slider_val)
                    slider.setTickPosition(QSlider.NoTicks)
                    val_lbl = QLabel(f"{slider_val * cfg['scale']:.3f}".rstrip("0").rstrip("."))
                    val_lbl.setFixedWidth(50)
                    val_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    slider.valueChanged.connect(
                        lambda v, lbl=val_lbl, s=cfg["scale"]: lbl.setText(
                            f"{v * s:.3f}".rstrip("0").rstrip(".")
                        )
                    )
                    entry = QWidget()
                    entry_layout = QHBoxLayout(entry)
                    entry_layout.setContentsMargins(0, 0, 0, 0)
                    entry_layout.setSpacing(6)
                    entry_layout.addWidget(slider, 1)
                    entry_layout.addWidget(val_lbl)
                    self._slider_widgets[(section, key)] = (slider, cfg["scale"])
                    group_layout.addWidget(entry, row, 1)
                elif key == "tts_engine":
                    entry = QComboBox()
                    entry.addItems(["kokoro"])
                    current_val = self.config.get(section, key)
                    idx = entry.findText(current_val)
                    if idx >= 0:
                        entry.setCurrentIndex(idx)
                    group_layout.addWidget(entry, row, 1)
                elif key in COMBO_OPTIONS:
                    entry = QComboBox()
                    options = COMBO_OPTIONS[key]
                    for val, label in options.items():
                        entry.addItem(label, val)
                    current_val = self.config.get(section, key)
                    idx = entry.findData(current_val)
                    if idx >= 0:
                        entry.setCurrentIndex(idx)
                    group_layout.addWidget(entry, row, 1)
                elif key in ("input_device", "output_device"):
                    entry = QComboBox()
                    entry.addItem(t("settings_editor.audio_default_device", self.lang), -1)
                    try:
                        import sounddevice as sd
                        kind = "input" if key == "input_device" else "output"
                        for d in sd.query_devices():
                            ch = d.get("max_input_channels" if kind == "input" else "max_output_channels", 0)
                            if ch > 0:
                                entry.addItem(f"{d['index']}: {d['name']}", d['index'])
                    except Exception:
                        pass
                    current_val = self.config.getint(section, key)
                    idx = entry.findData(current_val)
                    if idx >= 0:
                        entry.setCurrentIndex(idx)
                    group_layout.addWidget(entry, row, 1)
                elif key == "calendar_setup":
                    entry = QPushButton(t(f"settings_editor.field_labels.{key}", self.lang))
                    entry.setStyleSheet(
                        f"QPushButton {{ background-color: {BTN_BG}; color: {BTN_FG}; "
                        f"border: none; border-radius: 3px; padding: 8px 12px; "
                        f"font-weight: bold; }}"
                        "QPushButton:hover { background-color: #0d7377; }"
                    )
                    entry.clicked.connect(self._launch_google_setup)
                    group_layout.addWidget(entry, row, 1)
                else:
                    entry = QLineEdit()
                    entry.setText(self.config.get(section, key))
                    group_layout.addWidget(entry, row, 1)

                desc = t(f"settings_editor.field_descriptions.{key}", self.lang)
                desc_lbl = QLabel(desc)
                desc_lbl.setStyleSheet(
                    f"color: {DESCRIPTION_FG}; font-size: 11px; font-style: italic; "
                    f"margin-bottom: 4px;"
                )
                desc_lbl.setWordWrap(True)
                group_layout.addWidget(desc_lbl, row + 1, 1, 1, 1)

                if key == "mcp_server_url":
                    warn = t(f"settings_editor.field_descriptions.{key}_warning", self.lang)
                    warn_lbl = QLabel(warn)
                    warn_lbl.setStyleSheet("color: #e74c3c; font-size: 10px; font-style: italic; margin-bottom: 4px;")
                    warn_lbl.setWordWrap(True)
                    group_layout.addWidget(warn_lbl, row + 2, 1, 1, 1)
                    row += 1

                if key == "language":
                    entry.currentTextChanged.connect(
                        lambda new_lang, lbl=desc_lbl: lbl.setText(
                            t("settings_editor.field_descriptions.language", new_lang)
                        )
                    )

                self.entries[(section, key)] = entry

                if section == "ai" and key == "url" and not api_key_injected:
                    api_key_injected = True
                    row += 2
                    self._add_api_key_field(section, group_layout, row)

                row += 2

            if section == "google" and self._google_disabled:
                google_keys = ["calendar_enabled", "calendar_sync_enabled", "gmail_enabled", "google_home_enabled"]
                for gk in google_keys:
                    ge = self.entries.get((section, gk))
                    if ge is None:
                        continue
                    if isinstance(ge, QCheckBox):
                        ge.setEnabled(False)
                        ge.setChecked(False)
                    elif isinstance(ge, QWidget):
                        cb = ge.findChild(QCheckBox)
                        if cb:
                            cb.setEnabled(False)
                            cb.setChecked(False)

            content_layout.addWidget(group)

        for sec, label in section_items:
            item_text = label if label != sec else sec
            self.section_list.addItem(item_text)
        self.section_list.currentRowChanged.connect(self._on_section_selected)
        if self.section_list.count() > 0:
            self.section_list.setCurrentRow(0)

        right_panel.addWidget(self._scroll)

        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 5, 0, 0)
        btn_layout.addStretch()

        save_btn = QPushButton(t("settings_editor.buttons.save", self.lang))
        save_btn.clicked.connect(self.save)
        save_btn.setMinimumWidth(100)
        btn_layout.addWidget(save_btn)
        btn_layout.addSpacing(10)

        cancel_btn = QPushButton(t("settings_editor.buttons.cancel", self.lang))
        cancel_btn.clicked.connect(self.close)
        cancel_btn.setMinimumWidth(100)
        btn_layout.addWidget(cancel_btn)

        right_panel.addLayout(btn_layout)

        main_layout.addLayout(right_panel)

        QShortcut(QKeySequence("Ctrl+S"), self, self.save)

    def _on_section_selected(self, row):
        if row < 0:
            return
        section = list(self._section_widgets.keys())[row]
        group = self._section_widgets[section]
        self._scroll.ensureWidgetVisible(group, 0, 20)

    def _t(self, path):
        return t(path, self.lang)

    def save(self):
        err_title = self._t("settings_editor.dialog.error")
        for coord in (("gui", "x"), ("gui", "y")):
            entry = self.entries.get(coord)
            if entry:
                try:
                    val = int(entry.text())
                    if val < 0:
                        QMessageBox.critical(self, err_title,
                            self._t("settings_editor.errors.positive_number"))
                        return
                except ValueError:
                    QMessageBox.critical(self, err_title,
                        self._t("settings_editor.errors.positive_number"))
                    return

        w_entry = self.entries.get(("gui", "width"))
        h_entry = self.entries.get(("gui", "height"))
        try:
            if w_entry:
                w = int(w_entry.text())
                if w < 200 or w > 400:
                    QMessageBox.critical(self, err_title, self._t("settings_editor.errors.width_range"))
                    return
            if h_entry:
                h = int(h_entry.text())
                if h < 32 or h > 64:
                    QMessageBox.critical(self, err_title, self._t("settings_editor.errors.height_range"))
                    return
        except ValueError:
            pass

        lang_entry = self.entries.get(("locale", "language"))
        if lang_entry:
            lang = lang_entry.currentText()
            supported = self._get_supported_languages()
            if lang not in supported:
                QMessageBox.critical(self, err_title,
                    f"Lingua '{lang}' non supportata. Supportate: {', '.join(sorted(supported))}")
                return

        for res_key in ("cpu_max", "ram_max", "gpu_max", "vram_max"):
            entry = self.entries.get(("resources", res_key))
            if entry:
                try:
                    val = float(entry.text())
                    if val < 0 or val > 100:
                        QMessageBox.critical(self, err_title,
                            self._t("settings_editor.errors.pct_range").format(key=t(f"settings_editor.field_labels.{res_key}", self.lang)))
                        return
                except ValueError:
                    QMessageBox.critical(self, err_title,
                        self._t("settings_editor.errors.invalid_number"))
                    return

        timeout_entry = self.entries.get(("resources", "resource_timeout"))
        if timeout_entry:
            try:
                val = int(timeout_entry.text())
                if val < 0:
                    QMessageBox.critical(self, err_title,
                        self._t("settings_editor.errors.positive_number"))
                    return
            except ValueError:
                QMessageBox.critical(self, err_title,
                    self._t("settings_editor.errors.invalid_number"))
                return

        old_wakeword = None
        wakeword_entry = self.entries.get(("wakeword", "wakeword"))
        if wakeword_entry:
            old_wakeword = self.config.get("wakeword", "wakeword", fallback=None)

        for (section, key), entry in self.entries.items():
            if self._google_disabled and section == "google" and key in {"calendar_enabled", "calendar_sync_enabled", "gmail_enabled", "google_home_enabled"}:
                value = "false"
                self.config.set(section, key, value)
                continue
            if key == "calendar_setup":
                continue
            if (section, key) in self._slider_widgets:
                slider, scale = self._slider_widgets[(section, key)]
                value = f"{slider.value() * scale:.3f}".rstrip("0").rstrip(".")
            elif isinstance(entry, QComboBox):
                value = entry.currentData() if entry.currentData() is not None else entry.currentText()
                value = str(value)
            elif isinstance(entry, QCheckBox):
                value = "true" if entry.isChecked() else "false"
            elif isinstance(entry, QWidget) and key in BOOLEAN_KEYS:
                cb = entry.findChild(QCheckBox) or entry.findChild(QPushButton)
                if cb and hasattr(cb, 'isChecked'):
                    value = "true" if cb.isChecked() else "false"
                else:
                    value = "false"
            else:
                value = entry.text()

            if section == "ai" and key == "api_key":
                if value != self._original_api_key:
                    try:
                        import keyring
                        if value:
                            keyring.set_password("vass", "api_key", value)
                        else:
                            try:
                                keyring.delete_password("vass", "api_key")
                            except keyring.errors.PasswordDeleteError:
                                pass
                    except Exception:
                        pass
                continue
            else:
                self.config.set(section, key, value)

        with open(self.settings_file, "w", encoding="utf-8") as f:
            self.config.write(f)
        QMessageBox.information(self, self._t("settings_editor.dialog.info"),
                                self._t("settings_editor.errors.save_ok"))

        if old_wakeword is not None:
            new_val = wakeword_entry.currentText() if isinstance(wakeword_entry, QComboBox) else wakeword_entry.text()
            if new_val != old_wakeword:
                QMessageBox.warning(self, self._t("settings_editor.dialog.warning"),
                                   self._t("settings_editor.errors.restart_required"))
        self.close()


    def _update_llama_btn(self, btn):
        if btn.isChecked():
            btn.setText("🟢 " + t("settings_editor.buttons.llama_on", self.lang))
            btn.setStyleSheet(f"background-color: {BTN_BG}; color: #2ecc71; border: none; border-radius: 3px; padding: 4px 10px; font-weight: bold;")
        else:
            btn.setText("🔴 " + t("settings_editor.buttons.llama_off", self.lang))
            btn.setStyleSheet(f"background-color: {BTN_BG}; color: #e74c3c; border: none; border-radius: 3px; padding: 4px 10px; font-weight: bold;")

    def _launch_google_setup(self):
        import subprocess, os
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "setup_google.py")
        subprocess.Popen(["python", path, "--lang", self.lang])

    def _start_llama_server(self):
        from utils import start_llama_server
        path = self.config.get("llamacpp", "llama_server_path", fallback="").strip()
        if not path:
            QMessageBox.warning(self, "llama.cpp",
                self._t("settings_editor.errors.llama_no_path"))
            return
        cwd = self.config.get("llamacpp", "llama_server_working_directory", fallback="").strip()
        args = self.config.get("llamacpp", "llama_server_arguments", fallback="").strip()
        proc, status = start_llama_server(path, cwd, args)
        if status == "started":
            QMessageBox.information(self, "llama.cpp",
                self._t("settings_editor.errors.llama_started"))
        elif status == "already running":
            QMessageBox.information(self, "llama.cpp",
                self._t("settings_editor.errors.llama_already_running"))
        else:
            QMessageBox.warning(self, "llama.cpp",
                self._t("settings_editor.errors.llama_not_found").format(path=path))


if __name__ == "__main__":
    lang = "en"
    for i, a in enumerate(sys.argv[1:]):
        if a == "--lang" and i + 1 < len(sys.argv[1:]):
            lang = sys.argv[i + 2]
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    editor = SettingsEditor(language=lang)
    editor.show()
    sys.exit(app.exec())
