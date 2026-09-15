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

"""Windows 專屬行為的 GUI 測試（SRS-006 F-WIN-*、D-W*）。

與 `test_macos_gui.py` 同樣的分工：跨平台就該成立的規則不標記，
標了 `skipif` 的才是真的只有 Windows 才驗得到的部分。
"""

import os

import pytest

from stephany import platforms

if not platforms.IS_WINDOWS:  # 讓非 Windows 機器連 import Qt 都省下來
    pytest.skip("SRS-006 的 Windows 專屬測試", allow_module_level=True)

from PySide6.QtGui import QFont, QFontDatabase, QFontMetricsF  # noqa: E402
from PySide6.QtGui import QKeySequence  # noqa: E402


def _installed(family: str, style: str | None) -> bool:
    if family not in QFontDatabase.families():
        return False
    return style is None or style in QFontDatabase.styles(family)


def _ratio(family: str, style: str | None, size: int = 12) -> float:
    font = QFont(family, size)
    if style is not None:
        font.setStyleName(style)
    font.setFixedPitch(True)
    font.setKerning(False)
    fm = QFontMetricsF(font)
    return fm.horizontalAdvance("漢") / fm.horizontalAdvance("0")


# -- D-W9：測試環境本身必須量得到字型 ---------------------------------
def test_d_w9_the_test_run_is_not_using_the_offscreen_plugin():
    """Windows 的 offscreen 外掛字型資料庫是空的（實測 0 筆）。

    在 offscreen 底下，所有字型不變量的測試都會走 `pytest.skip`，於是
    CI 顯示全綠、但 F-WIN-07 一次都沒被驗過。這裡把「測試環境有沒有能力
    驗字型」本身變成一個會紅燈的斷言，而不是靠人記得。
    """
    assert os.environ.get("QT_QPA_PLATFORM") != "offscreen", (
        "Windows 上不得用 offscreen 跑 GUI 測試（SRS-006 D-W9）："
        "字型資料庫會是空的，字型測試會安靜地 skip"
    )


def test_d_w9_the_font_database_is_actually_populated(app):
    """上一個測試擋的是設定，這個測試擋的是結果。"""
    families = QFontDatabase.families()
    assert len(families) > 50, (
        f"只看得到 {len(families)} 個字型家族——字型不變量無從驗起"
    )


# -- F-WIN-07：字型不變量 ---------------------------------------------
def test_f_win_07_an_aligned_font_is_available_on_a_chinese_windows(app):
    """一般的繁中／簡中／日文 Windows 預設就有合格字型，不必先裝。

    乾淨的 en-US Windows 11 可能一個語言補充字型都沒有——那種機器走
    退路 + 狀態列警告（見下面的 fallback 測試），所以這裡 skip 而非紅燈。
    """
    installed = [e for e in platforms.ALIGNED_FONTS if _installed(*e)]
    if not installed:
        pytest.skip(
            "這台 Windows 沒有裝任何中文補充字型（en-US 精簡安裝）。"
            f"裝 {platforms.FONT_HINT} 其中之一再跑。"
        )
    for family, style in installed:
        ratio = _ratio(family, style)
        assert abs(ratio - 2.0) < 0.05, f"{family} 的比例是 {ratio:.3f}"


@pytest.mark.parametrize("size", [9, 12, 18, 24])
def test_f_win_07_the_ratio_holds_at_every_font_size(app, size):
    """欄模式的字級是可調的；只在 12pt 對得齊沒有意義。"""
    installed = [e for e in platforms.ALIGNED_FONTS if _installed(*e)]
    if not installed:
        pytest.skip("這台 Windows 沒有合格字型可量")
    for family, style in installed:
        ratio = _ratio(family, style, size)
        assert abs(ratio - 2.0) < 0.05, f"{family} 在 {size}pt 是 {ratio:.3f}"


def test_f_win_07_the_ratio_holds_for_characters_the_font_lacks(app):
    """繁中專用字、假名、全形標點、罕用字——字型本身缺字時會由系統遞補，
    遞補上來的 CJK 字型中文寬度同樣等於字級，所以還是準的。"""
    installed = [e for e in platforms.ALIGNED_FONTS if _installed(*e)]
    if not installed:
        pytest.skip("這台 Windows 沒有合格字型可量")
    family, style = installed[0]
    font = QFont(family, 12)
    if style is not None:
        font.setStyleName(style)
    font.setFixedPitch(True)
    font.setKerning(False)
    fm = QFontMetricsF(font)
    half = fm.horizontalAdvance("0")
    for char in "漢臺灣繁體国語あア（）：「」；、々鷗顥":
        ratio = fm.horizontalAdvance(char) / half
        assert abs(ratio - 2.0) < 0.05, f"{family} 的「{char}」是 {ratio:.3f}"


def test_br_win_4_the_proportional_variant_really_is_misaligned(app):
    """BR-WIN-4 不是憑空訂的規則——如果哪天 PMingLiU 其實是對齊的，
    這個測試會紅燈，提醒回去重看規則而不是默默守著一條過時的禁令。"""
    if not _installed("PMingLiU", None):
        pytest.skip("這台 Windows 沒有 PMingLiU")
    assert abs(_ratio("PMingLiU", None) - 2.0) >= 0.05, (
        "PMingLiU 量起來竟然是對齊的，BR-WIN-4 需要重新檢視"
    )


def test_the_editor_picks_an_aligned_font_when_one_is_installed(editor):
    installed = [e for e in platforms.ALIGNED_FONTS if _installed(*e)]
    if not installed:
        pytest.skip("這台 Windows 沒有合格字型可挑")
    assert editor.font_is_aligned, (
        f"挑到的是 {editor.font().family()}，中文不是半形的兩倍寬"
    )


