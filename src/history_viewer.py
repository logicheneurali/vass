import json
import os
import sys
from datetime import datetime

from PySide6.QtCore import QUrl
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget,
    QTextBrowser, QMessageBox,
)

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

USER_COLOR = "#2ecc71"
AI_COLOR = "#3498db"
BG = "#1e1e1e"
FG = "#e0e0e0"
TIME_COLOR = "#888888"

STYLESHEET = f"""
QMainWindow, QWidget {{ background-color: {BG}; color: {FG}; }}
QTextBrowser {{ background-color: {BG}; border: none; }}
QScrollBar:vertical {{ background: {BG}; width: 10px; }}
QScrollBar::handle:vertical {{ background: #2d2d2d; border-radius: 4px; min-height: 20px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
"""


def _escape_html(text):
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n", "<br>"))


def _to_html(history_data, lang):
    labels = {
        "copy": _tl("history_viewer.copy", lang),
        "resend": _tl("history_viewer.resend", lang),
        "read": _tl("history_viewer.read", lang),
    }
    parts = ['<html><head><meta charset="utf-8"><style>',
             'a { color:#777; text-decoration:none; font-size:10px; }',
             'a:hover { color:#bbb; }',
             '</style></head>',
             f'<body style="background:{BG}; color:{FG}; font-family:Segoe UI,sans-serif; font-size:13px; margin:8px;">']
    for orig_idx, entry in enumerate(history_data):
        role = entry.get("role", "")
        content = entry.get("content", "")
        ts = entry.get("ts", "")
        if role == "separator":
            parts.append(f'<div style="width:100%; text-align:center; color:#aaa; padding:10px 0; font-size:11px; border-top:1px solid #555; border-bottom:1px solid #555; margin:8px 0;">{_escape_html(content)}</div>')
            continue
        if not ts:
            ts = datetime.now().strftime("%d/%m %H:%M")
        is_user = role == "user"
        label = "User" if is_user else "AI"
        color = USER_COLOR if is_user else AI_COLOR
        align = "right" if is_user else "left"
        safe = _escape_html(content)

        action_links = (
            f'<a href="vass:copy:{orig_idx}">{labels["copy"]}</a>'
            + (f' &middot; <a href="vass:resend:{orig_idx}">{labels["resend"]}</a>' if is_user else '')
            + f' &middot; <a href="vass:read:{orig_idx}">{labels["read"]}</a>'
        )

        parts.append(
            f'<div style="margin-bottom:10px;">'
            f'<div style="text-align:{align}; color:{TIME_COLOR}; font-size:10px; margin-bottom:2px;">[{ts}] {label}</div>'
            f'<table width="100%" cellpadding="0" cellspacing="0"><tr><td align="{align}">'
            f'<table cellpadding="0" cellspacing="0" style="display:inline-block;">'
            f'<tr><td style="background:#2d2d2d; border-left:3px solid {color}; '
            f'border-radius:4px; padding:6px 12px 2px 12px; color:{FG}; font-size:13px; max-width:600px; display:inline-block;">'
            f'{safe}'
            f'<div style="margin-top:6px; text-align:right;">{action_links}</div>'
            f'</td></tr></table>'
            f'</td></tr></table>'
            f'</div>'
        )
    parts.append('</body></html>')
    return "\n".join(parts)


class HistoryViewer(QMainWindow):
    def __init__(self, history, language="en"):
        super().__init__()
        self.lang = language
        self.history_data = history
        self.setWindowTitle("VASS - " + self._t("history_viewer.title"))
        self.resize(750, 550)
        self.setMinimumSize(400, 300)
        self.setStyleSheet(STYLESHEET)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(6, 6, 6, 6)

        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(False)
        self.browser.setOpenLinks(False)
        self.browser.anchorClicked.connect(self._on_action)
        layout.addWidget(self.browser)

        self._build_messages()

    def _build_messages(self):
        html = _to_html(self.history_data, self.lang)
        self.browser.setHtml(html)

    def _on_action(self, url):
        href = url.toString()
        if not href.startswith("vass:"):
            return
        parts = href[5:].split(":", 1)
        if len(parts) != 2:
            return
        action, idx_str = parts
        try:
            idx = int(idx_str)
        except ValueError:
            return
        if idx < 0 or idx >= len(self.history_data):
            return
        if action == "copy":
            self._copy_message(idx)
        elif action == "resend":
            self._resend_message(idx)
        elif action == "read":
            self._read_message(idx)

    def _copy_message(self, idx):
        text = self.history_data[idx].get("content", "")
        if text:
            QApplication.clipboard().setText(text)

    @staticmethod
    def _esc(text):
        return text.replace('\\', '\\\\').replace('"', '\\"').replace('\n', ' ').replace('\r', ' ')

    def _resend_message(self, idx):
        entry = self.history_data[idx]
        if entry.get("role") != "user":
            return
        text = entry.get("content", "")
        if not text:
            return
        scr = '$r = ai("' + self._esc(text) + '")\nsay($r)'
        self._send_script(scr)
        QMessageBox.information(self, self._t("history_viewer.resend"),
            self._t("history_viewer.resend_sent"))

    def _read_message(self, idx):
        text = self.history_data[idx].get("content", "")
        if text:
            self._send_script('say("' + self._esc(text) + '")')

    @staticmethod
    def _send_script(code):
        import uuid
        queue_path = os.path.join(BASE, "scripts", "exec_queue.json")
        result_path = os.path.join(BASE, "scripts", "exec_result.json")
        for rp in [queue_path, result_path]:
            if os.path.exists(rp):
                try:
                    os.remove(rp)
                except OSError:
                    pass
        request = {"id": uuid.uuid4().hex[:12], "code": code, "timeout": 120}
        with open(queue_path, "w", encoding="utf-8") as f:
            json.dump(request, f)

    def _t(self, path):
        return _tl(path, self.lang)


def _tl(path, lang):
    try:
        from i18n import t
        return t(path, lang)
    except Exception:
        return path.split(".")[-1].title()


def main():
    data_path = os.path.join(BASE, "Allowed_root", ".history_view.json")
    history = []
    if os.path.exists(data_path):
        try:
            with open(data_path, encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            pass

    lang = "en"
    for i, a in enumerate(sys.argv[1:]):
        if a == "--lang":
            try:
                lang = sys.argv[i + 2]
            except IndexError:
                pass

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    viewer = HistoryViewer(history, language=lang)
    viewer.show()
    app.exec()
    try:
        os.remove(data_path)
    except Exception:
        pass


if __name__ == "__main__":
    main()
