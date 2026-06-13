import json
import os
import re
import shutil
import sys
import uuid

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QListWidget, QGroupBox,
    QLineEdit, QMessageBox, QComboBox, QSpinBox, QFileDialog, QCheckBox,
)
from theme import (BG, FG, ENTRY_BG, ENTRY_FG, LABEL_FG, BTN_BG, BTN_FG,
                   SECTION_FG, FRAME_BORDER, BTN_DEL_BG, BTN_DEL_FG)

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
    padding: 5px 6px; font-size: 12px;
}}
QPushButton {{
    background-color: {BTN_BG}; color: {BTN_FG};
    border: none; border-radius: 3px; padding: 6px 12px;
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
    padding: 4px 6px;
}}
QComboBox QAbstractItemView {{
    background-color: #252525; color: {FG};
    selection-background-color: {BTN_BG};
}}
QSpinBox {{
    background-color: {ENTRY_BG}; color: {ENTRY_FG};
    border: 1px solid {FRAME_BORDER}; border-radius: 3px;
    padding: 3px 6px;
}}
"""

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALLOWED = os.path.join(BASE, "Allowed_root")

CATEGORIES = ["events", "schedules"]

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_RE = re.compile(r"^\d{2}:\d{2}$")
RECUR_RE = re.compile(r"^\d+[hdm]$")


def _load(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("events", data.get("schedules", []))
    except Exception:
        return []


def _save(path, items, key):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({key: items}, f, ensure_ascii=False, indent=2)
        f.write("\n")


class EventsEditor(QMainWindow):
    def __init__(self, language="en"):
        super().__init__()
        self.lang = language
        self._current_category = CATEGORIES[0]
        self._current_items = []
        self._build_ui()
        self._load_category()

    def _t(self, path):
        from i18n import t
        return t(path, self.lang)

    def _file_path(self):
        return os.path.join(ALLOWED, f"{self._current_category}.json")

    def _key(self):
        return self._current_category

    def _load_category(self):
        self._current_items = _load(self._file_path())
        self._clear_form()
        self._refresh_list()

    def _refresh_list(self):
        self.list_widget.clear()
        for item in self._current_items:
            desc = item.get("description", "")
            date = item.get("date", "")
            time_str = item.get("time", "")
            line = f"{date} {time_str}  —  {desc}"
            if self._current_category == "events" and item.get("recur"):
                line += f" [{item['recur']}]"
            self.list_widget.addItem(line)
        if self._current_items:
            self.list_widget.setCurrentRow(0)
            self._on_select(0)

    def _clear_form(self):
        self.date_edit.clear()
        self.time_edit.clear()
        self.dur_spin.setValue(60)
        self.desc_edit.clear()
        self.recur_edit.clear()
        self.cmd_edit.clear()
        self.args_edit.clear()
        self.workdir_edit.clear()

    def _build_ui(self):
        self.setWindowTitle(self._t("events_editor.title"))
        self.resize(750, 500)
        self.setMinimumSize(550, 360)
        self.setStyleSheet(BASE_STYLESHEET)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        top_row = QHBoxLayout()
        top_row.addWidget(QLabel(self._t("events_editor.categories_label") + ":"))
        self.cat_combo = QComboBox()
        self.cat_combo.addItem(self._t("events_editor.categories.events"), "events")
        self.cat_combo.addItem(self._t("events_editor.categories.schedules"), "schedules")
        self.cat_combo.currentIndexChanged.connect(self._on_cat_change)
        top_row.addWidget(self.cat_combo)
        top_row.addStretch()
        layout.addLayout(top_row)

        list_group = QGroupBox(self._t("events_editor.list_label"))
        list_layout = QVBoxLayout(list_group)

        self.list_widget = QListWidget()
        self.list_widget.currentRowChanged.connect(self._on_select)
        list_layout.addWidget(self.list_widget)
        layout.addWidget(list_group, 1)

        form_group = QGroupBox(self._t("events_editor.form_label"))
        form_grid = QVBoxLayout(form_group)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel(self._t("events_editor.fields.date")))
        self.date_edit = QLineEdit()
        self.date_edit.setPlaceholderText("YYYY-MM-DD")
        row1.addWidget(self.date_edit)
        row1.addWidget(QLabel(self._t("events_editor.fields.time")))
        self.time_edit = QLineEdit()
        self.time_edit.setPlaceholderText("HH:MM")
        row1.addWidget(self.time_edit)
        row1.addWidget(QLabel(self._t("events_editor.fields.duration")))
        self.dur_spin = QSpinBox()
        self.dur_spin.setRange(1, 1440)
        self.dur_spin.setValue(60)
        row1.addWidget(self.dur_spin)
        form_grid.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel(self._t("events_editor.fields.description")))
        self.desc_edit = QLineEdit()
        row2.addWidget(self.desc_edit)
        form_grid.addLayout(row2)

        row_cmd = QHBoxLayout()
        self._cmd_label = QLabel(self._t("events_editor.fields.command"))
        row_cmd.addWidget(self._cmd_label)
        self.cmd_edit = QLineEdit()
        self.cmd_edit.setPlaceholderText("python")
        row_cmd.addWidget(self.cmd_edit)
        self._btn_cmd_browse = QPushButton("...")
        self._btn_cmd_browse.setFixedWidth(28)
        self._btn_cmd_browse.clicked.connect(self._browse_command)
        row_cmd.addWidget(self._btn_cmd_browse)
        form_grid.addLayout(row_cmd)

        row3 = QHBoxLayout()
        self._args_label = QLabel(self._t("events_editor.fields.arguments"))
        row3.addWidget(self._args_label)
        self.args_edit = QLineEdit()
        self.args_edit.setPlaceholderText('-c "print(1)"')
        row3.addWidget(self.args_edit)
        self._workdir_label = QLabel(self._t("events_editor.fields.workingdir"))
        row3.addWidget(self._workdir_label)
        self.workdir_edit = QLineEdit()
        self.workdir_edit.setPlaceholderText("C:\\...")
        row3.addWidget(self.workdir_edit)
        self._btn_wd_browse = QPushButton("...")
        self._btn_wd_browse.setFixedWidth(28)
        self._btn_wd_browse.clicked.connect(self._browse_workdir)
        row3.addWidget(self._btn_wd_browse)
        form_grid.addLayout(row3)

        row_recur = QHBoxLayout()
        self._recur_label = QLabel(self._t("events_editor.fields.recur"))
        row_recur.addWidget(self._recur_label)
        self.recur_edit = QLineEdit()
        self.recur_edit.setPlaceholderText("1d / 7d / 2h ...")
        row_recur.addWidget(self.recur_edit)
        self._enabled_cb = QCheckBox(self._t("events_editor.fields.enabled"))
        self._enabled_cb.setChecked(True)
        self._enabled_cb.setStyleSheet(f"color: {LABEL_FG};")
        row_recur.addWidget(self._enabled_cb)
        row_recur.addStretch()
        form_grid.addLayout(row_recur)
        layout.addWidget(form_group)

        self._toggle_fields()

        btn_row = QHBoxLayout()
        btn_add = QPushButton(self._t("events_editor.buttons.add"))
        btn_add.clicked.connect(self._add_item)
        btn_row.addWidget(btn_add)

        btn_upd = QPushButton(self._t("events_editor.buttons.update"))
        btn_upd.clicked.connect(self._update_item)
        btn_row.addWidget(btn_upd)

        btn_del = QPushButton(self._t("events_editor.buttons.delete"))
        btn_del.setStyleSheet(f"background-color: {BTN_DEL_BG}; color: {BTN_DEL_FG};")
        btn_del.clicked.connect(self._delete_item)
        btn_row.addWidget(btn_del)

        btn_row.addStretch()
        layout.addLayout(btn_row)

    def closeEvent(self, event):
        self._do_save()
        event.accept()

    def _toggle_fields(self):
        is_schedule = self._current_category == "schedules"
        self._cmd_label.setVisible(is_schedule)
        self.cmd_edit.setVisible(is_schedule)
        self._btn_cmd_browse.setVisible(is_schedule)
        self._args_label.setVisible(is_schedule)
        self.args_edit.setVisible(is_schedule)
        self._workdir_label.setVisible(is_schedule)
        self.workdir_edit.setVisible(is_schedule)
        self._btn_wd_browse.setVisible(is_schedule)

    def _on_cat_change(self, idx):
        data = self.cat_combo.currentData()
        if data and data != self._current_category:
            self._do_save()
            self._current_category = data
            self._toggle_fields()
            self._load_category()

    def _browse_command(self):
        path, _ = QFileDialog.getOpenFileName(self, self._t("events_editor.dialog.select_command"),
            "", "Eseguibili (*.exe *.bat *.ps1 *.py *.cmd *.vbs *.vass);;Tutti i file (*.*)")
        if path:
            self.cmd_edit.setText(path)

    def _browse_workdir(self):
        path = QFileDialog.getExistingDirectory(self, self._t("events_editor.dialog.select_workdir"))
        if path:
            self.workdir_edit.setText(path)

    def _on_select(self, row):
        if 0 <= row < len(self._current_items):
            item = self._current_items[row]
            self.date_edit.setText(item.get("date", ""))
            self.time_edit.setText(item.get("time", ""))
            self.dur_spin.setValue(int(item.get("duration", 60) or 60))
            self.desc_edit.setText(item.get("description", ""))
            self.recur_edit.setText(item.get("recur", ""))
            self.cmd_edit.setText(item.get("command", ""))
            self.args_edit.setText(item.get("arguments", ""))
            self.workdir_edit.setText(item.get("workingdir", ""))
            enabled = item.get("enabled", "true")
            self._enabled_cb.setChecked(enabled.lower() != "false")

    def _validate(self):
        date = self.date_edit.text().strip()
        time_str = self.time_edit.text().strip()
        desc = self.desc_edit.text().strip()
        recur = self.recur_edit.text().strip()

        if not desc:
            QMessageBox.warning(self, self._t("events_editor.dialog.error"), self._t("events_editor.errors.required"))
            return False
        if not DATE_RE.match(date):
            QMessageBox.warning(self, self._t("events_editor.dialog.error"), self._t("events_editor.errors.date_format"))
            return False
        if not TIME_RE.match(time_str):
            QMessageBox.warning(self, self._t("events_editor.dialog.error"), self._t("events_editor.errors.time_format"))
            return False
        if recur and not RECUR_RE.match(recur):
            QMessageBox.warning(self, self._t("events_editor.dialog.error"), self._t("events_editor.errors.recur_format"))
            return False

        from datetime import datetime
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            QMessageBox.warning(self, self._t("events_editor.dialog.error"), self._t("events_editor.errors.date_format"))
            return False
        try:
            h, m = map(int, time_str.split(":"))
            if h < 0 or h > 23 or m < 0 or m > 59:
                raise ValueError
        except ValueError:
            QMessageBox.warning(self, self._t("events_editor.dialog.error"), self._t("events_editor.errors.time_format"))
            return False

        if self._current_category == "schedules":
            cmd = self.cmd_edit.text().strip()
            if not cmd:
                QMessageBox.warning(self, self._t("events_editor.dialog.error"), self._t("events_editor.errors.required"))
                return False
            exe = cmd.split()[0]
            if not shutil.which(exe) and not os.path.exists(exe):
                # Allow .vass scripts as commands
                vass_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", f"{exe}.vass")
                if not os.path.exists(vass_path) and not cmd.lower().endswith(".vass"):
                    QMessageBox.warning(self, self._t("events_editor.dialog.error"),
                        self._t("events_editor.errors.command_not_found").replace("{cmd}", exe))
                    return False

            wd = self.workdir_edit.text().strip()
            if wd:
                if not os.path.isdir(wd):
                    QMessageBox.warning(self, self._t("events_editor.dialog.error"),
                        self._t("events_editor.errors.workingdir_not_found").replace("{dir}", wd))
                    return False
                if self._is_system_dir(wd):
                    QMessageBox.warning(self, self._t("events_editor.dialog.error"),
                        self._t("events_editor.errors.workingdir_system").replace("{dir}", wd))
                    return False

        return True

    def _is_system_dir(self, path):
        p = os.path.abspath(path).lower().rstrip(os.sep)
        if sys.platform == "win32":
            system_roots = [
                os.path.abspath("C:\\Windows").lower(),
                os.path.abspath("C:\\Windows\\System32").lower(),
                os.path.abspath("C:\\Program Files").lower(),
                os.path.abspath("C:\\Program Files (x86)").lower(),
            ]
            for sr in system_roots:
                if p == sr or p.startswith(sr + "\\"):
                    return True
        else:
            protected = {"/bin", "/boot", "/dev", "/etc", "/lib", "/proc", "/root", "/sbin", "/sys", "/usr", "/var", "/System", "/Library", "/private"}
            for pr in protected:
                if p == pr or p.startswith(pr + "/"):
                    return True
        return False

    def _build_item(self, existing=None):
        item = {
            "date": self.date_edit.text().strip(),
            "time": self.time_edit.text().strip(),
            "duration": self.dur_spin.value(),
            "description": self.desc_edit.text().strip(),
        }
        if existing and "id" in existing:
            item["id"] = existing["id"]
        else:
            item["id"] = uuid.uuid4().hex[:8]
        recur = self.recur_edit.text().strip()
        if recur:
            item["recur"] = recur
        if self._current_category == "schedules":
            item["command"] = self.cmd_edit.text().strip()
            args = self.args_edit.text().strip()
            if args:
                item["arguments"] = args
            wd = self.workdir_edit.text().strip()
            if wd:
                item["workingdir"] = wd
        item["enabled"] = "true" if self._enabled_cb.isChecked() else "false"
        desc = self.desc_edit.text().strip()
        date = self.date_edit.text().strip()
        time_str = self.time_edit.text().strip()
        item["name"] = f"{desc}_{date}_{time_str}".replace(" ", "_").lower()
        return item

    def _add_item(self):
        if not self._validate():
            return
        self._current_items.append(self._build_item())
        self._refresh_list()
        self.list_widget.setCurrentRow(len(self._current_items) - 1)

    def _update_item(self):
        row = self.list_widget.currentRow()
        if row < 0:
            return
        if not self._validate():
            return
        self._current_items[row] = self._build_item(existing=self._current_items[row])
        self._refresh_list()
        self.list_widget.setCurrentRow(row)

    def _delete_item(self):
        row = self.list_widget.currentRow()
        if row < 0:
            return
        del self._current_items[row]
        self._refresh_list()

    def _do_save(self):
        _save(self._file_path(), self._current_items, self._key())

    def _save_file(self):
        self._do_save()
        QMessageBox.information(self, "OK", self._t("events_editor.saved"))


def main():
    lang = "en"
    for i, a in enumerate(sys.argv[1:]):
        if a == "--lang" and i + 1 < len(sys.argv[1:]):
            lang = sys.argv[i + 2]

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    editor = EventsEditor(language=lang)
    editor.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
