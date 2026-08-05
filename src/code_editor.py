import re

from PySide6.QtCore import Qt, QRect, QSize
from PySide6.QtGui import (
    QColor, QFont, QPainter, QTextFormat,
    QSyntaxHighlighter, QTextCharFormat, QFontMetrics,
)
from PySide6.QtWidgets import QPlainTextEdit, QTextEdit, QWidget

from theme import BG, FG, FRAME_BORDER


LINE_BG = "#252525"
LINE_FG = "#858585"
LINE_HIGHLIGHT = "#2a2d2e"
COM_COLOR = "#6a9955"
STR_COLOR = "#ce9178"
VAR_COLOR = "#9cdcfe"
KW_COLOR = "#c586c0"
FUNC_COLOR = "#dcdcaa"
NUM_COLOR = "#b5cea8"
OP_COLOR = "#e0e0e0"


class VassScriptHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._rules = []

        fmt_comment = QTextCharFormat()
        fmt_comment.setForeground(QColor(COM_COLOR))
        fmt_comment.setFontItalic(True)
        self._rules.append((r"#.*$", fmt_comment))

        fmt_str = QTextCharFormat()
        fmt_str.setForeground(QColor(STR_COLOR))
        self._rules.append((r'"[^"\\]*(\\.[^"\\]*)*"', fmt_str))
        self._rules.append((r"'[^'\\]*(\\.[^'\\]*)*'", fmt_str))

        fmt_var = QTextCharFormat()
        fmt_var.setForeground(QColor(VAR_COLOR))
        self._rules.append((r"\$\w+(?:\.\w+)*", fmt_var))

        keywords = {
            "if", "else", "for", "while", "exit", "wait", "then", "end",
        }
        fmt_kw = QTextCharFormat()
        fmt_kw.setForeground(QColor(KW_COLOR))
        fmt_kw.setFontWeight(QFont.Weight.Bold)
        for kw in keywords:
            self._rules.append((rf"\b{kw}\b", fmt_kw))

        builtins = {
            "say", "say_async", "ai", "ai_raw", "run", "listen", "notify",
            "if_contains", "if_empty", "if_greater", "if_equal",
            "fetch_text", "fetch_json", "filter_json",
            "compress_memory", "get_datetime", "get_idle",
            "screen_search", "screen_click", "screen_highlight",
            "gcal_today", "gcal_tomorrow", "gcal_add", "gcal_search",
            "inject", "inject_memory", "save_tags", "load_tags",
            "search_web", "get_weather",
            "timer_start", "timer_list", "timer_cancel",
            "clipboard_get", "clipboard_set",
            "read_info", "write_info", "read_state", "write_state",
            "read_file", "write_file", "delete_event",
            "google_home_command", "google_home_ask",
            "trim", "get", "len", "round", "randint",
            "foreach",
        }
        fmt_func = QTextCharFormat()
        fmt_func.setForeground(QColor(FUNC_COLOR))
        for fn in builtins:
            self._rules.append((rf"\b{fn}\b", fmt_func))

        fmt_op = QTextCharFormat()
        fmt_op.setForeground(QColor(OP_COLOR))
        for op in [r"=", r"==", r"!=", r">=", r"<=", r">", r"<",
                   r"\+", r"-", r"\*", r"/", r"\(", r"\)",
                   r"\[", r"\]", r"\.", r","]:
            self._rules.append((op, fmt_op))

        fmt_num = QTextCharFormat()
        fmt_num.setForeground(QColor(NUM_COLOR))
        self._rules.append((r"\b\d+(?:\.\d+)?\b", fmt_num))

    def highlightBlock(self, text):
        for pattern, fmt in self._rules:
            for m in re.finditer(pattern, text):
                start = m.start()
                length = m.end() - start
                self.setFormat(start, length, fmt)


class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self):
        return QSize(self._editor.line_number_width(), 0)

    def paintEvent(self, event):
        self._editor.line_number_paint(event)


class CodeEditor(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        font = QFont("Consolas", 13)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)
        self.setTabStopDistance(QFontMetrics(font).horizontalAdvance(" ") * 4)
        self.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {LINE_BG};
                color: {FG};
                border: 1px solid {FRAME_BORDER};
                border-radius: 3px;
            }}
        """)

        self._line_number_area = LineNumberArea(self)
        self.blockCountChanged.connect(self._update_line_number_width)
        self.updateRequest.connect(self._update_line_number_area)
        self.cursorPositionChanged.connect(self._highlight_current_line)

        self._update_line_number_width()
        self._highlight_current_line()

        self._highlighter = VassScriptHighlighter(self.document())

    def line_number_width(self):
        digits = 1
        max_lines = max(1, self.blockCount())
        while max_lines >= 10:
            max_lines //= 10
            digits += 1
        return 14 + QFontMetrics(self.font()).horizontalAdvance("9") * digits

    def _update_line_number_width(self, _new_block_count=None):
        self.setViewportMargins(self.line_number_width(), 4, 4, 4)

    def _update_line_number_area(self, rect, dy):
        if dy:
            self._line_number_area.scroll(0, dy)
        else:
            self._line_number_area.update(
                0, rect.y(), self._line_number_area.width(), rect.height()
            )
        if rect.contains(self.viewport().rect()):
            self._update_line_number_width()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_line_number_width()
        vp = self.viewport()
        lnw = self.line_number_width()
        self._line_number_area.setGeometry(
            vp.x() - lnw, vp.y(), lnw, vp.height()
        )

    def line_number_paint(self, event):
        painter = QPainter(self._line_number_area)
        painter.fillRect(event.rect(), QColor(BG))

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())
        current = self.textCursor().block().blockNumber()

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                painter.setPen(QColor(LINE_FG))
                if block_number == current:
                    painter.setPen(QColor(FG))
                    f = self.font()
                    ps = f.pointSize()
                    if ps <= 0:
                        ps = max(8, round(f.pixelSize() * 0.75))
                    painter.setFont(QFont(f.family(), max(1, ps),
                                          QFont.Weight.Bold))
                else:
                    painter.setFont(self.font())
                painter.drawText(
                    0, top, self._line_number_area.width() - 4,
                    self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight, number
                )
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            block_number += 1

    def _highlight_current_line(self):
        extra_selections = []
        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()
            line_color = QColor(LINE_HIGHLIGHT)
            selection.format.setBackground(line_color)
            selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            extra_selections.append(selection)
        self.setExtraSelections(extra_selections)
