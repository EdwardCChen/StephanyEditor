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

"""圖示工具列的行為測試（SRS-007 F-TB-*）。

平台外掛由 conftest 決定，本檔不得自己設 QT_QPA_PLATFORM（SRS-006 D-W9）。
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QToolBar

from stephany.ui import icons, theme
from stephany.ui.mainwindow import TOOLBAR_LAYOUT


def toolbar(window) -> QToolBar:
    return window.findChild(QToolBar)


def icon_pixel(action) -> QColor:
    """取圖示上一個不透明的像素，用來確認它被塗成了什麼顏色。"""
    image = action.icon().pixmap(24, 24).toImage()
    for y in range(image.height()):
        for x in range(image.width()):
            color = image.pixelColor(x, y)
            if color.alpha() == 255:
                return color
    raise AssertionError("這個圖示整張都是透明的")


# -- F-TB-01：按鈕以圖示表示，不顯示文字 ------------------------------
def test_f_tb_01_the_toolbar_shows_icons_only(window):
    assert toolbar(window).toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonIconOnly


def test_f_tb_01_every_toolbar_button_actually_has_an_icon(window):
    """圖示是空的話，只顯示圖示的工具列就會變成一排看不出用途的空白按鈕。"""
    naked = [name for action, name in window._toolbar_icons if action.icon().isNull()]
    assert not naked, f"這些按鈕沒有圖示：{naked}"


def test_the_layout_table_and_the_real_toolbar_agree(window):
    """版面表是圖示測試的依據，它與實際工具列脫節的話那些測試就白測了。"""
    expected = [
        getattr(window, entry[0]) for entry in TOOLBAR_LAYOUT if entry is not None
    ]
    on_bar = [a for a in toolbar(window).actions() if not a.isSeparator()]
    assert on_bar == expected


def test_icon_only_is_much_narrower_than_the_old_text_toolbar(window, app):
    """這就是改動的理由：整列文字按鈕比視窗還寬。"""

    def width(style):
        bar = QToolBar(window)
        bar.setToolButtonStyle(style)
        for entry in TOOLBAR_LAYOUT:
            bar.addSeparator() if entry is None else bar.addAction(
                getattr(window, entry[0])
            )
        bar.show()
        app.processEvents()
        result = bar.sizeHint().width()
        bar.setParent(None)
        return result

    text_only = width(Qt.ToolButtonStyle.ToolButtonTextOnly)
    icon_only = width(Qt.ToolButtonStyle.ToolButtonIconOnly)
    assert icon_only < text_only * 0.7, (
        f"圖示工具列 {icon_only}px 並沒有比文字版 {text_only}px 省多少"
    )


# -- F-TB-02：名稱與快速鍵移到 tooltip --------------------------------
def test_f_tb_02_tooltips_carry_the_name_and_the_shortcut(window):
    """圖示不可能自我解釋，名稱不能消失。"""
    for action, name in window._toolbar_icons:
        tip = action.toolTip()
        assert tip, f"{name} 沒有 tooltip"
        if not action.shortcut().isEmpty():
            native = action.shortcut().toString(
                action.shortcut().SequenceFormat.NativeText
            )
            assert native in tip, f"{name} 的 tooltip 少了快速鍵：{tip!r}"


def test_f_tb_02_tooltips_do_not_leak_mnemonic_brackets(window):
    """「開新檔案(&N)」去掉 & 會留下沒有意義的「(N)」。"""
    import re

    for action, name in window._toolbar_icons:
        head = action.toolTip().split("\n")[0]
        assert "&" not in head, f"{name}：{head!r}"
        assert not re.search(r"\([A-Za-z0-9]\)", head), f"{name}：{head!r}"


def test_f_tb_02_an_existing_hint_is_kept_as_a_second_line(window):
    """黏著式欄選取原本就有一句補充說明，不該被 tooltip 改寫蓋掉。"""
    tip = window.act_sticky.toolTip()
    assert "\n" in tip
    assert window.act_sticky.statusTip() in tip


# -- F-TB-03：跟著深淺主題換色 ----------------------------------------
def test_f_tb_03_icons_are_painted_with_the_palette_colour(window):
    expected = theme.toolbar_icon_color(window.palette())
    action = window.act_bm_toggle
    assert icon_pixel(action).rgb() == expected.rgb()


def test_f_tb_03_switching_to_a_dark_palette_repaints_the_icons(window):
    """深色主題下不換色的話，工具列上會剩一排看不見的黑圖。"""
    before = icon_pixel(window.act_bm_toggle)

    dark = QPalette(window.palette())
    dark.setColor(QPalette.ColorRole.Button, QColor("#2a2a2a"))
    dark.setColor(QPalette.ColorRole.ButtonText, QColor("#f0f0f0"))
    window.setPalette(dark)  # 會送出 PaletteChange
    window._refresh_toolbar_icons()

    after = icon_pixel(window.act_bm_toggle)
    assert after.rgb() != before.rgb()
    assert after.rgb() == QColor("#f0f0f0").rgb()


def test_f_tb_03_a_palette_change_event_is_enough(window, app):
    """不必手動呼叫——changeEvent 要接到。"""
    from PySide6.QtCore import QEvent

    dark = QPalette(window.palette())
    dark.setColor(QPalette.ColorRole.ButtonText, QColor("#12ab34"))
    window.setPalette(dark)
    app.sendEvent(window, QEvent(QEvent.Type.PaletteChange))
    assert icon_pixel(window.act_bm_toggle).rgb() == QColor("#12ab34").rgb()


# -- F-TB-04：可勾選的動作仍看得出狀態 --------------------------------
def test_f_tb_04_checkable_actions_stay_checkable(window):
    """錄製中／黏著模式開著，靠的是按鈕的勾選外觀。"""
    assert window.act_sticky.isCheckable()
    assert window.act_macro_record.isCheckable()


# -- D-05：缺圖示時退回文字，而不是變成空白按鈕 -----------------------
def test_d_05_a_missing_icon_falls_back_to_an_empty_icon(app):
    assert icons.load("這個圖示不存在", QColor("#000000")).isNull()


# -- D-06：圖示只用在工具列 -------------------------------------------
def test_d_06_icons_do_not_leak_into_the_menus(window):
    """macOS 與現在的 GNOME 選單都不放圖示，三個平台一致。"""
    for action, name in window._toolbar_icons:
        assert not action.isIconVisibleInMenu(), name
