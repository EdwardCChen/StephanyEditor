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

"""主題色：所有顏色都從系統配色（QPalette）推導，不寫死。

這個模組的存在是為了修掉一個實際踩到的問題：當前行的反白底色原本寫死成
淺米色 #fbf7e8，使用者切到 GNOME 深色主題後，Qt 給的文字色變成白色，
於是白字配近白底，對比度只剩個位數，完全看不見自己打的字。

同樣的錯誤原本散在行號欄與語法上色裡（深藍色關鍵字配深色背景）。
因此改成：所有顏色一律由 palette 的 Base / Text / Highlight 推導，
深淺主題各自成立，使用者中途切換主題也會跟著變。

contrast_ratio() 是 WCAG 的對比度公式，用來在測試裡把「文字在當前行底色上
必須看得見」這件事釘死，避免同樣的問題再犯一次。
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette


def is_dark(palette: QPalette) -> bool:
    """以編輯區底色的亮度判定深淺主題。"""
    return palette.color(QPalette.ColorRole.Base).lightness() < 128


def blend(a: QColor, b: QColor, t: float) -> QColor:
    """把 a 往 b 混合 t（0~1）。用來從底色調出「稍微不一樣」的底色。"""
    t = max(0.0, min(1.0, t))
    return QColor(
        round(a.red() + (b.red() - a.red()) * t),
        round(a.green() + (b.green() - a.green()) * t),
        round(a.blue() + (b.blue() - a.blue()) * t),
    )


def _channel(value: int) -> float:
    c = value / 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(color: QColor) -> float:
    """WCAG 相對亮度。"""
    return (
        0.2126 * _channel(color.red())
        + 0.7152 * _channel(color.green())
        + 0.0722 * _channel(color.blue())
    )


def contrast_ratio(fg: QColor, bg: QColor) -> float:
    """WCAG 對比度，1（完全看不見）到 21（黑白）。內文一般要求 >= 4.5。"""
    a, b = relative_luminance(fg), relative_luminance(bg)
    lighter, darker = max(a, b), min(a, b)
    return (lighter + 0.05) / (darker + 0.05)


# --------------------------------------------------------------------------
# 工具列
# --------------------------------------------------------------------------
def toolbar_icon_color(palette: QPalette) -> QColor:
    """工具列圖示的顏色（SRS-007 BR-TB-2）。

    用按鈕文字色而不是寫死黑色：深色主題下它本來就是淺色，圖示才看得見。
    與這個模組其他函式同一條規則——顏色一律從 palette 推導。
    """
    return palette.color(QPalette.ColorRole.ButtonText)


# --------------------------------------------------------------------------
# 編輯區
# --------------------------------------------------------------------------
def current_line_color(palette: QPalette) -> QColor:
    """當前行的底色：從編輯區底色往強調色微調，深淺主題都只是「稍亮/稍暗」。

    刻意混得很淡（深色主題 16%、淺色 9%），文字色與它的對比幾乎不變，
    這正是原本寫死淺色所破壞的性質。
    """
    base = palette.color(QPalette.ColorRole.Base)
    accent = palette.color(QPalette.ColorRole.Highlight)
    return blend(base, accent, 0.16 if is_dark(palette) else 0.09)


def block_caret_color(palette: QPalette) -> QColor:
    """欄模式的多重游標。紅色系，在深淺底色上都要跳出來。"""
    return QColor("#ff6b60") if is_dark(palette) else QColor("#d1322a")


def bookmark_color(palette: QPalette) -> QColor:
    return QColor("#5aa9ff") if is_dark(palette) else QColor("#1a73e8")


def fold_marker_color(palette: QPalette) -> QColor:
    window = palette.color(QPalette.ColorRole.Window)
    text = palette.color(QPalette.ColorRole.WindowText)
    return blend(window, text, 0.55)


# --------------------------------------------------------------------------
# 行號欄
# --------------------------------------------------------------------------
def gutter_background(palette: QPalette) -> QColor:
    window = palette.color(QPalette.ColorRole.Window)
    text = palette.color(QPalette.ColorRole.WindowText)
    return blend(window, text, 0.05)


def gutter_border(palette: QPalette) -> QColor:
    window = palette.color(QPalette.ColorRole.Window)
    text = palette.color(QPalette.ColorRole.WindowText)
    return blend(window, text, 0.18)


def gutter_text(palette: QPalette) -> QColor:
    """行號：刻意比正文淡，但仍須可讀（測試要求對比 >= 3）。"""
    window = palette.color(QPalette.ColorRole.Window)
    text = palette.color(QPalette.ColorRole.WindowText)
    return blend(window, text, 0.55)


def gutter_current_text(palette: QPalette) -> QColor:
    """游標所在行的行號，用強調色但確保在行號欄底色上看得清楚。"""
    accent = palette.color(QPalette.ColorRole.Highlight)
    bg = gutter_background(palette)
    if contrast_ratio(accent, bg) >= 3.0:
        return accent
    # 強調色與底色太接近時，往文字色拉回來
    return blend(accent, palette.color(QPalette.ColorRole.WindowText), 0.5)


# --------------------------------------------------------------------------
# 語法上色
# --------------------------------------------------------------------------
#: 深色與淺色各一組。深色那組挑的是在 #1e1e1e ~ #303030 底色上可讀的亮色系。
SYNTAX_LIGHT = {
    "keyword": "#0033b3",
    "string": "#067d17",
    "comment": "#6a737d",
    "number": "#1750eb",
    "function": "#7a3e9d",
    "tag": "#0033b3",
}

SYNTAX_DARK = {
    "keyword": "#82aaff",
    "string": "#a5d6a7",
    "comment": "#9aa0a6",
    "number": "#ffb86c",
    "function": "#d7a3ff",
    "tag": "#82aaff",
}


def syntax_colors(palette: QPalette) -> dict[str, str]:
    return SYNTAX_DARK if is_dark(palette) else SYNTAX_LIGHT
