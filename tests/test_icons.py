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

"""工具列圖示檔的一致性測試（SRS-007 BR-TB-1、BR-TB-3）。

本檔刻意不 import PySide6，才能在 CI 的「核心邏輯（無 Qt）」job 裡跑；
版面表是直接從 mainwindow.py 的原始碼讀出來的，與 test_platform.py 同一個手法。
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ICON_DIR = ROOT / "stephany" / "resources" / "icons"
MAINWINDOW_SRC = (ROOT / "stephany" / "ui" / "mainwindow.py").read_text(encoding="utf-8")


def layout_icon_names() -> list[str]:
    """從 TOOLBAR_LAYOUT 撈出每一顆按鈕用的圖示名稱。"""
    block = MAINWINDOW_SRC[MAINWINDOW_SRC.index("TOOLBAR_LAYOUT") :]
    block = block[: block.index("\n)")]
    return re.findall(r'\("act_\w+",\s*"([\w-]+)"\)', block)


def shipped_icons() -> set[str]:
    return {p.stem for p in ICON_DIR.glob("*.svg")}


def test_the_layout_table_is_not_empty():
    """底下每個測試都建立在這張表上，它空掉的話全部會變成空轉。"""
    assert len(layout_icon_names()) >= 10


def test_br_tb_1_every_toolbar_button_has_an_icon_file():
    missing = [n for n in layout_icon_names() if not (ICON_DIR / f"{n}.svg").exists()]
    assert not missing, f"版面表指定了圖示但檔案不存在：{missing}"


def test_no_icon_file_is_shipped_without_being_used():
    """沒人用的圖示會跟著套件一起裝，久了就變成沒人敢刪的垃圾。"""
    orphans = shipped_icons() - set(layout_icon_names())
    assert not orphans, f"這些圖示沒有任何按鈕在用：{sorted(orphans)}"


def test_br_tb_3_every_icon_parses_and_uses_the_same_viewbox():
    """尺寸不一致的話，同一列圖示會大小不一。"""
    for path in sorted(ICON_DIR.glob("*.svg")):
        root = ET.fromstring(path.read_text(encoding="utf-8"))
        assert root.tag.endswith("svg"), path
        assert root.get("viewBox") == "0 0 24 24", path


def test_icons_ship_inside_the_python_package():
    """跟應用程式圖示一樣放在套件內，deb / .app / Windows 安裝都會帶到。"""
    assert (ICON_DIR.parent / "__init__.py").exists()
    assert 'ICON_DIR = RESOURCE_DIR / "icons"' in (
        ICON_DIR.parent / "__init__.py"
    ).read_text(encoding="utf-8")


def test_icons_are_monochrome_so_they_can_be_recoloured():
    """上色是把整張圖當遮罩塗一個顏色（D-02），所以來源不該有第二種顏色。

    只認黑色與 none；有人加了彩色圖示時這裡會擋下來，否則它在深色主題
    下會被整片塗成淺色，看起來像壞掉。
    """
    allowed = {"#000", "#000000", "none", None}
    for path in sorted(ICON_DIR.glob("*.svg")):
        text = path.read_text(encoding="utf-8")
        used = set(re.findall(r'(?:fill|stroke)="([^"]+)"', text))
        unexpected = {c for c in used if c.lower() not in allowed}
        assert not unexpected, f"{path.name} 用了非單色的顏色：{unexpected}"
