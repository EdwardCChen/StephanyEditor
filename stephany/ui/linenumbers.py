# Stephany Editor — 支援中文欄（直行）模式的文字編輯器
# Copyright (C) 2026 Edward Chen
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""行號欄：行號、書籤標記、摺疊箭號。

由左至右的版面：
    [ 書籤圓點 ][ 行號 ][ 摺疊箭號 ]
摺疊箭號放在最右邊（緊鄰文字區），與一般編輯器的慣例一致，
點擊該欄即可展開／摺疊（SRS-003 F-FD-01）。
"""

from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QWidget

from . import theme

#: 最右側保留給摺疊箭號的寬度
FOLD_COLUMN = 16
#: 最左側保留給書籤圓點的寬度
BOOKMARK_COLUMN = 14


class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self._editor = editor
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def sizeHint(self) -> QSize:
        return QSize(self._editor.line_number_area_width(), 0)

    # -- 版面 ------------------------------------------------------------
    def _iter_visible_blocks(self):
        """產生 (block, top, height)，只含畫得到的行。"""
        editor = self._editor
        block = editor.firstVisibleBlock()
        offset = editor.contentOffset()
        top = editor.blockBoundingGeometry(block).translated(offset).top()
        while block.isValid() and top <= self.rect().bottom():
            height = editor.blockBoundingRect(block).height()
            if block.isVisible():
                yield block, top, height
            block = block.next()
            top += height

    def _line_at(self, y: int) -> int | None:
        for block, top, height in self._iter_visible_blocks():
            if top <= y < top + height:
                return block.blockNumber()
        return None

    # -- 互動（F-FD-01）--------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        pos = event.position().toPoint()
        line = self._line_at(pos.y())
        if line is None:
            return super().mousePressEvent(event)
        if pos.x() >= self.width() - FOLD_COLUMN:
            if self._editor.foldable_at(line) is not None:
                self._editor.toggle_fold(line)
                return
        elif pos.x() < BOOKMARK_COLUMN:
            self._editor.toggle_bookmark(line)  # 點書籤欄切換書籤
            return
        super().mousePressEvent(event)

    # -- 繪製 ------------------------------------------------------------
    def paintEvent(self, event):
        editor = self._editor
        palette = editor.palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(event.rect(), theme.gutter_background(palette))
        painter.setPen(theme.gutter_border(palette))
        painter.drawLine(
            self.width() - 1, event.rect().top(), self.width() - 1, event.rect().bottom()
        )

        current = editor.textCursor().blockNumber()
        bookmark_colour = theme.bookmark_color(palette)
        fold_colour = theme.fold_marker_color(palette)
        number_width = self.width() - FOLD_COLUMN - BOOKMARK_COLUMN - 4

        for block, top, height in self._iter_visible_blocks():
            if top + height < event.rect().top():
                continue
            number = block.blockNumber()

            # 書籤圓點（SRS-002 F-BM-04）
            if number in editor.bookmarks:
                painter.setBrush(bookmark_colour)
                painter.setPen(Qt.PenStyle.NoPen)
                radius = max(3, int(height) // 5)
                painter.drawEllipse(
                    4, int(top) + (int(height) - radius * 2) // 2, radius * 2, radius * 2
                )
                painter.setBrush(Qt.BrushStyle.NoBrush)

            # 行號
            painter.setPen(
                theme.gutter_current_text(palette)
                if number == current
                else theme.gutter_text(palette)
            )
            painter.drawText(
                QRect(BOOKMARK_COLUMN, int(top), number_width, int(height)),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                str(number + 1),
            )

            # 摺疊箭號（SRS-003 F-FD-01）
            if editor.foldable_at(number) is not None:
                painter.setPen(fold_colour)
                painter.drawText(
                    QRect(
                        self.width() - FOLD_COLUMN, int(top), FOLD_COLUMN, int(height)
                    ),
                    Qt.AlignmentFlag.AlignCenter,
                    "▸" if number in editor.folds else "▾",
                )
