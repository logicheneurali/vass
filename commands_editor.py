import configparser
import os
import sys
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QListWidget, QComboBox,
    QGroupBox, QMessageBox
)
from PySide6.QtGui import QKeySequence, QShortcut
from i18n import t
from theme import (BG, FG, ENTRY_BG, ENTRY_FG, LABEL_FG, BTN_BG, BTN_FG,
                   SECTION_FG, DESCRIPTION_FG, FRAME_BORDER, BTN_DEL_BG, BTN_DEL_FG)

BASE_STYLESHEET = f"""
QMainWindow, QWidget {{ background-color: {BG}; color: {FG}; font-size: 12px; }}
QGroupBox {{
    font-weight: bold; color: {SECTION_FG};
    border: 1px solid {FRAME_BORDER}; border-radius: 4px;
    margin-top: 10px; padding-top: 14px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 6px;
}}
QLabel {{ color: {LABEL_FG}; }}
QLineEdit {{
    background-color: {ENTRY_BG}; color: {ENTRY_FG};
    border: 1px solid {FRAME_BORDER}; border-radius: 3px;
    padding: 5px 6px;
}}
QLineEdit:focus {{ border-color: {BTN_BG}; }}
QPushButton {{
    border: none; border-radius: 3px; padding: 6px 18px;
    font-weight: bold;
}}
QPushButton:hover {{ background-color: #0a5c5e; }}
QPushButton:pressed {{ background-color: #085052; }}
QListWidget {{
    background-color: #252525; color: {FG};
    border: 1px solid {FRAME_BORDER}; border-radius: 3px;
    outline: none;
}}
QListWidget::item:selected {{
    background-color: {BTN_BG}; color: {FG};
}}
QComboBox {{
    background-color: {ENTRY_BG}; color: {ENTRY_FG};
    border: 1px solid {FRAME_BORDER}; border-radius: 3px;
    padding: 5px 6px;
}}
QComboBox::drop-down {{
    border: none; width: 20px;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid #888888;
    margin-right: 6px;
}}
QComboBox:hover {{ border-color: {BTN_BG}; }}
QComboBox QAbstractItemView {{
    background-color: {ENTRY_BG}; color: {ENTRY_FG};
    selection-background-color: {BTN_BG};
    border: 1px solid {FRAME_BORDER};
}}
"""


