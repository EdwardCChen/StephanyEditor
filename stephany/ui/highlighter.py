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

"""輕量語法上色。依副檔名切換規則，夠用即可，不做完整剖析。"""

from __future__ import annotations

import re

from PySide6.QtCore import QRegularExpression
from PySide6.QtGui import QPalette
from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat

from .theme import syntax_colors


def _fmt(color: str, bold: bool = False, italic: bool = False) -> QTextCharFormat:
    f = QTextCharFormat()
    f.setForeground(QColor(color))
    if bold:
        f.setFontWeight(QFont.Weight.Bold)
    if italic:
        f.setFontItalic(True)
    return f


def build_formats(palette) -> dict[str, QTextCharFormat]:
    """依目前主題產生一組上色格式。

    原本是模組層級的常數（寫死淺色主題的深藍、深綠），在深色背景上幾乎
    看不見。改成依 palette 產生，並在主題切換時重建。
    """
    colors = syntax_colors(palette)
    return {
        "keyword": _fmt(colors["keyword"], bold=True),
        "string": _fmt(colors["string"]),
        "comment": _fmt(colors["comment"], italic=True),
        "number": _fmt(colors["number"]),
        "function": _fmt(colors["function"]),
        "tag": _fmt(colors["tag"], bold=True),
    }

PY_KEYWORDS = """False None True and as assert async await break class continue def del
elif else except finally for from global if import in is lambda nonlocal not or pass
raise return try while with yield match case""".split()

C_KEYWORDS = """auto break case char const continue default do double else enum extern
float for goto if inline int long register return short signed sizeof static struct
switch typedef union unsigned void volatile while class public private protected
namespace template typename new delete this true false nullptr virtual override
using constexpr explicit friend operator""".split()

JS_KEYWORDS = """await async break case catch class const continue debugger default
delete do else export extends finally for function if import in instanceof let new
return super switch this throw try typeof var void while with yield true false null
undefined of""".split()

SH_KEYWORDS = """if then else elif fi for while do done case esac function return
in select until break continue local export readonly declare source echo""".split()


LANGUAGES = {
    "python": {
        "exts": (".py", ".pyw", ".pyi"),
        "keywords": PY_KEYWORDS,
        "line_comment": "#",
        "strings": ('"', "'"),
        "triple": True,
    },
    "c": {
        "exts": (".c", ".h", ".cpp", ".hpp", ".cc", ".cxx", ".java", ".cs", ".go", ".rs"),
        "keywords": C_KEYWORDS,
        "line_comment": "//",
        "block_comment": ("/*", "*/"),
        "strings": ('"', "'"),
    },
    "javascript": {
        "exts": (".js", ".ts", ".jsx", ".tsx", ".json"),
        "keywords": JS_KEYWORDS,
        "line_comment": "//",
        "block_comment": ("/*", "*/"),
        "strings": ('"', "'", "`"),
    },
    "shell": {
        "exts": (".sh", ".bash", ".zsh", ".profile", ".bashrc"),
        "keywords": SH_KEYWORDS,
        "line_comment": "#",
        "strings": ('"', "'"),
    },
    "xml": {
        "exts": (".xml", ".html", ".htm", ".svg", ".xhtml"),
        "keywords": [],
        "block_comment": ("<!--", "-->"),
        "strings": ('"', "'"),
        "markup": True,
    },
    "ini": {
        "exts": (".ini", ".cfg", ".conf", ".toml"),
        "keywords": [],
        "line_comment": "#",
        "strings": ('"', "'"),
    },
}


def language_for(path: str | None) -> str | None:
    if not path:
        return None
    low = path.lower()
    for name, spec in LANGUAGES.items():
        if low.endswith(spec["exts"]):
            return name
    return None


class SimpleHighlighter(QSyntaxHighlighter):
    def __init__(self, document, language: str | None = None, palette=None):
        super().__init__(document)
        self._rules: list[tuple[QRegularExpression, QTextCharFormat]] = []
        self._block_start: QRegularExpression | None = None
        self._block_end: QRegularExpression | None = None
        self._language = language
        self._formats = build_formats(palette or QPalette())
        self.set_language(language)

    def refresh_theme(self, palette):
        """主題切換時重建格式並整份重上色。"""
        self._formats = build_formats(palette)
        self.set_language(self._language)

    def set_language(self, language: str | None):
        self._language = language
        self._rules.clear()
        self._block_start = self._block_end = None
        spec = LANGUAGES.get(language or "")
        if not spec:
            self.rehighlight()
            return

        for kw in spec.get("keywords", []):
            self._rules.append(
                (QRegularExpression(rf"\b{re.escape(kw)}\b"), self._formats["keyword"])
            )
        if spec.get("markup"):
            self._rules.append((QRegularExpression(r"</?[\w:.-]+"), self._formats["tag"]))
            self._rules.append((QRegularExpression(r"/?>"), self._formats["tag"]))
        self._rules.append(
            (QRegularExpression(r"\b\d+(\.\d+)?([eE][+-]?\d+)?\b"), self._formats["number"])
        )
        self._rules.append(
            (QRegularExpression(r"\b[A-Za-z_]\w*(?=\s*\()"), self._formats["function"])
        )
        for q in spec.get("strings", ()):
            esc = re.escape(q)
            self._rules.append(
                (QRegularExpression(rf"{esc}(\\.|[^{esc}\\])*{esc}"), self._formats["string"])
            )
        if lc := spec.get("line_comment"):
            self._rules.append((QRegularExpression(rf"{re.escape(lc)}[^\n]*"), self._formats["comment"]))
        if bc := spec.get("block_comment"):
            self._block_start = QRegularExpression(re.escape(bc[0]))
            self._block_end = QRegularExpression(re.escape(bc[1]))
        self.rehighlight()

    def highlightBlock(self, text: str):
        for pattern, fmt in self._rules:
            it = pattern.globalMatch(text)
            while it.hasNext():
                m = it.next()
                self.setFormat(m.capturedStart(), m.capturedLength(), fmt)

        if not self._block_start:
            return
        self.setCurrentBlockState(0)
        start = 0
        if self.previousBlockState() != 1:
            m = self._block_start.match(text)
            start = m.capturedStart() if m.hasMatch() else -1
        while start >= 0:
            m = self._block_end.match(text, start)
            if m.hasMatch():
                length = m.capturedEnd() - start
                self.setFormat(start, length, self._formats["comment"])
                nxt = self._block_start.match(text, m.capturedEnd())
                start = nxt.capturedStart() if nxt.hasMatch() else -1
            else:
                self.setCurrentBlockState(1)
                self.setFormat(start, len(text) - start, self._formats["comment"])
                break
