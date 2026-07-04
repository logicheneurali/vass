"""Permanent memory viewer/editor for VASS — manage tagged conversation entries."""
import sys, os, json
from PySide6.QtCore import Qt, QUrl, QTimer
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                                QHBoxLayout, QLabel, QPushButton, QCheckBox,
                                QMessageBox, QMenu, QDialog)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEnginePage

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALLOWED = os.path.join(BASE, "Allowed_root")
TAGS_PATH = os.path.join(ALLOWED, "memory_tags.json")
MEM_DIR = os.path.join(ALLOWED, "memory")

from theme import BG, FG, BTN_BG, BASE_STYLESHEET
ACCENT = BTN_BG
TAG_BG = "#3d3d3d"


def _t(path, lang="en"):
    try:
        from i18n import t
        return t(path, lang)
    except Exception:
        return path.split(".")[-1].replace("_", " ").title()


def _load_tags():
    if os.path.exists(TAGS_PATH):
        with open(TAGS_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"entries": []}


def _save_tags_data(data):
    os.makedirs(ALLOWED, exist_ok=True)
    with open(TAGS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _load_entry_content(entry_id):
    hf = os.path.join(MEM_DIR, f"{entry_id}.json")
    if os.path.exists(hf):
        try:
            with open(hf, encoding="utf-8") as f:
                data = json.load(f)
            info = json.loads(data.get("info", "{}"))
            return info.get("content", "(empty)"), info.get("role", "system")
        except Exception:
            pass
    return "(not available)", "system"


def _load_tag_weights():
    cfg_path = os.path.join(ALLOWED, "tags_config.json")
    if os.path.exists(cfg_path):
        with open(cfg_path, encoding="utf-8") as f:
            return json.load(f).get("tags", {})
    from tag_manager import _DEFAULT_TAGS, save_tags_config
    save_tags_config(_DEFAULT_TAGS, 10)
    return dict(_DEFAULT_TAGS)


class SourcesDialog(QDialog):
    def __init__(self, parent=None, lang="en"):
        super().__init__(parent)
        self.lang = lang
        self.setWindowTitle(_t("memory_editor.sources_title", lang))
        self.setFixedSize(350, 240)
        self.setStyleSheet(f"QDialog {{ background-color: {BG}; }}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        sources_path = os.path.join(ALLOWED, "memory_sources.json")
        try:
            with open(sources_path, encoding="utf-8") as f:
                self._sources = json.load(f)
        except Exception:
            self._sources = {"email": False, "calendar": False,
                             "events": False, "timers": False}

        self._checkboxes = {}
        for key, label_key in [("email", "sources_email"), ("calendar", "sources_calendar"),
                                ("events", "sources_events"), ("timers", "sources_timers")]:
            cb = QCheckBox(_t(f"memory_editor.{label_key}", lang))
            cb.setChecked(self._sources.get(key, False))
            cb.setStyleSheet(f"color: {FG}; spacing: 8px;")
            self._checkboxes[key] = cb
            layout.addWidget(cb)

        desc = QLabel(_t("memory_editor.sources_description", lang))
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(desc)

        layout.addStretch()
        btn_row = QHBoxLayout()
        cancel_btn = QPushButton(_t("memory_editor.dialog_cancel", lang))
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton(_t("memory_editor.dialog_save", lang))
        save_btn.setStyleSheet(f"background-color: {ACCENT}; font-weight: bold;")
        save_btn.clicked.connect(self._save)
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

    def _save(self):
        sources_path = os.path.join(ALLOWED, "memory_sources.json")
        for key, cb in self._checkboxes.items():
            self._sources[key] = cb.isChecked()
        os.makedirs(ALLOWED, exist_ok=True)
        with open(sources_path, "w", encoding="utf-8") as f:
            json.dump(self._sources, f, ensure_ascii=False, indent=2)
        print(f"[MemoryEditor] Sources saved: {self._sources}")
        QMessageBox.information(self, _t("memory_editor.sources_title", self.lang),
                                _t("memory_editor.sources_saved", self.lang))
        self.accept()


class _MemPage(QWebEnginePage):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._callback = None

    def set_callback(self, cb):
        self._callback = cb

    def acceptNavigationRequest(self, url, _type, is_main_frame):
        if url.scheme() == "vass" and self._callback:
            self._callback(url.toString())
            return False
        return True


class MemoryEditor(QMainWindow):
    def __init__(self, language="en"):
        super().__init__()
        self.lang = language
        self._data = _load_tags()
        self._dirty = False
        self._tag_weights = _load_tag_weights()
        self._build_ui()
        self._rebuild_content()

    def _tl(self, key):
        return _t(key, self.lang)

    def _build_ui(self):
        self.setWindowTitle(self._tl("memory_editor.title"))
        self.resize(800, 600)
        self.setStyleSheet(BASE_STYLESHEET)
        self.setMinimumSize(600, 400)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        page = _MemPage(self)
        page.set_callback(self._on_vass_link)
        self.browser = QWebEngineView()
        self.browser.setPage(page)
        self.browser.setStyleSheet("background-color: transparent;")
        page.setBackgroundColor(Qt.GlobalColor.transparent)
        layout.addWidget(self.browser, 1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        tags_btn = QPushButton(self._tl("memory_editor.manage_tags"))
        tags_btn.clicked.connect(self._open_tag_manager)
        btn_row.addWidget(tags_btn)
        sources_btn = QPushButton(self._tl("memory_editor.sources"))
        sources_btn.clicked.connect(self._open_sources_dialog)
        btn_row.addWidget(sources_btn)
        btn_row.addStretch()
        self.save_btn = QPushButton(self._tl("memory_editor.save"))
        self.save_btn.clicked.connect(self._save)
        self.save_btn.setStyleSheet(f"QPushButton {{ background-color: {ACCENT}; font-weight: bold; }}"
                                    "QPushButton:disabled { background-color: #2d2d2d; color: #666; }")
        self.save_btn.setEnabled(False)
        btn_row.addWidget(self.save_btn)
        layout.addLayout(btn_row)

    def _rebuild_content(self):
        self._scroll_y = self.browser.page().scrollPosition().y()

        entries = self._data.get("entries", [])
        dirty = False
        clean_entries = []
        for entry in entries:
            content, _role = _load_entry_content(entry.get("id", "?"))
            if content == "(not available)":
                dirty = True
                continue
            clean_entries.append(entry)
        if dirty:
            self._data["entries"] = clean_entries
            _save_tags_data(self._data)
            entries = clean_entries
        if not entries:
            self.browser.setHtml(f'<div style="color:#888; text-align:center; padding:40px;">'
                                 f'{self._escape_html(self._tl("memory_editor.no_entries"))}</div>',
                                 QUrl("vass://local/"))
            return

        lines = ['<!DOCTYPE html><html><head><meta charset="utf-8"><style>',
                '::-webkit-scrollbar { width: 10px; }',
                '::-webkit-scrollbar-track { background: #1e1e1e; }',
                '::-webkit-scrollbar-thumb { background: #2d2d2d; border-radius: 4px; }',
                '::-webkit-scrollbar-button { display: none; }',
                 'body { margin: 12px; }',
                 'a { color:#ccc; text-decoration:none; font-size:11px; }',
                 'a:hover { color:#fff; }',
                 '.entry-card { background:#252525; border:1px solid #3a3a3a; padding:14px; margin-bottom:12px; }',
                 '.flex-row { display:flex; align-items:center; }',
                 '.spacer { flex:1; }',
                 '</style></head>',
                 f'<body style="background-color:{BG}; color:{FG}; font-family:Segoe UI; font-size:13px;">']

        for i, entry in enumerate(entries):
            date_str = entry.get("ts", "?")
            tags = entry.get("tags", [])
            relevance = entry.get("relevance", 0)
            content, _role = _load_entry_content(entry.get("id", "?"))
            safe_content = self._escape_html(content[:600])

            lines.append(f'<div class="entry-card">')
            lines.append(f'<div style="margin-bottom:8px;">')
            lines.append(f'<span style="color:#888; font-size:11px;">[{date_str}]</span> ')
            lines.append(f'<span style="color:#aaa; font-size:11px;">{self._tl("memory_editor.relevance_label")}: {relevance}</span>')
            lines.append(f'</div>')
            lines.append(f'<div style="white-space:pre-wrap; margin-bottom:14px; font-size:12px;">{safe_content}</div>')
            lines.append(f'<div class="flex-row" style="margin-top:8px;">')
            lines.append(f'<div>')
            for tag in tags:
                weight = self._tag_weights.get(tag, "?")
                known = tag in self._tag_weights
                if known:
                    lines.append(f'<a href="vass:rmtag:{i}:{tag}" style="display:inline-block; background:{TAG_BG}; border-radius:3px; padding:3px 8px; margin:2px; font-size:11px;">'
                                 f'{tag} ({weight}) &times;</a>')
                else:
                    lines.append(f'<span style="display:inline-block; background:#444; color:#888; border-radius:3px; padding:3px 8px; margin:2px; font-size:11px;">'
                                 f'{tag} ({weight})</span>')
            lines.append(f'<a href="vass:addtag:{i}" style="display:inline-block; color:{ACCENT}; font-size:11px; margin:2px;">+ {self._tl("memory_editor.add_tag_button")}</a>')
            lines.append(f'</div>')
            lines.append(f'<a href="vass:delentry:{i}" style="color:#e74c3c; font-size:11px; white-space:nowrap;">{self._tl("memory_editor.delete_entry")}</a>')
            lines.append(f'</div>')
            lines.append(f'</div>')

        lines.append('</body></html>')
        self.browser.setHtml("\n".join(lines), QUrl("vass://local/"))
        if hasattr(self, '_scroll_y') and self._scroll_y > 0:
            QTimer.singleShot(50, lambda: self.browser.page().runJavaScript(
                f"window.scrollTo(0, {self._scroll_y});"))

    def _on_vass_link(self, href):
        if ":" not in href:
            return
        _, _, rest = href.partition(":")
        parts = rest.split(":", 2)
        action = parts[0]
        if action == "rmtag" and len(parts) >= 3:
            self._remove_tag(int(parts[1]), parts[2])
        elif action == "addtag" and len(parts) >= 2:
            self._show_add_tag_menu(int(parts[1]))
        elif action == "delentry" and len(parts) >= 2:
            self._delete_entry(int(parts[1]))

    def _remove_tag(self, entry_idx, tag):
        entries = self._data.get("entries", [])
        if entry_idx >= len(entries):
            return
        entry = entries[entry_idx]
        tags = entry.get("tags", [])
        if tag in tags:
            tags.remove(tag)
            if not tags:
                tags = ["generic"]
            entry["tags"] = tags
            entry["relevance"] = sum(self._tag_weights.get(t, 0) for t in tags)
            self._mark_dirty()
            self._rebuild_content()

    def _show_add_tag_menu(self, entry_idx):
        menu = QMenu(self)
        entries = self._data.get("entries", [])
        if entry_idx >= len(entries):
            return
        current_tags = set(entries[entry_idx].get("tags", []))
        for tag, weight in sorted(self._tag_weights.items(), key=lambda x: -x[1]):
            if tag not in current_tags:
                action = menu.addAction(f"{tag} ({weight})")
                action.triggered.connect(lambda checked, t=tag, i=entry_idx: self._add_tag(i, t))
        if menu.actions():
            menu.exec(self.mapToGlobal(self.rect().center()))

    def _add_tag(self, entry_idx, tag):
        entries = self._data.get("entries", [])
        if entry_idx >= len(entries):
            return
        entry = entries[entry_idx]
        tags = entry.get("tags", [])
        if tag not in tags:
            tags.append(tag)
            entry["tags"] = tags
            entry["relevance"] = sum(self._tag_weights.get(t, 0) for t in tags)
            self._mark_dirty()
            self._rebuild_content()

    def _delete_entry(self, entry_idx):
        entries = self._data.get("entries", [])
        if entry_idx >= len(entries):
            return
        msg = QMessageBox(self)
        msg.setWindowTitle(self._tl("memory_editor.delete_entry"))
        msg.setText(self._tl("memory_editor.delete_confirm"))
        msg.setIcon(QMessageBox.Icon.Question)
        yes_btn = msg.addButton(self._tl("memory_editor.dialog_yes"), QMessageBox.ButtonRole.YesRole)
        msg.addButton(self._tl("memory_editor.dialog_no"), QMessageBox.ButtonRole.NoRole)
        msg.exec()
        if msg.clickedButton() == yes_btn:
            del entries[entry_idx]
            self._mark_dirty()
            self._rebuild_content()

    def _mark_dirty(self):
        self._dirty = True
        self.save_btn.setEnabled(True)

    def _save(self):
        _save_tags_data(self._data)
        self._dirty = False
        self.save_btn.setEnabled(False)

    def _check_unsaved_and_close(self):
        if self._dirty:
            msg = QMessageBox(self)
            msg.setWindowTitle(self._tl("memory_editor.unsaved_title"))
            msg.setText(self._tl("memory_editor.unsaved_changes"))
            msg.setIcon(QMessageBox.Icon.Question)
            save_btn = msg.addButton(self._tl("memory_editor.dialog_save"), QMessageBox.ButtonRole.AcceptRole)
            discard_btn = msg.addButton(self._tl("memory_editor.dialog_discard"), QMessageBox.ButtonRole.DestructiveRole)
            cancel_btn = msg.addButton(self._tl("memory_editor.dialog_cancel"), QMessageBox.ButtonRole.RejectRole)
            msg.exec()
            clicked = msg.clickedButton()
            if clicked == save_btn:
                self._save()
                self.close()
            elif clicked == discard_btn:
                self.close()
        else:
            self.close()

    def _open_tag_manager(self):
        from tag_manager import TagManager
        dlg = TagManager(self, self.lang)
        if dlg.exec():
            self._tag_weights = dlg.tags
            self._rebuild_content()

    def _open_sources_dialog(self):
        dlg = SourcesDialog(self, self.lang)
        dlg.exec()

    def closeEvent(self, event):
        self._check_unsaved_and_close()
        event.ignore()

    @staticmethod
    def _escape_html(text):
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def main():
    lang = "en"
    for i, a in enumerate(sys.argv[1:]):
        if a == "--lang" and i + 1 < len(sys.argv[1:]):
            lang = sys.argv[i + 2]
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    editor = MemoryEditor(language=lang)
    editor.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
