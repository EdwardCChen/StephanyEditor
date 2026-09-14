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

"""平台相關行為的 GUI 測試（SRS-005 F-MAC-*、BR-MAC-3）。

有些項目（字型不變量、⌥ 誤打字）是跨平台的規則，在哪裡跑都該成立；
標了 `skipif` 的才是真的只有 macOS 才驗得到的部分。
"""

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import (  # noqa: E402
    QAction,
    QFont,
    QFontDatabase,
    QFontMetricsF,
    QKeyEvent,
    QKeySequence,
)

from stephany import platforms  # noqa: E402

ROOT_MAIN = Path(__file__).resolve().parent.parent / "stephany" / "__main__.py"

mac_only = pytest.mark.skipif(not platforms.IS_MAC, reason="只有 macOS 驗得到")


def _installed(family: str, style: str | None) -> bool:
    if family not in QFontDatabase.families():
        return False
    return style is None or style in QFontDatabase.styles(family)


def _ratio(family: str, style: str | None) -> float:
    font = QFont(family, 12)
    if style is not None:
        font.setStyleName(style)
    font.setFixedPitch(True)
    font.setKerning(False)
    fm = QFontMetricsF(font)
    return fm.horizontalAdvance("漢") / fm.horizontalAdvance("0")


# -- F-MAC-07：字型不變量 ---------------------------------------------
def test_every_aligned_font_really_is_double_width(app):
    """清單上標成「對得齊」的字型，就必須真的是中文兩倍寬。

    這是整個欄模式的前提；清單寫錯的話畫面上的矩形會是鋸齒狀，而且
    只有在那台機器剛好裝了那個字型時才會發生，很難事後追。
    """
    checked = []
    for family, style in platforms.ALIGNED_FONTS:
        if not _installed(family, style):
            continue
        checked.append((family, style, _ratio(family, style)))
    for family, style, ratio in checked:
        assert abs(ratio - 2.0) < 0.05, f"{family} {style} 的比例是 {ratio:.3f}"
    assert checked, "這台機器一個 CJK 等寬字型都沒有，測不到（請安裝後再跑）"


@mac_only
def test_f_mac_07_macos_picks_an_aligned_font_out_of_the_box(editor):
    """macOS 不必先裝字型就該對得齊——靠的是系統內建的 Osaka Regular-Mono。"""
    assert editor.font_is_aligned, (
        f"挑到的是 {editor.font().family()} / {editor.font().styleName()}，"
        "中文不是半形的兩倍寬"
    )


@mac_only
def test_the_font_style_name_is_carried_over_not_just_the_family(editor):
    """只設家族名稱會拿到比例 1.5 的 Osaka 預設樣式（BR-MAC-6）。"""
    if editor.font().family() == "Osaka":
        assert editor.font().styleName() == "Regular-Mono"


# -- BR-MAC-3：⌥ + 字母不得被當成文字插入 ------------------------------
def _press(editor, key, text, modifiers):
    editor.keyPressEvent(
        QKeyEvent(QKeyEvent.Type.KeyPress, key, modifiers, text)
    )


def test_br_mac_3_option_plus_letter_does_not_type_into_the_block(editor):
    """macOS 上 ⌥C 送出的是 `ç`。快速鍵沒攔到時不能讓它插進矩形每一行。"""
    editor.setPlainText("abc\ndef\nghi")
    editor.start_block_mode(0, 0)
    editor._move_caret(2, 0)
    _press(editor, Qt.Key.Key_C, "ç", Qt.KeyboardModifier.AltModifier)
    assert editor.toPlainText() == "abc\ndef\nghi"


def test_br_mac_3_option_plus_digit_does_not_type_into_the_block(editor):
    """⌥0 是 `º`；摺疊層級的快速鍵全都是 ⌥ + 數字。"""
    editor.setPlainText("abc\ndef")
    editor.start_block_mode(0, 0)
    editor._move_caret(1, 0)
    _press(editor, Qt.Key.Key_0, "º", Qt.KeyboardModifier.AltModifier)
    assert editor.toPlainText() == "abc\ndef"


def test_plain_typing_in_the_block_still_works(editor):
    """上面兩個測試不能把正常輸入一起擋掉。"""
    editor.setPlainText("abc\ndef")
    editor.start_block_mode(0, 0)
    editor._move_caret(1, 0)
    _press(editor, Qt.Key.Key_X, "x", Qt.KeyboardModifier.NoModifier)
    assert editor.toPlainText() == "xabc\nxdef"


# -- F-MAC-06：關於／結束屬於應用程式選單 ------------------------------
def test_f_mac_06_about_and_quit_declare_their_menu_roles(window):
    """Qt 是靠英文字樣猜 menuRole 的，中文選單猜不到，必須明講。

    順帶修掉一個實質 bug：沒有 QuitRole 時 Qt 自己補的 ⌘Q 走
    QApplication.quit()，不經 closeEvent，未存檔的修改會直接消失。
    """
    assert window.act_about.menuRole() == QAction.MenuRole.AboutRole
    assert window.act_quit.menuRole() == QAction.MenuRole.QuitRole


# -- F-MAC-08：以 ⌘ 為主修飾鍵 ----------------------------------------
@mac_only
def test_f_mac_08_portable_shortcuts_resolve_to_command(window):
    """跨平台只寫一份 `Ctrl+X`，Qt 在 macOS 會解析成 ⌘X（D-05）。"""
    native = window.act_copy.shortcut().toString(
        QKeySequence.SequenceFormat.NativeText
    )
    assert native == "⌘C", native


