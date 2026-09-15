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

"""主視窗層的整合測試：選單動作真的接到編輯器上。

對應 SRS-002 F-BM-*、F-MC-*、BR-BM-4、BR-MC-5、NF-03。
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from stephany.core.macro import Macro, MacroStep, MacroStore


def press(ed, key, text="", mods=Qt.KeyboardModifier.NoModifier):
    ed.keyPressEvent(QKeyEvent(QKeyEvent.Type.KeyPress, key, mods, text))


def goto(ed, line):
    cur = ed.textCursor()
    cur.setPosition(ed.document().findBlockByNumber(line).position())
    ed.setTextCursor(cur)


# -- 書籤 ---------------------------------------------------------------
def test_bookmark_menu_action_toggles_on_current_line(window):
    ed = window.editor()
    ed.setPlainText("a\nb\nc")
    goto(ed, 1)
    window.act_bm_toggle.trigger()
    assert ed.bookmarks.lines() == [1]


def test_bookmark_navigation_actions_move_the_cursor(window):
    ed = window.editor()
    ed.setPlainText("\n".join("abcdef"))
    goto(ed, 4)
    window.act_bm_toggle.trigger()
    goto(ed, 0)
    window.act_bm_next.trigger()
    assert ed.textCursor().blockNumber() == 4


def test_br_bm_4_navigation_without_bookmarks_shows_a_message(window):
    ed = window.editor()
    ed.setPlainText("a\nb")
    window.act_bm_next.trigger()
    assert "沒有書籤" in window.statusBar().currentMessage()


def test_delete_bookmarked_lines_action(window):
    ed = window.editor()
    ed.setPlainText("甲\n乙\n丙")
    goto(ed, 1)
    window.act_bm_toggle.trigger()
    window.act_bm_delete.trigger()
    assert ed.toPlainText() == "甲\n丙"
    assert "已刪除 1 行" in window.statusBar().currentMessage()


def test_bookmark_count_shows_in_status_bar(window):
    ed = window.editor()
    ed.setPlainText("a\nb\nc")
    goto(ed, 0)
    window.act_bm_toggle.trigger()
    assert "書籤 1" in window.lbl_mode.text()


# -- 巨集 ---------------------------------------------------------------
def test_f_mc_01_record_action_toggles_state_and_label(window):
    window.act_macro_record.trigger()
    assert window.recorder.recording is True
    assert "停止錄製" in window.act_macro_record.text()
    window.act_macro_record.trigger()
    assert window.recorder.recording is False
    assert "開始錄製" in window.act_macro_record.text()


def test_f_mc_08_recording_shows_in_status_bar(window):
    ed = window.editor()
    ed.setPlainText("")
    window.act_macro_record.trigger()
    press(ed, Qt.Key.Key_A, "x")
    window._update_status()
    assert "錄製中" in window.lbl_mode.text()
    window.act_macro_record.trigger()


def test_record_then_play_through_the_window(window):
    ed = window.editor()
    ed.setPlainText("")
    window.act_macro_record.trigger()
    press(ed, Qt.Key.Key_A, "中")
    press(ed, Qt.Key.Key_A, "文")
    window.act_macro_record.trigger()
    window.act_macro_play.trigger()
    assert ed.toPlainText() == "中文中文"


def test_br_mc_5_play_while_recording_is_refused(window):
    ed = window.editor()
    ed.setPlainText("")
    window.act_macro_record.trigger()
    window.act_macro_play.trigger()
    assert "錄製中無法播放" in window.statusBar().currentMessage()
    assert ed.toPlainText() == ""
    window.act_macro_record.trigger()


def test_playing_an_empty_macro_reports_instead_of_crashing(window):
    window.act_macro_play.trigger()
    assert "沒有可播放的巨集" in window.statusBar().currentMessage()


def test_recorder_is_shared_across_tabs(window):
    first = window.editor()
    second = window.new_tab()
    assert second.recorder is window.recorder
    assert first.recorder is second.recorder


def test_macro_recorded_in_one_tab_replays_in_another(window):
    first = window.editor()
    first.setPlainText("")
    window.act_macro_record.trigger()
    press(first, Qt.Key.Key_A, "★")
    window.act_macro_record.trigger()

    second = window.new_tab()
    second.setPlainText("")
    window.act_macro_play.trigger()
    assert second.toPlainText() == "★"


# -- 巨集儲存（F-MC-04、F-MC-06、NF-03）--------------------------------
def test_f_mc_04_06_saved_macro_persists_to_disk(window, tmp_path):
    ed = window.editor()
    ed.setPlainText("")
    window.act_macro_record.trigger()
    press(ed, Qt.Key.Key_A, "※")
    window.act_macro_record.trigger()

    window.macro_store.add(window.recorder.current.renamed("加註記"))

    reloaded = MacroStore(tmp_path / "macros.json")
    reloaded.load()
    assert reloaded.names() == ["加註記"]
    assert reloaded.macros["加註記"].steps[0].args["text"] == "※"


def test_saved_macro_can_be_replayed_after_reload(window, tmp_path):
    store = MacroStore(tmp_path / "macros.json")
    store.add(Macro("插入分隔線", [MacroStep("insert_text", {"text": "----"})]))
    window.macro_store.load()
    ed = window.editor()
    ed.setPlainText("")
    window._run_macro(window.macro_store.macros["插入分隔線"])
    assert ed.toPlainText() == "----"


def test_nf_03_corrupt_macro_file_does_not_block_startup(app, tmp_path, monkeypatch):
    import stephany.ui.mainwindow as mw

    (tmp_path / "macros.json").write_text("壞掉的內容", encoding="utf-8")
    monkeypatch.setattr(mw, "default_store_path", lambda: tmp_path / "macros.json")
    win = mw.MainWindow([])
    assert win.macro_store.macros == {}
    assert "無法讀取" in win.statusBar().currentMessage()
    win.editor().document().setModified(False)
    win.close()
    win.setParent(None)


# -- 選單完整性 ---------------------------------------------------------
def test_new_menus_are_present(window):
    names = [a.text() for a in window.menuBar().actions()]
    assert "書籤(&K)" in names
    assert "巨集(&M)" in names


# -- 桌面身分（SRS-004 F-PK-01、NF-01）--------------------------------
def test_f_pk_01_application_declares_its_desktop_identity(app):
    """沒有設 desktopFileName 時，Wayland 會退回執行檔名稱而顯示成 python3。"""
    from stephany.__main__ import APP_ID, configure_identity

    from stephany import platforms

    configure_identity(app)
    assert app.desktopFileName() == APP_ID  # Wayland app_id
    # macOS 沒有 WM_CLASS，身分由 .app 的 Info.plist 提供（SRS-005 D-01），
    # applicationName 只是從原始碼執行時的退路，用人看得懂的名稱即可。
    expected = "Stephany Editor" if platforms.IS_MAC else APP_ID
    assert app.applicationName() == expected  # X11 WM_CLASS
    assert app.applicationDisplayName() == "Stephany Editor"


def test_f_pk_01_window_icon_is_loaded(app):
    from stephany.__main__ import configure_identity

    configure_identity(app)
    assert not app.windowIcon().isNull()


# -- 選單接線：帶具名參數的命令 ---------------------------------------
def test_fold_to_level_menu_actions_actually_run(window):
    """「摺疊到指定層級」是唯一用具名參數呼叫 perform() 的選單項目。

    `_ed_call(name, *args)` 沒有收 `**kwargs`，而選單是用
    `_ed_call("perform", "fold_level", level=n)` 呼叫的——按下去會丟
    TypeError，Alt+1 ~ Alt+8 在三個平台上全都是壞的。
    """
    ed = window.editor()
    ed.setPlainText("def a():\n    if x:\n        pass\n    return 1\n")
    window.act_fold_levels[0].trigger()  # 摺疊到第 1 層
    assert len(ed.folds) > 0, "沒有任何區塊被摺疊，選單接線沒真的執行到"
