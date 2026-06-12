import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QTextBrowser,
)

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

STYLESHEET = """
QMainWindow, QWidget { background-color: #1e1e1e; color: #e0e0e0; }
QTextBrowser { background-color: #1e1e1e; border: none; font-size: 13px; }
QScrollBar:vertical { background: #1e1e1e; width: 10px; }
QScrollBar::handle:vertical { background: #2d2d2d; border-radius: 4px; min-height: 20px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
"""


class MarkdownViewer(QMainWindow):
    def __init__(self, title="", content="", file_path=""):
        super().__init__()
        self.setWindowTitle(title)
        self.resize(800, 600)
        self.setMinimumSize(400, 300)
        self.setStyleSheet(STYLESHEET)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(10, 10, 10, 10)

        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        self.browser.setOpenLinks(True)
        layout.addWidget(self.browser)

        if file_path and os.path.exists(file_path):
            with open(file_path, encoding="utf-8") as f:
                content = f.read()
        self.browser.setMarkdown(content)

    @staticmethod
    def show_file(title, file_path):
        if os.path.exists(file_path):
            viewer = MarkdownViewer(title=title, file_path=file_path)
            viewer.show()
            return viewer
        return None

    @staticmethod
    def show_content(title, content):
        viewer = MarkdownViewer(title=title, content=content)
        viewer.show()
        return viewer


def main():
    lang = "en"
    for i, a in enumerate(sys.argv[1:]):
        if a == "--lang":
            try:
                lang = sys.argv[i + 2]
            except IndexError:
                pass
        elif a == "--file":
            try:
                file_path = sys.argv[i + 2]
            except IndexError:
                pass
        elif a == "--content":
            try:
                content = sys.argv[i + 2]
            except IndexError:
                pass

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    if 'file_path' in dir():
        viewer = MarkdownViewer(title="Markdown", file_path=file_path)
    elif 'content' in dir():
        viewer = MarkdownViewer(title="Markdown", content=content)
    else:
        viewer = MarkdownViewer(title="Markdown", content="# No content")

    viewer.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
