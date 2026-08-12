import json
import os
import sys
import uuid

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QListWidget, QGroupBox,
    QLineEdit, QMessageBox, QComboBox, QTabWidget,
)
from theme import (BG, FG, ENTRY_BG, ENTRY_FG, LABEL_FG, BTN_BG, BTN_FG,
                   SECTION_FG, FRAME_BORDER, BTN_DEL_BG, BTN_DEL_FG, BASE_STYLESHEET)

STYLESHEET = BASE_STYLESHEET

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALLOWED = os.path.join(BASE, "Allowed_root")

CATEGORIES = ["news_sources", "shopping", "weather", "currency", "recipes", "movies"]

LANGS = ["it", "en", "de", "fr", "es", "pt", "ja", "ko", "zh"]
LANG_NAMES = {
    "it": "Italiano", "en": "English", "de": "Deutsch", "fr": "Francais",
    "es": "Espanol", "pt": "Portugues", "ja": "日本語", "ko": "한국어", "zh": "中文",
}



def _load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f).get("sources", [])
    except Exception:
        return []


def _save(path, sources):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"sources": sources}, f, ensure_ascii=False, indent=2)
        f.write("\n")


class SourcesEditor(QMainWindow):
    def __init__(self, language="en"):
        super().__init__()
        self.lang = language
        self._current_category = CATEGORIES[0]
        self._current_sources = []
        self._build_ui()
        self._load_category()

    def _t(self, path):
        from i18n import t
        return t(path, self.lang)

    def _file_path(self):
        return os.path.join(ALLOWED, f"{self._current_category}_{self.lang}.json")

    def _load_category(self):
        self._current_sources = _load(self._file_path())
        self._refresh_list()

    def _refresh_list(self):
        self.list_widget.clear()
        for src in self._current_sources:
            desc = src.get("description", "")
            link = src.get("link", "")
            self.list_widget.addItem(f"{desc}  —  {link}")
        self.list_widget.setCurrentRow(0)

    def _build_ui(self):
        self.setWindowTitle("VASS - Fonti Online")
        self.resize(700, 580)
        self.setMinimumSize(600, 440)
        self.setStyleSheet(STYLESHEET)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(6, 6, 6, 6)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs)

        self._build_online_tab()


        QShortcut(QKeySequence("Ctrl+S"), self, self._save_file)


    def _build_online_tab(self):
        online = QWidget()
        layout = QHBoxLayout(online)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        left_group = QGroupBox(self._t("sources_editor.categories"))
        left_layout = QVBoxLayout(left_group)

        self.cat_list = QListWidget()
        self.cat_list.addItems(CATEGORIES)
        self.cat_list.currentTextChanged.connect(self._on_cat_change)
        left_layout.addWidget(self.cat_list)

        lang_lbl = QLabel(self._t("sources_editor.language") + ":")
        left_layout.addWidget(lang_lbl)
        self.lang_combo = QComboBox()
        for lc in LANGS:
            self.lang_combo.addItem(LANG_NAMES.get(lc, lc), lc)
        idx = self.lang_combo.findData(self.lang)
        if idx >= 0:
            self.lang_combo.setCurrentIndex(idx)
        self.lang_combo.currentIndexChanged.connect(self._on_lang_change)
        left_layout.addWidget(self.lang_combo)

        layout.addWidget(left_group, 1)

        right_group = QGroupBox(self._t("sources_editor.sources"))
        right_layout = QVBoxLayout(right_group)

        self.list_widget = QListWidget()
        self.list_widget.currentRowChanged.connect(self._on_select)
        right_layout.addWidget(self.list_widget)

        form = QHBoxLayout()
        form.addWidget(QLabel(self._t("sources_editor.description") + ":"))
        self.desc_edit = QLineEdit()
        form.addWidget(self.desc_edit)
        form.addWidget(QLabel(self._t("sources_editor.link") + ":"))
        self.link_edit = QLineEdit()
        form.addWidget(self.link_edit)
        right_layout.addLayout(form)

        btn_row = QHBoxLayout()
        btn_add = QPushButton(self._t("sources_editor.buttons.add"))
        btn_add.setStyleSheet(f"background-color: {BTN_BG}; color: {BTN_FG};")
        btn_add.clicked.connect(self._add_source)
        btn_row.addWidget(btn_add)

        btn_save = QPushButton(self._t("sources_editor.buttons.save"))
        btn_save.setStyleSheet(f"background-color: {BTN_BG}; color: {BTN_FG};")
        btn_save.clicked.connect(self._save_source)
        btn_row.addWidget(btn_save)

        btn_del = QPushButton(self._t("sources_editor.buttons.delete"))
        btn_del.setStyleSheet(f"background-color: {BTN_DEL_BG}; color: {BTN_DEL_FG};")
        btn_del.clicked.connect(self._delete_source)
        btn_row.addWidget(btn_del)

        btn_row.addStretch()

        btn_save_file = QPushButton(self._t("sources_editor.buttons.save_file"))
        btn_save_file.setStyleSheet(f"background-color: {BTN_BG}; color: {BTN_FG};")
        btn_save_file.clicked.connect(self._save_online)
        btn_row.addWidget(btn_save_file)
        right_layout.addLayout(btn_row)

        layout.addWidget(right_group, 2)

        self.tabs.addTab(online, self._t("sources_editor.tab.online"))


    def _on_cat_change(self, cat):
        if cat:
            self._current_category = cat
            self._load_category()

    def _on_lang_change(self):
        data = self.lang_combo.currentData()
        if data:
            self.lang = data
            self._load_category()

    def _on_select(self, row):
        if 0 <= row < len(self._current_sources):
            src = self._current_sources[row]
            self.desc_edit.setText(src.get("description", ""))
            self.link_edit.setText(src.get("link", ""))

    def _add_source(self):
        self.list_widget.clearSelection()
        self.desc_edit.clear()
        self.link_edit.clear()
        self.desc_edit.setFocus()

    def _save_source(self):
        desc = self.desc_edit.text().strip()
        link = self.link_edit.text().strip()
        if not desc or not link:
            QMessageBox.warning(self, self._t("sources_editor.errors.title"), self._t("sources_editor.errors.required"))
            return
        row = self.list_widget.currentRow()
        if row < 0 or row >= len(self._current_sources):
            self._current_sources.append({"id": uuid.uuid4().hex[:8], "description": desc, "link": link})
            self._refresh_list()
            self.list_widget.setCurrentRow(len(self._current_sources) - 1)
        else:
            existing = self._current_sources[row]
            self._current_sources[row] = {"id": existing.get("id", uuid.uuid4().hex[:8]), "description": desc, "link": link}
            self._refresh_list()
            self.list_widget.setCurrentRow(row)

    def _delete_source(self):
        row = self.list_widget.currentRow()
        if row < 0:
            return
        del self._current_sources[row]
        self._refresh_list()

    def _save_online(self):
        _save(self._file_path(), self._current_sources)
        QMessageBox.information(self, "OK", self._t("sources_editor.saved"))

    def _save_file(self):
        self._save_online()



def main():
    lang = "en"
    for i, a in enumerate(sys.argv[1:]):
        if a == "--lang" and i + 1 < len(sys.argv[1:]):
            lang = sys.argv[i + 2]

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    editor = SourcesEditor(language=lang)
    editor.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
