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

"""摺疊範圍偵測與摺疊狀態測試。對應 SRS-003 D-01、BR-FD-*、NF-02。"""

import pytest

from stephany.core.folding import (
    BRACE,
    INDENT,
    FoldRegion,
    FoldState,
    compute_regions,
    hidden_lines,
    innermost_region_containing,
    region_starting_at,
    regions_hiding,
    style_for,
)

PYTHON = [
    "def 計算(a, b):",       # 0
    "    總和 = a + b",      # 1
    "",                      # 2
    "    if 總和 > 10:",     # 3
    "        return 總和",   # 4
    "    return 0",          # 5
    "",                      # 6
    "def 其他():",           # 7
    "    pass",              # 8
]


def starts_ends(regions):
    return [(r.start, r.end) for r in regions]


# -- 語言判定 -----------------------------------------------------------
def test_style_for_picks_braces_for_c_family():
    assert style_for("main.c") == BRACE
    assert style_for("App.tsx") == BRACE
    assert style_for("data.json") == BRACE


def test_style_for_defaults_to_indent():
    assert style_for("script.py") == INDENT
    assert style_for("notes.txt") == INDENT
    assert style_for(None) == INDENT


# -- 縮排式偵測 ---------------------------------------------------------
def test_indent_regions_are_detected_with_nesting():
    regions = compute_regions(PYTHON, INDENT)
    assert starts_ends(regions) == [(0, 5), (3, 4), (7, 8)]
    assert [r.level for r in regions] == [0, 1, 0]


def test_br_fd_1_blank_lines_do_not_break_a_block():
    """第 2 行是空行，區塊仍從 0 延伸到 5。"""
    regions = compute_regions(PYTHON, INDENT)
    assert region_starting_at(regions, 0).end == 5


def test_br_fd_1_trailing_blank_lines_are_not_part_of_the_block():
    lines = ["def f():", "    a", "", "", "def g():", "    b"]
    regions = compute_regions(lines, INDENT)
    assert region_starting_at(regions, 0).end == 1


def test_single_line_without_children_is_not_foldable():
    assert compute_regions(["a = 1", "b = 2"], INDENT) == []


def test_tabs_count_as_indentation():
    lines = ["def f():", "\ta = 1", "\tb = 2"]
    assert starts_ends(compute_regions(lines, INDENT, tab_width=4)) == [(0, 2)]


def test_deeply_nested_indentation_levels():
    lines = ["a:", "  b:", "    c:", "      d", "e"]
    regions = compute_regions(lines, INDENT, tab_width=2)
    assert starts_ends(regions) == [(0, 3), (1, 3), (2, 3)]
    assert [r.level for r in regions] == [0, 1, 2]


def test_nf_02_detection_is_linear_on_large_input():
    lines = []
    for _ in range(5000):
        lines += ["def f():", "    pass"]
    regions = compute_regions(lines, INDENT)
    assert len(regions) == 5000


# -- 大括號式偵測 -------------------------------------------------------
def test_brace_regions_with_nesting():
    lines = [
        "int main() {",
        "    if (x) {",
        "        return 1;",
        "    }",
        "    return 0;",
        "}",
    ]
    regions = compute_regions(lines, BRACE)
    assert starts_ends(regions) == [(0, 5), (1, 3)]
    assert [r.level for r in regions] == [0, 1]


def test_br_fd_7_braces_inside_strings_are_ignored():
    lines = ['void f() {', '    printf("} 這不是結尾 {");', '    int x = 1;', '}']
    assert starts_ends(compute_regions(lines, BRACE)) == [(0, 3)]


def test_br_fd_7_braces_inside_line_comments_are_ignored():
    lines = ["void f() {", "    // } 這也不算", "    x = 1;", "}"]
    assert starts_ends(compute_regions(lines, BRACE)) == [(0, 3)]


def test_br_fd_7_braces_inside_block_comments_spanning_lines_are_ignored():
    lines = ["void f() {", "    /* {", "       } */", "    x = 1;", "}"]
    assert starts_ends(compute_regions(lines, BRACE)) == [(0, 4)]


def test_br_fd_7_escaped_quote_does_not_end_the_string():
    lines = ['void f() {', '    char *s = "\\" {";', '    x = 1;', '}']
    assert starts_ends(compute_regions(lines, BRACE)) == [(0, 3)]


def test_braces_on_the_same_line_are_not_foldable():
    assert compute_regions(["int f() { return 1; }"], BRACE) == []


def test_unbalanced_braces_do_not_crash():
    assert compute_regions(["void f() {", "    x;"], BRACE) == []
    assert compute_regions(["}", "}"], BRACE) == []


# -- 查詢 ---------------------------------------------------------------
def test_innermost_region_containing():
    regions = compute_regions(PYTHON, INDENT)
    assert innermost_region_containing(regions, 4).start == 3  # 挑最內層
    assert innermost_region_containing(regions, 1).start == 0
    assert innermost_region_containing(regions, 6) is None


def test_region_starting_at_returns_none_for_plain_lines():
    regions = compute_regions(PYTHON, INDENT)
    assert region_starting_at(regions, 1) is None


# -- 隱藏行計算 ---------------------------------------------------------
def test_br_fd_2_header_line_stays_visible():
    regions = compute_regions(PYTHON, INDENT)
    hidden = hidden_lines(regions, {0})
    assert 0 not in hidden
    assert hidden == {1, 2, 3, 4, 5}


def test_br_fd_3_inner_fold_is_remembered_while_outer_is_folded():
    """外層摺疊會蓋住內層，但內層自己的狀態保留——展開外層後內層仍摺疊。"""
    regions = compute_regions(PYTHON, INDENT)
    folded = FoldState([0, 3])
    assert hidden_lines(regions, folded) == {1, 2, 3, 4, 5}
    folded.remove(0)  # 只展開外層
    assert hidden_lines(regions, folded) == {4}


def test_regions_hiding_lists_ancestors_outermost_first():
    regions = compute_regions(PYTHON, INDENT)
    hiding = regions_hiding(regions, 4, {0, 3})
    assert [r.start for r in hiding] == [0, 3]


def test_regions_hiding_is_empty_for_a_visible_line():
    regions = compute_regions(PYTHON, INDENT)
    assert regions_hiding(regions, 4, set()) == []


def test_hidden_count_reports_lines_concealed():
    assert FoldRegion(3, 9, 0).hidden_count == 6


# -- 摺疊狀態 -----------------------------------------------------------
def test_br_fd_4_sync_drops_folds_that_are_no_longer_block_starts():
    regions = compute_regions(PYTHON, INDENT)
    state = FoldState([0, 3, 99])
    state.sync_with(regions)
    assert state.lines() == [0, 3]


def test_br_fd_4_fold_state_shifts_when_lines_are_inserted_above():
    state = FoldState([5])
    state.apply_line_delta(2, 3)
    assert state.lines() == [8]


def test_f_fd_05_fold_to_level():
    regions = compute_regions(PYTHON, INDENT)
    state = FoldState()
    state.fold_to_level(regions, 1)  # 只摺內層，最外層維持展開
    assert state.lines() == [3]
    state.fold_to_level(regions, 0)  # 全部
    assert state.lines() == [0, 3, 7]
