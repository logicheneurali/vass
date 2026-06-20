BG = "#1e1e1e"
FG = "#e0e0e0"
ENTRY_BG = "#2d2d2d"
ENTRY_FG = "#e0e0e0"
LABEL_FG = "#aaaaaa"
BTN_BG = "#0d7377"
BTN_FG = "#ffffff"
SECTION_FG = "#4ec9b0"
DESCRIPTION_FG = "#6e6e6e"
FRAME_BORDER = "#3c3c3c"
BTN_DEL_BG = "#a83232"
BTN_DEL_FG = "#ffffff"

BASE_STYLESHEET = f"""
QMainWindow, QWidget, QDialog {{ background-color: {BG}; color: {FG}; font-size: 12px; }}
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
    padding: 5px 6px;
}}
QLineEdit:focus {{ border-color: {BTN_BG}; }}
QTextEdit, QPlainTextEdit {{
    background-color: {ENTRY_BG}; color: {ENTRY_FG};
    border: 1px solid {FRAME_BORDER}; border-radius: 3px;
    padding: 6px;
}}
QPushButton {{
    background-color: {BTN_BG}; color: {BTN_FG};
    border: none; border-radius: 3px;
    padding: 6px 12px; font-weight: bold;
}}
QPushButton:hover {{ background-color: #0a5c5e; }}
QPushButton:pressed {{ background-color: #085052; }}
QListWidget {{
    background-color: #252525; color: {FG};
    border: 1px solid {FRAME_BORDER}; border-radius: 3px;
    outline: none;
}}
QListWidget::item:selected {{ background-color: {BTN_BG}; color: {FG}; }}
QComboBox {{
    background-color: {ENTRY_BG}; color: {ENTRY_FG};
    border: 1px solid {FRAME_BORDER}; border-radius: 3px;
    padding: 5px 6px;
}}
QComboBox::drop-down {{ border: none; }}
QComboBox QAbstractItemView {{
    background-color: {ENTRY_BG}; color: {ENTRY_FG};
    selection-background-color: {BTN_BG};
}}
QMenu {{
    background-color: #2d2d2d; color: {FG};
    border: 1px solid {FRAME_BORDER}; padding: 4px;
}}
QMenu::item {{ padding: 6px 20px; }}
QMenu::item:selected {{ background-color: {BTN_BG}; }}
QScrollBar:vertical {{
    background: {BG}; width: 10px;
}}
QScrollBar::handle:vertical {{
    background: {ENTRY_BG}; border-radius: 4px; min-height: 20px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
QScrollBar:horizontal {{
    background: {BG}; height: 10px;
}}
QScrollBar::handle:horizontal {{
    background: {ENTRY_BG}; border-radius: 4px; min-width: 20px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0px; }}
QTextBrowser {{
    background-color: {ENTRY_BG}; color: {ENTRY_FG};
    border: 1px solid {FRAME_BORDER}; border-radius: 3px;
}}
"""
