"""Tag manager for VASS permanent memory — add/edit/delete tags and weights."""
import sys, os, json
from PySide6.QtCore import Qt, QUrl
from PySide6.QtWidgets import (QApplication, QDialog, QVBoxLayout, QHBoxLayout,
                                QLabel, QPushButton, QLineEdit, QSpinBox,
                                QMessageBox)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEnginePage

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALLOWED = os.path.join(BASE, "Allowed_root")
TAGS_CONFIG = os.path.join(ALLOWED, "tags_config.json")

from theme import BG, FG, BTN_BG, BTN_DEL_BG, ENTRY_BG, BASE_STYLESHEET

ACCENT = BTN_BG
TAG_BG = "#3d3d3d"
DEL_BG = BTN_DEL_BG
CARD_BG = "#252525"


def _t(path, lang="en"):
    try:
        from i18n import t
        return t(path, lang)
    except Exception:
        return path.split(".")[-1].replace("_", " ").title()


_DEFAULT_TAGS = {
    "personal_data": 10, "health": 10, "finance": 10,
    "family": 10, "pets": 10,
    "contacts": 8,
    "preferences": 7, "personal_interests": 7, "purchases": 7,
    "orders": 6, "bills": 6, "invoices": 6, "work": 6, "education": 6,
    "favorite_music": 5, "food": 5, "home": 5, "personal_means_of_transport": 5,
    "deliveries": 4, "travel": 4, "tech": 4, "events": 4,
    "sales": 3,
    "generic": 1,
}


