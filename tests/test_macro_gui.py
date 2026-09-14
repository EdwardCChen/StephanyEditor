"""巨集錄製與重播的整合測試。對應 SRS-002 F-MC-*、BR-MC-*、D-01。"""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QInputMethodEvent, QKeyEvent

from stephany.core.macro import Macro, MacroStep


def press(ed, key, text="", mods=Qt.KeyboardModifier.NoModifier):
    ed.keyPressEvent(QKeyEvent(QKeyEvent.Type.KeyPress, key, mods, text))


def type_text(ed, text):
    for ch in text:
        press(ed, Qt.Key.Key_A, ch)


def goto(ed, line, col=0):
    blk = ed.document().findBlockByNumber(line)
    cur = ed.textCursor()
    cur.setPosition(blk.position() + col)
    ed.setTextCursor(cur)


# -- 錄製（D-01：錄的是語意命令）---------------------------------------
def test_d_01_keystrokes_are_recorded_as_semantic_commands(editor):
    editor.setPlainText("")
    editor.recorder.start()
    type_text(editor, "ab")
    press(editor, Qt.Key.Key_Left)
    macro = editor.recorder.stop()
    assert [s.command for s in macro.steps] == ["insert_text", "move"]
    assert macro.steps[0].args == {"text": "ab"}  # BR-MC-1 已合併
    assert macro.steps[1].args == {"op": "left", "select": False}


def test_f_mc_07_ime_commit_is_recorded_in_normal_mode(editor):
    editor.setPlainText("")
    editor.recorder.start()
    event = QInputMethodEvent("", [])
    event.setCommitString("測試")
    editor.inputMethodEvent(event)
    macro = editor.recorder.stop()
    assert macro.steps == [MacroStep("insert_text", {"text": "測試"})]


def test_nothing_is_recorded_when_not_recording(editor):
    editor.setPlainText("")
    type_text(editor, "abc")
    assert editor.recorder.stop().steps == []


# -- 重播 ---------------------------------------------------------------
def test_f_mc_02_replay_repeats_the_recorded_edit(editor):
    editor.setPlainText("")
    editor.recorder.start()
    type_text(editor, "→")
    macro = editor.recorder.stop()
    done, error = editor.replay(macro)
    assert (done, error) == (1, None)
    assert editor.toPlainText() == "→→"


def test_f_mc_03_replay_multiple_times(editor):
    editor.setPlainText("")
    macro = Macro("x", [MacroStep("insert_text", {"text": "*"})])
    done, error = editor.replay(macro, count=5)
    assert (done, error) == (5, None)
    assert editor.toPlainText() == "*****"


def test_replay_records_nothing_even_if_recorder_was_used_before(editor):
    editor.setPlainText("")
    macro = Macro("x", [MacroStep("insert_text", {"text": "a"})])
    editor.replay(macro)
    assert editor.recorder.pending_count == 0


def test_br_mc_2_whole_replay_is_a_single_undo_step(editor):
    editor.setPlainText("開始")
    macro = Macro("x", [MacroStep("insert_text", {"text": "#"})])
    editor.replay(macro, count=10)
    assert editor.toPlainText() == "##########開始"
    editor.undo()
    assert editor.toPlainText() == "開始"


def test_br_mc_5_cannot_replay_while_recording(editor):
    editor.setPlainText("")
    editor.recorder.start()
    done, error = editor.replay(Macro("x", [MacroStep("insert_text", {"text": "a"})]))
    assert done == 0
    assert "錄製中" in error
    editor.recorder.cancel()


def test_br_mc_4_failing_step_stops_replay_and_reports(editor):
    editor.setPlainText("abc")
    macro = Macro(
        "x",
        [
            MacroStep("insert_text", {"text": "1"}),
            MacroStep("find_next", {"pattern": "這個字串不存在"}),
            MacroStep("insert_text", {"text": "2"}),
        ],
    )
    done, error = editor.replay(macro)
    assert done == 0
    assert "第 2 步" in error
    assert "2" not in editor.toPlainText()  # 第 3 步沒有被執行


def test_unknown_command_is_reported_not_raised(editor):
    editor.setPlainText("")
    done, error = editor.replay(Macro("x", [MacroStep("不存在的命令", {})]))
    assert done == 0
    assert "未知的命令" in error


def test_empty_macro_is_reported(editor):
    done, error = editor.replay(Macro("x", []))
    assert (done, error) == (0, "巨集是空的")


# -- 直到檔尾（BR-MC-3）------------------------------------------------
def test_br_mc_3_until_eof_stops_at_end_of_document(editor):
    editor.setPlainText("一\n二\n三")
    goto(editor, 0)
    macro = Macro("x", [MacroStep("move", {"op": "doc_end"})])
    done, error = editor.replay(macro, until_eof=True)
    assert error is None
    assert done == 1  # 第一輪就到檔尾，不再跑第二輪


