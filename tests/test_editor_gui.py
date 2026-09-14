"""GUI 層測試。用 offscreen 平台跑，不需要真的開視窗。"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtGui import QInputMethodEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from stephany.ui.editor import ColumnEditor  # noqa: E402


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def editor(app):
    ed = ColumnEditor()
    ed.resize(800, 600)
    return ed


def text_of(ed):
    return ed.toPlainText().split("\n")


def test_block_typing_inserts_on_every_line(editor):
    editor.setPlainText("項目一\n項目二\n項目三")
    editor.start_block_mode(0, 0)
    editor._move_caret(2, 0)
    editor.block_insert_text("※")
    assert text_of(editor) == ["※項目一", "※項目二", "※項目三"]


def test_block_typing_replaces_rectangle(editor):
    editor.setPlainText("abcdef\nghijkl")
    editor.start_block_mode(0, 2)
    editor._move_caret(1, 4)
    editor.block_insert_text("X")
    assert text_of(editor) == ["abXef", "ghXkl"]


def test_input_method_commit_applies_to_whole_block(editor):
    """模擬注音輸入法送出「測試」兩個字。"""
    editor.setPlainText("1\n2\n3")
    editor.start_block_mode(0, 1)
    editor._move_caret(2, 1)
    event = QInputMethodEvent("", [])
    event.setCommitString("測試")
    editor.inputMethodEvent(event)
    assert text_of(editor) == ["1測試", "2測試", "3測試"]


def test_preedit_does_not_modify_document(editor):
    """組字中（尚未送出）不該動到文件內容。"""
    editor.setPlainText("a\nb")
    editor.start_block_mode(0, 1)
    editor._move_caret(1, 1)
    editor.inputMethodEvent(QInputMethodEvent("ㄘㄜ", []))
    assert text_of(editor) == ["a", "b"]


def test_block_delete_across_cjk(editor):
    editor.setPlainText("你好世界\nabcdefgh")
    editor.start_block_mode(0, 1)
    editor._move_caret(1, 5)
    editor.block_delete()
    assert text_of(editor) == ["  界", "afgh"]


def test_undo_reverts_whole_block_operation(editor):
    editor.setPlainText("aaa\nbbb\nccc")
    editor.document().setModified(False)
    editor.start_block_mode(0, 1)
    editor._move_caret(2, 1)
    editor.block_insert_text("中")
    assert text_of(editor) == ["a中aa", "b中bb", "c中cc"]
    editor.undo()
    assert text_of(editor) == ["aaa", "bbb", "ccc"]


def test_block_copy_and_paste_rectangle(editor, app):
    editor.setPlainText("一二三四\n甲乙丙丁\nabcdefgh")
    editor.start_block_mode(0, 2)
    editor._move_caret(2, 6)
    editor.copy()
    assert QApplication.clipboard().text() == "二三\n乙丙\ncdef"
    editor.exit_block_mode()
    editor.setPlainText("....\n....\n....")
    editor.start_block_mode(0, 1)
    editor.paste()
    assert text_of(editor) == [".二三...", ".乙丙...", ".cdef..."]


def test_paste_extends_document_when_too_short(editor):
    editor.setPlainText("x")
    editor.start_block_mode(0, 1)
    editor._paste_as_block(0, 1, ["A", "B", "C"])
    assert text_of(editor) == ["xA", " B", " C"]


def test_column_number_sequence(editor):
    editor.setPlainText("apple\nbanana\ncherry")
    editor.start_block_mode(0, 0)
    editor._move_caret(2, 0)
    editor.column_insert_numbers(8, 1, 1, 10, True)
    assert text_of(editor) == ["08apple", "09banana", "10cherry"]


def test_alt_drag_starts_block_mode(editor, app):
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QMouseEvent

    editor.setPlainText("abcdefgh\nijklmnop")
    editor.show()
    press = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(60, 5),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.AltModifier,
    )
    editor.mousePressEvent(press)
    assert editor.block_mode is True
    editor.exit_block_mode()


def test_sticky_mode_starts_block_without_alt(editor):
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QMouseEvent

    editor.setPlainText("abcdefgh")
    editor.set_sticky_column_mode(True)
    press = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(40, 5),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    editor.mousePressEvent(press)
    assert editor.block_mode is True


def test_status_text_reports_display_column(editor):
    editor.setPlainText("你好abc")
    cur = editor.textCursor()
    cur.setPosition(2)  # 「你好」之後
    editor.setTextCursor(cur)
    assert "欄 5" in editor.status_text()  # 顯示欄位 4 -> 1-based 是 5
