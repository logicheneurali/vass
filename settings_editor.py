import configparser
import os
import sys
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
    QGroupBox, QMessageBox, QComboBox, QSlider, QCheckBox
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

BOOLEAN_KEYS = {"llama_autostart"}

SLIDER_CONFIG = {
    "sensitivity": {"min": 1, "max": 20, "scale": 0.001, "default": 5},
    "similarity":  {"min": 0, "max": 100, "scale": 0.01, "default": 60},
}



class SettingsEditor(QMainWindow):
    def __init__(self, settings_file=None, language="en"):
        super().__init__()
        self.lang = language
        if settings_file is None:
            self.settings_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.ini")
        else:
            self.settings_file = settings_file
        self.config = configparser.ConfigParser()
        self.load_config()
        self.entries = {}
        self._slider_widgets = {}
        self._original_api_key = self._load_original_api_key()
        self.build_ui()

    def _get_supported_languages(self):
        supported = []
        locales_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "locales")
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
            self.config.read(self.settings_file)

    def build_ui(self):
        self.setWindowTitle(t("settings_editor.title", self.lang))
        self.resize(620, 700)
        self.setMinimumSize(520, 400)
        self.setStyleSheet(BASE_STYLESHEET)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(10, 10, 10, 10)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        scroll.setWidget(content)
        content_layout = QVBoxLayout(content)

        for section in self.config.sections():
            label = t(f"settings_editor.section_labels.{section}", self.lang)
            group = QGroupBox(label)
            group_layout = QGridLayout(group)
            group_layout.setColumnMinimumWidth(0, 140)
            group_layout.setColumnStretch(1, 1)
            group_layout.setVerticalSpacing(8)

            api_key_injected = False
            row = 0
            for i, key in enumerate(self.config.options(section)):
                if section == "ai" and key == "api_key":
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

            content_layout.addWidget(group)

        layout.addWidget(scroll)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        save_btn = QPushButton(t("settings_editor.buttons.save", self.lang))
        save_btn.clicked.connect(self.save)
        save_btn.setMinimumWidth(100)
        btn_layout.addWidget(save_btn)

        cancel_btn = QPushButton(t("settings_editor.buttons.cancel", self.lang))
        cancel_btn.clicked.connect(self.close)
        cancel_btn.setMinimumWidth(100)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)

        QShortcut(QKeySequence("Ctrl+S"), self, self.save)

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
            if (section, key) in self._slider_widgets:
                slider, scale = self._slider_widgets[(section, key)]
                value = f"{slider.value() * scale:.3f}".rstrip("0").rstrip(".")
            elif isinstance(entry, QComboBox):
                value = entry.currentText()
            elif isinstance(entry, QCheckBox):
                value = "true" if entry.isChecked() else "false"
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
