"""摺疊在編輯器中的整合測試。對應 SRS-003 F-FD-*、BR-FD-*、D-02、D-05。"""

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtCore import QPointF

CODE = "\n".join(
    [
        "def 外層():",        # 0
        "    a = 1",          # 1
        "    if a:",          # 2
        "        b = 2",      # 3
        "    return a",       # 4
        "",                   # 5
        "def 其他():",        # 6
        "    pass",           # 7
    ]
)


def visible(ed):
    doc = ed.document()
    return [
        n for n in range(ed.blockCount()) if doc.findBlockByNumber(n).isVisible()
    ]


def goto(ed, line):
    cur = ed.textCursor()
    cur.setPosition(ed.document().findBlockByNumber(line).position())
    ed.setTextCursor(cur)


def press(ed, key, text="", mods=Qt.KeyboardModifier.NoModifier):
    ed.keyPressEvent(QKeyEvent(QKeyEvent.Type.KeyPress, key, mods, text))


# -- 偵測與基本摺疊 -----------------------------------------------------
def test_foldable_lines_are_detected(editor):
    editor.setPlainText(CODE)
    assert editor.foldable_at(0) is not None
    assert editor.foldable_at(2) is not None
    assert editor.foldable_at(1) is None  # 一般行不可摺疊


def test_br_fd_2_folding_hides_content_but_keeps_the_header(editor):
    editor.setPlainText(CODE)
    editor.toggle_fold(0)
    assert 0 in visible(editor)
    assert visible(editor) == [0, 5, 6, 7]


def test_unfolding_restores_the_lines(editor):
    editor.setPlainText(CODE)
    editor.toggle_fold(0)
    editor.toggle_fold(0)
    assert visible(editor) == list(range(8))


def test_folding_from_a_line_inside_the_block_folds_the_enclosing_block(editor):
    editor.setPlainText(CODE)
    goto(editor, 3)
    assert editor.toggle_fold() is True
    assert 2 in editor.folds  # 摺疊包住游標的最內層區塊


def test_toggle_on_a_line_with_no_block_reports_false(editor):
    editor.setPlainText("a = 1\nb = 2")
    goto(editor, 0)
    assert editor.toggle_fold() is False


# -- 全部摺疊 / 展開 / 層級 --------------------------------------------
def test_f_fd_03_04_fold_all_and_unfold_all(editor):
    editor.setPlainText(CODE)
    editor.fold_all()
    assert visible(editor) == [0, 5, 6]
    editor.unfold_all()
    assert visible(editor) == list(range(8))


def test_f_fd_05_fold_to_level_keeps_outer_blocks_open(editor):
    editor.setPlainText(CODE)
    editor.fold_to_level(1)  # 只摺內層
    assert editor.folds.lines() == [2]
    assert visible(editor) == [0, 1, 2, 4, 5, 6, 7]


def test_br_fd_3_inner_fold_survives_unfolding_the_outer_block(editor):
    editor.setPlainText(CODE)
    editor.toggle_fold(2)  # 先摺內層
    editor.toggle_fold(0)  # 再摺外層
    assert visible(editor) == [0, 5, 6, 7]
    editor.toggle_fold(0)  # 展開外層，內層應維持摺疊
    assert visible(editor) == [0, 1, 2, 4, 5, 6, 7]


# -- 游標與導航（BR-FD-5、BR-FD-6）-------------------------------------
def test_br_fd_6_cursor_is_moved_out_of_hidden_lines(editor):
    editor.setPlainText(CODE)
    goto(editor, 3)
    editor.toggle_fold(0)
    assert editor.textCursor().block().isVisible()
    assert editor.textCursor().blockNumber() == 0


def test_br_fd_5_goto_line_unfolds_to_reveal_the_target(editor):
    editor.setPlainText(CODE)
    editor.toggle_fold(0)
    editor._goto_line(3)
    assert editor.textCursor().blockNumber() == 3
    assert editor.document().findBlockByNumber(3).isVisible()


def test_br_fd_5_search_unfolds_to_reveal_the_match(editor):
    editor.setPlainText(CODE)
    editor.toggle_fold(0)
    goto(editor, 0)
    assert editor.perform("find_next", pattern="b = 2") is True
    assert editor.document().findBlockByNumber(3).isVisible()


