"""書籤：行號集合與它在文件變動時的平移邏輯。

規格：SRS-002 F-BM-01 ~ F-BM-10、BR-BM-1 ~ BR-BM-5、D-03、NF-01、NF-04

為什麼不把書籤存在 QTextBlock 上（D-03）：
  * `QTextBlock.userState` 已經被語法上色的「區塊註解跨行狀態」佔用。
  * `QTextBlockUserData` 在 undo/redo 之後會失效，書籤會莫名消失。
所以書籤獨立成一個行號集合，由文件的 contentsChange 訊號驅動平移。
好處是這段邏輯完全純函式，可以單元測試到每個邊界。

內部一律維持「已排序」的行號串列，跳轉用二分搜尋（NF-04）。
"""

from __future__ import annotations

import bisect
from typing import Iterable, Iterator


class BookmarkSet:
    """一個分頁的書籤集合（D-06：每個分頁獨立，不隨檔案存檔）。"""

    __slots__ = ("_lines",)

    def __init__(self, lines: Iterable[int] = ()):
        self._lines: list[int] = sorted(set(lines))

    # -- 查詢 ----------------------------------------------------------
    def __contains__(self, line: int) -> bool:
        i = bisect.bisect_left(self._lines, line)
        return i < len(self._lines) and self._lines[i] == line

    def __len__(self) -> int:
        return len(self._lines)

    def __iter__(self) -> Iterator[int]:
        return iter(self._lines)

    def __eq__(self, other) -> bool:
        if isinstance(other, BookmarkSet):
            return self._lines == other._lines
        return NotImplemented

    def __repr__(self) -> str:
        return f"BookmarkSet({self._lines!r})"

    def lines(self) -> list[int]:
        return list(self._lines)

    # -- 增刪 ----------------------------------------------------------
    def add(self, line: int) -> None:
        if line < 0:
            return
        i = bisect.bisect_left(self._lines, line)
        if i == len(self._lines) or self._lines[i] != line:
            self._lines.insert(i, line)

    def remove(self, line: int) -> None:
        i = bisect.bisect_left(self._lines, line)
        if i < len(self._lines) and self._lines[i] == line:
            del self._lines[i]

    def toggle(self, line: int) -> bool:
        """切換並回傳切換後的狀態（F-BM-01）。"""
        if line in self:
            self.remove(line)
            return False
        self.add(line)
        return True

    def clear(self) -> None:
        self._lines.clear()

    def invert(self, line_count: int) -> None:
        """反轉：有書籤的移除、沒有的加上（F-BM-09）。"""
        marked = set(self._lines)
        self._lines = [n for n in range(line_count) if n not in marked]

    # -- 跳轉（BR-BM-3 繞回式）----------------------------------------
    def next_after(self, line: int) -> int | None:
        """比 `line` 大的第一個書籤；沒有就繞回最小的（BR-BM-2/3/4）。"""
        if not self._lines:
            return None
        i = bisect.bisect_right(self._lines, line)
        return self._lines[i] if i < len(self._lines) else self._lines[0]

    def prev_before(self, line: int) -> int | None:
        """比 `line` 小的最後一個書籤；沒有就繞回最大的。"""
        if not self._lines:
            return None
        i = bisect.bisect_left(self._lines, line)
        return self._lines[i - 1] if i > 0 else self._lines[-1]

    # -- 文件變動時的平移（BR-BM-1、BR-BM-2）---------------------------
    def apply_line_delta(self, start_line: int, delta: int) -> None:
        """文件在 `start_line` 處增減了 `delta` 行，調整所有書籤。

        規則刻意定義成「以 start_line 這一行為分界」：

        * delta > 0（插入）：只有**嚴格大於** start_line 的書籤往下移。
          在第 5 行中間按 Enter 會把第 5 行拆成兩行，第 5 行的書籤留在
          上半段——這與 Notepad++ 的行為一致，也才符合「書籤標的是這一行
          的開頭」的直覺。

        * delta < 0（刪除）：被吃掉的 (start_line, start_line-delta] 這些行
          上的書籤直接移除（BR-BM-2），更下面的往上移。
        """
        if delta == 0 or not self._lines:
            return
        if delta > 0:
            self._lines = [n + delta if n > start_line else n for n in self._lines]
            return
        gone_end = start_line - delta  # delta 為負，等於 start_line + 刪掉的行數
        moved = []
        for n in self._lines:
            if n <= start_line:
                moved.append(n)
            elif n <= gone_end:
                continue  # 這一行整行被刪掉了
            else:
                moved.append(n + delta)
        self._lines = moved

    def clamp(self, line_count: int) -> None:
        """丟棄超出文件範圍的書籤（BR-BM-5）。"""
        self._lines = [n for n in self._lines if 0 <= n < line_count]

    # -- 批次操作用（F-BM-06 / 07 / 08）--------------------------------
    def contiguous_ranges(self) -> list[tuple[int, int]]:
        """把書籤行併成連續區間 [(起, 迄含), ...]，由大到小排列。

        由大到小是為了讓呼叫端可以從文件尾端往前刪，前面的行號才不會位移。
        """
        if not self._lines:
            return []
        ranges: list[tuple[int, int]] = []
        start = prev = self._lines[0]
        for n in self._lines[1:]:
            if n == prev + 1:
                prev = n
                continue
            ranges.append((start, prev))
            start = prev = n
        ranges.append((start, prev))
        ranges.reverse()
        return ranges
