"""檔案讀寫：編碼偵測、BOM、換行字元。

因為使用者是繁體中文環境，編碼偵測順序刻意把 Big5 排在 GB18030 前面
（GB18030 幾乎什麼位元組都吃得下，先試它會把 Big5 檔案解成亂碼）。
"""

from __future__ import annotations

import codecs
from dataclasses import dataclass

#: 選單上提供的編碼（顯示名稱 -> Python codec）
ENCODINGS = {
    "UTF-8": "utf-8",
    "UTF-8 (含 BOM)": "utf-8-sig",
    "UTF-16 LE": "utf-16-le",
    "UTF-16 BE": "utf-16-be",
    "Big5 (繁體中文)": "big5",
    "Big5-HKSCS (香港)": "big5hkscs",
    "GB18030 (簡體中文)": "gb18030",
    "Shift-JIS (日文)": "shift_jis",
    "Latin-1": "latin-1",
}

#: 自動偵測時的嘗試順序
SNIFF_ORDER = ("utf-8", "big5hkscs", "gb18030", "shift_jis", "latin-1")

EOL_NAMES = {"\r\n": "Windows (CRLF)", "\n": "Unix (LF)", "\r": "Mac 舊版 (CR)"}


@dataclass
class LoadResult:
    text: str
    encoding: str
    eol: str
    had_bom: bool


def detect_eol(text: str) -> str:
    crlf = text.count("\r\n")
    lf = text.count("\n") - crlf
    cr = text.count("\r") - crlf
    if crlf >= lf and crlf >= cr and crlf > 0:
        return "\r\n"
    if cr > lf:
        return "\r"
    return "\n"


def decode(data: bytes, encoding: str | None = None) -> LoadResult:
    """把位元組解成文字。encoding=None 代表自動偵測。"""
    if encoding is None:
        for bom, enc in (
            (codecs.BOM_UTF8, "utf-8-sig"),
            (codecs.BOM_UTF32_LE, "utf-32-le"),
            (codecs.BOM_UTF32_BE, "utf-32-be"),
            (codecs.BOM_UTF16_LE, "utf-16-le"),
            (codecs.BOM_UTF16_BE, "utf-16-be"),
        ):
            if data.startswith(bom):
                text = data[len(bom) :].decode(enc.replace("-sig", ""), errors="replace")
                return _finish(text, enc, True)
        for enc in SNIFF_ORDER:
            try:
                text = data.decode(enc)
            except (UnicodeDecodeError, LookupError):
                continue
            return _finish(text, enc, False)
        return _finish(data.decode("utf-8", errors="replace"), "utf-8", False)

    had_bom = encoding == "utf-8-sig" and data.startswith(codecs.BOM_UTF8)
    text = data.decode(encoding, errors="replace")
    return _finish(text, encoding, had_bom)


def _finish(text: str, encoding: str, had_bom: bool) -> LoadResult:
    eol = detect_eol(text)
    # 文件內部一律用 \n，存檔時再換回去
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return LoadResult(text=normalized, encoding=encoding, eol=eol, had_bom=had_bom)


def encode(text: str, encoding: str, eol: str) -> bytes:
    """把編輯器內容轉回位元組。無法以該編碼表示的字會拋 UnicodeEncodeError。"""
    if eol != "\n":
        text = text.replace("\n", eol)
    return text.encode(encoding)


def unencodable_chars(text: str, encoding: str) -> list[str]:
    """找出無法用指定編碼儲存的字元（例如把含 emoji 的檔案存成 Big5）。"""
    bad = []
    seen = set()
    for ch in text:
        if ch in seen:
            continue
        seen.add(ch)
        try:
            ch.encode(encoding)
        except UnicodeEncodeError:
            bad.append(ch)
    return bad
