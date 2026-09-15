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

"""從單一 SVG 產生各尺寸 PNG（SRS-004 D-06、SRS-005 D-03）。

用 PySide6 自己的 QtSvg 算圖，建構主機就不必另外安裝 rsvg-convert 或 inkscape。

三種輸出格式，來源都是同一個 SVG：

    make-icons.py 圖示.svg <hicolor 目錄>              # Linux 圖示主題
    make-icons.py 圖示.svg <目錄.iconset> --iconset    # macOS，之後交給 iconutil
    make-icons.py 圖示.svg <圖示.ico> --ico            # Windows
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

SIZES = (16, 22, 24, 32, 48, 64, 128, 256)

#: Windows 的 .ico 是一個容器，裡面塞多張不同尺寸的圖，由系統依場合挑：
#: 16 是檔案總管的小圖示、32 是捷徑與工作列、48 是「中圖示」檢視、
#: 256 是「超大圖示」。少了哪一個，Windows 會拿最接近的去縮放，看起來就糊。
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)

#: macOS 的 .iconset 只認這十個檔名（`iconutil` 會照這份清單挑）。
#: @2x 是同一個尺寸的兩倍像素版本，Retina 螢幕用的。
ICONSET_SIZES = (
    ("icon_16x16.png", 16),
    ("icon_16x16@2x.png", 32),
    ("icon_32x32.png", 32),
    ("icon_32x32@2x.png", 64),
    ("icon_128x128.png", 128),
    ("icon_128x128@2x.png", 256),
    ("icon_256x256.png", 256),
    ("icon_256x256@2x.png", 512),
    ("icon_512x512.png", 512),
    ("icon_512x512@2x.png", 1024),
)


def _force_utf8_output() -> None:
    """把自己的輸出串流轉成 UTF-8（SRS-006 NF-W4）。

    本專案的訊息全是中文，而 Windows 主控台的字碼頁是跟著系統語系走的：
    en-US 是 cp1252，一個中文字都編不出來，`print()` 會直接
    `UnicodeEncodeError` 中止——GitHub 的 windows runner 就是這樣炸的。

    NF-W4 當初選 Python 來寫建構腳本，是因為 cmd 與 PowerShell 的編碼行為
    更不可靠；但光是用 Python 並不會自動解決，得自己把串流轉過來。

    `errors="replace"` 是最後一道保險：真的有編不出來的字元時印成問號，
    也不要讓建構掛掉。
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            # pythonw 底下 stdout 可能是 None，或不是 TextIOWrapper
            pass


def main() -> int:
    _force_utf8_output()  # 由 build-win.py 以子行程呼叫，stdout 直接繼承
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    iconset = "--iconset" in sys.argv[1:]
    ico = "--ico" in sys.argv[1:]
    if len(args) != 2 or (iconset and ico):
        print(
            "用法：make-icons.py <來源.svg> <hicolor 目錄>\n"
            "      make-icons.py <來源.svg> <目錄.iconset> --iconset\n"
            "      make-icons.py <來源.svg> <圖示.ico> --ico",
            file=sys.stderr,
        )
        return 2
    source, dest = Path(args[0]), Path(args[1])

    from PySide6.QtCore import QBuffer, Qt
    from PySide6.QtGui import QGuiApplication, QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    app = QGuiApplication(["make-icons"])  # noqa: F841  QImage/QPainter 需要它
    renderer = QSvgRenderer(str(source))
    if not renderer.isValid():
        print(f"SVG 無法解析：{source}", file=sys.stderr)
        return 1

    def render(size: int, target: Path) -> bool:
        image = QImage(size, size, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        renderer.render(painter)
        painter.end()
        target.parent.mkdir(parents=True, exist_ok=True)
        if not image.save(str(target)):
            print(f"寫入失敗：{target}", file=sys.stderr)
            return False
        return True

    if iconset:
        for name, size in ICONSET_SIZES:
            if not render(size, dest / name):
                return 1
        print(f"已產生 {len(ICONSET_SIZES)} 個 iconset PNG：{dest}")
        return 0

    if ico:
        # macOS 有 iconutil 可以把一疊 PNG 包成 .icns，Windows 沒有對應的
        # 內建工具。所幸 .ico 的容器格式很單純（一個目錄加上各尺寸的圖），
        # 而且 Vista 以後接受直接內嵌 PNG，所以自己寫比拉一個第三方相依
        # 進來划算得多（SRS-006 D-W3）。
        payloads = []
        for size in ICO_SIZES:
            buffer = QBuffer()
            buffer.open(QBuffer.OpenModeFlag.WriteOnly)
            image = QImage(size, size, QImage.Format.Format_ARGB32)
            image.fill(Qt.GlobalColor.transparent)
            painter = QPainter(image)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            renderer.render(painter)
            painter.end()
            if not image.save(buffer, "PNG"):
                print(f"{size}x{size} 算圖失敗", file=sys.stderr)
                return 1
            payloads.append((size, bytes(buffer.data())))

        # ICONDIR：保留欄位、型別（1 = 圖示，2 是滑鼠游標）、張數
        header = struct.pack("<HHH", 0, 1, len(payloads))
        offset = len(header) + 16 * len(payloads)
        directory, blob = b"", b""
        for size, payload in payloads:
            directory += struct.pack(
                "<BBBBHHII",
                size if size < 256 else 0,   # 寬：256 在這個欄位要寫成 0
                size if size < 256 else 0,   # 高：同上
                0,                           # 調色盤色數，全彩是 0
                0,                           # 保留欄位
                1,                           # 色彩平面
                32,                          # 每像素位元數
                len(payload),
                offset,
            )
            blob += payload
            offset += len(payload)

        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(header + directory + blob)
        print(f"已產生 {len(payloads)} 種尺寸的 .ico：{dest}")
        return 0


    for size in SIZES:
        if not render(size, dest / f"{size}x{size}" / "apps" / "stephany-editor.png"):
            return 1

    scalable = dest / "scalable" / "apps"
    scalable.mkdir(parents=True, exist_ok=True)
    (scalable / "stephany-editor.svg").write_bytes(source.read_bytes())
    print(f"已產生 {len(SIZES)} 種尺寸的 PNG 與 1 個 SVG")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
