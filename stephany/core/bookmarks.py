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
