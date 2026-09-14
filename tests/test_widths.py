from stephany.core.widths import (
    char_width,
    col_to_index,
    display_width,
    index_to_col,
    iter_cells,
    next_col,
    prev_col,
)


def test_ascii_and_cjk_widths():
    assert char_width("a") == 1
    assert char_width("漢") == 2
    assert char_width("，") == 2  # 全形標點
    assert char_width("́") == 0  # 組合附加符號


def test_ambiguous_width_is_configurable():
    assert char_width("℃") == 1
    assert char_width("℃", ambiguous_wide=True) == 2


def test_display_width_mixes_widths():
    assert display_width("你好ab") == 6
    assert display_width("") == 0


def test_tab_expands_to_next_stop():
    assert display_width("a\tb", tab_width=4) == 5  # a(1) + tab(3) + b(1)
    assert display_width("\t", tab_width=4) == 4
    assert display_width("你\t", tab_width=4) == 4  # 中文佔 2，tab 只補 2


def test_combining_marks_join_base_char():
    cells = list(iter_cells("éx"))
    assert [c.text for c in cells] == ["é", "x"]
    assert [c.width for c in cells] == [1, 1]


def test_index_and_col_round_trip():
    line = "你好ab"
    assert index_to_col(line, 0) == 0
    assert index_to_col(line, 1) == 2
    assert index_to_col(line, 2) == 4
    assert col_to_index(line, 0) == 0
    assert col_to_index(line, 2) == 1
    assert col_to_index(line, 3) == 1  # 落在「好」中間 -> 回到該字起點


def test_col_beyond_end_extends_virtually():
    assert col_to_index("ab", 10) == 2
    assert index_to_col("ab", 5) == 5


def test_prev_next_col_step_over_whole_cjk_char():
    line = "a你b"
    assert next_col(line, 0) == 1
    assert next_col(line, 1) == 3  # 跨過整個「你」
    assert prev_col(line, 3) == 1
    assert prev_col(line, 0) == 0
