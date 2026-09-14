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

"""主題色測試。

這組測試存在的理由是一個實際踩到的問題：當前行反白的底色寫死成淺米色，
使用者切到 GNOME 深色主題後，白色文字配近白色底，完全看不見自己打的字。

所以這裡不測「顏色等於某個值」，而是測「對比度足夠」——把可讀性這件事
變成可驗證的性質，換了配色也一樣成立。
"""

import pytest
from PySide6.QtGui import QColor, QPalette

from stephany.ui import theme


def make_palette(base, text, window, window_text, highlight):
    p = QPalette()
    p.setColor(QPalette.ColorRole.Base, QColor(base))
    p.setColor(QPalette.ColorRole.Text, QColor(text))
    p.setColor(QPalette.ColorRole.Window, QColor(window))
    p.setColor(QPalette.ColorRole.WindowText, QColor(window_text))
    p.setColor(QPalette.ColorRole.Highlight, QColor(highlight))
    return p


@pytest.fixture
def dark():
    # 使用者實際環境：Ubuntu Yaru-purple-dark
    return make_palette("#2a2a2a", "#ffffff", "#2a2a2a", "#ffffff", "#7460d4")


@pytest.fixture
def light():
    return make_palette("#ffffff", "#000000", "#f5f5f5", "#000000", "#0a66c2")


# -- 對比度公式 ---------------------------------------------------------
def test_contrast_ratio_extremes():
    assert theme.contrast_ratio(QColor("#000000"), QColor("#ffffff")) == pytest.approx(21, abs=0.1)
    assert theme.contrast_ratio(QColor("#777777"), QColor("#777777")) == pytest.approx(1.0)


def test_blend_endpoints_and_midpoint():
    a, b = QColor("#000000"), QColor("#ffffff")
    assert theme.blend(a, b, 0.0).name() == "#000000"
    assert theme.blend(a, b, 1.0).name() == "#ffffff"
    assert theme.blend(a, b, 0.5).red() == 128


def test_blend_clamps_out_of_range_t():
    a, b = QColor("#000000"), QColor("#ffffff")
    assert theme.blend(a, b, -5).name() == "#000000"
    assert theme.blend(a, b, 5).name() == "#ffffff"


def test_is_dark_detection(dark, light):
    assert theme.is_dark(dark) is True
    assert theme.is_dark(light) is False


# -- 迴歸：當前行反白必須看得見 ----------------------------------------
@pytest.mark.parametrize("palette_name", ["dark", "light"])
def test_text_stays_readable_on_current_line_highlight(palette_name, request):
    """這就是回報的問題本身：深色主題下白字配近白底，對比只有 1.07。"""
    palette = request.getfixturevalue(palette_name)
    bg = theme.current_line_color(palette)
    fg = palette.color(QPalette.ColorRole.Text)
    assert theme.contrast_ratio(fg, bg) >= 4.5


def test_the_original_hardcoded_colour_would_fail_this_test(dark):
    """留存問題本身：原本寫死的 #fbf7e8 在深色主題下對比度只有 1.07。"""
    fg = dark.color(QPalette.ColorRole.Text)
    assert theme.contrast_ratio(fg, QColor("#fbf7e8")) < 1.5


def test_current_line_is_distinguishable_from_normal_background(dark, light):
    """既要看得見文字，也要看得出來「這是當前行」。"""
    for palette in (dark, light):
        base = palette.color(QPalette.ColorRole.Base)
        current = theme.current_line_color(palette)
        assert current.name() != base.name()


# -- 行號欄 -------------------------------------------------------------
@pytest.mark.parametrize("palette_name", ["dark", "light"])
def test_gutter_text_is_readable(palette_name, request):
    palette = request.getfixturevalue(palette_name)
    bg = theme.gutter_background(palette)
    assert theme.contrast_ratio(theme.gutter_text(palette), bg) >= 3.0
    assert theme.contrast_ratio(theme.gutter_current_text(palette), bg) >= 3.0


def test_gutter_current_text_falls_back_when_accent_is_too_close():
    """強調色若與行號欄底色太接近，要自動往文字色拉回來。"""
    palette = make_palette("#2a2a2a", "#ffffff", "#2a2a2a", "#ffffff", "#323232")
    bg = theme.gutter_background(palette)
    assert theme.contrast_ratio(theme.gutter_current_text(palette), bg) >= 3.0


def test_gutter_differs_from_editing_area(dark, light):
    for palette in (dark, light):
        assert (
            theme.gutter_background(palette).name()
            != palette.color(QPalette.ColorRole.Base).name()
        )


# -- 語法上色 -----------------------------------------------------------
@pytest.mark.parametrize("palette_name", ["dark", "light"])
def test_every_syntax_colour_is_readable_on_the_editing_background(palette_name, request):
    palette = request.getfixturevalue(palette_name)
    base = palette.color(QPalette.ColorRole.Base)
    for role, value in theme.syntax_colors(palette).items():
        ratio = theme.contrast_ratio(QColor(value), base)
        assert ratio >= 4.0, f"{role} 在此主題下對比度只有 {ratio:.2f}"


def test_syntax_colours_switch_with_the_theme(dark, light):
    assert theme.syntax_colors(dark) != theme.syntax_colors(light)


# -- 欄模式游標與書籤 ---------------------------------------------------
@pytest.mark.parametrize("palette_name", ["dark", "light"])
def test_block_caret_and_bookmark_stand_out(palette_name, request):
    palette = request.getfixturevalue(palette_name)
    base = palette.color(QPalette.ColorRole.Base)
    assert theme.contrast_ratio(theme.block_caret_color(palette), base) >= 3.0
    gutter = theme.gutter_background(palette)
    assert theme.contrast_ratio(theme.bookmark_color(palette), gutter) >= 3.0
