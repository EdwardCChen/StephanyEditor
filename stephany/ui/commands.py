"""語意命令層：所有可錄製、可重播的編輯動作。

規格：SRS-002 D-01、F-MC-07、BR-MC-2 ~ BR-MC-6

D-01 決定巨集錄的是「語意命令」而不是原始鍵盤事件，這個檔案就是那層抽象：
鍵盤與選單都經由 `perform()` 進來，執行的同時順手交給錄製器記一筆。
因此「能被使用者操作的」與「能被巨集重播的」永遠是同一組動作，
不會出現某個功能忘了支援巨集的情況。

欄模式的步驟一律記「相對位移」（BR-MC-6），重播時才能套用到別的位置。
"""

from __future__ import annotations

from PySide6.QtCore import QRegularExpression
from PySide6.QtGui import QTextCursor, QTextDocument

from ..core.macro import Macro, ReplayState, should_continue
from ..core.widths import col_to_index, index_to_col

#: 游標移動命令 -> QTextCursor 的移動操作
MOVE_OPS = {
    "left": QTextCursor.MoveOperation.Left,
    "right": QTextCursor.MoveOperation.Right,
    "up": QTextCursor.MoveOperation.Up,
    "down": QTextCursor.MoveOperation.Down,
    "home": QTextCursor.MoveOperation.StartOfLine,
    "end": QTextCursor.MoveOperation.EndOfLine,
    "word_left": QTextCursor.MoveOperation.PreviousWord,
    "word_right": QTextCursor.MoveOperation.NextWord,
    "doc_start": QTextCursor.MoveOperation.Start,
    "doc_end": QTextCursor.MoveOperation.End,
}


class MacroError(RuntimeError):
    """重播中某個步驟失敗（BR-MC-4）。"""


class _BoundaryStop(Exception):
    """「跑到檔尾」模式下某步驟已無對象可做——這是正常結束，不是錯誤。

    例如「每行加註記」的巨集最後一輪會在「游標下移一行」處碰到最後一行。
    在指定次數模式下這算失敗（使用者明確要求跑 N 輪卻跑不完），
    但在跑到檔尾模式下它正是停止條件本身。
    """


