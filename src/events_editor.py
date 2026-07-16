import copy
import json
import os
import re
import shutil
import sys
import uuid
from utils import get_project_root, get_path

from PySide6.QtCore import Qt, QDate, QRectF, QPoint
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QListWidget, QGroupBox,
    QLineEdit, QMessageBox, QComboBox, QSpinBox, QFileDialog, QCheckBox,
    QCalendarWidget, QListWidgetItem,
)
from PySide6.QtGui import QTextCharFormat, QColor, QFont, QPen, QPalette
from theme import (BG, FG, ENTRY_BG, ENTRY_FG, LABEL_FG, BTN_BG, BTN_FG,
                   SECTION_FG, FRAME_BORDER, BTN_DEL_BG, BTN_DEL_FG, BASE_STYLESHEET)

STYLESHEET = BASE_STYLESHEET + f"""
QSpinBox {{
    background-color: {ENTRY_BG}; color: {ENTRY_FG};
    border: 1px solid {FRAME_BORDER}; border-radius: 3px;
    padding: 3px 6px;
}}
"""

BASE = get_project_root()
ALLOWED = os.path.join(BASE, "Allowed_root")

CATEGORIES = ["events", "schedules"]

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_RE = re.compile(r"^\d{2}:\d{2}$")
RECUR_RE = re.compile(r"^\d+[mhdwM]$")


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


