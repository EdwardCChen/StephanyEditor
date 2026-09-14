"""行號欄。"""

from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

from . import theme


class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self._editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        editor = self._editor
        painter = QPainter(self)
        palette = editor.palette()
        painter.fillRect(event.rect(), theme.gutter_background(palette))
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(theme.gutter_border(palette))
        painter.drawLine(
            self.width() - 1, event.rect().top(), self.width() - 1, event.rect().bottom()
        )

        block = editor.firstVisibleBlock()
        number = block.blockNumber()
        offset = editor.contentOffset()
        top = editor.blockBoundingGeometry(block).translated(offset).top()
        bottom = top + editor.blockBoundingRect(block).height()
        current = editor.textCursor().blockNumber()
        height = editor.fontMetrics().height()

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                # 書籤標記（F-BM-04）：行號左側的藍色圓點
                if number in editor.bookmarks:
                    painter.setBrush(theme.bookmark_color(palette))
                    painter.setPen(Qt.PenStyle.NoPen)
                    radius = max(3, height // 5)
                    painter.drawEllipse(
                        4, int(top) + (height - radius * 2) // 2, radius * 2, radius * 2
                    )
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(
                    theme.gutter_current_text(palette)
                    if number == current
                    else theme.gutter_text(palette)
                )
                painter.drawText(
                    QRect(0, int(top), self.width() - 6, height),
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                    str(number + 1),
                )
            block = block.next()
            top = bottom
            bottom = top + editor.blockBoundingRect(block).height()
            number += 1
