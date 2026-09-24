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

import pytest

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


# -- 說明視窗：不得講別的平台的事（SRS-006 F-WIN-08 的收尾）------------
def test_the_help_text_never_mentions_another_platform(window):
    """替代鍵的說明原本是為 macOS 寫死的：「功能鍵按不到時（不必壓 Fn）」、
    「Alt+C 在 macOS 會打出 ç」。Windows 也開始有替代鍵之後，這段文字就會
    對著 Windows 使用者講 Mac 的事。

    GNOME 那句提示同理——原本的條件是「不是 macOS 就顯示」，於是 Windows
    也看得到。
    """
    from stephany import platforms

    text = window._help_text()

    if not platforms.IS_MAC:
        for word in ("Fn", "ç", "macOS", "⌘", "⌥"):
            assert word not in text, f"非 macOS 平台的說明不該提到「{word}」"
    if not platforms.IS_LINUX:
        assert "GNOME" not in text, "只有 Linux 才需要 GNOME 的提示"


def test_the_help_text_lists_every_extra_shortcut_of_this_platform(window):
    """有補鍵就要講，而且要講對——說明與實際綁定不能各說各話。"""
    from PySide6.QtGui import QKeySequence

    from stephany import platforms
    from stephany.ui.mainwindow import EXTRA_SHORTCUT_LABELS

    text = window._help_text()
    for action_id, sequences in platforms.EXTRA_SHORTCUTS.items():
        assert EXTRA_SHORTCUT_LABELS[action_id] in text, action_id
        for sequence in sequences:
            native = QKeySequence(sequence).toString(
                QKeySequence.SequenceFormat.NativeText
            )
            assert native in text, f"{action_id} 的 {native} 沒出現在說明裡"


def test_the_help_text_has_no_extra_section_when_nothing_is_rebound(window):
    """Linux 什麼都不必補，就不該冒出一個空的「替代鍵」段落。"""
    from stephany import platforms

    if platforms.EXTRA_SHORTCUTS:
        pytest.skip("這個平台有補鍵")
    assert "替代" not in window._help_text()


# -- 字型 ---------------------------------------------------------------
def test_choosing_a_font_size_in_the_dialog_changes_the_editor(window):
    """檢視 → 選擇字型：選了大小要真的套用到所有分頁。

    對話框必須是 Qt 自己的：GNOME 的原生 GTK 字型選擇器會把
    `WenQuanYi Zen Hei Mono` 往返轉成 `Sans 10`，選的大小完全不見。
    """
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QFontDialog, QListView

    ed = window.editor()
    target = 20 if ed.font().pointSize() != 20 else 16
    seen = {}

    def pick_size():
        dialog = QApplication.activeModalWidget()
        seen["is_dialog"] = isinstance(dialog, QFontDialog)
        seen["native"] = not dialog.testOption(
            QFontDialog.FontDialogOption.DontUseNativeDialog
        )
        sizes = dialog.findChildren(QListView)[2]
        model = sizes.model()
        for row in range(model.rowCount()):
            if model.index(row, 0).data() == str(target):
                sizes.setCurrentIndex(model.index(row, 0))
        dialog.accept()

    QTimer.singleShot(0, pick_size)
    window.act_font.trigger()

    assert seen["is_dialog"]
    assert not seen["native"]
    assert ed.font().pointSize() == target
