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

from pathlib import Path

import pytest

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
def _installed_aligned_fonts() -> list[tuple[str, str | None]]:
    return [entry for entry in platforms.ALIGNED_FONTS if _installed(*entry)]


def test_every_aligned_font_really_is_double_width(app):
    """清單上標成「對得齊」的字型，就必須真的是中文兩倍寬。

    這是整個欄模式的前提；清單寫錯的話畫面上的矩形會是鋸齒狀，而且只有在
    那台機器剛好裝了那個字型時才會發生，很難事後追。

    量得到幾個就驗幾個——「這台機器裝了什麼字型」是環境條件，不是程式的錯，
    所以一個都沒有時 skip 而不是紅燈。CI 會刻意裝一個，避免這裡永遠空轉。
    """
    installed = _installed_aligned_fonts()
    if not installed:
        pytest.skip(
            "這台機器一個 CJK 等寬字型都沒有，量不到。"
            f"裝 {platforms.FONT_HINT} 其中之一再跑。"
        )
    for family, style in installed:
        ratio = _ratio(family, style)
        assert abs(ratio - 2.0) < 0.05, f"{family} {style} 的比例是 {ratio:.3f}"


def test_the_editor_picks_an_aligned_font_when_one_is_installed(editor):
    """有對得齊的字型可用時，就不該退回會歪掉的那一組。"""
    if not _installed_aligned_fonts():
        pytest.skip("這台機器沒有對得齊的字型可挑")
    assert editor.font_is_aligned, (
        f"挑到的是 {editor.font().family()} / {editor.font().styleName()}，"
        "中文不是半形的兩倍寬"
    )


@mac_only
def test_f_mac_07_the_built_in_osaka_mono_is_double_width(app):
    """F-MAC-07「不必先裝字型」靠的就是這個系統內建字型。

    它是隨 macOS 安裝的字型資產，一般桌面安裝都有；精簡過的映像（例如 CI
    runner）可能沒有，那種機器就退回狀態列警告 + 請使用者自己裝（見 FONT_HINT）。
    """
    if not _installed("Osaka", "Regular-Mono"):
        pytest.skip("這個 macOS 沒有 Osaka Regular-Mono（精簡映像）")
    assert abs(_ratio("Osaka", "Regular-Mono") - 2.0) < 0.05


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


# -- BR-MAC-7：不得讓 Qt 用選單文字猜 menuRole ------------------------
#
# 這組測試是為了一個實際發生過的 bug：載入 qtbase_zh_TW 之後，Qt 眼中的
# "Quit" 與 "Exit" 都變成「離開」，於是「離開欄模式」被判定成 QuitRole，
# 搶走了應用程式選單的結束位置——按「結束 Stephany Editor」實際執行的是
# 離開欄模式，程式關不掉。


def _role_keywords() -> dict[str, str]:
    """Qt 用來猜角色的關鍵字，翻譯後的樣子。"""
    from PySide6.QtCore import QCoreApplication

    sources = (
        "About", "Config", "Preference", "Options", "Setting", "Setup",
        "Quit", "Exit", "Cut", "Copy", "Paste", "Select All",
    )
    return {s: QCoreApplication.translate("QCocoaMenuItem", s) for s in sources}


def test_br_mac_7_no_action_is_left_on_the_text_heuristic_role(window):
    """每個動作都要明講 menuRole。

    Qt 的預設 `TextHeuristicRole` 是「拿選單文字去比對關鍵字來猜」，而那些
    關鍵字會跟著翻譯走——同一份程式碼，載入不同語言的 Qt 翻譯就會有不同的
    選單行為。對中文介面來說這種猜測只會製造無聲的碰撞。
    """
    from PySide6.QtGui import QAction

    guessed = [
        a.text()
        for a in window.findChildren(QAction)
        if a.menuRole() == QAction.MenuRole.TextHeuristicRole
    ]
    assert not guessed, f"這些動作還讓 Qt 用文字猜角色：{guessed}"


def test_br_mac_7_exactly_one_action_owns_each_application_menu_slot(window):
    """應用程式選單的「關於」與「結束」各只有一個位置，被搶走就沒有第二個。"""
    from PySide6.QtGui import QAction

    def owners(role):
        return [a for a in window.findChildren(QAction) if a.menuRole() == role]

    assert owners(QAction.MenuRole.QuitRole) == [window.act_quit]
    assert owners(QAction.MenuRole.AboutRole) == [window.act_about]


def test_br_mac_7_actions_whose_text_matches_a_role_keyword_are_neutralised(
    translated, window
):
    """撞到關鍵字的動作必須是 NoRole，否則就會被搬走。

    這個測試會自己跟著介面文字走：之後新增的選單項只要開頭撞到翻譯後的
    關鍵字（例如再來一個「離開…」或「設定…」），沒設 NoRole 就會紅燈。
    """
    from PySide6.QtGui import QAction

    keywords = _role_keywords()
    intentional = {window.act_about, window.act_quit}
    collisions = []
    for action in window.findChildren(QAction):
        text = action.text().replace("&", "")
        for source, translation in keywords.items():
            if translation != source and text.startswith(translation):
                collisions.append((action, text, source, translation))
    assert collisions, (
        "沒有任何選單文字撞到關鍵字，這個測試變成空轉了——"
        "是介面文字改了，還是翻譯沒載入？"
    )
    for action, text, source, translation in collisions:
        if action in intentional:
            continue
        assert action.menuRole() == QAction.MenuRole.NoRole, (
            f"{text!r} 開頭是 {translation!r}（Qt 的 {source} 關鍵字），"
            f"必須設成 NoRole，否則會被搬進應用程式選單"
        )


def test_br_mac_7_the_column_mode_exit_action_is_not_treated_as_quit(translated, window):
    """回歸測試：就是這一項曾經搶走「結束」。"""
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtGui import QAction

    assert window.act_exit_block.text().startswith(
        QCoreApplication.translate("QCocoaMenuItem", "Quit")
    ), "介面文字改了的話，這個回歸測試要跟著改（見上面那個自動跟隨的測試）"
    assert window.act_exit_block.menuRole() == QAction.MenuRole.NoRole


def test_quit_actually_closes_the_window(window):
    """回歸測試：這就是回報的症狀——選「結束」沒反應，只有紅色 x 有用。"""
    assert window.isVisible() or True  # fixture 不一定 show()，看的是有沒有被關掉
    window.act_quit.trigger()
    assert not window.isVisible(), "觸發「結束」之後視窗還在"


def test_quit_asks_before_discarding_unsaved_work(window, monkeypatch):
    """「結束」必須走 closeEvent，未存檔的修改才有機會提示。

    `QApplication.quit()` 不送 close 事件，接到視窗的 `close()` 才會——
    這是「結束」要接在視窗上、而不是接在 app 上的理由。
    """
    from PySide6.QtWidgets import QMessageBox

    asked = []

    def fake_question(*args, **kwargs):
        asked.append(args[2] if len(args) > 2 else "")
        return QMessageBox.StandardButton.Cancel

    monkeypatch.setattr(QMessageBox, "question", staticmethod(fake_question))
    editor = window.editor()
    editor.setPlainText("還沒存的東西")
    editor.document().setModified(True)

    window.show()
    window.act_quit.trigger()

    assert asked, "有未存檔的修改，結束前卻沒有問過"
    assert window.isVisible(), "使用者按了取消，不該關掉"
    editor.document().setModified(False)  # 讓 fixture 收得掉


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
