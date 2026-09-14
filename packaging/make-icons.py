"""從單一 SVG 產生各尺寸 PNG（SRS-004 D-06）。

用 PySide6 自己的 QtSvg 算圖，建構主機就不必另外安裝 rsvg-convert 或 inkscape。
"""

from __future__ import annotations

import sys
from pathlib import Path

SIZES = (16, 22, 24, 32, 48, 64, 128, 256)


def main() -> int:
    if len(sys.argv) != 3:
        print("用法：make-icons.py <來源.svg> <hicolor 目錄>", file=sys.stderr)
        return 2
    source, dest = Path(sys.argv[1]), Path(sys.argv[2])

    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication, QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    app = QGuiApplication(["make-icons"])  # noqa: F841  QImage/QPainter 需要它
    renderer = QSvgRenderer(str(source))
    if not renderer.isValid():
        print(f"SVG 無法解析：{source}", file=sys.stderr)
        return 1

    for size in SIZES:
        image = QImage(size, size, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        renderer.render(painter)
        painter.end()
        out = dest / f"{size}x{size}" / "apps"
        out.mkdir(parents=True, exist_ok=True)
        target = out / "stephany-editor.png"
        if not image.save(str(target)):
            print(f"寫入失敗：{target}", file=sys.stderr)
            return 1

    scalable = dest / "scalable" / "apps"
    scalable.mkdir(parents=True, exist_ok=True)
    (scalable / "stephany-editor.svg").write_bytes(source.read_bytes())
    print(f"已產生 {len(SIZES)} 種尺寸的 PNG 與 1 個 SVG")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
