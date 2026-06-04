import json
import os
import sys
from datetime import datetime

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QWidget,
    QListWidget, QListWidgetItem, QTextEdit, QLabel, QPushButton,
    QFrame, QMessageBox, QSizePolicy,
)

BASE = os.path.dirname(os.path.abspath(__file__))

USER_COLOR = "#2ecc71"
AI_COLOR = "#3498db"
BG = "#1e1e1e"
FG = "#e0e0e0"
TIME_COLOR = "#888888"
BTN_BG = "#3d3d3d"
BTN_FG = "#e0e0e0"
MSG_BG = "#2d2d2d"

STYLESHEET = f"""
QMainWindow, QWidget {{ background-color: {BG}; color: {FG}; }}
QListWidget {{ background-color: {BG}; border: none; }}
QListWidget::item {{ background-color: transparent; padding: 0px; }}
QScrollBar:vertical {{ background: {BG}; width: 10px; }}
QScrollBar::handle:vertical {{ background: #2d2d2d; border-radius: 4px; min-height: 20px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
QPushButton {{ background-color: {BTN_BG}; color: {BTN_FG}; border: none; border-radius: 3px; padding: 2px 6px; font-size: 10px; }}
QPushButton:hover {{ background-color: #555; }}
"""


class _Bubble(QTextEdit):
    def __init__(self, color, font, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.NoFrame)
        self.setFont(font)
        self.setStyleSheet(
            f"background-color: {MSG_BG}; border-radius: 8px; padding: 10px 14px; "
            f"border-left: 3px solid {color}; color: {FG};"
        )
        self.setFixedHeight(50)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.document().setDocumentMargin(0)

    def setContent(self, text):
        safe = (text
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("\n", "<br>"))
        self.setHtml(f"<p style='margin:0;'>{safe}</p>")


class _RowWidget(QWidget):
    def __init__(self, entry, color, font_base, font_time, font_small, t_fn, parent=None):
        super().__init__(parent)
        self._t_fn = t_fn
        content = entry.get("content", "")
        ts = entry.get("ts", "")
        is_user = entry.get("role", "") == "user"
        label = "User" if is_user else "AI"

        time_lbl = QLabel(f"[{ts}] {label}")
        time_lbl.setFont(font_time)
        time_lbl.setStyleSheet(f"color: {TIME_COLOR}; background: transparent;")
        time_lbl.setAlignment(Qt.AlignLeft if is_user else Qt.AlignRight)

        bubble = _Bubble(color, font_base)
        bubble.setContent(content)

        copy_btn = QPushButton(t_fn("history_viewer.copy"))
        copy_btn.setFont(font_small)
        copy_btn.setFixedWidth(50)
        copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(content))

        resend_btn = QPushButton(t_fn("history_viewer.resend"))
        resend_btn.setFont(font_small)
        resend_btn.setFixedWidth(60)
        resend_btn.clicked.connect(lambda: self._resend(content))

        read_btn = QPushButton(t_fn("history_viewer.read"))
        read_btn.setFont(font_small)
        read_btn.setFixedWidth(50)
        read_btn.clicked.connect(lambda: self._speak(content))

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 2, 0, 0)
        btn_row.setSpacing(4)
        if is_user:
            btn_row.addWidget(copy_btn)
            btn_row.addWidget(resend_btn)
            btn_row.addWidget(read_btn)
            btn_row.addStretch()
        else:
            btn_row.addStretch()
            btn_row.addWidget(read_btn)
            btn_row.addWidget(copy_btn)

        bubble_row = QHBoxLayout()
        bubble_row.setContentsMargins(0, 0, 0, 0)
        bubble_row.setSpacing(0)
        bubble_row.addWidget(bubble, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 8)
        layout.setSpacing(2)
        layout.addWidget(time_lbl)
        layout.addLayout(bubble_row)
        layout.addLayout(btn_row)

        self._bubble = bubble

    def _resend(self, text):
        self._send_script('$r = ai("' + text.replace('\\', '\\\\').replace('"', '\\"') + '")\nsay($r)')
        QMessageBox.information(self, self._t_fn("history_viewer.resend"),
            self._t_fn("history_viewer.resend_sent"))

    def _speak(self, text):
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
        layout.setContentsMargins(10, 10, 10, 10)

        self.list_widget = QListWidget()
        self.list_widget.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_widget.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        layout.addWidget(self.list_widget)

        self.font_base = QFont("Segoe UI", 11)
        self.font_small = QFont("Segoe UI", 9)
        self.font_time = QFont("Segoe UI", 8)

        self._build_messages()

    def _build_messages(self):
        self.list_widget.clear()
        for entry in reversed(self.history_data):
            is_user = entry.get("role", "") == "user"
            color = USER_COLOR if is_user else AI_COLOR
            row = _RowWidget(entry, color, self.font_base, self.font_time,
                             self.font_small, self._t)
            item = QListWidgetItem(self.list_widget)
            item.setSizeHint(QSize(0, 80))
            self.list_widget.setItemWidget(item, row)
            item.setFlags(Qt.NoItemFlags)
        self.list_widget.scrollToTop()

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