def load_tags_config():
    if os.path.exists(TAGS_CONFIG):
        with open(TAGS_CONFIG, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("tags", {}), data.get("min_relevance", 10)
    tags = dict(_DEFAULT_TAGS)
    save_tags_config(tags, 10)
    return tags, 10


def save_tags_config(tags, min_relevance):
    os.makedirs(ALLOWED, exist_ok=True)
    with open(TAGS_CONFIG, "w", encoding="utf-8") as f:
        json.dump({"min_relevance": min_relevance, "tags": tags}, f, ensure_ascii=False, indent=2)


class _TagPage(QWebEnginePage):
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


class TagManager(QDialog):
    def __init__(self, parent=None, language="en"):
        super().__init__(parent)
        self.lang = language
        self._tags, self._min_rel = load_tags_config()
        self._build_ui()
        self._rebuild_content()

    def _tl(self, key):
        return _t(key, self.lang)

    def _build_ui(self):
        self.setWindowTitle(self._tl("tag_manager.title"))
        self.resize(550, 580)
        self.setMinimumSize(450, 400)
        self.setStyleSheet(BASE_STYLESHEET +
                           f"QPushButton:hover {{ background-color: {ACCENT}; }}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        page = _TagPage(self)
        page.set_callback(self._on_vass_link)
        self.browser = QWebEngineView()
        self.browser.setPage(page)
        self.browser.setStyleSheet("background-color: transparent;")
        page.setBackgroundColor(Qt.GlobalColor.transparent)
        layout.addWidget(self.browser, 1)

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(8)
        bottom_row.addStretch()
        cancel_btn = QPushButton(self._tl("tag_manager.cancel"))
        cancel_btn.clicked.connect(self.reject)
        bottom_row.addWidget(cancel_btn)
        save_btn = QPushButton(self._tl("tag_manager.save"))
        save_btn.clicked.connect(self._save)
        save_btn.setStyleSheet(f"QPushButton {{ background-color: {ACCENT}; font-weight: bold; }}")
        bottom_row.addWidget(save_btn)
        layout.addLayout(bottom_row)

    def _rebuild_content(self):
        lines = ['<!DOCTYPE html><html><head><meta charset="utf-8"><style>',
                '::-webkit-scrollbar { width: 10px; }',
                '::-webkit-scrollbar-track { background: #1e1e1e; }',
                '::-webkit-scrollbar-thumb { background: #2d2d2d; border-radius: 4px; }',
                '::-webkit-scrollbar-button { display: none; }',
                 '* { user-select: none; -webkit-user-select: none; }',
                 'body { margin: 12px; }',
                 'a { color:#ccc; text-decoration:none; font-size:11px; }',
                 'a:hover { color:#fff; }',
                 'a.del { color:#e74c3c; }',
                 'a.add { color:#2ecc71; }',
                 'a.sub { color:#e67e22; }',
                 '.minrel-box { background:#1a3a3a; border:1px solid #0d7377; padding:5px; margin-bottom:8px; }',
                 '.tag-card { background:#252525; border:1px solid #3a3a3a; padding:10px; margin-bottom:6px; }',
                 '.flex-row { display:flex; align-items:center; }',
                 '.spacer { flex:1; }',
                 '.desc { color:#888; font-size:11px; font-style:italic; padding:5px; }',
                 '.add-tag-btn { display:block; width:100%; box-sizing:border-box; text-align:center;',
                 '  background:#0d7377; color:#fff; border-radius:3px; font-size:15px; font-weight:bold;',
                 '  padding:5px; margin:12px 0 12px 0; text-decoration:none; }',
                 '</style></head>',
                 f'<body style="background-color:{BG}; color:{FG}; font-family:Segoe UI; font-size:13px;">']

        lines.append(f'<div class="minrel-box">')
        lines.append(f'<div class="flex-row">')
        lines.append(f'<span class="spacer" style="font-weight:bold;">{self._tl("tag_manager.min_relevance")}: '
                     f'<span style="color:{ACCENT}; font-size:18px;">{self._min_rel}</span></span>')
        lines.append(f'<a href="vass:minrel:down" class="sub" style="font-size:16px; font-weight:bold; padding:0 8px;">\u2212</a>')
        lines.append(f'<a href="vass:minrel:up" class="add" style="font-size:16px; font-weight:bold; padding:0 8px;">+</a>')
        lines.append(f'</div>')
        lines.append(f'<div class="desc">{self._tl("tag_manager.min_relevance_desc")}</div>')
        lines.append(f'</div>')

        lines.append(f'<a href="vass:addtag" class="add-tag-btn">+ {self._tl("tag_manager.add_tag")}</a>')

        if not self._tags:
            lines.append(f'<div style="color:#888; text-align:center; padding:20px;">{self._tl("tag_manager.no_tags")}</div>')
        else:
            for tag, weight in sorted(self._tags.items(), key=lambda x: -x[1]):
                lines.append(f'<div class="tag-card">')
                lines.append(f'<div class="flex-row">')
                lines.append(f'<span style="font-weight:bold; font-size:14px;">{self._escape_html(tag)}</span>')
                lines.append(f'<span class="spacer"></span>')
                lines.append(f'<span style="color:#aaa; margin:0 12px; font-size:18px; min-width:30px; text-align:center;">{weight}</span>')
                lines.append(f'<a href="vass:weight:{tag}:up" class="add" style="font-size:16px; font-weight:bold; padding:2px 6px;">+</a>')
                lines.append(f'<a href="vass:weight:{tag}:down" class="sub" style="font-size:16px; font-weight:bold; padding:2px 6px; margin-left:2px;">\u2212</a>')
                lines.append(f'<a href="vass:delete:{tag}" class="del" style="margin-left:20px; font-size:11px;">{self._tl("tag_manager.delete_tag")}</a>')
                lines.append(f'</div></div>')

        lines.append('</body></html>')
        self.browser.setHtml("\n".join(lines), QUrl("vass://local/"))

    def _on_vass_link(self, href):
        if ":" not in href:
            return
        _, _, rest = href.partition(":")
        parts = rest.split(":", 2)
        action = parts[0]

        if action == "minrel" and len(parts) >= 2:
            delta = 1 if parts[1] == "up" else -1
            self._min_rel = max(1, min(100, self._min_rel + delta))
            self._rebuild_content()
        elif action == "addtag":
            self._show_add_dialog()
        elif action == "weight" and len(parts) >= 3:
            tag = parts[1]
            delta = 1 if parts[2] == "up" else -1
            if tag in self._tags:
                self._tags[tag] = max(1, min(100, self._tags.get(tag, 1) + delta))
            self._rebuild_content()
        elif action == "delete" and len(parts) >= 2:
            tag = parts[1]
            msg = QMessageBox(self)
            msg.setWindowTitle(self._tl("tag_manager.delete"))
            msg.setText(self._tl("tag_manager.delete_confirm").format(name=tag))
            msg.setIcon(QMessageBox.Icon.Question)
            yes_btn = msg.addButton(_t("memory_editor.dialog_yes", self.lang), QMessageBox.ButtonRole.YesRole)
            msg.addButton(_t("memory_editor.dialog_no", self.lang), QMessageBox.ButtonRole.NoRole)
            msg.exec()
            if msg.clickedButton() == yes_btn:
                self._tags.pop(tag, None)
                self._rebuild_content()

    def _show_add_dialog(self):
        dlg = QDialog(self)
        dlg.setWindowTitle(self._tl("tag_manager.add_tag"))
        dlg.setMinimumWidth(350)
        dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
        dlg.setStyleSheet(f"QWidget {{ background-color: {BG}; color: {FG}; font-size: 13px; }}"
                          f"QLineEdit {{ background-color: #2d2d2d; border:1px solid #555; border-radius:3px; padding:6px; color:{FG}; }}"
                          f"QSpinBox {{ background-color: #2d2d2d; border:1px solid #555; border-radius:3px; padding:4px; color:{FG}; }}"
                           f"QPushButton {{ background-color: {TAG_BG}; border:none; border-radius:3px; padding:6px 12px; }}"
                          f"QPushButton:hover {{ background-color: {ACCENT}; }}")

        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel(self._tl("tag_manager.name")))
        name_edit = QLineEdit()
        name_edit.setPlaceholderText("tag_name")
        layout.addWidget(name_edit)
        layout.addWidget(QLabel(self._tl("tag_manager.weight")))
        weight_spin = QSpinBox()
        weight_spin.setRange(1, 100)
        weight_spin.setValue(1)
        layout.addWidget(weight_spin)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton(self._tl("tag_manager.cancel"))
        cancel_btn.clicked.connect(dlg.reject)
        btn_row.addWidget(cancel_btn)
        add_btn = QPushButton(self._tl("tag_manager.add"))
        add_btn.setStyleSheet(f"QPushButton {{ background-color: {ACCENT}; font-weight: bold; }}")
        add_btn.clicked.connect(dlg.accept)
        btn_row.addWidget(add_btn)
        layout.addLayout(btn_row)

        code = dlg.exec()
        if code == QDialog.DialogCode.Accepted:
            name = name_edit.text().strip().lower()
            if name and " " not in name:
                self._tags[name] = weight_spin.value()
                self._rebuild_content()
            elif name:
                QMessageBox.warning(self, self._tl("tag_manager.error"), self._tl("tag_manager.invalid_name"))

    def _save(self):
        save_tags_config(self._tags, self._min_rel)
        QMessageBox.information(self, self._tl("tag_manager.save"), self._tl("tag_manager.saved"))
        self.accept()

    @property
    def tags(self):
        return dict(self._tags)

    @property
    def min_relevance(self):
        return self._min_rel

    @staticmethod
    def _escape_html(text):
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    lang = sys.argv[2] if len(sys.argv) > 2 and sys.argv[1] == "--lang" else "en"
    dlg = TagManager(language=lang)
    dlg.exec()