class CommandsEditor(QMainWindow):
    def __init__(self, commands_file=None, language="en"):
        super().__init__()
        self.lang = language
        if commands_file is None:
            self.commands_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "commands.ini")
        else:
            self.commands_file = commands_file
        self.config = configparser.ConfigParser()
        self.load_config()
        self.entries = []
        self.selected_index = None
        self.build_ui()

    def _t(self, path):
        return t(path, self.lang)

    def load_config(self):
        if os.path.exists(self.commands_file):
            self.config.read(self.commands_file)

    def rebuild_entries(self):
        self.entries = []
        for section in self.config.sections():
            for key, value in self.config.items(section):
                self.entries.append((section, key, value))
        self.entries.sort(key=lambda e: (e[0], e[1]))

    def build_ui(self):
        self.setWindowTitle(self._t("commands_editor.title"))
        self.resize(750, 500)
        self.setMinimumSize(700, 450)
        self.setStyleSheet(BASE_STYLESHEET)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # --- Left: list ---
        left_group = QGroupBox(self._t("commands_editor.list_label"))
        left_layout = QVBoxLayout(left_group)

        self.list_widget = QListWidget()
        self.list_widget.currentRowChanged.connect(self.on_select)
        left_layout.addWidget(self.list_widget)

        layout.addWidget(left_group, 1)

        # --- Right: form ---
        right_group = QGroupBox(self._t("commands_editor.form_label"))
        right_group.setFixedWidth(380)
        right_layout = QVBoxLayout(right_group)
        right_layout.setSpacing(6)

        sec_lbl = QLabel(self._t("commands_editor.section_label"))
        right_layout.addWidget(sec_lbl)

        self.section_combo = QComboBox()
        self.section_combo.addItems(["general", "system"])
        right_layout.addWidget(self.section_combo)

        kw_lbl = QLabel(self._t("commands_editor.keyword_label"))
        right_layout.addWidget(kw_lbl)

        self.keyword_entry = QLineEdit()
        right_layout.addWidget(self.keyword_entry)

        cmd_lbl = QLabel(self._t("commands_editor.command_label"))
        right_layout.addWidget(cmd_lbl)

        self.command_entry = QLineEdit()
        right_layout.addWidget(self.command_entry)

        cmd_desc = QLabel(self._t("commands_editor.command_desc"))
        cmd_desc.setStyleSheet(f"color: {DESCRIPTION_FG}; font-size: 11px; font-style: italic;")
        right_layout.addWidget(cmd_desc)

        right_layout.addSpacing(8)

        btn_row = QHBoxLayout()
        self.add_btn = QPushButton(self._t("commands_editor.buttons.add"))
        self.add_btn.setStyleSheet(f"background-color: {BTN_BG}; color: {BTN_FG};")
        self.add_btn.clicked.connect(self.add_command)
        btn_row.addWidget(self.add_btn)

        self.update_btn = QPushButton(self._t("commands_editor.buttons.update"))
        self.update_btn.setStyleSheet(f"background-color: {BTN_BG}; color: {BTN_FG};")
        self.update_btn.clicked.connect(self.update_command)
        btn_row.addWidget(self.update_btn)

        self.delete_btn = QPushButton(self._t("commands_editor.buttons.delete"))
        self.delete_btn.setStyleSheet(f"background-color: {BTN_DEL_BG}; color: {BTN_DEL_FG};")
        self.delete_btn.clicked.connect(self.delete_command)
        btn_row.addStretch()
        btn_row.addWidget(self.delete_btn)

        right_layout.addLayout(btn_row)

        cancel_btn = QPushButton(self._t("commands_editor.buttons.cancel"))
        cancel_btn.setStyleSheet(f"background-color: {BTN_BG}; color: {BTN_FG};")
        cancel_btn.clicked.connect(self.clear_form)
        right_layout.addWidget(cancel_btn)

        right_layout.addStretch()

        layout.addWidget(right_group)

        self.rebuild_entries()
        self.refresh_listbox()

        QShortcut(QKeySequence("Ctrl+S"), self, self.save_file)

    def refresh_listbox(self):
        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        for section, key, value in self.entries:
            display = f"[{section}] {key}  \u2192  {value[:60]}{'\u2026' if len(value) > 60 else ''}"
            self.list_widget.addItem(display)
        self.list_widget.blockSignals(False)

    def on_select(self, row):
        if row < 0 or row >= len(self.entries):
            return
        self.selected_index = row
        section, key, value = self.entries[row]
        self.section_combo.setCurrentText(section)
        self.keyword_entry.setText(key)
        self.command_entry.setText(value)

    def clear_form(self):
        self.selected_index = None
        self.list_widget.clearSelection()
        self.section_combo.setCurrentIndex(0)
        self.keyword_entry.clear()
        self.command_entry.clear()

    def validate(self):
        err = self._t("commands_editor.dialog.error")
        keyword = self.keyword_entry.text().strip()
        command = self.command_entry.text().strip()
        if not keyword:
            QMessageBox.critical(self, err, self._t("commands_editor.errors.keyword_empty"))
            return False
        if not command:
            QMessageBox.critical(self, err, self._t("commands_editor.errors.command_empty"))
            return False
        return True

    def add_command(self):
        if not self.validate():
            return
        keyword = self.keyword_entry.text().strip()
        command = self.command_entry.text().strip()
        section = self.section_combo.currentText()

        for s, k, v in self.entries:
            if k.lower() == keyword.lower():
                msg = self._t("commands_editor.errors.keyword_exists").replace("{keyword}", keyword)
                QMessageBox.critical(self, self._t("commands_editor.dialog.error"), msg)
                return

        if section not in self.config:
            self.config[section] = {}
        self.config.set(section, keyword, command)
        self.rebuild_entries()
        self.refresh_listbox()
        self.clear_form()

    def update_command(self):
        err = self._t("commands_editor.dialog.error")
        if self.selected_index is None:
            QMessageBox.critical(self, err, self._t("commands_editor.errors.select_first"))
            return
        if not self.validate():
            return

        old_section, old_keyword, old_value = self.entries[self.selected_index]
        new_section = self.section_combo.currentText()
        new_keyword = self.keyword_entry.text().strip()
        new_command = self.command_entry.text().strip()

        for idx, (s, k, v) in enumerate(self.entries):
            if idx != self.selected_index and k.lower() == new_keyword.lower():
                msg = self._t("commands_editor.errors.keyword_exists").replace("{keyword}", new_keyword)
                QMessageBox.critical(self, err, msg)
                return

        self.config.remove_option(old_section, old_keyword)
        if new_section not in self.config:
            self.config[new_section] = {}
        self.config.set(new_section, new_keyword, new_command)
        self.rebuild_entries()
        self.refresh_listbox()
        self.clear_form()

    def delete_command(self):
        err = self._t("commands_editor.dialog.error")
        if self.selected_index is None:
            QMessageBox.critical(self, err, self._t("commands_editor.errors.select_first"))
            return
        section, key, value = self.entries[self.selected_index]
        confirm_title = self._t("commands_editor.confirm.title")
        confirm_msg = self._t("commands_editor.confirm.delete").replace("{key}", key)
        if not QMessageBox.question(self, confirm_title, confirm_msg,
                                     QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            return
        self.config.remove_option(section, key)
        self.rebuild_entries()
        self.refresh_listbox()
        self.clear_form()

    def save_file(self):
        with open(self.commands_file, "w", encoding="utf-8") as f:
            self.config.write(f)

    def closeEvent(self, event):
        self.save_file()
        event.accept()


if __name__ == "__main__":
    lang = "en"
    for i, a in enumerate(sys.argv[1:]):
        if a == "--lang" and i + 1 < len(sys.argv[1:]):
            lang = sys.argv[i + 2]
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    editor = CommandsEditor(language=lang)
    editor.show()
    sys.exit(app.exec())
