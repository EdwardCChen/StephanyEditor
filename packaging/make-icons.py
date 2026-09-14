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

兩種輸出格式，來源都是同一個 SVG：

    make-icons.py 圖示.svg <hicolor 目錄>              # Linux 圖示主題
    make-icons.py 圖示.svg <目錄.iconset> --iconset    # macOS，之後交給 iconutil
"""

from __future__ import annotations

import sys
from pathlib import Path

SIZES = (16, 22, 24, 32, 48, 64, 128, 256)

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


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    iconset = "--iconset" in sys.argv[1:]
    if len(args) != 2:
        print(
            "用法：make-icons.py <來源.svg> <hicolor 目錄>\n"
            "      make-icons.py <來源.svg> <目錄.iconset> --iconset",
            file=sys.stderr,
        )
        return 2
    source, dest = Path(args[0]), Path(args[1])

    from PySide6.QtCore import Qt
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
