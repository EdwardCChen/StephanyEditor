"""程式進入點。"""

from __future__ import annotations

import argparse
import sys

from . import __version__

USAGE = """Stephany Editor — 支援中文欄（直行）模式的文字編輯器

用法：
  stephany [檔案 ...]

欄模式快速鍵：
  Alt + 滑鼠拖曳        拉出矩形選取
  Alt + Shift + 方向鍵  從游標處展開矩形
  Ctrl + Shift + B      黏著式欄選取（不必按 Alt，適用於 Alt+拖曳被 GNOME 攔截時）
  Alt + C               欄位編輯器（整欄插入文字或遞增數列）
  F1                    完整操作說明
"""


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(
        prog="stephany",
        description=USAGE,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=True,
    )
    parser.add_argument("files", nargs="*", help="要開啟的檔案")
    parser.add_argument("--version", action="version", version=f"Stephany Editor {__version__}")
    args = parser.parse_args(argv)

    from PySide6.QtWidgets import QApplication

    from .ui.mainwindow import APP_NAME, MainWindow

    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    window = MainWindow(args.files)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
