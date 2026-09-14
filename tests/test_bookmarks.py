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

"""書籤核心邏輯測試。對應 SRS-002 F-BM-*、BR-BM-*。"""

from stephany.core.bookmarks import BookmarkSet


def test_f_bm_01_toggle_returns_new_state():
    bm = BookmarkSet()
    assert bm.toggle(3) is True
    assert 3 in bm
    assert bm.toggle(3) is False
    assert 3 not in bm


def test_set_stays_sorted_and_deduplicated():
    bm = BookmarkSet([9, 1, 5, 1])
    assert bm.lines() == [1, 5, 9]
    bm.add(5)
    assert bm.lines() == [1, 5, 9]


def test_f_bm_02_next_after():
    bm = BookmarkSet([2, 7, 11])
    assert bm.next_after(0) == 2
    assert bm.next_after(2) == 7
    assert bm.next_after(7) == 11


def test_br_bm_3_next_wraps_around():
    bm = BookmarkSet([2, 7])
    assert bm.next_after(7) == 2
    assert bm.next_after(99) == 2


def test_f_bm_03_prev_before_and_wrap():
    bm = BookmarkSet([2, 7, 11])
    assert bm.prev_before(11) == 7
    assert bm.prev_before(2) == 11  # 繞回最大的
    assert bm.prev_before(0) == 11


def test_br_bm_4_navigation_on_empty_set_returns_none():
    bm = BookmarkSet()
    assert bm.next_after(0) is None
    assert bm.prev_before(0) is None


def test_br_bm_1_insert_above_pushes_bookmarks_down():
    bm = BookmarkSet([5, 9])
    bm.apply_line_delta(2, 3)  # 在第 2 行處插入 3 行
    assert bm.lines() == [8, 12]


def test_br_bm_1_bookmark_on_split_line_stays_put():
    """在第 5 行中間按 Enter：第 5 行的書籤留在上半段。"""
    bm = BookmarkSet([5])
    bm.apply_line_delta(5, 1)
    assert bm.lines() == [5]


def test_br_bm_1_insert_below_does_not_move_bookmarks():
    bm = BookmarkSet([1, 2])
    bm.apply_line_delta(8, 4)
    assert bm.lines() == [1, 2]


def test_br_bm_2_deleted_lines_lose_their_bookmarks():
    bm = BookmarkSet([3, 4, 5, 9])
    bm.apply_line_delta(3, -2)  # 吃掉第 4、5 行
    assert bm.lines() == [3, 7]


def test_br_bm_2_delete_removes_all_bookmarks_in_range():
    bm = BookmarkSet([4, 5, 6])
    bm.apply_line_delta(3, -3)
    assert bm.lines() == []


def test_apply_zero_delta_is_a_noop():
    bm = BookmarkSet([1, 4])
    bm.apply_line_delta(0, 0)
    assert bm.lines() == [1, 4]


def test_br_bm_5_clamp_drops_out_of_range_bookmarks():
    bm = BookmarkSet([0, 3, 88])
    bm.clamp(10)
    assert bm.lines() == [0, 3]


def test_f_bm_09_invert():
    bm = BookmarkSet([1, 3])
    bm.invert(5)
    assert bm.lines() == [0, 2, 4]


def test_f_bm_05_clear():
    bm = BookmarkSet([1, 2, 3])
    bm.clear()
    assert len(bm) == 0


def test_contiguous_ranges_merges_runs_descending():
    bm = BookmarkSet([1, 2, 3, 7, 9, 10])
    # 由大到小，呼叫端才能從尾端往前刪而不位移
    assert bm.contiguous_ranges() == [(9, 10), (7, 7), (1, 3)]


def test_contiguous_ranges_empty():
    assert BookmarkSet().contiguous_ranges() == []


def test_nf_04_navigation_is_fast_on_large_sets():
    bm = BookmarkSet(range(0, 100_000, 2))
    assert bm.next_after(50_001) == 50_002
    assert bm.prev_before(50_001) == 50_000
