"""欄（直行）模式的純邏輯：矩形範圍的取出、插入、刪除、取代、貼上。

這一層完全不依賴 Qt，輸入是「一串行字串」，輸出是「每行要做什麼修改」
（LineEdit），由 UI 層再套用到 QTextDocument 上。這樣做有兩個好處：
  1. 可以完全用 pytest 驗證中英混排的各種邊界情況，不用開視窗。
  2. UI 層可以把所有 LineEdit 包在同一個 undo 區塊裡，Ctrl+Z 一次還原。

核心難題是「切到半個中文字怎麼辦」。本編輯器採用 Emacs rectangle 的作法：
被矩形邊界切開的全形字元會被移除，並用空白補回它露在矩形外的那半邊。

    你好世界        選取第 1~5 欄        [空白]好[空白]
    ^^^^^^^^        ------>              刪除後剩 "  界"

這樣做的理由是：唯一的替代方案（不切、整個字算進去或整個字排除）會讓
矩形在畫面上變成鋸齒狀，後續的插入位置也會跟著歪掉。寧可補空白保持對齊。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from .widths import (
    DEFAULT_TAB_WIDTH,
    display_width,
    iter_cells,
    next_col,
    prev_col,
)


@dataclass(frozen=True)
class BlockOptions:
    """欄位運算的行為設定。"""

    tab_width: int = DEFAULT_TAB_WIDTH
    ambiguous_wide: bool = False
    #: 插入時，比目標欄還短的行是否要補空白對齊（Notepad++ 的行為）
    pad_short_lines: bool = True


DEFAULT_OPTIONS = BlockOptions()


@dataclass(frozen=True)
class BlockRegion:
    """正規化後的矩形範圍：第 top..bottom 行（含），第 left..right 欄（不含右）。"""

    top: int
    bottom: int
    left: int
    right: int

    @property
    def is_empty_width(self) -> bool:
        """寬度為零 = 多重游標（每行一個插入點）。"""
        return self.left == self.right

    @property
    def line_count(self) -> int:
        return self.bottom - self.top + 1

    def lines(self) -> range:
        return range(self.top, self.bottom + 1)


def make_region(
    anchor_line: int, anchor_col: int, caret_line: int, caret_col: int
) -> BlockRegion:
    """由「錨點」與「游標」兩個角落算出正規化的矩形。"""
    return BlockRegion(
        top=min(anchor_line, caret_line),
        bottom=max(anchor_line, caret_line),
        left=min(anchor_col, caret_col),
        right=max(anchor_col, caret_col),
    )


@dataclass(frozen=True)
class ColAnchor:
    """一行文字在某個顯示欄位上的「切點」。

    左半 = line[:index] + lead
    右半 = tail + line[resume:]
    中間被切掉的 line[index:resume] 是那個跨越邊界的全形字（或 TAB）。
    """

    index: int
    lead: str
    tail: str
    resume: int
    at_col: int  # 實際到達的欄位（沒補空白的短行會小於目標欄）


def col_anchor(
    line: str,
    col: int,
    *,
    pad: bool,
    options: BlockOptions = DEFAULT_OPTIONS,
) -> ColAnchor:
    """找出 `line` 在顯示欄位 `col` 的切點。

    pad=True 時，短於 col 的行會在尾端補空白直到 col（用於插入）。
    pad=False 時保持原樣（用於複製與刪除，不製造多餘空白）。
    """
    for cell in iter_cells(
        line, tab_width=options.tab_width, ambiguous_wide=options.ambiguous_wide
    ):
        if cell.col == col:
            return ColAnchor(cell.start, "", "", cell.start, col)
        if cell.col < col < cell.end_col:
            # 切到全形字或 TAB 的中間：整格拿掉，兩邊各補回露出來的空白
            return ColAnchor(
                index=cell.start,
                lead=" " * (col - cell.col),
                tail=" " * (cell.end_col - col),
                resume=cell.end,
                at_col=col,
            )
    end_col = display_width(
        line, tab_width=options.tab_width, ambiguous_wide=options.ambiguous_wide
    )
    if col > end_col and pad:
        return ColAnchor(len(line), " " * (col - end_col), "", len(line), col)
    return ColAnchor(len(line), "", "", len(line), end_col)


@dataclass(frozen=True)
class LineEdit:
    """把某一行的 [start, end) 這段字元換成 text。"""

    line: int
    start: int
    end: int
    text: str


def line_edit_for(
    line_no: int,
    line: str,
    left: int,
    right: int,
    insert: str = "",
    *,
    options: BlockOptions = DEFAULT_OPTIONS,
    pad: bool | None = None,
) -> LineEdit:
    """單行的矩形操作：把 [left, right) 欄換成 insert。

    這一個函式同時涵蓋刪除（insert=""）、插入（left==right）與取代。
    """
    if pad is None:
        # 有東西要插入時才補空白；單純刪除不該把短行撐長
        pad = options.pad_short_lines and bool(insert)
    a = col_anchor(line, left, pad=pad, options=options)
    b = col_anchor(line, right, pad=False, options=options)
    if b.index < a.index or (b.index == a.index and b.resume < a.resume):
        b = a  # 右界落在行尾之前（短行），退回左界
    return LineEdit(
        line=line_no,
        start=a.index,
        end=max(a.resume, b.resume),
        text=a.lead + insert + b.tail,
    )


def edits_for_delete(
    lines: Sequence[str],
    region: BlockRegion,
    *,
    options: BlockOptions = DEFAULT_OPTIONS,
) -> list[LineEdit]:
    """刪除矩形範圍內的內容。"""
    if region.is_empty_width:
        return []
    out = []
    for n in region.lines():
        if n >= len(lines):
            break
        edit = line_edit_for(
            n, lines[n], region.left, region.right, "", options=options, pad=False
        )
        if edit.start != edit.end or edit.text:
            out.append(edit)
    return out


def edits_for_insert(
    lines: Sequence[str],
    region: BlockRegion,
    text: str,
    *,
    options: BlockOptions = DEFAULT_OPTIONS,
) -> list[LineEdit]:
    """把同一段 `text` 插入矩形每一行（矩形有寬度時等於取代）。"""
    out = []
    for n in region.lines():
        if n >= len(lines):
            break
        out.append(
            line_edit_for(
                n, lines[n], region.left, region.right, text, options=options
            )
        )
    return out


def edits_for_segments(
    lines: Sequence[str],
    top: int,
    col: int,
    segments: Sequence[str],
    *,
    options: BlockOptions = DEFAULT_OPTIONS,
) -> list[LineEdit]:
    """逐行插入不同內容（貼上矩形、欄位編輯器的遞增數列都走這裡）。"""
    out = []
    for offset, seg in enumerate(segments):
        n = top + offset
        if n >= len(lines):
            break
        out.append(line_edit_for(n, lines[n], col, col, seg, options=options))
    return out


def extract_block(
    lines: Sequence[str],
    region: BlockRegion,
    *,
    options: BlockOptions = DEFAULT_OPTIONS,
) -> list[str]:
    """取出矩形範圍的文字（複製用），一行一個字串。"""
    out = []
    for n in region.lines():
        if n >= len(lines):
            break
        line = lines[n]
        a = col_anchor(line, region.left, pad=False, options=options)
        if a.at_col < region.left:
            out.append("")  # 這行比矩形左界還短
            continue
        b = col_anchor(line, region.right, pad=False, options=options)
        out.append(a.tail + line[a.resume : b.index] + b.lead)
    return out


def backspace_region(
    lines: Sequence[str],
    region: BlockRegion,
    *,
    options: BlockOptions = DEFAULT_OPTIONS,
) -> BlockRegion:
    """寬度為零時，Backspace 要刪掉的矩形。

    刪除寬度取決於「游標所在那一行」左邊那個字的寬度，而不是各行自己算。
    這是刻意的：統一寬度才能讓矩形保持是矩形；其他行若因此切到全形字，
    會依照本模組的通則降級成空白。
    """
    if not region.is_empty_width:
        return region
    ref = lines[region.top] if region.top < len(lines) else ""
    left = prev_col(
        ref,
        region.left,
        tab_width=options.tab_width,
        ambiguous_wide=options.ambiguous_wide,
    )
    return BlockRegion(region.top, region.bottom, left, region.right)


def delete_region(
    lines: Sequence[str],
    region: BlockRegion,
    *,
    options: BlockOptions = DEFAULT_OPTIONS,
) -> BlockRegion:
    """寬度為零時，Delete 要刪掉的矩形（同 backspace_region，方向相反）。"""
    if not region.is_empty_width:
        return region
    ref = lines[region.top] if region.top < len(lines) else ""
    right = next_col(
        ref,
        region.right,
        tab_width=options.tab_width,
        ambiguous_wide=options.ambiguous_wide,
    )
    return BlockRegion(region.top, region.bottom, region.left, right)


def apply_edits(lines: Sequence[str], edits: Sequence[LineEdit]) -> list[str]:
    """把 LineEdit 套到行陣列上。UI 走 QTextCursor，這裡給測試與批次處理用。"""
    out = list(lines)
    for e in edits:
        line = out[e.line]
        out[e.line] = line[: e.start] + e.text + line[e.end :]
    return out


# --------------------------------------------------------------------------
# 欄位編輯器（對應 Notepad++ 的 Column Editor）
# --------------------------------------------------------------------------

_DIGITS = "0123456789ABCDEF"


def format_number(value: int, base: int, width: int, leading_zeros: bool) -> str:
    """把整數轉成指定進位，必要時補前導零。"""
    if base not in (2, 8, 10, 16):
        raise ValueError(f"不支援的進位：{base}")
    neg = value < 0
    v = abs(value)
    s = ""
    while True:
        s = _DIGITS[v % base] + s
        v //= base
        if v == 0:
            break
    if leading_zeros and len(s) < width:
        s = "0" * (width - len(s)) + s
    return ("-" + s) if neg else s


def number_sequence(
    count: int,
    initial: int = 1,
    increase: int = 1,
    repeat: int = 1,
    base: int = 10,
    leading_zeros: bool = False,
) -> list[str]:
    """產生遞增數列。repeat 表示每個數字要連續用幾行。"""
    repeat = max(1, repeat)
    values = []
    value = initial
    for i in range(count):
        values.append(value)
        if (i + 1) % repeat == 0:
            value += increase
    width = max((len(format_number(v, base, 0, False)) for v in values), default=1)
    return [format_number(v, base, width, leading_zeros) for v in values]
