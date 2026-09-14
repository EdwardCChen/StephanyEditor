"""輕量語法上色。依副檔名切換規則，夠用即可，不做完整剖析。"""

from __future__ import annotations

import re

from PySide6.QtCore import QRegularExpression
from PySide6.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat


def _fmt(color: str, bold: bool = False, italic: bool = False) -> QTextCharFormat:
    f = QTextCharFormat()
    f.setForeground(QColor(color))
    if bold:
        f.setFontWeight(QFont.Weight.Bold)
    if italic:
        f.setFontItalic(True)
    return f


KEYWORD = _fmt("#0033b3", bold=True)
STRING = _fmt("#067d17")
COMMENT = _fmt("#8c8c8c", italic=True)
NUMBER = _fmt("#1750eb")
FUNC = _fmt("#7a3e9d")
TAG = _fmt("#0033b3", bold=True)

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
    def __init__(self, document, language: str | None = None):
        super().__init__(document)
        self._rules: list[tuple[QRegularExpression, QTextCharFormat]] = []
        self._block_start: QRegularExpression | None = None
        self._block_end: QRegularExpression | None = None
        self.set_language(language)

    def set_language(self, language: str | None):
        self._rules.clear()
        self._block_start = self._block_end = None
        spec = LANGUAGES.get(language or "")
        if not spec:
            self.rehighlight()
            return

        for kw in spec.get("keywords", []):
            self._rules.append(
                (QRegularExpression(rf"\b{re.escape(kw)}\b"), KEYWORD)
            )
        if spec.get("markup"):
            self._rules.append((QRegularExpression(r"</?[\w:.-]+"), TAG))
            self._rules.append((QRegularExpression(r"/?>"), TAG))
        self._rules.append(
            (QRegularExpression(r"\b\d+(\.\d+)?([eE][+-]?\d+)?\b"), NUMBER)
        )
        self._rules.append(
            (QRegularExpression(r"\b[A-Za-z_]\w*(?=\s*\()"), FUNC)
        )
        for q in spec.get("strings", ()):
            esc = re.escape(q)
            self._rules.append(
                (QRegularExpression(rf"{esc}(\\.|[^{esc}\\])*{esc}"), STRING)
            )
        if lc := spec.get("line_comment"):
            self._rules.append((QRegularExpression(rf"{re.escape(lc)}[^\n]*"), COMMENT))
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
                self.setFormat(start, length, COMMENT)
                nxt = self._block_start.match(text, m.capturedEnd())
                start = nxt.capturedStart() if nxt.hasMatch() else -1
            else:
                self.setCurrentBlockState(1)
                self.setFormat(start, len(text) - start, COMMENT)
                break