def test_br_mc_3_until_eof_stops_when_macro_makes_no_progress(editor):
    editor.setPlainText("內容")
    goto(editor, 0)
    macro = Macro("x", [MacroStep("bookmark_toggle", {})])
    done, error = editor.replay(macro, until_eof=True)
    assert error is None
    assert done == 1  # 偵測到空轉就停，不會無窮迴圈


def test_until_eof_processes_every_line(editor):
    editor.setPlainText("甲\n乙\n丙\n丁")
    goto(editor, 0)
    macro = Macro(
        "加註",
        [
            MacroStep("insert_text", {"text": "※"}),
            MacroStep("move", {"op": "down"}),
            MacroStep("move", {"op": "home"}),
        ],
    )
    done, error = editor.replay(macro, until_eof=True)
    # 最後一輪會在「游標下移」碰到檔尾——那是停止條件，不是錯誤（不該跳警告）
    assert error is None
    assert done == 4
    assert editor.toPlainText().split("\n") == ["※甲", "※乙", "※丙", "※丁"]


# -- 欄模式（BR-MC-6：相對位移）---------------------------------------
def test_br_mc_6_block_steps_are_recorded_as_relative_offsets(editor):
    editor.setPlainText("aaaa\nbbbb\ncccc")
    goto(editor, 0, 1)
    editor.recorder.start()
    press(editor, Qt.Key.Key_Down, mods=Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.ShiftModifier)
    press(editor, Qt.Key.Key_Down, mods=Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.ShiftModifier)
    press(editor, Qt.Key.Key_X, "中")
    macro = editor.recorder.stop()
    commands = [s.command for s in macro.steps]
    assert commands == ["block_begin", "block_extend", "block_extend", "block_insert"]
    assert macro.steps[1].args == {"dline": 1, "dcol": 0}  # 相對，不是絕對行號
    assert editor.toPlainText().split("\n") == ["a中aaa", "b中bbb", "c中ccc"]


def test_block_macro_replays_at_a_different_position(editor):
    macro = Macro(
        "整欄加註",
        [
            MacroStep("block_begin", {}),
            MacroStep("block_extend", {"dline": 2, "dcol": 0}),
            MacroStep("block_insert", {"text": "|"}),
            MacroStep("block_end", {}),
        ],
    )
    editor.setPlainText("1111\n2222\n3333\n4444\n5555\n6666")
    goto(editor, 3, 2)  # 從完全不同的位置重播
    done, error = editor.replay(macro)
    assert (done, error) == (1, None)
    assert editor.toPlainText().split("\n")[3:] == ["44|44", "55|55", "66|66"]


def test_block_delete_is_recorded_and_replayed(editor):
    editor.setPlainText("abcd\nefgh")
    goto(editor, 0, 1)
    editor.recorder.start()
    press(editor, Qt.Key.Key_Down, mods=Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.ShiftModifier)
    press(editor, Qt.Key.Key_Right, mods=Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.ShiftModifier)
    press(editor, Qt.Key.Key_Delete)
    macro = editor.recorder.stop()
    assert [s.command for s in macro.steps] == [
        "block_begin",
        "block_extend",
        "block_extend",
        "block_delete",
    ]
    assert editor.toPlainText().split("\n") == ["acd", "egh"]


# -- 書籤操作可被錄製（F-MC-07）----------------------------------------
def test_f_mc_07_bookmark_operations_are_recordable(editor):
    editor.setPlainText("a\nb\nc")
    goto(editor, 0)
    editor.recorder.start()
    editor.perform("bookmark_toggle")
    editor.perform("move", op="down")
    editor.perform("bookmark_toggle")
    macro = editor.recorder.stop()
    assert [s.command for s in macro.steps] == [
        "bookmark_toggle",
        "move",
        "bookmark_toggle",
    ]
    assert editor.bookmarks.lines() == [0, 1]


def test_find_next_macro_drives_a_search_and_edit_loop(editor):
    editor.setPlainText("狗 貓 狗 貓 狗")
    goto(editor, 0)
    macro = Macro(
        "狗改成鳥",
        [
            MacroStep("find_next", {"pattern": "狗"}),
            MacroStep("insert_text", {"text": "鳥"}),
        ],
    )
    done, error = editor.replay(macro, count=3)
    assert (done, error) == (3, None)
    assert editor.toPlainText() == "鳥 貓 鳥 貓 鳥"


def test_boundary_stop_is_an_error_in_fixed_count_mode(editor):
    """指定次數模式下跑不完就是失敗——使用者明確要求 N 輪（BR-MC-4）。"""
    editor.setPlainText("甲\n乙")
    goto(editor, 0)
    macro = Macro("x", [MacroStep("move", {"op": "down"})])
    done, error = editor.replay(macro, count=5)
    assert done == 1
    assert "沒有可執行的對象" in error
