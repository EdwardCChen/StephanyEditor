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

"""Markdown 預覽的核心邏輯測試。對應 SRS-008 F-MD-*、BR-MD-*、NF-*。

本檔刻意不 import PySide6，才能在 CI 的「核心邏輯（無 Qt）」job 裡跑。
"""

import re
import time
from pathlib import Path

import pytest

from stephany.core import markdown as md


# ----------------------------------------------------------------------
# BR-MD-1：什麼算 Markdown 檔
# ----------------------------------------------------------------------
@pytest.mark.parametrize(
    "path",
    ["README.md", "/a/b/notes.markdown", "x.mdown", "x.mkd", "x.mkdn", "大寫.MD", "Mixed.Markdown"],
)
def test_br_md_1_markdown_extensions(path):
    assert md.is_markdown(path)


@pytest.mark.parametrize("path", ["a.txt", "a.py", "README", "a.md.bak", "md", "/dir.md/file.txt"])
def test_br_md_1_other_files_are_not_markdown(path):
    assert not md.is_markdown(path)


def test_br_md_1_untitled_counts_as_markdown():
    """D-05：未命名分頁常是貼上來的草稿，所以放行。"""
    assert md.is_markdown(None)


# ----------------------------------------------------------------------
# BR-MD-2：圖片基準目錄
# ----------------------------------------------------------------------
def test_br_md_2_base_dir_is_the_files_directory(tmp_path):
    path = tmp_path / "docs" / "a.md"
    assert md.base_dir(str(path)) == str(tmp_path / "docs")


def test_br_md_2_untitled_has_no_base_dir():
    assert md.base_dir(None) is None


# ----------------------------------------------------------------------
# BR-MD-4：哪些連結交給系統開啟
# ----------------------------------------------------------------------
@pytest.mark.parametrize(
    "url", ["http://example.com", "https://example.com/a?b=1", "HTTPS://EXAMPLE.COM", "mailto:a@b.c"]
)
def test_br_md_4_external_links(url):
    assert md.is_external_link(url)


@pytest.mark.parametrize(
    "url",
    ["docs/other.md", "#section", "file:///etc/passwd", "javascript:alert(1)", "", "ftp://x", "data:text/html,x"],
)
def test_br_md_4_everything_else_stays_inside(url):
    assert not md.is_external_link(url)


# ----------------------------------------------------------------------
# F-MD-02：GitHub Flavored Markdown
# ----------------------------------------------------------------------
def test_f_md_02_headings_and_emphasis():
    html = md.render("# 標題\n\n**粗** *斜* ~~刪~~")
    assert "<h1" in html and "標題</h1>" in html
    assert "<strong>粗</strong>" in html
    assert "<em>斜</em>" in html
    assert re.search(r"<(s|del)>刪</(s|del)>", html)


def test_f_md_02_table_with_alignment():
    html = md.render("| 左 | 中 | 右 |\n|:---|:---:|---:|\n| 1 | 2 | 3 |\n")
    assert "<table>" in html
    assert len(re.findall(r"<th[ >]", html)) == 3
    assert len(re.findall(r"<td[ >]", html)) == 3
    assert "text-align:center" in html.replace(" ", "")
    assert "text-align:right" in html.replace(" ", "")


def test_f_md_02_task_list():
    html = md.render("- [x] 完成\n- [ ] 待辦\n")
    boxes = re.findall(r"<input[^>]*type=\"checkbox\"[^>]*>", html)
    assert len(boxes) == 2
    assert "checked" in boxes[0]
    assert "checked" not in boxes[1]
    # 預覽是唯讀的（BR-MD-3），勾選框不能讓人以為可以點
    assert all("disabled" in box for box in boxes)


def test_f_md_02_nested_list_is_nested():
    """清單縮排是否被正確解讀為巢狀，是預覽要讓人確認的重點之一。"""
    html = md.render("- 外\n  - 內\n")
    assert re.search(r"<li>外\s*<ul>\s*<li>內</li>", html)


def test_f_md_02_footnote():
    html = md.render("正文[^1]\n\n[^1]: 註腳內容\n")
    assert "footnote" in html
    assert "註腳內容" in html


def test_f_md_02_inline_html_passes_through():
    """GitHub 允許內嵌 HTML；安全性由預覽端關閉 JavaScript 處理（D-08）。"""
    assert "<kbd>Ctrl</kbd>" in md.render("按 <kbd>Ctrl</kbd>")


def test_f_md_02_blockquote_rule_and_image():
    html = md.render("> 引言\n\n---\n\n![圖](img/a.png)")
    assert "<blockquote>" in html
    assert "<hr" in html
    assert '<img src="img/a.png" alt="圖"' in html


def test_f_md_02_bare_urls_become_links():
    """GitHub 會把裸網址變成連結（autolink 擴充）。"""
    assert '<a href="https://example.com">' in md.render("見 https://example.com 說明")


# ----------------------------------------------------------------------
# F-MD-03：程式碼上色；BR-MD-6：一律跳脫
# ----------------------------------------------------------------------
def test_f_md_03_fenced_code_is_highlighted():
    html = md.render("```python\ndef f():\n    return 1\n```\n")
    assert "<span class=" in html
    assert "def" in html and "return" in html


def test_f_md_03_unknown_language_is_shown_as_is():
    html = md.render("```nosuchlang\na < b\n```\n")
    assert "a &lt; b" in html


def test_f_md_03_no_language_is_shown_as_is():
    html = md.render("```\nplain\n```\n")
    assert "plain" in html and "<pre" in html


@pytest.mark.parametrize("lang", ["", "html", "python", "nosuchlang"])
def test_br_md_6_code_content_is_escaped(lang):
    html = md.render(f"```{lang}\n<script>alert(1)</script>\n```\n")
    assert "<script>" not in html


def test_br_md_6_indented_and_inline_code_are_escaped():
    html = md.render("`<b>x</b>`\n\n    <i>y</i>\n")
    assert "<b>" not in html and "<i>" not in html


# ----------------------------------------------------------------------
# 頁面外殼：NF-02 不需網路、F-MD-10 深色
# ----------------------------------------------------------------------
def test_page_wraps_body_in_content_container():
    page = md.page("<p>內容</p>", dark=False)
    assert page.startswith("<!DOCTYPE html>")
    assert '<meta charset="utf-8">' in page
    assert re.search(r'<article[^>]*id="content"[^>]*>\s*<p>內容</p>', page)


def test_nf_02_page_loads_nothing_from_the_network():
    page = md.page(md.render("# x\n\n```py\nx = 1\n```"), dark=False)
    assert not re.search(r"<(link|script)[^>]+(href|src)=", page)
    assert "@import" not in page
    assert "<style>" in page


def test_f_md_10_dark_page_uses_dark_colors():
    light = md.page("", dark=False)
    dark = md.page("", dark=True)
    assert light != dark
    assert "color-scheme: dark" in dark
    assert "color-scheme: light" in light


def test_f_md_10_both_themes_style_highlighted_code():
    """上色樣式兩種主題都要有，否則深色底上的程式碼會是深色字。"""
    for dark in (False, True):
        page = md.page("", dark=dark)
        assert ".highlight .k" in page  # Pygments 的關鍵字 class


# ----------------------------------------------------------------------
# NF-03：效能
# ----------------------------------------------------------------------
def test_nf_03_one_megabyte_renders_within_a_second():
    section = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")
    text = (section * (1_000_000 // len(section.encode("utf-8")) + 1))
    assert len(text.encode("utf-8")) >= 1_000_000
    start = time.perf_counter()
    md.render(text)
    assert time.perf_counter() - start < 1.0
