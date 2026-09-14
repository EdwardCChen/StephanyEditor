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

import pytest

from stephany.core.block import (
    BlockOptions,
    apply_edits,
    backspace_region,
    col_anchor,
    delete_region,
    edits_for_delete,
    edits_for_insert,
    edits_for_segments,
    extract_block,
    format_number,
    make_region,
    number_sequence,
)

OPTS = BlockOptions()


@pytest.fixture
def lines():
    return ["你好世界", "abcdefgh", "中a中b", "xy"]


def test_make_region_normalises_corners():
    r = make_region(5, 9, 2, 3)
    assert (r.top, r.bottom, r.left, r.right) == (2, 5, 3, 9)


def test_col_anchor_on_clean_boundary():
    a = col_anchor("你好", 2, pad=False)
    assert (a.index, a.lead, a.tail, a.resume) == (1, "", "", 1)


def test_col_anchor_splitting_wide_char_pads_both_halves():
    # 第 1 欄切在「你」的正中間：整個字拿掉，左右各補一個空白
    a = col_anchor("你好", 1, pad=False)
    assert (a.index, a.lead, a.tail, a.resume) == (0, " ", " ", 1)


def test_col_anchor_pads_short_line_only_when_asked():
    assert col_anchor("ab", 6, pad=True).lead == "    "
    assert col_anchor("ab", 6, pad=False).lead == ""
    assert col_anchor("ab", 6, pad=False).at_col == 2


def test_extract_keeps_rectangle_width(lines):
    region = make_region(0, 1, 3, 5)
    got = extract_block(lines, region)
    assert got == [" 好 ", "bcde", " a中", "y"]


def test_extract_short_line_gives_empty_string():
    region = make_region(0, 4, 0, 8)
    assert extract_block(["ab"], region) == [""]


def test_delete_rectangle_degrades_split_cjk_to_spaces(lines):
    region = make_region(0, 1, 3, 5)
    assert apply_edits(lines, edits_for_delete(lines, region)) == [
        "  界",
        "afgh",
        " b",
        "x",
    ]


def test_delete_does_not_pad_short_lines():
    lines = ["abcdefgh", "ab"]
    region = make_region(0, 4, 1, 6)
    assert apply_edits(lines, edits_for_delete(lines, region)) == ["abcdgh", "ab"]


def test_insert_aligns_every_line_at_same_column(lines):
    region = make_region(0, 1, 3, 1)  # 寬度為零 = 多重游標
    out = apply_edits(lines, edits_for_insert(lines, region, "#"))
    assert out == [" # 好世界", "a#bcdefgh", " # a中b", "x#y"]


def test_insert_pads_lines_shorter_than_target_column():
    lines = ["abcdef", "ab"]
    region = make_region(0, 4, 1, 4)
    out = apply_edits(lines, edits_for_insert(lines, region, "X"))
    assert out == ["abcdXef", "ab  X"]


def test_insert_chinese_text_into_rectangle():
    lines = ["item1", "item2", "item3"]
    region = make_region(0, 0, 2, 0)
    out = apply_edits(lines, edits_for_insert(lines, region, "項目："))
    assert out == ["項目：item1", "項目：item2", "項目：item3"]


def test_rectangle_with_width_replaces_content(lines):
    region = make_region(0, 2, 1, 4)
    out = apply_edits(lines, edits_for_insert(lines, region, "==="))
    assert out == ["你===世界", "ab===efgh", "中a中b", "xy"]


def test_segments_paste_one_line_each():
    lines = ["aaa", "bbb", "ccc"]
    edits = edits_for_segments(lines, 0, 1, ["一", "二", "三"])
    assert apply_edits(lines, edits) == ["a一aa", "b二bb", "c三cc"]


def test_segments_stop_at_end_of_document():
    lines = ["aaa"]
    edits = edits_for_segments(lines, 0, 0, ["x", "y", "z"])
    assert apply_edits(lines, edits) == ["xaaa"]


def test_backspace_uses_caret_line_char_width():
    lines = ["ab你", "cdef"]
    region = make_region(0, 4, 1, 4)  # 游標行是第 0 行，左邊是「你」佔 2 欄
    target = backspace_region(lines, region)
    assert (target.left, target.right) == (2, 4)
    assert apply_edits(lines, edits_for_delete(lines, target)) == ["ab", "cd"]


def test_delete_key_extends_right_by_one_cell():
    lines = ["ab你x", "cdefg"]
    region = make_region(0, 2, 1, 2)
    target = delete_region(lines, region)
    assert (target.left, target.right) == (2, 4)
    assert apply_edits(lines, edits_for_delete(lines, target)) == ["abx", "cdg"]


def test_tab_split_in_the_middle_becomes_spaces():
    lines = ["a\tb"]
    region = make_region(0, 2, 0, 3)
    assert apply_edits(lines, edits_for_delete(lines, region)) == ["a  b"]


def test_round_trip_cut_then_paste_restores_text(lines):
    region = make_region(0, 2, 1, 6)
    taken = extract_block(lines, region)
    cut = apply_edits(lines, edits_for_delete(lines, region))
    back = apply_edits(cut, edits_for_segments(cut, 0, 2, taken))
    assert back[:2] == lines[:2]


def test_format_number_bases():
    assert format_number(255, 16, 0, False) == "FF"
    assert format_number(5, 2, 4, True) == "0101"
    assert format_number(-7, 10, 3, True) == "-007"


def test_number_sequence_pads_to_widest_value():
    assert number_sequence(3, 8, 1, 1, 10, True) == ["08", "09", "10"]


def test_number_sequence_repeat():
    assert number_sequence(4, 1, 1, 2, 10, False) == ["1", "1", "2", "2"]