class CalendarWidget(QCalendarWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._event_dates = {}      # date_str -> count (active)
        self._inactive_dates = {}   # date_str -> count (disabled)
        pal = self.palette()
        pal.setColor(QPalette.Highlight, QColor(0, 0, 0, 0))
        pal.setColor(QPalette.HighlightedText, QColor("#ffffff"))
        self.setPalette(pal)

    def set_event_dates(self, dates, inactive=None):
        self._event_dates = dates
        self._inactive_dates = inactive or {}
        self.updateCells()

    def paintCell(self, painter, rect, date):
        super().paintCell(painter, rect, date)
        dkey = date.toString("yyyy-MM-dd")
        active_count = self._event_dates.get(dkey, 0)
        inactive_count = self._inactive_dates.get(dkey, 0)

        if active_count > 0 or inactive_count > 0:
            painter.save()
            painter.setPen(Qt.NoPen)
            tri_size = 8
            x = rect.left()
            y = rect.top()
            color = QColor("#0d7377") if active_count > 0 else QColor("#666666")
            painter.setBrush(color)
            triangle = [QPoint(x, y), QPoint(x + tri_size, y), QPoint(x, y + tri_size)]
            painter.drawPolygon(triangle)
            painter.restore()

        # Current day: small red triangle bottom-right
        if date == QDate.currentDate():
            painter.save()
            painter.setBrush(QColor("#e94560"))
            painter.setPen(Qt.NoPen)
            tri_size = 8
            x = rect.right() - tri_size
            y = rect.bottom() - tri_size
            triangle = [QPoint(x, rect.bottom()), QPoint(rect.right(), y), QPoint(rect.right(), rect.bottom())]
            painter.drawPolygon(triangle)
            painter.restore()
        # Selected day: white border
        if date == self.selectedDate():
            painter.save()
            pen = QPen(QColor("#ffffff"), 1)
            painter.setPen(pen)
            painter.drawRect(QRectF(rect).adjusted(1.5, 1.5, -1.5, -1.5))
            painter.restore()
        # Event dots
        if inactive_count > 0 or active_count > 0:
            max_cols = 6
            max_rows = 3
            ds = 3
            gap = 1
            step = ds + gap
            painter.save()
            # Gray dots (inactive) — right side
            for i in range(min(inactive_count, max_cols * max_rows)):
                col = i % max_cols
                row = i // max_cols
                x = int(rect.right()) - (col + 1) * step - 2
                y = int(rect.bottom()) - (max_rows - row) * step + gap - 2
                painter.fillRect(QRectF(x, y, ds, ds), QColor("#666666"))
            # Red dots (active) — left of gray, or right-aligned if no gray
            offset = min(inactive_count, max_cols * max_rows)
            total_active = min(active_count, max_cols * max_rows)
            for i in range(total_active):
                idx = offset + i
                col = idx % max_cols
                row = idx // max_cols
                if row >= max_rows:
                    break
                x = int(rect.right()) - (col + 1) * step - 2
                y = int(rect.bottom()) - (max_rows - row) * step + gap - 2
                painter.fillRect(QRectF(x, y, ds, ds), QColor("#e94560"))
            if active_count + inactive_count > max_cols * max_rows:
                painter.setPen(QColor("#e94560"))
                painter.setFont(QFont(painter.font().family(), 6))
                px = int(rect.right()) - 10
                py = int(rect.bottom()) - 6
                painter.drawText(QRectF(px - 8, py - 8, 14, 10), Qt.AlignCenter, "+")
            painter.restore()


class EventsEditor(QMainWindow):
    def __init__(self, language="en"):
        super().__init__()
        self.lang = language
        self._current_category = CATEGORIES[0]
        self._current_items = []
        self._items_snapshot = []
        self._selected_idx = None
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
        self._items_snapshot = copy.deepcopy(self._current_items)
        self._clear_form()
        self._refresh_list()

    def _refresh_list(self):
        self._highlight_calendar()
        self.day_list.blockSignals(True)
        self.day_list.clear()
        selected_date = self.calendar.selectedDate().toString("yyyy-MM-dd")
        lines = []  # (time_str_for_sort, line, idx, is_future, is_disabled, [orig_date_for_recurrence])
        for i, item in enumerate(self._current_items):
            is_disabled = str(item.get("enabled", "true")).lower() == "false"
            if item.get("date") == selected_date:
                time_str = item.get("time", "")
                desc = item.get("description", "")
                line = f"{time_str}  \u2014  {desc}"
                if item.get("recur"):
                    line += f" [\u21bb {item['recur']}]"
                lines.append((time_str, line, i, False, is_disabled))
            # Future recurrences
            recur = item.get("recur", "")
            if recur and item.get("date", "") <= selected_date and item.get("date") != selected_date:
                from utils import generate_recurrences
                for fd, ft in generate_recurrences(item.get("date", ""), item.get("time", "00:00"), recur, selected_date):
                    if fd == selected_date:
                        desc = item.get("description", "")
                        line = f"\u21bb {ft}  \u2014  {desc} [\u21bb {recur}]"
                        lines.append((ft, line, -1, True, is_disabled, item.get("date", "")))
                        break
        lines.sort(key=lambda x: x[0])
        for time_sort, line, idx, is_future, is_disabled, *rest in lines:
            orig_date = rest[0] if rest else ""
            li = QListWidgetItem()
            li.setData(Qt.UserRole, idx)
            if is_disabled:
                li.setForeground(QColor("#e67e22"))
            if is_future:
                if not is_disabled:
                    li.setForeground(QColor("#666666"))
                li.setFlags(Qt.ItemNeverHasChildren)
                w = QWidget()
                wr = QHBoxLayout(w)
                wr.setContentsMargins(2, 1, 2, 1)
                wr.setSpacing(4)
                lbl = QLabel(line)
                lbl.setStyleSheet("background:transparent;")
                f = lbl.font()
                f.setItalic(True)
                lbl.setFont(f)
                if is_disabled:
                    lbl.setStyleSheet("color:#e67e22;background:transparent;")
                elif orig_date:
                    lbl.setStyleSheet("color:#666666;background:transparent;")
                wr.addWidget(lbl)
                wr.addStretch()
                if orig_date:
                    lnk = QPushButton("\u2197")
                    lnk.setFixedSize(20, 18)
                    lnk.setFlat(True)
                    lnk.setCursor(Qt.CursorShape.PointingHandCursor)
                    lnk.setStyleSheet("QPushButton{color:#0d7377;font-size:12px;padding:0;border:none;}QPushButton:hover{color:#e0e0e0;}")
                    lnk.setToolTip(self._t("events_editor.go_to_date"))
                    lnk.clicked.connect(lambda checked, d=orig_date: self._navigate_to_date(d))
                    wr.addWidget(lnk)
                li.setSizeHint(w.sizeHint())
                self.day_list.addItem(li)
                self.day_list.setItemWidget(li, w)
            else:
                li.setText(line)
                self.day_list.addItem(li)
        self.day_list.blockSignals(False)
        if lines:
            self.day_list.setCurrentRow(0)
        else:
            self._clear_form()
            self.date_edit.setText(selected_date)

    def _highlight_calendar(self):
        event_fmt = QTextCharFormat()
        event_fmt.setFontWeight(QFont.Weight.Bold)
        event_fmt.setForeground(QColor("#ffffff"))
        year = self.calendar.yearShown()
        month = self.calendar.monthShown()
        days_in = QDate(year, month, 1).daysInMonth()
        for day in range(1, days_in + 1):
            self.calendar.setDateTextFormat(QDate(year, month, day), QTextCharFormat())
        active_counts = {}
        inactive_counts = {}
        month_start = QDate(year, month, 1).toString("yyyy-MM-dd")
        month_end = QDate(year, month, days_in).toString("yyyy-MM-dd")
        for item in self._current_items:
            date_str = item.get("date", "")
            is_active = str(item.get("enabled", "true")).lower() != "false"
            target = active_counts if is_active else inactive_counts
            if DATE_RE.match(date_str):
                y, m, d = map(int, date_str.split("-"))
                qd = QDate(y, m, d)
                self.calendar.setDateTextFormat(qd, event_fmt)
                target[date_str] = target.get(date_str, 0) + 1
            recur = item.get("recur", "")
            if recur and date_str:
                from utils import generate_recurrences
                for fd, _ in generate_recurrences(date_str, item.get("time", "00:00"), recur, month_end):
                    if fd >= month_start:
                        target[fd] = target.get(fd, 0) + 1
        self.calendar.set_event_dates(active_counts, inactive_counts)

    def _clear_form(self):
        self.date_edit.clear()
        self.time_edit.clear()
        self.dur_spin.setValue(60)
        self.desc_edit.clear()
        self.recur_edit.clear()
        self.cmd_edit.clear()
        self.args_edit.clear()
        self.workdir_edit.clear()
        self._wait_cb.setChecked(False)
        self._run_on_startup_cb.setChecked(False)
        self._check_running_cb.setChecked(False)

    def _build_ui(self):
        self.setWindowTitle(self._t("events_editor.title"))
        self.resize(940, 500)
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

        content_row = QHBoxLayout()
        content_row.setSpacing(10)

        calendar_group = QGroupBox()
        cal_layout = QVBoxLayout(calendar_group)
        self.calendar = CalendarWidget()
        self.calendar.setFixedWidth(280)
        self.calendar.setStyleSheet("QAbstractItemView { selection-background-color: transparent; }")
        self.calendar.clicked.connect(self._on_date_clicked)
        self.calendar.currentPageChanged.connect(lambda y, m: self._highlight_calendar())
        cal_layout.addWidget(self.calendar)
        content_row.addWidget(calendar_group)

        right_panel = QVBoxLayout()
        right_panel.setSpacing(6)

        day_group = QGroupBox(self._t("events_editor.list_label"))
        day_layout = QVBoxLayout(day_group)
        day_layout.setContentsMargins(4, 4, 4, 4)
        self.day_list = QListWidget()
        self.day_list.setMinimumHeight(80)
        self.day_list.currentRowChanged.connect(self._on_select)
        day_layout.addWidget(self.day_list)
        right_panel.addWidget(day_group)

        form_group = QGroupBox(self._t("events_editor.form_label"))
        form_grid = QVBoxLayout(form_group)

        row_enabled = QHBoxLayout()
        self._enabled_cb = QCheckBox(self._t("events_editor.fields.enabled"))
        self._enabled_cb.setChecked(True)
        self._enabled_cb.setStyleSheet(f"color: {LABEL_FG};")
        self._enabled_cb.setToolTip(self._t("events_editor.descriptions.enabled"))
        row_enabled.addWidget(self._enabled_cb)
        row_enabled.addStretch()
        form_grid.addLayout(row_enabled)

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
        self.cmd_edit.textChanged.connect(self._on_cmd_changed)
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
        self.recur_edit.setPlaceholderText("30m / 2h / 1d / 1w / 1M")
        row_recur.addWidget(self.recur_edit)
        self._run_on_startup_cb = QCheckBox(self._t("events_editor.fields.run_on_startup"))
        self._run_on_startup_cb.setStyleSheet(f"color: {LABEL_FG};")
        self._run_on_startup_cb.setToolTip(self._t("events_editor.descriptions.run_on_startup"))
        self._run_on_startup_cb.setEnabled(False)
        row_recur.addWidget(self._run_on_startup_cb)
        self._silent_cb = QCheckBox(self._t("events_editor.fields.silent"))
        self._silent_cb.setStyleSheet(f"color: {LABEL_FG};")
        self._silent_cb.setToolTip(self._t("events_editor.descriptions.silent"))
        row_recur.addWidget(self._silent_cb)
        row_recur.addStretch()
        form_grid.addLayout(row_recur)

        row_flags = QHBoxLayout()
        self._wait_cb = QCheckBox(self._t("events_editor.fields.wait_for_completion"))
        self._wait_cb.setStyleSheet(f"color: {LABEL_FG};")
        self._wait_cb.setToolTip(self._t("events_editor.descriptions.wait_for_completion"))
        self._wait_cb.setEnabled(False)
        row_flags.addWidget(self._wait_cb)

        self._check_running_cb = QCheckBox(self._t("events_editor.fields.check_already_running"))
        self._check_running_cb.setStyleSheet(f"color: {LABEL_FG};")
        self._check_running_cb.setToolTip(self._t("events_editor.descriptions.check_already_running"))
        self._check_running_cb.setEnabled(False)
        row_flags.addWidget(self._check_running_cb)
        row_flags.addStretch()
        form_grid.addLayout(row_flags)

        form_grid.addSpacing(8)
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
        form_grid.addLayout(btn_row)

        right_panel.addWidget(form_group)
        content_row.addLayout(right_panel, 1)
        layout.addLayout(content_row, 1)

        self._toggle_fields()

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
        self._wait_cb.setVisible(is_schedule)
        self._run_on_startup_cb.setVisible(is_schedule)
        self._check_running_cb.setVisible(is_schedule)
        if not is_schedule:
            self._wait_cb.setChecked(False)
            self._run_on_startup_cb.setChecked(False)
            self._check_running_cb.setChecked(False)

    def _on_cmd_changed(self, text=""):
        cmd = text or self.cmd_edit.text().strip()
        is_exe = bool(cmd) and any(
            cmd.lower().endswith(ext) for ext in (".exe", ".bat", ".ps1", ".cmd")
        ) and (os.path.exists(cmd.split()[0]) if os.path.isabs(cmd.split()[0]) else bool(shutil.which(cmd.split()[0])))
        for cb in [self._wait_cb, self._run_on_startup_cb, self._check_running_cb]:
            cb.setEnabled(is_exe)
            if not is_exe:
                cb.setChecked(False)

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

    def _on_date_clicked(self, qdate):
        self._selected_idx = None
        self._refresh_list()

    def _on_select(self, row):
        item_widget = self.day_list.item(row)
        if item_widget is None:
            self._selected_idx = None
            return
        actual_idx = item_widget.data(Qt.UserRole)
        if actual_idx is None or actual_idx < 0 or actual_idx >= len(self._current_items):
            if actual_idx == -1:
                self._selected_idx = None
            else:
                self._selected_idx = None
            return
        self._selected_idx = actual_idx
        item = self._current_items[actual_idx]
        self.date_edit.setText(item.get("date", ""))
        self.time_edit.setText(item.get("time", ""))
        self.dur_spin.setValue(int(item.get("duration", 60) or 60))
        self.desc_edit.setText(item.get("description", ""))
        self.recur_edit.setText(item.get("recur", ""))
        self.cmd_edit.setText(item.get("command", ""))
        self.args_edit.setText(item.get("arguments", ""))
        self.workdir_edit.setText(item.get("workingdir", ""))
        enabled = str(item.get("enabled", "true"))
        self._enabled_cb.setChecked(enabled.lower() != "false")
        silent = str(item.get("silent", "false"))
        self._silent_cb.setChecked(silent.lower() == "true")
        self._wait_cb.setChecked(str(item.get("wait_for_completion", "false")).lower() == "true")
        self._run_on_startup_cb.setChecked(str(item.get("run_on_startup", "false")).lower() == "true")
        self._check_running_cb.setChecked(str(item.get("check_already_running", "false")).lower() == "true")

    def _navigate_to_date(self, date_str):
        y, m, d = map(int, date_str.split("-"))
        self.calendar.setSelectedDate(QDate(y, m, d))
        self._selected_idx = None
        self._refresh_list()

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
                vass_path = os.path.join(get_project_root(), "scripts", f"{exe}.vass")
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
            if self._wait_cb.isEnabled() and self._wait_cb.isChecked():
                item["wait_for_completion"] = "true"
            if self._run_on_startup_cb.isEnabled() and self._run_on_startup_cb.isChecked():
                item["run_on_startup"] = "true"
            if self._check_running_cb.isEnabled() and self._check_running_cb.isChecked():
                item["check_already_running"] = "true"
        item["enabled"] = "true" if self._enabled_cb.isChecked() else "false"
        if self._silent_cb.isChecked():
            item["silent"] = "true"
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
        idx = len(self._current_items) - 1
        for i in range(self.day_list.count()):
            if self.day_list.item(i).data(Qt.UserRole) == idx:
                self.day_list.setCurrentRow(i)
                break

    def _update_item(self):
        if self._selected_idx is None:
            return
        if not self._validate():
            return
        self._current_items[self._selected_idx] = self._build_item(existing=self._current_items[self._selected_idx])
        self._refresh_list()
        for i in range(self.day_list.count()):
            if self.day_list.item(i).data(Qt.UserRole) == self._selected_idx:
                self.day_list.setCurrentRow(i)
                break

    def _delete_item(self):
        if self._selected_idx is None:
            return
        item = self._current_items[self._selected_idx]
        desc = item.get("description", "?")
        date = item.get("date", "")
        detail = f"{desc} ({date})" if date else desc
        msg = QMessageBox(self)
        msg.setWindowTitle(self._t("events_editor.delete_confirm_title"))
        msg.setText(self._t("events_editor.delete_confirm_text").replace("{item}", detail))
        msg.setIcon(QMessageBox.Icon.Question)
        yes_btn = msg.addButton(self._t("events_editor.dialog_yes"), QMessageBox.ButtonRole.YesRole)
        no_btn = msg.addButton(self._t("events_editor.dialog_no"), QMessageBox.ButtonRole.NoRole)
        msg.exec()
        if msg.clickedButton() != yes_btn:
            return
        del self._current_items[self._selected_idx]
        self._selected_idx = None
        self._refresh_list()

    @staticmethod
    def _item_fallback_key(item):
        return (item.get("description", ""), item.get("date", ""), item.get("time", ""))

    def _do_save(self):
        path = self._file_path()
        key = self._key()
        fresh_items = _load(path)

        # Ensure all fresh items have an id for reliable matching
        for fi in fresh_items:
            if "id" not in fi:
                fi["id"] = uuid.uuid4().hex[:8]

        fresh_by_id = {fi["id"]: fi for fi in fresh_items if fi.get("id")}
        fresh_by_fallback = {self._item_fallback_key(fi): fi for fi in fresh_items}
        snap_by_id = {si["id"]: si for si in self._items_snapshot if si.get("id")}
        snap_by_fallback = {self._item_fallback_key(si): si for si in self._items_snapshot}

        EDITABLE = {"date", "time", "duration", "description", "recur",
                     "command", "arguments", "workingdir", "enabled", "silent"}

        merged = []
        seen_ids = set()

        for item in self._current_items:
            item_id = item.get("id")

            # Match by id or fallback to desc+date+time
            fresh = fresh_by_id.get(item_id) if item_id else None
            if not fresh and not item_id:
                fresh = fresh_by_fallback.get(self._item_fallback_key(item))
                if fresh:
                    item["id"] = fresh["id"]

            snap = snap_by_id.get(item["id"]) if item.get("id") else None
            if not snap:
                snap = snap_by_fallback.get(self._item_fallback_key(item))

            if "id" not in item:
                item["id"] = uuid.uuid4().hex[:8]
            item_id = item["id"]
            seen_ids.add(item_id)

            if fresh:
                merged_item = dict(fresh)
                if snap:
                    for field in EDITABLE:
                        if item.get(field) != snap.get(field):
                            merged_item[field] = item[field]
                desc = merged_item.get("description", "")
                d = merged_item.get("date", "")
                t = merged_item.get("time", "")
                merged_item["name"] = f"{desc}_{d}_{t}".replace(" ", "_").lower()
                merged.append(merged_item)
            else:
                merged.append(dict(item))

        self._items_snapshot = copy.deepcopy(merged)
        _save(path, merged, key)

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