class EditorCommands:
    """給 ColumnEditor 混入的命令層。

    預期宿主提供：`recorder`（MacroRecorder）、`bookmarks`（BookmarkSet），
    以及 QPlainTextEdit 的一般 API。
    """

    # ------------------------------------------------------------------
    # 派送
    # ------------------------------------------------------------------
    def perform(self, command: str, *, record: bool = True, **args) -> bool:
        """執行一個語意命令；錄製中就同時記下來。

        回傳 False 代表「這個命令在目前狀態下沒有東西可做」
        （例如沒有書籤時按 F2），重播遇到時會停下來（BR-MC-4）。
        """
        handler = getattr(self, f"cmd_{command}", None)
        if handler is None:
            raise MacroError(f"未知的命令：{command}")
        ok = handler(**args)
        if ok is not False and record and self.recorder.recording:
            self.recorder.record(command, **args)
        return ok is not False

    # ------------------------------------------------------------------
    # 一般模式的編輯命令
    # ------------------------------------------------------------------
    def cmd_insert_text(self, text: str) -> bool:
        if self.block_mode:
            self.block_insert_text(text)
            return True
        cur = self.textCursor()
        cur.insertText(text)
        self.setTextCursor(cur)
        self.ensureCursorVisible()
        return True

    def cmd_newline(self) -> bool:
        self.exit_block_mode()
        cur = self.textCursor()
        cur.insertText("\n")
        self.setTextCursor(cur)
        self.ensureCursorVisible()
        return True

    def cmd_delete_left(self) -> bool:
        cur = self.textCursor()
        if cur.hasSelection():
            cur.removeSelectedText()
        else:
            cur.deletePreviousChar()
        self.setTextCursor(cur)
        return True

    def cmd_delete_right(self) -> bool:
        cur = self.textCursor()
        if cur.hasSelection():
            cur.removeSelectedText()
        else:
            cur.deleteChar()
        self.setTextCursor(cur)
        return True

    def cmd_delete_word_left(self) -> bool:
        cur = self.textCursor()
        cur.movePosition(
            QTextCursor.MoveOperation.PreviousWord, QTextCursor.MoveMode.KeepAnchor
        )
        cur.removeSelectedText()
        self.setTextCursor(cur)
        return True

    def cmd_delete_word_right(self) -> bool:
        cur = self.textCursor()
        cur.movePosition(
            QTextCursor.MoveOperation.NextWord, QTextCursor.MoveMode.KeepAnchor
        )
        cur.removeSelectedText()
        self.setTextCursor(cur)
        return True

    #: 這些移動是冪等的：已經在目標位置時「沒有移動」不算失敗，
    #: 否則巨集裡一個「回到行首」會在游標剛好已在行首時整段中止（BR-MC-4）。
    _IDEMPOTENT_MOVES = frozenset({"home", "end", "doc_start", "doc_end"})

    def cmd_move(self, op: str, select: bool = False) -> bool:
        mode = (
            QTextCursor.MoveMode.KeepAnchor
            if select
            else QTextCursor.MoveMode.MoveAnchor
        )
        cur = self.textCursor()

        if op in ("up", "down", "page_up", "page_down"):
            rows = 1
            if op.startswith("page_"):
                rows = max(
                    1, self.viewport().height() // max(1, self.fontMetrics().height())
                )
            direction = -1 if op in ("up", "page_up") else 1
            moved = self._move_vertical(cur, direction * rows, mode)
        else:
            operation = MOVE_OPS.get(op)
            if operation is None:
                raise MacroError(f"未知的游標移動：{op}")
            moved = cur.movePosition(operation, mode)

        self.setTextCursor(cur)
        self.ensureCursorVisible()
        return True if op in self._IDEMPOTENT_MOVES else moved

    def _move_vertical(self, cur: QTextCursor, rows: int, mode) -> bool:
        """上下移動並保留「顯示欄位」。

        不用 QTextCursor 內建的 Up/Down 有兩個原因：
          1. 它靠的是文字版面的視覺 X 座標，而巨集重播整段包在 beginEditBlock
             裡、版面尚未重算，Up/Down 會掉到行首——重播與互動行為不一致。
          2. 本編輯器一切以顯示欄位為準（中文佔兩欄），自己算才與欄模式一致。
        """
        target_line = cur.blockNumber() + rows
        if target_line < 0 or target_line >= self.blockCount():
            return False
        col = index_to_col(
            cur.block().text(),
            cur.positionInBlock(),
            tab_width=self.options.tab_width,
            ambiguous_wide=self.options.ambiguous_wide,
        )
        blk = self.document().findBlockByNumber(target_line)
        index = col_to_index(
            blk.text(),
            col,
            tab_width=self.options.tab_width,
            ambiguous_wide=self.options.ambiguous_wide,
        )
        cur.setPosition(blk.position() + index, mode)
        return True

    def cmd_select_all(self) -> bool:
        self.exit_block_mode()
        self.selectAll()
        return True

    # ------------------------------------------------------------------
    # 剪貼簿
    # ------------------------------------------------------------------
    def cmd_copy(self) -> bool:
        self.copy()
        return True

    def cmd_cut(self) -> bool:
        self.cut()
        return True

    def cmd_paste(self) -> bool:
        self.paste()
        return True

    # ------------------------------------------------------------------
    # 欄模式（BR-MC-6：一律記相對位移）
    # ------------------------------------------------------------------
    def cmd_block_begin(self) -> bool:
        cur = self.textCursor()
        self.start_block_mode(cur.blockNumber(), self.caret_display_col())
        return True

    def cmd_block_extend(self, dline: int = 0, dcol: int = 0) -> bool:
        if not self.block_mode:
            return False
        self._move_caret(self._caret.line + dline, self._caret.col + dcol, extend=True)
        return True

    def cmd_block_extend_edge(self, edge: str) -> bool:
        """把矩形展開到行首或行尾。

        Home/End 的欄位位移與該行內容有關，錄成欄位差值在別的位置重播會錯，
        所以獨立成一個命令（BR-MC-6）。
        """
        if not self.block_mode:
            return False
        if edge == "home":
            col = 0
        elif edge == "end":
            from ..core.widths import display_width

            col = display_width(
                self._line_text(self._caret.line),
                tab_width=self.options.tab_width,
                ambiguous_wide=self.options.ambiguous_wide,
            )
        else:
            raise MacroError(f"未知的邊界：{edge}")
        self._move_caret(self._caret.line, col, extend=True)
        return True

    def cmd_block_insert(self, text: str) -> bool:
        if not self.block_mode:
            return False
        self.block_insert_text(text)
        return True

    def cmd_block_delete(self, direction: str = "region") -> bool:
        if not self.block_mode:
            return False
        from ..core import block as B

        region = self.region()
        if direction == "left":
            region = B.backspace_region(self._doc_lines(), region, options=self.options)
        elif direction == "right":
            region = B.delete_region(self._doc_lines(), region, options=self.options)
        self._delete_region(region, collapse_left=True)
        return True

    def cmd_block_end(self) -> bool:
        self.exit_block_mode()
        return True

    # ------------------------------------------------------------------
    # 書籤（F-MC-07 要求巨集能錄書籤操作）
    # ------------------------------------------------------------------
    def cmd_bookmark_toggle(self) -> bool:
        self.toggle_bookmark()
        return True

    def cmd_bookmark_next(self) -> bool:
        return self.goto_next_bookmark()

    def cmd_bookmark_prev(self) -> bool:
        return self.goto_prev_bookmark()

    # ------------------------------------------------------------------
    # 搜尋（讓「找到→改掉→再找」這種巨集成立）
    # ------------------------------------------------------------------
    def cmd_find_next(
        self,
        pattern: str,
        case: bool = False,
        word: bool = False,
        regex: bool = False,
        backward: bool = False,
        wrap: bool = False,
    ) -> bool:
        """尋找下一個。繞回（wrap）也在這一層處理，巨集才會錄成單一步驟。"""
        if not pattern:
            return False
        self.exit_block_mode()
        flags = QTextDocument.FindFlag(0)
        if case:
            flags |= QTextDocument.FindFlag.FindCaseSensitively
        if word:
            flags |= QTextDocument.FindFlag.FindWholeWords
        if backward:
            flags |= QTextDocument.FindFlag.FindBackward
        needle: object = pattern
        if regex:
            rx = QRegularExpression(pattern)
            if not case:
                rx.setPatternOptions(
                    QRegularExpression.PatternOption.CaseInsensitiveOption
                )
            if not rx.isValid():
                raise MacroError(f"正規表示式錯誤：{rx.errorString()}")
            needle = rx
        found = self.document().find(needle, self.textCursor(), flags)
        if found.isNull() and wrap:
            restart = QTextCursor(self.document())
            if backward:
                restart.movePosition(QTextCursor.MoveOperation.End)
            found = self.document().find(needle, restart, flags)
        if found.isNull():
            return False
        self.setTextCursor(found)
        self.ensureCursorVisible()
        return True

    # ------------------------------------------------------------------
    # 重播
    # ------------------------------------------------------------------
    def replay(
        self, macro: Macro, count: int = 1, until_eof: bool = False
    ) -> tuple[int, str | None]:
        """重播巨集，回傳（完成的迭代次數, 錯誤訊息或 None）。

        BR-MC-2：整段（含所有迭代）包在單一 undo 區塊，一次 Ctrl+Z 全還原。
        BR-MC-3：until_eof 的停止條件交給 core.macro.should_continue 判斷。
        BR-MC-4：任一步驟失敗即停止，不續跑剩餘步驟。
        BR-MC-5：錄製中不得重播。
        """
        if self.recorder.recording:
            return 0, "錄製中無法播放巨集（BR-MC-5）"
        if not macro.steps:
            return 0, "巨集是空的"

        cur = QTextCursor(self.document())
        cur.beginEditBlock()
        done = 0
        error: str | None = None
        previous: ReplayState | None = None
        try:
            iteration = 0
            while True:
                if until_eof:
                    if iteration > 0 and not should_continue(
                        iteration, self._replay_state(), previous
                    ):
                        break
                elif iteration >= count:
                    break
                previous = self._replay_state()
                try:
                    for index, step in enumerate(macro.steps, start=1):
                        try:
                            ok = self.perform(step.command, record=False, **step.args)
                        except MacroError as exc:
                            raise MacroError(f"第 {index} 步 {step.describe()}：{exc}")
                        if not ok:
                            if until_eof:
                                raise _BoundaryStop()
                            raise MacroError(
                                f"第 {index} 步 {step.describe()} 沒有可執行的對象，已停止"
                            )
                except _BoundaryStop:
                    # 這一輪已經做掉了前面幾步，算它完成
                    done = iteration + 1
                    break
                iteration += 1
                done = iteration
        except MacroError as exc:
            error = str(exc)
        finally:
            cur.endEditBlock()
        return done, error

    def _replay_state(self) -> ReplayState:
        return ReplayState(
            position=self.textCursor().position(),
            length=self.document().characterCount() - 1,
            line_count=self.blockCount(),
        )
