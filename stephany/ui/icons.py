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

"""工具列圖示：單色 SVG，執行時依系統配色上色（SRS-007 D-01、D-02）。

為什麼自己畫而不是用 `QIcon.fromTheme()`：那是 freedesktop 的圖示主題機制，
只有 Linux 有。實測 macOS 上 `QIcon.themeName()` 是空字串，`document-new`
之類的標準名稱 `hasThemeIcon()` 全部回 False；Windows 同樣沒有。`QStyle` 的
內建圖示三個平台都拿得到，但沒有書籤／摺疊／巨集／欄選取這些概念，而且各
平台長相差很多。本專案的重點就是三個平台同一套操作，工具列不該長得不一樣。

為什麼要在執行時上色：SVG 裡的顏色是寫死的黑色，深色主題下會看不見。
這裡把算好的圖當成遮罩（CompositionMode_SourceIn），整片塗成呼叫端給的
顏色——顏色由 `theme.toolbar_icon_color()` 從 QPalette 推導，與專案其他
地方同一條規則（SRS-003）：不寫死顏色，使用者中途切換深淺主題也跟著變。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap

from ..resources import ICON_DIR

#: 產生哪些尺寸的點陣圖。16/24 是實際會用到的按鈕尺寸，其餘給 HiDPI 與選單用。
SIZES = (16, 20, 24, 32, 48)

#: (圖示名稱, 顏色) -> QIcon。每次重畫 12 個圖示要好幾毫秒，切主題時會整批重來。
_cache: dict[tuple[str, int], QIcon] = {}


def path_for(name: str) -> Path:
    return ICON_DIR / f"{name}.svg"


def available() -> frozenset[str]:
    """套件裡實際有哪些圖示。"""
    return frozenset(p.stem for p in ICON_DIR.glob("*.svg"))


def clear_cache() -> None:
    _cache.clear()


def _render(source: Path, size: int, color: QColor) -> QPixmap:
    """算出一張上好色的圖。

    刻意畫在 `QImage` 上而不是直接畫在 `QPixmap` 上：上色用的
    `CompositionMode_SourceIn` 只有 raster 繪圖引擎保證支援，而 `QPixmap`
    在各平台可能改用原生繪圖後端。Windows CI 實測過——直接畫在 QPixmap 上
    時整張圖是全透明的，工具列變成一排空白按鈕。`QImage` 一定是 raster。
    """
    from PySide6.QtSvg import QSvgRenderer

    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    QSvgRenderer(str(source)).render(painter)
    # 把算好的圖當遮罩整片上色。用 SourceIn 而不是逐像素改色，邊緣的
    # 半透明像素才會保留，小尺寸下不會有鋸齒。
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(image.rect(), color)
    painter.end()
    return QPixmap.fromImage(image)


def load(name: str, color: QColor) -> QIcon:
    """取得上好色的圖示。

    找不到圖示檔就回傳空的 `QIcon`——Qt 遇到空圖示會退回顯示動作文字，
    少一個圖示只是那一顆按鈕變成文字，不會變成一顆看不出用途的空白按鈕
    （SRS-007 D-05）。
    """
    key = (name, color.rgba())
    cached = _cache.get(key)
    if cached is not None:
        return cached

    source = path_for(name)
    icon = QIcon()
    if source.exists():
        for size in SIZES:
            icon.addPixmap(_render(source, size, color))
    _cache[key] = icon
    return icon