@mac_only
def test_f_mac_08_the_bookmark_shortcut_is_not_the_system_one(window):
    """macOS 的 ⌃F2 是系統的「移動焦點到選單列」；我們的是 ⌘F2，不衝突。"""
    natives = [
        s.toString(QKeySequence.SequenceFormat.NativeText)
        for s in window.act_bm_toggle.shortcuts()
    ]
    assert "⌘F2" in natives
    assert "⌃F2" not in natives


# -- F-MAC-09：功能鍵的替代鍵 -----------------------------------------
@mac_only
@pytest.mark.parametrize(
    "attr,action_id",
    [
        ("act_help", "help"),
        ("act_bm_toggle", "bookmark_toggle"),
        ("act_bm_next", "bookmark_next"),
        ("act_bm_prev", "bookmark_prev"),
        ("act_column_editor", "column_editor"),
    ],
)
def test_f_mac_09_extra_shortcuts_are_actually_bound(window, attr, action_id):
    """MacBook 預設要壓 Fn 才送得出 F1/F2，所以另外綁一個按得到的。"""
    action = getattr(window, attr)
    bound = {s.toString() for s in action.shortcuts()}
    for extra in platforms.extra_shortcuts(action_id):
        assert QKeySequence(extra).toString() in bound, extra


@mac_only
def test_f_mac_09_the_original_cross_platform_key_is_kept(window):
    """替代鍵是「多一個」，不是「換一個」——跨平台的肌肉記憶不能斷。"""
    bound = {s.toString() for s in window.act_bm_toggle.shortcuts()}
    assert QKeySequence("Ctrl+F2").toString() in bound


def test_redo_accepts_the_platform_standard_key(window):
    """macOS 的重做是 ⇧⌘Z，Windows/Linux 是 Ctrl+Y；兩個都要能用。"""
    bound = {s.toString() for s in window.act_redo.shortcuts()}
    assert QKeySequence("Ctrl+Y").toString() in bound
    assert QKeySequence(QKeySequence.StandardKey.Redo).toString() in bound


# -- F-MAC-12 / D-09：Qt 自己那些字串也要是中文 ------------------------
@pytest.fixture
def translated(app):
    """裝上 Qt 的繁中翻譯，測完拆掉，不影響同一個 session 的其他測試。"""
    from stephany.__main__ import install_translations

    translator = install_translations(app)
    yield translator
    if translator is not None:
        app.removeTranslator(translator)


def test_f_mac_12_the_application_menu_strings_are_translated(translated, app):
    """macOS 的「關於／服務／隱藏／結束」不是本專案建的選單項目，是 Qt 依
    平台慣例自己組的，字串來自 `MAC_APPLICATION_MENU` 這個翻譯 context。
    沒載入翻譯的話，一整排中文選單裡會冒出幾個英文項目。
    """
    from PySide6.QtCore import QCoreApplication

    assert translated is not None, "找不到 Qt 的 qtbase_zh_TW 翻譯檔"
    expected = {
        "About %1": "關於 %1",
        "Quit %1": "結束 %1",
        "Services": "服務",
        "Hide %1": "隱藏 %1",
        "Hide Others": "隱藏其他",
        "Show All": "顯示全部",
    }
    for source, want in expected.items():
        got = QCoreApplication.translate("MAC_APPLICATION_MENU", source)
        assert got == want, f"{source} -> {got}"


def test_f_mac_12_standard_dialog_buttons_are_translated(translated, app):
    """QMessageBox 的按鈕同樣是 Qt 提供的字串。"""
    from PySide6.QtCore import QCoreApplication

    assert QCoreApplication.translate("QPlatformTheme", "OK") == "確定"
    assert QCoreApplication.translate("QPlatformTheme", "Cancel") == "取消"


def test_f_mac_12_translations_are_installed_before_the_menu_bar_is_built():
    """選單列一旦建好，之後再裝翻譯也來不及了——順序要由原始碼保證。"""
    source = (ROOT_MAIN).read_text(encoding="utf-8")
    assert source.index("install_translations(app)") < source.index("MainWindow(")


# -- D-07 / F-MAC-04：Finder 開檔走 QFileOpenEvent ---------------------
def test_d_07_file_open_event_opens_a_tab(window, tmp_path):
    """macOS 從 Finder 開檔不經 argv，而是送事件給已經在跑的程序。"""
    from stephany.__main__ import _make_file_open_relay

    path = tmp_path / "來自Finder.txt"
    path.write_text("內容", encoding="utf-8")

    relay = _make_file_open_relay()
    relay.attach(window)
    relay.deliver(str(path))

    assert window.editor().toPlainText() == "內容"
    assert window.editor().file_path == str(path)


def test_d_07_events_arriving_before_the_window_are_queued(window, tmp_path):
    """冷啟動時事件會比主視窗先到，不能就這樣丟掉。"""
    from stephany.__main__ import _make_file_open_relay

    path = tmp_path / "早到.txt"
    path.write_text("排隊", encoding="utf-8")

    relay = _make_file_open_relay()
    relay.deliver(str(path))  # 視窗還不存在
    assert relay.pending == [str(path)]

    relay.attach(window)
    assert relay.pending == []
    assert window.editor().toPlainText() == "排隊"


def test_d_07_the_event_filter_understands_a_real_file_open_event(window, tmp_path):
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QFileOpenEvent

    from stephany.__main__ import _make_file_open_relay

    path = tmp_path / "事件.txt"
    path.write_text("由事件送進來", encoding="utf-8")

    relay = _make_file_open_relay()
    relay.attach(window)
    handled = relay.eventFilter(window, QFileOpenEvent(QUrl.fromLocalFile(str(path))))

    assert handled
    assert window.editor().toPlainText() == "由事件送進來"


def test_launch_services_process_serial_argument_is_not_treated_as_a_file():
    from stephany.__main__ import _cli_files

    assert _cli_files(["-psn_0_12345", "檔案.txt"]) == ["檔案.txt"]
