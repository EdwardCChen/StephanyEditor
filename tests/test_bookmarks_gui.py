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

"""書籤在編輯器中的整合測試。對應 SRS-002 F-BM-*、BR-BM-*。"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication


def press(ed, key, text="", mods=Qt.KeyboardModifier.NoModifier):
    ed.keyPressEvent(QKeyEvent(QKeyEvent.Type.KeyPress, key, mods, text))


def goto(ed, line):
    cur = ed.textCursor()
    cur.setPosition(ed.document().findBlockByNumber(line).position())
    ed.setTextCursor(cur)


def test_f_bm_01_toggle_on_current_line(editor):
    editor.setPlainText("一\n二\n三")
    goto(editor, 1)
    assert editor.toggle_bookmark() is True
    assert editor.bookmarks.lines() == [1]
    assert editor.toggle_bookmark() is False
    assert editor.bookmarks.lines() == []


def test_f_bm_02_03_navigation_moves_the_cursor(editor):
    editor.setPlainText("\n".join(str(n) for n in range(10)))
    for line in (2, 6):
        goto(editor, line)
        editor.toggle_bookmark()
    goto(editor, 0)
    assert editor.goto_next_bookmark() is True
    assert editor.textCursor().blockNumber() == 2
    assert editor.goto_next_bookmark() is True
    assert editor.textCursor().blockNumber() == 6
    assert editor.goto_next_bookmark() is True  # BR-BM-3 繞回
    assert editor.textCursor().blockNumber() == 2
    assert editor.goto_prev_bookmark() is True
    assert editor.textCursor().blockNumber() == 6  # 往回也繞回


def test_br_bm_4_navigation_without_bookmarks_returns_false(editor):
    editor.setPlainText("a\nb")
    assert editor.goto_next_bookmark() is False
    assert editor.goto_prev_bookmark() is False


def test_br_bm_1_bookmark_follows_its_line_when_text_inserted_above(editor):
    editor.setPlainText("零\n一\n二\n三")
    goto(editor, 3)
    editor.toggle_bookmark()
    # 在第 0 行行首按兩次 Enter，第 3 行會被推到第 5 行
    goto(editor, 0)
    press(editor, Qt.Key.Key_Return)
    press(editor, Qt.Key.Key_Return)
    assert editor.bookmarks.lines() == [5]
    assert editor._line_text(5) == "三"


def test_br_bm_2_bookmark_disappears_with_its_deleted_line(editor):
    editor.setPlainText("a\nb\nc\nd")
    goto(editor, 2)
    editor.toggle_bookmark()
    # 選取第 1~2 行整段刪掉
    cur = editor.textCursor()
    cur.setPosition(editor.document().findBlockByNumber(1).position())
    cur.setPosition(
        editor.document().findBlockByNumber(3).position(),
        cur.MoveMode.KeepAnchor,
    )
    cur.removeSelectedText()
    editor.setTextCursor(cur)
    assert editor.bookmarks.lines() == []


def test_bookmark_survives_editing_within_the_same_line(editor):
    editor.setPlainText("aaa\nbbb\nccc")
    goto(editor, 1)
    editor.toggle_bookmark()
    press(editor, Qt.Key.Key_X, "x")
    assert editor.bookmarks.lines() == [1]
    assert editor._line_text(1) == "xbbb"


def test_f_bm_06_copy_bookmarked_lines(editor, app):
    editor.setPlainText("甲\n乙\n丙\n丁")
    for line in (0, 2):
        goto(editor, line)
        editor.toggle_bookmark()
    assert editor.copy_bookmarked_lines() == 2
    assert QApplication.clipboard().text() == "甲\n丙"


def test_f_bm_08_delete_bookmarked_lines(editor):
    editor.setPlainText("甲\n乙\n丙\n丁")
    for line in (0, 2):
        goto(editor, line)
        editor.toggle_bookmark()
    assert editor.delete_bookmarked_lines() == 2
    assert editor.toPlainText() == "乙\n丁"
    assert editor.bookmarks.lines() == []


def test_f_bm_08_delete_handles_contiguous_runs_and_last_line(editor):
    editor.setPlainText("a\nb\nc\nd\ne")
    for line in (1, 2, 4):  # 連續的 1-2 加上最後一行
        goto(editor, line)
        editor.toggle_bookmark()
    assert editor.delete_bookmarked_lines() == 3
    assert editor.toPlainText() == "a\nd"


def test_f_bm_07_cut_copies_then_deletes(editor, app):
    editor.setPlainText("甲\n乙\n丙")
    goto(editor, 1)
    editor.toggle_bookmark()
    assert editor.cut_bookmarked_lines() == 1
    assert QApplication.clipboard().text() == "乙"
    assert editor.toPlainText() == "甲\n丙"


def test_delete_bookmarked_lines_is_one_undo_step(editor):
    editor.setPlainText("a\nb\nc\nd")
    for line in (0, 2):
        goto(editor, line)
        editor.toggle_bookmark()
    editor.delete_bookmarked_lines()
    editor.undo()
    assert editor.toPlainText() == "a\nb\nc\nd"


def test_f_bm_09_invert(editor):
    editor.setPlainText("a\nb\nc")
    goto(editor, 1)
    editor.toggle_bookmark()
    editor.invert_bookmarks()
    assert editor.bookmarks.lines() == [0, 2]


def test_f_bm_05_clear(editor):
    editor.setPlainText("a\nb")
    editor.toggle_bookmark(0)
    editor.clear_bookmarks()
    assert len(editor.bookmarks) == 0


def test_loading_a_new_document_clears_bookmarks(editor):
    editor.setPlainText("a\nb")
    editor.toggle_bookmark(0)
    editor.setPlainText("完全不同的內容\n第二行")
    assert len(editor.bookmarks) == 0


def test_bookmarks_changed_signal_fires(editor):
    editor.setPlainText("a\nb")
    seen = []
    editor.bookmarks_changed.connect(lambda: seen.append(1))
    editor.toggle_bookmark(0)
    assert seen