# -- F-WIN-08：Alt+C 的替代鍵 -----------------------------------------
def test_f_win_08_the_column_editor_has_a_key_that_is_not_swallowed(window):
    """實測：Alt+C 被選單列的 編碼(&C) 助憶鍵吃掉，完全按不到。"""
    bound = {s.toString() for s in window.act_column_editor.shortcuts()}
    assert QKeySequence("Ctrl+Shift+C").toString() in bound


def test_br_win_5_the_original_alt_c_is_kept_as_well(window):
    """替代鍵是「多一個」不是「換一個」——別的平台仍然用得到 Alt+C。"""
    bound = {s.toString() for s in window.act_column_editor.shortcuts()}
    assert QKeySequence("Alt+C").toString() in bound


def _press_and_see_if_it_fires(window, action, key, modifiers):
    """送一次按鍵，回報那個 action 有沒有被觸發。

    會先把 action 原本的 slot 拔掉：`Ctrl+Shift+C` 真的會開出 modal 的
    欄位編輯器對話框，測試跑到那裡就整個卡住了。
    """
    from PySide6.QtTest import QTest

    try:
        action.triggered.disconnect()
    except RuntimeError:
        pass
    fired = []
    action.triggered.connect(lambda *a: fired.append(1))
    window.editor().setFocus()
    QTest.keyClick(window, key, modifiers)
    window.window().windowHandle()  # 讓事件跑完
    QTest.qWait(10)
    return bool(fired)


def test_f_win_08_alt_c_really_is_shadowed_by_the_menu_mnemonic(window):
    """這是 F-WIN-08 存在的理由，直接測給它看。

    **一定要有對照組**：`QTest.keyClick` 送到一個沒有 show() 的視窗時，
    連 `Ctrl+N` 都不會觸發——沒有對照組的話，這個測試會因為「什麼都沒送到」
    而通過，而不是因為「Alt+C 真的被吃掉」。實測（本機、視窗已顯示）：

        Alt+0        -> 觸發
        Ctrl+Shift+C -> 觸發
        Alt+C        -> 不觸發

    差別只在於選單列有沒有一個同字母的助憶鍵。哪天 Qt 改了行為，這個測試
    會紅燈，提醒可以把替代鍵拿掉。
    """
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    names = [a.text() for a in window.menuBar().actions()]
    assert any("(&C)" in name for name in names), "選單列沒有 &C 助憶鍵了"

    window.show()
    QTest.qWait(50)
    assert window.isVisible()

    alt = Qt.KeyboardModifier.AltModifier
    ctrl_shift = (
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier
    )

    # 對照組：同樣的送鍵方式，Alt+0 必須觸發，否則下面的斷言毫無意義
    assert _press_and_see_if_it_fires(
        window, window.act_fold_all, Qt.Key.Key_0, alt
    ), "對照組 Alt+0 都沒觸發——這個測試根本沒送到鍵，結論不成立"

    # 替代鍵必須真的按得到（F-WIN-08 的重點不是「有綁」而是「按得到」）
    assert _press_and_see_if_it_fires(
        window, window.act_column_editor, Qt.Key.Key_C, ctrl_shift
    ), "替代鍵 Ctrl+Shift+C 按不到"

    # 主角：Alt+C 被 編碼(&C) 助憶鍵吃掉
    assert not _press_and_see_if_it_fires(
        window, window.act_column_editor, Qt.Key.Key_C, alt
    ), "Alt+C 竟然按得到了——F-WIN-08 的替代鍵可以重新檢視"


# -- F-WIN-01 / D-W1：應用程式身分 ------------------------------------
def _explicit_app_user_model_id() -> str | None:
    """問 Windows：這個程序目前宣告的 AppUserModelID 是什麼？"""
    import ctypes

    buf = ctypes.c_wchar_p()
    hr = ctypes.windll.shell32.GetCurrentProcessExplicitAppUserModelID(
        ctypes.byref(buf)
    )
    return buf.value if hr == 0 else None


def test_d_w1_the_process_declares_its_app_user_model_id():
    """沒有宣告時，Windows 會用執行檔路徑推導身分——而所有 Python 程式的
    執行檔路徑都是同一個 pythonw.exe，工作列會把我們跟別的 Python 程式
    分到同一組，工作管理員也顯示成 pythonw。

    這是 SRS-004 D-01（Dock 顯示成 python3）與 SRS-005 D-01（選單列顯示成
    main.py）在 Windows 上的第三個版本。
    """
    from stephany import BUNDLE_ID

    assert platforms.set_app_user_model_id() is True
    assert _explicit_app_user_model_id() == BUNDLE_ID


def test_f_win_01_configure_identity_sets_it_too(app):
    """實際啟動路徑要真的走到它，不能只有函式存在。

    AppUserModelID 是**程序層級**的狀態，而上一個測試已經設過了——不先
    蓋掉的話，就算把 `configure_identity()` 裡那一行刪掉，這個測試照樣
    會過。先設成一個哨兵值，才問得出「這一次呼叫有沒有真的設」。
    """
    import ctypes

    from stephany import BUNDLE_ID
    from stephany.__main__ import configure_identity

    sentinel = "io.github.edwardcchen.SENTINEL-not-the-real-id"
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(sentinel)
    assert _explicit_app_user_model_id() == sentinel, "哨兵沒設進去，測試無效"

    configure_identity(app)
    assert _explicit_app_user_model_id() == BUNDLE_ID
