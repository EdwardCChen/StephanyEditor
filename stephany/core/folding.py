"""程式碼摺疊：可摺疊範圍的偵測，以及摺疊狀態。

規格：SRS-003 D-01、F-FD-*、BR-FD-1/2/3/4/7、NF-01、NF-02

D-01 決定不做語法剖析，改用兩種啟發式：

  * **縮排**（Python、YAML、純文字）：某一行後面接著更深縮排的行，
    它就是一個可摺疊區塊的標頭，區塊延伸到縮排回到同層之前。
  * **大括號**（C / C++ / Java / JS / JSON / Rust …）：從含有未配對 `{`
    的那一行，到配對 `}` 的那一行。掃描時會跳過字串與註解裡的括號
    （BR-FD-7），否則 `printf("{")` 之類會把整份檔案的層級算歪。

每支援一種語言就寫一個 parser 的維護成本太高，而這兩種啟發式已涵蓋
絕大多數實際檔案。偵測是單次線性掃描（NF-02）。
"""

from __future__ import annotations

from dataclasses import dataclass

from .linemarks import LineMarkSet
from .widths import DEFAULT_TAB_WIDTH

#: 用大括號判斷層級的副檔名；其餘一律用縮排
BRACE_EXTENSIONS = (
    ".c", ".h", ".cpp", ".hpp", ".cc", ".cxx", ".java", ".cs", ".go", ".rs",
    ".js", ".ts", ".jsx", ".tsx", ".json", ".css", ".scss", ".php", ".swift",
    ".kt", ".scala", ".m", ".mm",
)

INDENT = "indent"
BRACE = "brace"


def style_for(path: str | None) -> str:
    """依副檔名決定用哪種啟發式。"""
    if path and path.lower().endswith(BRACE_EXTENSIONS):
        return BRACE
    return INDENT


@dataclass(frozen=True)
class FoldRegion:
    """一個可摺疊區塊。

    `start` 是標頭行，摺疊時它本身保持可見（BR-FD-2）；
    隱藏的是 start+1 到 end。
    """

    start: int
    end: int
    level: int

    @property
    def hidden_count(self) -> int:
        return self.end - self.start


def _indent_width(line: str, tab_width: int) -> int | None:
    """前導空白的顯示寬度。整行空白回傳 None（BR-FD-1：不參與判斷）。"""
    col = 0
    for ch in line:
        if ch == " ":
            col += 1
        elif ch == "\t":
            col += tab_width - (col % tab_width)
        else:
            return col
    return None


def _indent_regions(lines, tab_width: int) -> list[FoldRegion]:
    regions: list[FoldRegion] = []
    stack: list[tuple[int, int]] = []  # (縮排寬度, 標頭行)
    prev_line = -1
    prev_indent = -1
    for i, text in enumerate(lines):
        indent = _indent_width(text, tab_width)
        if indent is None:
            continue  # 空白行不影響區塊判斷
        if prev_line >= 0 and indent > prev_indent:
            stack.append((prev_indent, prev_line))
        while stack and indent <= stack[-1][0]:
            _, start = stack.pop()
            if prev_line > start:
                regions.append(FoldRegion(start, prev_line, len(stack)))
        prev_line, prev_indent = i, indent
    while stack:
        _, start = stack.pop()
        if prev_line > start:
            regions.append(FoldRegion(start, prev_line, len(stack)))
    regions.sort(key=lambda r: r.start)
    return regions


def _brace_regions(lines, tab_width: int) -> list[FoldRegion]:
    regions: list[FoldRegion] = []
    stack: list[int] = []
    in_block_comment = False
    for i, text in enumerate(lines):
        j = 0
        n = len(text)
        in_string: str | None = None
        while j < n:
            ch = text[j]
            if in_block_comment:
                if ch == "*" and j + 1 < n and text[j + 1] == "/":
                    in_block_comment = False
                    j += 2
                    continue
            elif in_string is not None:
                if ch == "\\":
                    j += 2
                    continue
                if ch == in_string:
                    in_string = None
            elif ch in "\"'`":
                in_string = ch
            elif ch == "/" and j + 1 < n and text[j + 1] == "/":
                break  # 行註解，這一行剩下的不看
            elif ch == "#" and j == 0:
                break  # 前置處理指令／井字註解
            elif ch == "/" and j + 1 < n and text[j + 1] == "*":
                in_block_comment = True
                j += 2
                continue
            elif ch == "{":
                stack.append(i)
            elif ch == "}" and stack:
                start = stack.pop()
                if i > start:
                    regions.append(FoldRegion(start, i, len(stack)))
            j += 1
    regions.sort(key=lambda r: r.start)
    return regions


def compute_regions(
    lines,
    style: str = INDENT,
    tab_width: int = DEFAULT_TAB_WIDTH,
) -> list[FoldRegion]:
    """偵測所有可摺疊區塊，依標頭行排序。"""
    if style == BRACE:
        return _brace_regions(lines, tab_width)
    return _indent_regions(lines, tab_width)


def region_starting_at(regions, line: int) -> FoldRegion | None:
    for region in regions:
        if region.start == line:
            return region
    return None


def innermost_region_containing(regions, line: int) -> FoldRegion | None:
    """包含 `line` 的最內層區塊（標頭行本身算在內）。"""
    best: FoldRegion | None = None
    for region in regions:
        if region.start <= line <= region.end:
            if best is None or region.level > best.level:
                best = region
    return best


def hidden_lines(regions, folded) -> set[int]:
    """目前被藏起來的行號集合。

    巢狀時外層摺疊會連內層一起藏，而內層自己的摺疊狀態保留不變——
    展開外層後內層仍是摺疊的（BR-FD-3）。
    """
    hidden: set[int] = set()
    for region in regions:
        if region.start in folded:
            hidden.update(range(region.start + 1, region.end + 1))
    return hidden


def regions_hiding(regions, line: int, folded) -> list[FoldRegion]:
    """所有「因為自己是摺疊的而藏住了 `line`」的區塊，由外而內。"""
    out = [
        r for r in regions if r.start in folded and r.start < line <= r.end
    ]
    out.sort(key=lambda r: r.level)
    return out


class FoldState(LineMarkSet):
    """目前被摺疊的區塊（以標頭行號表示）。

    沿用 LineMarkSet 的平移規則，文件增減行時摺疊狀態會跟著移動（BR-FD-4）。
    """

    def sync_with(self, regions) -> None:
        """丟掉已經不是區塊起點的摺疊狀態（BR-FD-4）。"""
        starts = {r.start for r in regions}
        self.replace([n for n in self if n in starts])

    def fold_to_level(self, regions, level: int) -> None:
        """摺疊第 `level` 層（0 起算）以內的所有區塊，較外層維持展開（F-FD-05）。"""
        self.replace([r.start for r in regions if r.level >= level])
