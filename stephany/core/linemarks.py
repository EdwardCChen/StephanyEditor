"""以「行號集合」為基礎的標記，以及它在文件增減行時的平移規則。

書籤（SRS-002）與摺疊狀態（SRS-003）需要的是同一種資料結構：一組行號，
在文件上方插入或刪除行時要跟著平移，被刪掉那幾行的標記要消失。
把它抽出來共用，平移規則只有一份實作、一組測試。
"""

from __future__ import annotations

import bisect
from typing import Iterable, Iterator


class LineMarkSet:
    """排序好的行號集合。跳轉用二分搜尋（SRS-002 NF-04）。"""

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
        if isinstance(other, LineMarkSet):
            return self._lines == other._lines
        return NotImplemented

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self._lines!r})"

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
        if line in self:
            self.remove(line)
            return False
        self.add(line)
        return True

    def clear(self) -> None:
        self._lines.clear()

    def replace(self, lines: Iterable[int]) -> None:
        self._lines = sorted(set(lines))

    def invert(self, line_count: int) -> None:
        marked = set(self._lines)
        self._lines = [n for n in range(line_count) if n not in marked]

    # -- 跳轉（繞回式）--------------------------------------------------
    def next_after(self, line: int) -> int | None:
        if not self._lines:
            return None
        i = bisect.bisect_right(self._lines, line)
        return self._lines[i] if i < len(self._lines) else self._lines[0]

    def prev_before(self, line: int) -> int | None:
        if not self._lines:
            return None
        i = bisect.bisect_left(self._lines, line)
        return self._lines[i - 1] if i > 0 else self._lines[-1]

    # -- 文件變動時的平移 ----------------------------------------------
    def apply_line_delta(self, start_line: int, delta: int) -> None:
        """文件在 `start_line` 處增減了 `delta` 行，調整所有標記。

        * delta > 0（插入）：只有**嚴格大於** start_line 的標記往下移。
          在第 5 行中間按 Enter 會把該行拆成兩行，第 5 行的標記留在上半段
          ——與 Notepad++ 一致，也符合「標記標的是這一行的開頭」的直覺。
        * delta < 0（刪除）：被吃掉的 (start_line, start_line-delta] 這些行
          上的標記直接移除，更下面的往上移。
        """
        if delta == 0 or not self._lines:
            return
        if delta > 0:
            self._lines = [n + delta if n > start_line else n for n in self._lines]
            return
        gone_end = start_line - delta
        moved = []
        for n in self._lines:
            if n <= start_line:
                moved.append(n)
            elif n <= gone_end:
                continue
            else:
                moved.append(n + delta)
        self._lines = moved

    def clamp(self, line_count: int) -> None:
        self._lines = [n for n in self._lines if 0 <= n < line_count]

    def contiguous_ranges(self) -> list[tuple[int, int]]:
        """連續區間 [(起, 迄含), ...]，由大到小——呼叫端可從尾端往前刪不位移。"""
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
