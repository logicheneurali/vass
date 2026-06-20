import json
import os
import sys
import uuid

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut, QIntValidator
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QListWidget, QGroupBox,
    QLineEdit, QMessageBox, QComboBox, QTabWidget, QCheckBox,
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

RSS_FILE = os.path.join(ALLOWED, "rss_feeds.json")
INTERVAL_UNITS = {"min": "minuti", "hours": "ore", "days": "giorni"}


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
        self._rss_feeds = []
        self._build_ui()
        self._load_category()
        self._load_rss_feeds()

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
        self._build_rss_tab()

        self.tabs.currentChanged.connect(self._on_tab_changed)

        QShortcut(QKeySequence("Ctrl+S"), self, self._save_file)

    def _on_tab_changed(self, index):
        if index == 1:
            self._refresh_rss_list()

    def _build_online_tab(self):
        online = QWidget()
        layout = QHBoxLayout(online)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        left_group = QGroupBox("Categorie")
        left_layout = QVBoxLayout(left_group)

        self.cat_list = QListWidget()
        self.cat_list.addItems(CATEGORIES)
        self.cat_list.currentTextChanged.connect(self._on_cat_change)
        left_layout.addWidget(self.cat_list)

        lang_lbl = QLabel("Lingua:")
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

        right_group = QGroupBox("Sorgenti")
        right_layout = QVBoxLayout(right_group)

        self.list_widget = QListWidget()
        self.list_widget.currentRowChanged.connect(self._on_select)
        right_layout.addWidget(self.list_widget)

        form = QHBoxLayout()
        form.addWidget(QLabel("Descrizione:"))
        self.desc_edit = QLineEdit()
        form.addWidget(self.desc_edit)
        form.addWidget(QLabel("Link:"))
        self.link_edit = QLineEdit()
        form.addWidget(self.link_edit)
        right_layout.addLayout(form)

        btn_row = QHBoxLayout()
        btn_add = QPushButton("Aggiungi")
        btn_add.setStyleSheet(f"background-color: {BTN_BG}; color: {BTN_FG};")
        btn_add.clicked.connect(self._add_source)
        btn_row.addWidget(btn_add)

        btn_upd = QPushButton("Aggiorna")
        btn_upd.setStyleSheet(f"background-color: {BTN_BG}; color: {BTN_FG};")
        btn_upd.clicked.connect(self._update_source)
        btn_row.addWidget(btn_upd)

        btn_del = QPushButton("Elimina")
        btn_del.setStyleSheet(f"background-color: {BTN_DEL_BG}; color: {BTN_DEL_FG};")
        btn_del.clicked.connect(self._delete_source)
        btn_row.addWidget(btn_del)

        btn_row.addStretch()

        btn_save = QPushButton("Salva")
        btn_save.setStyleSheet(f"background-color: {BTN_BG}; color: {BTN_FG};")
        btn_save.clicked.connect(self._save_online)
        btn_row.addWidget(btn_save)
        right_layout.addLayout(btn_row)

        layout.addWidget(right_group, 2)

        self.tabs.addTab(online, "Fonti Online")

    def _build_rss_tab(self):
        rss = QWidget()
        layout = QVBoxLayout(rss)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        group = QGroupBox("Feed RSS")
        group_layout = QVBoxLayout(group)

        self.rss_list = QListWidget()
        self.rss_list.currentRowChanged.connect(self._on_rss_select)
        group_layout.addWidget(self.rss_list)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Nome:"))
        self.rss_name_edit = QLineEdit()
        row1.addWidget(self.rss_name_edit)
        row1.addWidget(QLabel("URL Feed:"))
        self.rss_url_edit = QLineEdit()
        row1.addWidget(self.rss_url_edit)
        group_layout.addLayout(row1)

        row2 = QHBoxLayout()
        self.rss_active_cb = QCheckBox("Attivo")
        self.rss_active_cb.setStyleSheet(f"color: {LABEL_FG};")
        row2.addWidget(self.rss_active_cb)

        row2.addWidget(QLabel("Controlla ogni:"))
        self.rss_interval_edit = QLineEdit()
        self.rss_interval_edit.setMaximumWidth(50)
        self.rss_interval_edit.setValidator(QIntValidator(1, 9999))
        row2.addWidget(self.rss_interval_edit)

        self.rss_unit_combo = QComboBox()
        for key, label in INTERVAL_UNITS.items():
            self.rss_unit_combo.addItem(label, key)
        row2.addWidget(self.rss_unit_combo)

        row2.addSpacing(10)
        row2.addWidget(QLabel("Lingua:"))
        self.rss_lang_combo = QComboBox()
        for lc in LANGS:
            self.rss_lang_combo.addItem(LANG_NAMES.get(lc, lc), lc)
        idx = self.rss_lang_combo.findData(self.lang)
        if idx >= 0:
            self.rss_lang_combo.setCurrentIndex(idx)
        row2.addWidget(self.rss_lang_combo)
        row2.addStretch()
        group_layout.addLayout(row2)

        btn_row = QHBoxLayout()
        btn_add = QPushButton("Aggiungi")
        btn_add.setStyleSheet(f"background-color: {BTN_BG}; color: {BTN_FG};")
        btn_add.clicked.connect(self._add_rss_feed)
        btn_row.addWidget(btn_add)

        btn_upd = QPushButton("Aggiorna")
        btn_upd.setStyleSheet(f"background-color: {BTN_BG}; color: {BTN_FG};")
        btn_upd.clicked.connect(self._update_rss_feed)
        btn_row.addWidget(btn_upd)

        btn_del = QPushButton("Elimina")
        btn_del.setStyleSheet(f"background-color: {BTN_DEL_BG}; color: {BTN_DEL_FG};")
        btn_del.clicked.connect(self._delete_rss_feed)
        btn_row.addWidget(btn_del)

        btn_row.addStretch()

        btn_save = QPushButton("Salva")
        btn_save.setStyleSheet(f"background-color: {BTN_BG}; color: {BTN_FG};")
        btn_save.clicked.connect(self._save_rss_file)
        btn_row.addWidget(btn_save)
        group_layout.addLayout(btn_row)

        layout.addWidget(group)
        self.tabs.addTab(rss, "Feed RSS")

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
        desc = self.desc_edit.text().strip()
        link = self.link_edit.text().strip()
        if not desc or not link:
            QMessageBox.warning(self, "Errore", "Descrizione e link sono obbligatori.")
            return
        self._current_sources.append({"id": uuid.uuid4().hex[:8], "description": desc, "link": link})
        self._refresh_list()
        self.list_widget.setCurrentRow(len(self._current_sources) - 1)

    def _update_source(self):
        row = self.list_widget.currentRow()
        if row < 0:
            return
        desc = self.desc_edit.text().strip()
        link = self.link_edit.text().strip()
        if not desc or not link:
            QMessageBox.warning(self, "Errore", "Descrizione e link sono obbligatori.")
            return
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
        QMessageBox.information(self, "OK", "File salvato.")

    def _save_file(self):
        if self.tabs.currentIndex() == 0:
            self._save_online()
        else:
            self._save_rss_file()

    def _load_rss_feeds(self):
        try:
            with open(RSS_FILE, encoding="utf-8") as f:
                self._rss_feeds = json.load(f).get("feeds", [])
        except Exception:
            self._rss_feeds = []
        self._refresh_rss_list()

    def _save_rss_feeds(self):
        with open(RSS_FILE, "w", encoding="utf-8") as f:
            json.dump({"feeds": self._rss_feeds}, f, ensure_ascii=False, indent=2)
            f.write("\n")

    def _refresh_rss_list(self):
        self.rss_list.clear()
        for feed in self._rss_feeds:
            status = "\u2713" if feed.get("active", True) else "\u2717"
            unit = feed.get("interval_unit", "min")
            interval = feed.get("interval", 0)
            name = feed.get("name", "")
            self.rss_list.addItem(f"{status} {name} [{interval}{unit[:1]}]")
        if self.rss_list.count() > 0:
            self.rss_list.setCurrentRow(0)

    def _on_rss_select(self, row):
        if 0 <= row < len(self._rss_feeds):
            feed = self._rss_feeds[row]
            self.rss_name_edit.setText(feed.get("name", ""))
            self.rss_url_edit.setText(feed.get("url", ""))
            self.rss_active_cb.setChecked(feed.get("active", True))
            self.rss_interval_edit.setText(str(feed.get("interval", "")))
            unit = feed.get("interval_unit", "min")
            idx = self.rss_unit_combo.findData(unit)
            if idx >= 0:
                self.rss_unit_combo.setCurrentIndex(idx)
            lang = feed.get("lang", self.lang)
            idx_l = self.rss_lang_combo.findData(lang)
            if idx_l >= 0:
                self.rss_lang_combo.setCurrentIndex(idx_l)

    def _add_rss_feed(self):
        name = self.rss_name_edit.text().strip()
        url = self.rss_url_edit.text().strip()
        interval_str = self.rss_interval_edit.text().strip()
        if not name or not url:
            QMessageBox.warning(self, "Errore", "Nome e URL sono obbligatori.")
            return
        try:
            interval = int(interval_str)
            if interval <= 0:
                raise ValueError
        except (ValueError, TypeError):
            QMessageBox.warning(self, "Errore", "L'intervallo deve essere un numero intero maggiore di zero.")
            return
        unit = self.rss_unit_combo.currentData()
        active = self.rss_active_cb.isChecked()
        lang = self.rss_lang_combo.currentData()
        self._rss_feeds.append({
            "id": uuid.uuid4().hex[:8],
            "name": name,
            "url": url,
            "active": active,
            "interval": interval,
            "interval_unit": unit,
            "lang": lang,
        })
        self._refresh_rss_list()
        self.rss_list.setCurrentRow(len(self._rss_feeds) - 1)

    def _update_rss_feed(self):
        row = self.rss_list.currentRow()
        if row < 0:
            return
        name = self.rss_name_edit.text().strip()
        url = self.rss_url_edit.text().strip()
        interval_str = self.rss_interval_edit.text().strip()
        if not name or not url:
            QMessageBox.warning(self, "Errore", "Nome e URL sono obbligatori.")
            return
        try:
            interval = int(interval_str)
            if interval <= 0:
                raise ValueError
        except (ValueError, TypeError):
            QMessageBox.warning(self, "Errore", "L'intervallo deve essere un numero intero maggiore di zero.")
            return
        unit = self.rss_unit_combo.currentData()
        active = self.rss_active_cb.isChecked()
        lang = self.rss_lang_combo.currentData()
        existing = self._rss_feeds[row]
        self._rss_feeds[row] = {
            "id": existing.get("id", uuid.uuid4().hex[:8]),
            "name": name,
            "url": url,
            "active": active,
            "interval": interval,
            "interval_unit": unit,
            "lang": lang,
        }
        self._refresh_rss_list()
        self.rss_list.setCurrentRow(row)

    def _delete_rss_feed(self):
        row = self.rss_list.currentRow()
        if row < 0:
            return
        del self._rss_feeds[row]
        self._refresh_rss_list()

    def _save_rss_file(self):
        self._save_rss_feeds()
        QMessageBox.information(self, "OK", "File RSS salvato.")


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