def test_br_fd_5_bookmark_navigation_unfolds(editor):
    editor.setPlainText(CODE)
    editor.toggle_bookmark(3)
    editor.toggle_fold(0)
    goto(editor, 6)
    assert editor.goto_next_bookmark() is True
    assert editor.document().findBlockByNumber(3).isVisible()


def test_cursor_down_skips_folded_lines(editor):
    editor.setPlainText(CODE)
    editor.toggle_fold(0)
    goto(editor, 0)
    press(editor, Qt.Key.Key_Down)
    assert editor.textCursor().blockNumber() == 5  # 跳過 1-4


def test_cursor_up_skips_folded_lines(editor):
    editor.setPlainText(CODE)
    editor.toggle_fold(0)
    goto(editor, 5)
    press(editor, Qt.Key.Key_Up)
    assert editor.textCursor().blockNumber() == 0


# -- 編輯後的行為（BR-FD-4）-------------------------------------------
def test_br_fd_4_fold_state_shifts_when_lines_are_inserted_above(editor):
    editor.setPlainText(CODE)
    editor.toggle_fold(6)
    goto(editor, 0)
    press(editor, Qt.Key.Key_Return)
    press(editor, Qt.Key.Key_Return)
    assert editor.folds.lines() == [8]
    assert editor._line_text(8) == "def 其他():"


def test_br_fd_4_regions_are_recomputed_after_editing(editor):
    editor.setPlainText("def f():\n    a")
    assert editor.foldable_at(0) is not None
    editor.setPlainText("a = 1\nb = 2")
    assert editor.foldable_at(0) is None


def test_loading_a_new_document_clears_folds(editor):
    editor.setPlainText(CODE)
    editor.fold_all()
    editor.setPlainText("完全不同\n的內容")
    assert len(editor.folds) == 0
    assert visible(editor) == [0, 1]


# -- 大括號語言（D-01）-------------------------------------------------
def test_brace_style_is_used_for_c_like_files(editor):
    editor.set_fold_style_for("main.c")
    editor.setPlainText("int main() {\n    return 0;\n}\n")
    assert editor.foldable_at(0) is not None


def test_indent_style_is_the_default(editor):
    editor.set_fold_style_for("notes.txt")
    editor.setPlainText("標題\n    內容\n")
    assert editor.foldable_at(0) is not None


# -- 行號欄互動（F-FD-01）---------------------------------------------
def test_clicking_the_fold_column_toggles_the_block(editor):
    editor.setPlainText(CODE)
    editor.resize(600, 400)
    editor.show()
    gutter = editor._gutter
    x = gutter.width() - 6  # 摺疊欄
    event = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(x, 5),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    gutter.mousePressEvent(event)
    assert 0 in editor.folds


def test_clicking_the_bookmark_column_toggles_a_bookmark(editor):
    editor.setPlainText(CODE)
    editor.resize(600, 400)
    editor.show()
    gutter = editor._gutter
    event = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(3, 5),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    gutter.mousePressEvent(event)
    assert 0 in editor.bookmarks


# -- 巨集可錄製 ---------------------------------------------------------
def test_fold_commands_are_recordable(editor):
    editor.setPlainText(CODE)
    goto(editor, 0)
    editor.recorder.start()
    editor.perform("fold_all")
    editor.perform("unfold_all")
    macro = editor.recorder.stop()
    assert [s.command for s in macro.steps] == ["fold_all", "unfold_all"]


def test_doc_lines_adapter_raises_indexerror_past_the_end(editor):
    """_DocLines 只有 __getitem__，超出範圍必須拋 IndexError。

    原本回傳空字串，導致 enumerate() 走舊式迭代協定時永遠停不下來，
    摺疊偵測一跑就當掉。
    """
    import pytest

    editor.setPlainText("一\n二")
    lines = editor._doc_lines()
    assert len(lines) == 2
    assert lines[1] == "二"
    with pytest.raises(IndexError):
        lines[2]
    assert list(enumerate(lines)) == [(0, "一"), (1, "二")]
