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

"""Markdown 預覽的核心：哪些檔案要預覽、Markdown → HTML、頁面外殼（SRS-008）。

轉換放在 Python 端而不是網頁裡（D-02）：規則才是要測的東西，放這裡就能在
不裝 Qt 的 CI job 裡完整測試。顯示交給 `ui/preview.py`。

Ubuntu 的系統套件是 markdown-it-py 3.x／mdit-py-plugins 0.4，pip 上是更新的
版本；這裡只用兩邊都有的 API。
"""

from __future__ import annotations

import os
from functools import lru_cache
from urllib.parse import urlsplit

from markdown_it import MarkdownIt
from mdit_py_plugins.footnote import footnote_plugin
from mdit_py_plugins.tasklists import tasklists_plugin
from pygments import highlight as _pygments_highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from pygments.util import ClassNotFound

#: BR-MD-1：比對時一律轉小寫
MARKDOWN_SUFFIXES = (".md", ".markdown", ".mdown", ".mkd", ".mkdn")

#: BR-MD-4：只有這些交給系統開啟
EXTERNAL_SCHEMES = ("http", "https", "mailto")


def is_markdown(path: str | None) -> bool:
    """BR-MD-1。未命名（`None`）也算——常是貼上來的草稿（D-05）。"""
    if path is None:
        return True
    return os.path.splitext(path)[1].lower() in MARKDOWN_SUFFIXES


def base_dir(path: str | None) -> str | None:
    """BR-MD-2：相對路徑圖片的基準目錄（F-MD-06）。"""
    if path is None:
        return None
    return os.path.dirname(os.path.abspath(path))


def is_external_link(url: str) -> bool:
    """BR-MD-4：點了要交給系統預設程式的連結。

    `file:`、`javascript:`、`data:`、相對路徑一律不算——預覽面板不是瀏覽器（D-10）。
    """
    return urlsplit(url).scheme.lower() in EXTERNAL_SCHEMES


# ----------------------------------------------------------------------
# Markdown → HTML
# ----------------------------------------------------------------------
_FORMATTER = HtmlFormatter(nowrap=True)


def _highlight(code: str, lang: str, _attrs) -> str:
    """F-MD-03。回傳空字串時 markdown-it 會自己跳脫後照原樣輸出。

    回傳值以 `<pre` 開頭，markdown-it 就不會再包一層 `<pre><code>`。
    Pygments 會跳脫內容，所以 BR-MD-6 在這條路徑上也成立。
    """
    if not lang:
        return ""
    try:
        lexer = get_lexer_by_name(lang)
    except ClassNotFound:
        return ""
    spans = _pygments_highlight(code, lexer, _FORMATTER)
    return f'<pre class="highlight"><code>{spans}</code></pre>'


@lru_cache(maxsize=1)
def _parser() -> MarkdownIt:
    # gfm-like：表格、刪除線、裸網址自動連結；html=True 讓行內 HTML 通過
    # （GitHub 也允許，執行期安全由預覽端關閉 JS 處理，D-08）
    parser = MarkdownIt("gfm-like", {"html": True, "highlight": _highlight})
    # enabled=False 會輸出 disabled 的勾選框：預覽是唯讀的（BR-MD-3）
    return parser.use(tasklists_plugin, enabled=False).use(footnote_plugin)


def render(text: str) -> str:
    """把 Markdown 轉成 HTML 片段（F-MD-02）。"""
    return _parser().render(text)


# ----------------------------------------------------------------------
# 頁面外殼
# ----------------------------------------------------------------------
# 配色取自 GitHub 的 Primer 設計系統；全部內嵌，不從網路載入（NF-02）。
_COLORS = {
    False: {
        "scheme": "light", "fg": "#1f2328", "bg": "#ffffff", "muted": "#59636e",
        "border": "#d1d9e0", "link": "#0969da", "code-bg": "rgba(129,139,152,0.12)",
        "pre-bg": "#f6f8fa", "row-alt": "#f6f8fa", "kbd-bg": "#f6f8fa",
    },
    True: {
        "scheme": "dark", "fg": "#f0f6fc", "bg": "#0d1117", "muted": "#9198a1",
        "border": "#3d444d", "link": "#4493f8", "code-bg": "rgba(101,108,118,0.2)",
        "pre-bg": "#151b23", "row-alt": "#151b23", "kbd-bg": "#151b23",
    },
}

