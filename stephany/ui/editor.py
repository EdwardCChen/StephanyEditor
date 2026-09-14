"""支援中文欄（直行）模式的編輯器 widget。

架構重點
--------
1. 欄模式的狀態只有兩個角落：`_anchor`（起點）與 `_caret`（游標），
   兩者都是 (行號, 顯示欄位)。真正的矩形由 core.block.make_region() 正規化。
2. 所有文字異動都先由 core.block 算出 LineEdit 清單，再一次套用到文件上，
   並包在同一個 undo 區塊裡 —— 所以 Ctrl+Z 會把整個矩形操作一次還原。
3. 矩形選取與多重游標是自己畫的（paintEvent），因為 Qt 的 QTextCursor
   只支援連續選取，沒有矩形選取的概念。
4. 中文輸入法：預編輯（組字中）交給 Qt 原生處理，只攔截「送出」那一刻，
   把送出的字串套用到矩形的每一行。
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QRect, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QInputMethodEvent,
    QKeyEvent,
    QPainter,
    QTextCursor,
    QTextFormat,
)
from PySide6.QtWidgets import QApplication, QPlainTextEdit, QTextEdit

from ..core import block as B
from ..core.bookmarks import BookmarkSet
from ..core.macro import MacroRecorder
from ..core.widths import display_width, index_to_col, col_to_index
from .commands import EditorCommands

BLOCK_MIME = "application/x-stephany-block"

#: 優先使用的等寬字型。中文必須剛好是英文的兩倍寬，欄位模式才能對齊。
PREFERRED_FONTS = (
    "Noto Sans Mono CJK TC",
    "Noto Sans Mono CJK SC",
    "Sarasa Mono TC",
    "Sarasa Mono SC",
    "WenQuanYi Zen Hei Mono",
    "Noto Sans Mono",
    "DejaVu Sans Mono",
    "Monospace",
)


class _DocLines:
    """把 QTextDocument 包成「行陣列」介面，給 core.block 使用。

    不預先展開成 list 是因為大檔案每按一個鍵都重建整份清單會太慢；
    這裡每次存取只取需要的那幾行。
    """

    __slots__ = ("_doc",)

    def __init__(self, doc):
        self._doc = doc

    def __len__(self) -> int:
        return self._doc.blockCount()

    def __getitem__(self, n: int) -> str:
        blk = self._doc.findBlockByNumber(n)
        return blk.text() if blk.isValid() else ""


@dataclass
class Pos:
    """欄模式的座標：行號 + 顯示欄位。"""

    line: int = 0
    col: int = 0


class ColumnEditor(EditorCommands, QPlainTextEdit):
    """主編輯器。

    繼承 EditorCommands 取得語意命令層：所有編輯動作都經由 perform() 派送，
    因此「使用者能操作的」與「巨集能重播的」永遠是同一組動作（SRS-002 D-01）。
    """

    block_mode_changed = Signal(bool)
    status_changed = Signal()
    bookmarks_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setFrameStyle(0)

        self.options = B.BlockOptions()
        self._cell_w = 8.0
        self._font_ok = True

        # --- 書籤與巨集（SRS-002）---
        #: 每個分頁獨立的書籤，不隨檔案存檔（D-06）
        self.bookmarks = BookmarkSet()
        #: 預設每個編輯器各自一個；MainWindow 會換成全視窗共用的那一個
        self.recorder = MacroRecorder()
        self._prev_block_count = self.blockCount()
        self.document().contentsChange.connect(self._on_contents_change)

        # --- 欄模式狀態 ---
        self._block_on = False
        self._anchor = Pos()
        self._caret = Pos()
        self._dragging = False
        self._sticky = False  # 黏著式欄位選取：不按 Alt 直接拖曳也是矩形
        self._syncing = False

        self._caret_visible = True
        self._blink = QTimer(self)
        self._blink.timeout.connect(self._toggle_caret)

        self._autoscroll = QTimer(self)
        self._autoscroll.setInterval(40)
        self._autoscroll.timeout.connect(self._do_autoscroll)
        self._last_drag_pos = None

        from .linenumbers import LineNumberArea

        self._gutter = LineNumberArea(self)
        self.blockCountChanged.connect(self._update_gutter_width)
        self.updateRequest.connect(self._update_gutter)
        self.cursorPositionChanged.connect(self._on_cursor_moved)
        self._update_gutter_width()

        self.apply_font(self._pick_font())
        self._highlight_current_line()

    # ------------------------------------------------------------------
    # 字型與度量
    # ------------------------------------------------------------------
    def _pick_font(self) -> QFont:
        from PySide6.QtGui import QFontDatabase

        families = set(QFontDatabase.families())
        for name in PREFERRED_FONTS:
            if name in families:
                return QFont(name, 12)
        f = QFont()
        f.setStyleHint(QFont.StyleHint.Monospace)
        f.setPointSize(12)
        return f

    def apply_font(self, font: QFont):
        font.setFixedPitch(True)
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setKerning(False)
        self.setFont(font)
        fm = QFontMetricsF(font)
        self._cell_w = fm.horizontalAdvance("0")
        cjk = fm.horizontalAdvance("漢")
        # 欄位模式假設「一個中文字 = 兩個半形字」。字型若不符合就會歪掉。
        self._font_ok = abs(cjk - 2 * self._cell_w) < 0.5
        self.setTabStopDistance(self._cell_w * self.options.tab_width)
        self._update_gutter_width()
        self.viewport().update()
        self.status_changed.emit()

    @property
    def font_is_aligned(self) -> bool:
        """目前字型的中文是否剛好等於兩個半形字寬。"""
        return self._font_ok

    def set_tab_width(self, width: int):
        self.options = B.BlockOptions(
            tab_width=width,
            ambiguous_wide=self.options.ambiguous_wide,
            pad_short_lines=self.options.pad_short_lines,
        )
        self.setTabStopDistance(self._cell_w * width)
        self.viewport().update()

    def set_ambiguous_wide(self, wide: bool):
        self.options = B.BlockOptions(
            tab_width=self.options.tab_width,
            ambiguous_wide=wide,
            pad_short_lines=self.options.pad_short_lines,
        )
        self.viewport().update()
        self.status_changed.emit()

    # ------------------------------------------------------------------
    # 行號欄
    # ------------------------------------------------------------------
    def line_number_area_width(self) -> int:
        digits = max(3, len(str(max(1, self.blockCount()))))
        return 24 + int(self._cell_w * digits)  # 左側留給書籤圓點（F-BM-04）

    def _update_gutter_width(self, *_):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def _update_gutter(self, rect, dy):
        if dy:
            self._gutter.scroll(0, dy)
        else:
            self._gutter.update(0, rect.y(), self._gutter.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_gutter_width()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._gutter.setGeometry(
            QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height())
        )

    def _highlight_current_line(self):
        sel = QTextEdit.ExtraSelection()
        sel.format.setBackground(QColor("#fbf7e8"))
        sel.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
        cur = self.textCursor()
        cur.clearSelection()
        sel.cursor = cur
        self.setExtraSelections([sel])

    # ------------------------------------------------------------------
    # 座標換算
    # ------------------------------------------------------------------
    def _x_for_col(self, col: int) -> float:
        return (
            self.contentOffset().x() + self.document().documentMargin() + col * self._cell_w
        )

    def _col_for_x(self, x: float) -> int:
        rel = x - self.contentOffset().x() - self.document().documentMargin()
        return max(0, int(round(rel / self._cell_w)))

    def _line_text(self, n: int) -> str:
        blk = self.document().findBlockByNumber(n)
        return blk.text() if blk.isValid() else ""

    def caret_display_col(self) -> int:
        """一般模式下游標的顯示欄位（狀態列用）。"""
        cur = self.textCursor()
        return index_to_col(
            cur.block().text(),
            cur.positionInBlock(),
            tab_width=self.options.tab_width,
            ambiguous_wide=self.options.ambiguous_wide,
        )

    # ------------------------------------------------------------------
    # 欄模式：進入 / 離開 / 範圍
    # ------------------------------------------------------------------
    @property
    def block_mode(self) -> bool:
        return self._block_on

    @property
    def sticky_column_mode(self) -> bool:
        return self._sticky

    def set_sticky_column_mode(self, on: bool):
        """黏著模式：直接拖曳就是矩形選取，不必按 Alt。

        GNOME 預設會把 Alt+拖曳吃掉當成「搬移視窗」，所以一定要留這條路。
        """
        self._sticky = on
        if not on:
            self.exit_block_mode()
        self.status_changed.emit()

    def region(self) -> B.BlockRegion:
        return B.make_region(
            self._anchor.line, self._anchor.col, self._caret.line, self._caret.col
        )

    def start_block_mode(self, line: int, col: int):
        self._block_on = True
        self._anchor = Pos(line, col)
        self._caret = Pos(line, col)
        self.setCursorWidth(0)
        self._caret_visible = True
        self._blink.start(max(200, QApplication.cursorFlashTime() // 2))
        self._sync_text_cursor()
        self.viewport().update()
        self.block_mode_changed.emit(True)
        self.status_changed.emit()

    def exit_block_mode(self):
        if not self._block_on:
            return
        self._block_on = False
        self._dragging = False
        self._blink.stop()
        self._autoscroll.stop()
        self.setCursorWidth(1)
        self.viewport().update()
        self.block_mode_changed.emit(False)
        self.status_changed.emit()

    def _move_caret(self, line: int, col: int, extend: bool = True):
        line = max(0, min(line, self.blockCount() - 1))
        self._caret = Pos(line, max(0, col))
        if not extend:
            self._anchor = Pos(line, max(0, col))
        self._sync_text_cursor()
        self._caret_visible = True
        self.viewport().update()
        self.status_changed.emit()

    def _sync_text_cursor(self):
        """把真正的 QTextCursor 擺到矩形游標所在位置。

        這樣捲動、ensureCursorVisible、以及輸入法候選窗的定位都能沿用 Qt 原生行為。
        """
        blk = self.document().findBlockByNumber(self._caret.line)
        if not blk.isValid():
            return
        idx = col_to_index(
            blk.text(),
            self._caret.col,
            tab_width=self.options.tab_width,
            ambiguous_wide=self.options.ambiguous_wide,
        )
        cur = self.textCursor()
        self._syncing = True
        cur.setPosition(blk.position() + idx)
        self.setTextCursor(cur)
        self._syncing = False
        self.ensureCursorVisible()

    def _on_cursor_moved(self):
        self._highlight_current_line()
        if not self._syncing and self._block_on and not self._dragging:
            pass  # 由鍵盤/滑鼠處理器決定何時離開，這裡不主動退出
        self.status_changed.emit()

    def _toggle_caret(self):
        self._caret_visible = not self._caret_visible
        self.viewport().update()

    # ------------------------------------------------------------------
    # 繪製
    # ------------------------------------------------------------------
    def paintEvent(self, event):
        super().paintEvent(event)
        if not self._block_on:
            return
        region = self.region()
        painter = QPainter(self.viewport())
        fill = QColor(self.palette().highlight().color())
        fill.setAlpha(90)
        edge = QColor(self.palette().highlight().color())
        caret_color = QColor("#d1322a")

        x1 = self._x_for_col(region.left)
        x2 = self._x_for_col(region.right)
        xc = self._x_for_col(self._caret.col)

        blk = self.firstVisibleBlock()
        offset = self.contentOffset()
        top = self.blockBoundingGeometry(blk).translated(offset).top()
        while blk.isValid() and top <= event.rect().bottom():
            height = self.blockBoundingRect(blk).height()
            n = blk.blockNumber()
            if region.top <= n <= region.bottom and blk.isVisible():
                rect = QRect(int(x1), int(top), max(1, int(x2 - x1)), int(height))
                if region.is_empty_width:
                    # 寬度為零 = 多重游標，只畫一條細線標示範圍
                    painter.fillRect(QRect(int(x1), int(top), 1, int(height)), edge)
                else:
                    painter.fillRect(rect, fill)
                if self._caret_visible:
                    painter.fillRect(
                        QRect(int(xc), int(top), 2, int(height)), caret_color
                    )
            blk = blk.next()
            top += height
        painter.end()

    # ------------------------------------------------------------------
    # 滑鼠
    # ------------------------------------------------------------------
    def _block_start_from_mouse(self, event) -> bool:
        mods = event.modifiers()
        alt = bool(mods & Qt.KeyboardModifier.AltModifier)
        return alt or self._sticky

    def mousePressEvent(self, event):
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._block_start_from_mouse(event)
        ):
            pos = event.position().toPoint()
            line = self.cursorForPosition(pos).blockNumber()
            col = self._col_for_x(pos.x())
            self.start_block_mode(line, col)
            self._dragging = True
            event.accept()
            return
        self.exit_block_mode()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
            pos = event.position().toPoint()
            self._last_drag_pos = pos
            vp = self.viewport().rect()
            if pos.y() < vp.top() or pos.y() > vp.bottom() or pos.x() > vp.right():
                if not self._autoscroll.isActive():
                    self._autoscroll.start()
            else:
                self._autoscroll.stop()
            self._update_drag(pos)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def _update_drag(self, pos):
        line = self.cursorForPosition(pos).blockNumber()
        col = self._col_for_x(pos.x())
        self._move_caret(line, col, extend=True)

    def _do_autoscroll(self):
        if not self._dragging or self._last_drag_pos is None:
            self._autoscroll.stop()
            return
        pos = self._last_drag_pos
        vp = self.viewport().rect()
        vbar = self.verticalScrollBar()
        hbar = self.horizontalScrollBar()
        if pos.y() < vp.top():
            vbar.setValue(vbar.value() - 1)
        elif pos.y() > vp.bottom():
            vbar.setValue(vbar.value() + 1)
        if pos.x() > vp.right():
            hbar.setValue(hbar.value() + 2)
        elif pos.x() < vp.left():
            hbar.setValue(hbar.value() - 2)
        self._update_drag(pos)

    def mouseReleaseEvent(self, event):
        if self._dragging:
            self._dragging = False
            self._autoscroll.stop()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if self._block_on and not self._sticky:
            self.exit_block_mode()
        super().mouseDoubleClickEvent(event)

    # ------------------------------------------------------------------
    # 鍵盤
    # ------------------------------------------------------------------
    _NAV_KEYS = {
        Qt.Key.Key_Left,
        Qt.Key.Key_Right,
        Qt.Key.Key_Up,
        Qt.Key.Key_Down,
        Qt.Key.Key_Home,
        Qt.Key.Key_End,
        Qt.Key.Key_PageUp,
        Qt.Key.Key_PageDown,
    }

    #: (按鍵, 是否按 Ctrl) -> 命令層的游標移動名稱
    _MOVE_BY_KEY = {
        (Qt.Key.Key_Left, False): "left",
        (Qt.Key.Key_Left, True): "word_left",
        (Qt.Key.Key_Right, False): "right",
        (Qt.Key.Key_Right, True): "word_right",
        (Qt.Key.Key_Up, False): "up",
        (Qt.Key.Key_Down, False): "down",
        (Qt.Key.Key_Home, False): "home",
        (Qt.Key.Key_Home, True): "doc_start",
        (Qt.Key.Key_End, False): "end",
        (Qt.Key.Key_End, True): "doc_end",
        (Qt.Key.Key_PageUp, False): "page_up",
        (Qt.Key.Key_PageDown, False): "page_down",
    }

    def keyPressEvent(self, event: QKeyEvent):
        """把按鍵翻成語意命令再交給 perform()。

        走這一層而不是直接動文件，是為了讓每個編輯動作都自動具備可錄製性
        （SRS-002 D-01 / F-MC-07）——新增功能時不會忘了接巨集。
        無法對應到命令的按鍵才落回 QPlainTextEdit 的預設處理。
        """
        mods = event.modifiers()
        alt = bool(mods & Qt.KeyboardModifier.AltModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        key = event.key()

        # 從一般模式用 Alt+Shift+方向鍵直接開始欄選取
        if not self._block_on and alt and shift and key in self._NAV_KEYS:
            self.perform("block_begin")

        if self._block_on and self._handle_block_key(event, key, alt, shift, ctrl):
            return

        command = self._normal_command_for(event, key, ctrl, shift, alt)
        if command is not None:
            name, args = command
            self.perform(name, **args)
            return
        super().keyPressEvent(event)

    def _normal_command_for(self, event, key, ctrl, shift, alt):
        """一般模式的按鍵 -> (命令名稱, 參數)。無對應時回傳 None。"""
        if key == Qt.Key.Key_Backspace:
            return ("delete_word_left" if ctrl else "delete_left", {})
        if key == Qt.Key.Key_Delete:
            return ("delete_word_right" if ctrl else "delete_right", {})
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not ctrl:
            return ("newline", {})
        if key in self._NAV_KEYS and not alt:
            op = self._MOVE_BY_KEY.get((key, ctrl))
            if op is not None:
                return ("move", {"op": op, "select": shift})
            return None
        text = event.text()
        if text and not ctrl and not alt and (text.isprintable() or text == "\t"):
            return ("insert_text", {"text": text})
        return None

    def _handle_block_key(self, event, key, alt, shift, ctrl) -> bool:
        """欄模式的按鍵。回傳 False 代表「請退回一般模式處理這個鍵」。"""
        if key == Qt.Key.Key_Escape:
            self.perform("block_end")
            return True

        if key in self._NAV_KEYS:
            if alt and shift:
                self._extend_by_key(key)
                return True
            self.exit_block_mode()
            return False

        if key == Qt.Key.Key_Backspace:
            self.perform("block_delete", direction="left")
            return True
        if key == Qt.Key.Key_Delete:
            self.perform("block_delete", direction="right")
            return True

        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.exit_block_mode()
            return False

        if ctrl and key == Qt.Key.Key_C:
            self.perform("copy")
            return True
        if ctrl and key == Qt.Key.Key_X:
            self.perform("cut")
            return True
        if ctrl and key == Qt.Key.Key_V:
            self.perform("paste")
            return True
        if ctrl and key in (Qt.Key.Key_Z, Qt.Key.Key_Y, Qt.Key.Key_A):
            self.exit_block_mode()
            return False

        if key == Qt.Key.Key_Tab:
            self.perform("block_insert", text=" " * self.options.tab_width)
            return True

        text = event.text()
        if text and text.isprintable() and not ctrl:
            self.perform("block_insert", text=text)
            return True
        return False

    def _extend_by_key(self, key):
        """Alt+Shift+方向鍵展開矩形。

        一律錄成相對位移（BR-MC-6），重播時才能套用到別的位置；
        Home/End 的位移與該行內容相關，改錄成 edge 命令而不是欄位差值。
        """
        rows = max(1, self.viewport().height() // max(1, self.fontMetrics().height()))
        deltas = {
            Qt.Key.Key_Left: (0, -1),
            Qt.Key.Key_Right: (0, 1),
            Qt.Key.Key_Up: (-1, 0),
            Qt.Key.Key_Down: (1, 0),
            Qt.Key.Key_PageUp: (-rows, 0),
            Qt.Key.Key_PageDown: (rows, 0),
        }
        if key in deltas:
            dline, dcol = deltas[key]
            self.perform("block_extend", dline=dline, dcol=dcol)
        elif key == Qt.Key.Key_Home:
            self.perform("block_extend_edge", edge="home")
        elif key == Qt.Key.Key_End:
            self.perform("block_extend_edge", edge="end")

    # ------------------------------------------------------------------
    # 書籤（SRS-002 F-BM-*）
    # ------------------------------------------------------------------
    def _on_contents_change(self, position: int, removed: int, added: int):
        """文件增減行時平移書籤（BR-BM-1、BR-BM-2）。

        Qt 的 contentsChange 給的是「字元」增減，換算不出行數，所以改用
        blockCount 的前後差值；訊號發出時文件已更新，findBlock(position)
        取到的就是變動起點所在的那一行。
        """
        count = self.blockCount()
        delta = count - self._prev_block_count
        self._prev_block_count = count
        if delta and len(self.bookmarks):
            start = self.document().findBlock(position).blockNumber()
            self.bookmarks.apply_line_delta(start, delta)
            self._notify_bookmarks()

    def _notify_bookmarks(self):
        self._gutter.update()
        self.bookmarks_changed.emit()
        self.status_changed.emit()

    def setPlainText(self, text: str):
        """換掉整份文件內容時清掉書籤——它們標的是舊內容的行。"""
        self.bookmarks.clear()
        super().setPlainText(text)
        self._prev_block_count = self.blockCount()
        self._notify_bookmarks()

    def toggle_bookmark(self, line: int | None = None) -> bool:
        """F-BM-01"""
        if line is None:
            line = self.textCursor().blockNumber()
        state = self.bookmarks.toggle(line)
        self._notify_bookmarks()
        return state

    def _goto_line(self, line: int):
        self.exit_block_mode()
        blk = self.document().findBlockByNumber(line)
        if not blk.isValid():
            return
        cur = self.textCursor()
        cur.setPosition(blk.position())
        self.setTextCursor(cur)
        self.ensureCursorVisible()

    def goto_next_bookmark(self) -> bool:
        """F-BM-02。沒有書籤時回傳 False（BR-BM-4）。"""
        self.bookmarks.clamp(self.blockCount())
        target = self.bookmarks.next_after(self.textCursor().blockNumber())
        if target is None:
            return False
        self._goto_line(target)
        return True

    def goto_prev_bookmark(self) -> bool:
        """F-BM-03"""
        self.bookmarks.clamp(self.blockCount())
        target = self.bookmarks.prev_before(self.textCursor().blockNumber())
        if target is None:
            return False
        self._goto_line(target)
        return True

    def clear_bookmarks(self):
        """F-BM-05"""
        self.bookmarks.clear()
        self._notify_bookmarks()

    def invert_bookmarks(self):
        """F-BM-09"""
        self.bookmarks.invert(self.blockCount())
        self._notify_bookmarks()

    def bookmarked_lines_text(self) -> str:
        """F-BM-06：所有書籤行的文字，依行號由小到大。"""
        self.bookmarks.clamp(self.blockCount())
        return "\n".join(self._line_text(n) for n in self.bookmarks)

    def copy_bookmarked_lines(self) -> int:
        """F-BM-06"""
        text = self.bookmarked_lines_text()
        if not text and not len(self.bookmarks):
            return 0
        QApplication.clipboard().setText(text)
        return len(self.bookmarks)

    def delete_bookmarked_lines(self) -> int:
        """F-BM-08：刪除所有書籤行，整批包在同一個 undo 區塊。"""
        self.bookmarks.clamp(self.blockCount())
        ranges = self.bookmarks.contiguous_ranges()  # 由大到小，從尾端刪不位移
        if not ranges:
            return 0
        removed = sum(end - start + 1 for start, end in ranges)
        doc = self.document()
        cur = QTextCursor(doc)
        cur.beginEditBlock()
        try:
            for start, end in ranges:
                first = doc.findBlockByNumber(start)
                last = doc.findBlockByNumber(end)
                if not first.isValid() or not last.isValid():
                    continue
                c = QTextCursor(doc)
                c.setPosition(first.position())
                end_pos = last.position() + last.length() - 1
                if last.next().isValid():
                    end_pos += 1  # 連同該行的換行字元一起刪掉
                elif first.previous().isValid():
                    c.setPosition(first.position() - 1)  # 最後一行改吃前面的換行
                c.setPosition(end_pos, QTextCursor.MoveMode.KeepAnchor)
                c.removeSelectedText()
        finally:
            cur.endEditBlock()
        self.bookmarks.clear()
        self._notify_bookmarks()
        return removed

    def cut_bookmarked_lines(self) -> int:
        """F-BM-07"""
        count = self.copy_bookmarked_lines()
        if count:
            self.delete_bookmarked_lines()
        return count

    def _doc_lines(self):
        """給命令層取用的行陣列介面。"""
        return _DocLines(self.document())

    # ------------------------------------------------------------------
    # 中文輸入法
    # ------------------------------------------------------------------
    def inputMethodEvent(self, event: QInputMethodEvent):
        """組字過程交給 Qt 原生顯示，只攔截「送出」那一刻套用到整個矩形。

        直接讓 base class 處理 commitString 會把字只插到游標那一行，
        所以這裡把 commit 抽掉、改由 block_insert_text() 逐行套用。
        """
        if not self._block_on:
            super().inputMethodEvent(event)
            # 一般模式的送出交給 Qt 原生插入，這裡只補記一筆給巨集（F-MC-07）
            if event.commitString() and self.recorder.recording:
                self.recorder.record("insert_text", text=event.commitString())
            return
        commit = event.commitString()
        preedit = event.preeditString()
        # 只把預編輯（組字中、尚未確定）交給原生繪製，游標那行會顯示候選字串
        passthrough = QInputMethodEvent(preedit, event.attributes())
        super().inputMethodEvent(passthrough)
        if commit:
            self.block_insert_text(commit)

    # ------------------------------------------------------------------
    # 欄模式的文字異動
    # ------------------------------------------------------------------
    def _apply_edits(self, edits):
        if not edits:
            return
        doc = self.document()
        cur = QTextCursor(doc)
        cur.beginEditBlock()
        try:
            for e in edits:
                blk = doc.findBlockByNumber(e.line)
                if not blk.isValid():
                    continue
                c = QTextCursor(doc)
                c.setPosition(blk.position() + min(e.start, blk.length() - 1))
                c.setPosition(
                    blk.position() + min(e.end, blk.length() - 1),
                    QTextCursor.MoveMode.KeepAnchor,
                )
                c.insertText(e.text)
        finally:
            cur.endEditBlock()

    def block_insert_text(self, text: str):
        """把 text 插入矩形的每一行（矩形有寬度時等於取代）。"""
        if not self._block_on or "\n" in text:
            return
        region = self.region()
        lines = _DocLines(self.document())
        edits = B.edits_for_insert(lines, region, text, options=self.options)
        self._apply_edits(edits)
        width = display_width(
            text,
            tab_width=self.options.tab_width,
            ambiguous_wide=self.options.ambiguous_wide,
        )
        col = region.left + width
        self._anchor = Pos(region.top, col)
        self._caret = Pos(self._caret.line, col)
        self._move_caret(self._caret.line, col, extend=True)

    def _delete_region(self, region: B.BlockRegion, collapse_left: bool):
        lines = _DocLines(self.document())
        edits = B.edits_for_delete(lines, region, options=self.options)
        self._apply_edits(edits)
        col = region.left
        self._anchor = Pos(region.top, col)
        self._caret = Pos(self._caret.line, col)
        self._move_caret(self._caret.line, col, extend=True)

    def block_delete(self):
        if self._block_on:
            self._delete_region(self.region(), collapse_left=True)

    def block_text(self) -> list[str]:
        return B.extract_block(
            _DocLines(self.document()), self.region(), options=self.options
        )

    # ------------------------------------------------------------------
    # 剪貼簿（矩形）
    # ------------------------------------------------------------------
    def copy(self):
        if not self._block_on:
            super().copy()
            return
        from PySide6.QtCore import QMimeData

        segments = self.block_text()
        data = QMimeData()
        payload = "\n".join(segments)
        data.setText(payload)
        data.setData(BLOCK_MIME, payload.encode("utf-8"))
        QApplication.clipboard().setMimeData(data)

    def cut(self):
        if not self._block_on:
            super().cut()
            return
        self.copy()
        self.block_delete()

    def paste(self):
        data = QApplication.clipboard().mimeData()
        is_block = data.hasFormat(BLOCK_MIME)
        text = data.text() if data.hasText() else ""
        if not self._block_on:
            if is_block:
                self._paste_as_block(
                    self.textCursor().blockNumber(),
                    self.caret_display_col(),
                    text.split("\n"),
                )
                return
            super().paste()
            return
        if not text:
            return
        segments = text.split("\n")
        region = self.region()
        if len(segments) == 1 and not is_block:
            self.block_insert_text(segments[0])
            return
        # 先清掉矩形範圍，再逐行貼上
        if not region.is_empty_width:
            self._apply_edits(
                B.edits_for_delete(
                    _DocLines(self.document()), region, options=self.options
                )
            )
        self._paste_as_block(region.top, region.left, segments)

    def _paste_as_block(self, top: int, col: int, segments: list[str]):
        needed = top + len(segments) - self.blockCount()
        doc = self.document()
        if needed > 0:
            cur = QTextCursor(doc)
            cur.movePosition(QTextCursor.MoveOperation.End)
            cur.beginEditBlock()
            cur.insertText("\n" * needed)
            cur.endEditBlock()
        edits = B.edits_for_segments(
            _DocLines(doc), top, col, segments, options=self.options
        )
        self._apply_edits(edits)
        last = top + len(segments) - 1
        width = max(
            (
                display_width(
                    s,
                    tab_width=self.options.tab_width,
                    ambiguous_wide=self.options.ambiguous_wide,
                )
                for s in segments
            ),
            default=0,
        )
        self._block_on or self.start_block_mode(top, col)
        self._anchor = Pos(top, col)
        self._move_caret(last, col + width, extend=True)

    # ------------------------------------------------------------------
    # 欄位編輯器（Notepad++ Column Editor）
    # ------------------------------------------------------------------
    def column_insert_text(self, text: str):
        """在矩形每一行插入同一段文字。"""
        self.block_insert_text(text)

    def column_insert_numbers(
        self,
        initial: int,
        increase: int,
        repeat: int,
        base: int,
        leading_zeros: bool,
    ):
        """在矩形每一行插入遞增數列。"""
        if not self._block_on:
            return
        region = self.region()
        segments = B.number_sequence(
            region.line_count, initial, increase, repeat, base, leading_zeros
        )
        lines = _DocLines(self.document())
        if not region.is_empty_width:
            self._apply_edits(B.edits_for_delete(lines, region, options=self.options))
        edits = B.edits_for_segments(
            lines, region.top, region.left, segments, options=self.options
        )
        self._apply_edits(edits)
        width = max((len(s) for s in segments), default=0)
        self._anchor = Pos(region.top, region.left)
        self._move_caret(region.bottom, region.left + width, extend=True)

    # ------------------------------------------------------------------
    # 狀態列資訊
    # ------------------------------------------------------------------
    def status_text(self) -> str:
        cur = self.textCursor()
        line = cur.blockNumber() + 1
        if self._block_on:
            r = self.region()
            rows = r.line_count
            cols = r.right - r.left
            kind = "多重游標" if r.is_empty_width else "矩形選取"
            return (
                f"行 {self._caret.line + 1}   欄 {self._caret.col + 1}   "
                f"[欄模式] {kind} {rows} 行 × {cols} 欄"
            )
        col = self.caret_display_col() + 1
        idx = cur.positionInBlock() + 1
        sel = ""
        if cur.hasSelection():
            n = len(cur.selectedText())
            sel = f"   已選 {n} 字"
        return f"行 {line}   欄 {col}   字元 {idx}{sel}"
