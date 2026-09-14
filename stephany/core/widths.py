"""字元顯示寬度，以及「顯示欄位 <-> 字元索引」的互相轉換。

整個欄（直行）模式都建立在這一層之上。關鍵觀念：

    "你好ab"  ->  你(2欄) 好(2欄) a(1欄) b(1欄)  = 共 6 欄，但只有 4 個字元

如果矩形選取是用「第幾個字元」去算，中英文混排時畫面上根本不會是矩形。
所以這裡提供的所有 API 都以「顯示欄位」(display column) 為單位，
欄位 0 代表行首、欄位 n 代表第 n 個字身寬度之後的位置。

TAB 的寬度取決於它出現的位置（下一個定位點），因此寬度計算一律是
「從行首往右走」的位置相依運算，不能單看一個字元。
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Iterator

DEFAULT_TAB_WIDTH = 4

# 這些區段在 unicodedata 裡不一定被標成 Mn/Me，但排版上不佔寬度。
_ZERO_WIDTH_RANGES = (
    (0x200B, 0x200F),  # ZWSP / ZWNJ / ZWJ / LRM / RLM
    (0xFE00, 0xFE0F),  # 變體選擇符 VS1-16
    (0xE0100, 0xE01EF),  # 變體選擇符 VS17-256
)


def _in_ranges(cp: int, ranges) -> bool:
    return any(lo <= cp <= hi for lo, hi in ranges)


def is_zero_width(ch: str) -> bool:
    """組合附加符號、變體選擇符等不佔顯示寬度的字元。"""
    if unicodedata.combining(ch):
        return True
    if unicodedata.category(ch) in ("Mn", "Me", "Cf"):
        return True
    return _in_ranges(ord(ch), _ZERO_WIDTH_RANGES)


def char_width(ch: str, *, ambiguous_wide: bool = False) -> int:
    """單一字元的顯示寬度（0 / 1 / 2）。TAB 請交給 iter_cells 處理。"""
    if ch == "\t":
        raise ValueError("TAB 的寬度與位置相依，請使用 iter_cells()")
    if is_zero_width(ch):
        return 0
    eaw = unicodedata.east_asian_width(ch)
    if eaw in ("W", "F"):  # Wide / Fullwidth：中日韓文字、全形標點
        return 2
    if eaw == "A":  # Ambiguous：希臘字母、※、℃ 之類，各家終端機不一致
        return 2 if ambiguous_wide else 1
    return 1


@dataclass(frozen=True)
class Cell:
    """一個「顯示單元」= 一個基底字元加上它後面所有的零寬附加符號。

    以 cluster 為單位是為了避免把 "é"（e + U+0301）這種組合切成兩半。
    """

    start: int  # 在該行字串中的起始索引
    end: int  # 結束索引（不含）
    col: int  # 起始顯示欄位
    width: int  # 顯示寬度
    text: str  # 原始文字

    @property
    def end_col(self) -> int:
        return self.col + self.width


def iter_cells(
    line: str,
    *,
    tab_width: int = DEFAULT_TAB_WIDTH,
    ambiguous_wide: bool = False,
) -> Iterator[Cell]:
    """由左至右走過一行，產生每個顯示單元的索引與欄位資訊。"""
    i = 0
    col = 0
    n = len(line)
    while i < n:
        ch = line[i]
        j = i + 1
        if ch == "\t":
            width = tab_width - (col % tab_width)
        else:
            width = char_width(ch, ambiguous_wide=ambiguous_wide)
            # 把後面連續的零寬字元併入同一個 cluster
            while j < n and line[j] != "\t" and is_zero_width(line[j]):
                j += 1
        yield Cell(start=i, end=j, col=col, width=width, text=line[i:j])
        col += width
        i = j


def display_width(
    line: str, *, tab_width: int = DEFAULT_TAB_WIDTH, ambiguous_wide: bool = False
) -> int:
    """一整行的顯示寬度（總欄數）。"""
    col = 0
    for cell in iter_cells(line, tab_width=tab_width, ambiguous_wide=ambiguous_wide):
        col = cell.end_col
    return col


def index_to_col(
    line: str,
    index: int,
    *,
    tab_width: int = DEFAULT_TAB_WIDTH,
    ambiguous_wide: bool = False,
) -> int:
    """字元索引 -> 顯示欄位。索引超過行尾時以行尾計算後再往右延伸。"""
    col = 0
    for cell in iter_cells(line, tab_width=tab_width, ambiguous_wide=ambiguous_wide):
        if cell.start >= index:
            return cell.col
        col = cell.end_col
    return col + max(0, index - len(line))


def col_to_index(
    line: str,
    col: int,
    *,
    tab_width: int = DEFAULT_TAB_WIDTH,
    ambiguous_wide: bool = False,
) -> int:
    """顯示欄位 -> 字元索引。

    落在寬字元中間時回傳該字元的起始索引；超過行尾時回傳 len(line)。
    給「滑鼠點到哪個字」這類需要粗略對應的地方使用。
    """
    for cell in iter_cells(line, tab_width=tab_width, ambiguous_wide=ambiguous_wide):
        if col < cell.end_col:
            return cell.start
    return len(line)


def prev_col(
    line: str,
    col: int,
    *,
    tab_width: int = DEFAULT_TAB_WIDTH,
    ambiguous_wide: bool = False,
) -> int:
    """往左一個顯示單元的欄位。行尾之後每次退一欄。"""
    if col <= 0:
        return 0
    last = 0
    for cell in iter_cells(line, tab_width=tab_width, ambiguous_wide=ambiguous_wide):
        if cell.end_col >= col:
            return cell.col
        last = cell.end_col
    return max(last, col - 1)


def next_col(
    line: str,
    col: int,
    *,
    tab_width: int = DEFAULT_TAB_WIDTH,
    ambiguous_wide: bool = False,
) -> int:
    """往右一個顯示單元的欄位。行尾之後每次進一欄。"""
    for cell in iter_cells(line, tab_width=tab_width, ambiguous_wide=ambiguous_wide):
        if cell.end_col > col:
            return cell.end_col
    return col + 1