_CSS = """
:root { color-scheme: %(scheme)s; }
html, body { margin: 0; background: %(bg)s; }
.markdown-body {
  box-sizing: border-box; max-width: 980px; margin: 0 auto; padding: 24px 32px;
  color: %(fg)s; background: %(bg)s;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans", Helvetica,
    Arial, "PingFang TC", "Microsoft JhengHei", "Noto Sans CJK TC", sans-serif;
  font-size: 16px; line-height: 1.5; word-wrap: break-word;
}
.markdown-body > *:first-child { margin-top: 0 !important; }
.markdown-body p, .markdown-body blockquote, .markdown-body ul, .markdown-body ol,
.markdown-body dl, .markdown-body table, .markdown-body pre, .markdown-body details {
  margin-top: 0; margin-bottom: 16px;
}
.markdown-body h1, .markdown-body h2, .markdown-body h3,
.markdown-body h4, .markdown-body h5, .markdown-body h6 {
  margin-top: 24px; margin-bottom: 16px; font-weight: 600; line-height: 1.25;
}
.markdown-body h1 { font-size: 2em; padding-bottom: .3em; border-bottom: 1px solid %(border)s; }
.markdown-body h2 { font-size: 1.5em; padding-bottom: .3em; border-bottom: 1px solid %(border)s; }
.markdown-body h3 { font-size: 1.25em; }
.markdown-body h4 { font-size: 1em; }
.markdown-body h5 { font-size: .875em; }
.markdown-body h6 { font-size: .85em; color: %(muted)s; }
.markdown-body a { color: %(link)s; text-decoration: none; }
.markdown-body a:hover { text-decoration: underline; }
.markdown-body hr {
  height: .25em; padding: 0; margin: 24px 0; border: 0; background: %(border)s;
}
.markdown-body hr.footnotes-sep { height: 1px; }
.markdown-body blockquote {
  margin-left: 0; margin-right: 0; padding: 0 1em;
  color: %(muted)s; border-left: .25em solid %(border)s;
}
.markdown-body ul, .markdown-body ol { padding-left: 2em; }
.markdown-body ul ul, .markdown-body ul ol, .markdown-body ol ol, .markdown-body ol ul {
  margin-top: 0; margin-bottom: 0;
}
.markdown-body li + li { margin-top: .25em; }
.markdown-body .contains-task-list { padding-left: 0; list-style: none; }
.markdown-body .contains-task-list .contains-task-list { padding-left: 2em; }
.markdown-body .task-list-item-checkbox { margin: 0 .2em .25em -1.4em; vertical-align: middle; }
.markdown-body .contains-task-list > .task-list-item { padding-left: 1.6em; }
.markdown-body table {
  display: block; width: max-content; max-width: 100%%; overflow: auto;
  border-spacing: 0; border-collapse: collapse;
}
.markdown-body th { font-weight: 600; }
.markdown-body th, .markdown-body td { padding: 6px 13px; border: 1px solid %(border)s; }
.markdown-body tr { background: %(bg)s; border-top: 1px solid %(border)s; }
.markdown-body tr:nth-child(2n) { background: %(row-alt)s; }
.markdown-body img { max-width: 100%%; box-sizing: content-box; }
.markdown-body code, .markdown-body kbd, .markdown-body pre {
  font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas,
    "Liberation Mono", "Noto Sans Mono CJK TC", monospace;
}
.markdown-body code {
  padding: .2em .4em; margin: 0; font-size: 85%%;
  white-space: break-spaces; background: %(code-bg)s; border-radius: 6px;
}
.markdown-body pre {
  padding: 16px; overflow: auto; font-size: 85%%; line-height: 1.45;
  color: %(fg)s; background: %(pre-bg)s; border-radius: 6px;
}
.markdown-body pre code {
  padding: 0; font-size: 100%%; white-space: pre; background: transparent; border: 0;
}
.markdown-body kbd {
  display: inline-block; padding: 3px 5px; font-size: 11px; line-height: 10px;
  vertical-align: middle; background: %(kbd-bg)s; border: 1px solid %(border)s;
  border-bottom-width: 2px; border-radius: 6px;
}
.markdown-body .footnotes { font-size: 12px; color: %(muted)s; }
.markdown-body .footnote-ref a { font-size: .75em; }
.stephany-notice { color: %(muted)s; font-style: italic; }
"""


def _pygments_css(dark: bool) -> str:
    # github-dark 是 Pygments 2.14 才有；更舊的版本退回 monokai，不讓預覽整個失敗
    for name in (("github-dark", "monokai") if dark else ("default",)):
        try:
            css = HtmlFormatter(style=name).get_style_defs(".highlight")
        except ClassNotFound:
            continue
        # 背景交給 .markdown-body pre，不然深色樣式自帶的底色會和頁面的不一致
        return "\n".join(
            line for line in css.splitlines() if not line.startswith(".highlight { background")
        )
    return ""


def page(body_html: str, dark: bool) -> str:
    """完整的預覽頁面。內容放在 `#content`，之後的更新只換它（D-06）。"""
    css = _CSS % _COLORS[dark] + _pygments_css(dark)
    return (
        "<!DOCTYPE html>\n<html>\n<head>\n"
        '<meta charset="utf-8">\n'
        f"<style>{css}</style>\n"
        "</head>\n<body>\n"
        f'<article class="markdown-body" id="content">{body_html}</article>\n'
        "</body>\n</html>\n"
    )
