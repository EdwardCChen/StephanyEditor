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

"""書籤。規格：SRS-002 F-BM-01 ~ F-BM-10、BR-BM-1 ~ BR-BM-5、D-03

資料結構與平移規則共用自 core.linemarks.LineMarkSet——摺疊狀態（SRS-003）
需要的是同一種東西，平移邏輯只留一份實作。

為什麼不把書籤存在 QTextBlock 上（SRS-002 D-03）：
  * `QTextBlock.userState` 已經被語法上色的「區塊註解跨行狀態」佔用。
  * `QTextBlockUserData` 在 undo/redo 之後會失效，書籤會莫名消失。
"""

from __future__ import annotations

from .linemarks import LineMarkSet


class BookmarkSet(LineMarkSet):
    """一個分頁的書籤集合（SRS-002 D-06：每個分頁獨立，不隨檔案存檔）。"""
