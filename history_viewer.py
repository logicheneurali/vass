import json
import os
import sys
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget,
    QTextBrowser, QPushButton, QMessageBox,
)

BASE = os.path.dirname(os.path.abspath(__file__))

USER_COLOR = "#2ecc71"
AI_COLOR = "#3498db"
BG = "#1e1e1e"
FG = "#e0e0e0"
TIME_COLOR = "#888888"
BTN_BG = "#3d3d3d"
BTN_FG = "#e0e0e0"

STYLESHEET = f"""
QMainWindow, QWidget {{ background-color: {BG}; color: {FG}; }}
QTextBrowser {{ background-color: {BG}; border: none; }}
QScrollBar:vertical {{ background: {BG}; width: 10px; }}
QScrollBar::handle:vertical {{ background: #2d2d2d; border-radius: 4px; min-height: 20px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
QPushButton {{ background-color: {BTN_BG}; color: {BTN_FG}; border: none; border-radius: 3px; padding: 2px 6px; font-size: 10px; }}
QPushButton:hover {{ background-color: #555; }}
"""


def _escape_html(text):
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n", "<br>"))


def _to_html(history_data):
    parts = ['<html><head><meta charset="utf-8"></head>',
             f'<body style="background:{BG}; color:{FG}; font-family:Segoe UI,sans-serif; font-size:13px; margin:8px;">']
    for entry in reversed(history_data):
        role = entry.get("role", "")
        content = entry.get("content", "")
        ts = entry.get("ts", "")
        if not ts:
            ts = datetime.now().strftime("%d/%m %H:%M")
        is_user = role == "user"
        label = "User" if is_user else "AI"
        color = USER_COLOR if is_user else AI_COLOR
        align = "right" if is_user else "left"
        safe = _escape_html(content)
        parts.append(
            f'<div style="margin-bottom:10px;">'
            f'<div style="text-align:{align}; color:{TIME_COLOR}; font-size:10px; margin-bottom:2px;">[{ts}] {label}</div>'
            f'<table width="100%" cellpadding="0" cellspacing="0"><tr><td align="{align}">'
            f'<table cellpadding="0" cellspacing="0" style="display:inline-block;">'
            f'<tr><td style="background:#2d2d2d; border-left:3px solid {color}; '
            f'border-radius:4px; padding:8px 12px; color:{FG}; font-size:13px; max-width:600px; display:inline-block;">'
            f'{safe}'
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

        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)

        self.copy_btn = QPushButton(self._t("history_viewer.copy"))
        self.copy_btn.clicked.connect(self._copy_selected)

        self.resend_btn = QPushButton(self._t("history_viewer.resend"))
        self.resend_btn.clicked.connect(self._resend_selected)

        self.read_btn = QPushButton(self._t("history_viewer.read"))
        self.read_btn.clicked.connect(self._read_selected)

        btn_row.addWidget(self.copy_btn)
        btn_row.addWidget(self.resend_btn)
        btn_row.addWidget(self.read_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(False)
        self.browser.setOpenLinks(False)
        layout.addWidget(self.browser)

        self._build_messages()

    def _build_messages(self):
        html = _to_html(self.history_data)
        self.browser.setHtml(html)

    def _get_selected_text(self):
        cursor = self.browser.textCursor()
        return cursor.selectedText() if cursor.hasSelection() else ""

    def _copy_selected(self):
        text = self._get_selected_text()
        if text:
            QApplication.clipboard().setText(text)

    def _resend_selected(self):
        text = self._get_selected_text()
        if text:
            self._send_script('$r = ai("' + text.replace('\\', '\\\\').replace('"', '\\"') + '")\nsay($r)')
            QMessageBox.information(self, self._t("history_viewer.resend"),
                self._t("history_viewer.resend_sent"))

    def _read_selected(self):
        text = self._get_selected_text()
        if text:
            self._send_script('say("' + text.replace('\\', '\\\\').replace('"', '\\"') + '")')

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
        try:
            sys.path.insert(0, BASE)
            from i18n import t
            return t(path, self.lang)
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
