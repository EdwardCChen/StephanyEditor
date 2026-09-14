"""程式進入點。

桌面整合（SRS-004 D-01、F-PK-01）：
Qt 6 在 Wayland 下以 `QGuiApplication.desktopFileName()` 作為 xdg-shell 的
`app_id`，桌面環境再拿它去比對 `/usr/share/applications/<app_id>.desktop`，
才知道這個視窗屬於哪個已安裝的應用程式。這個值若是空的（預設），就會退回
使用執行檔名稱，於是 Dock 上顯示成 `python3`。

所以以下三者必須完全一致，缺一不可：
    app_id（本檔設定）== .desktop 檔名 == desktop 檔裡的 StartupWMClass
"""

from __future__ import annotations

import argparse
import sys

from . import __version__

#: 應用程式識別碼。與 .desktop 檔名、StartupWMClass 一致（D-01）。
APP_ID = "stephany-editor"

USAGE = """Stephany Editor — 支援中文欄（直行）模式的文字編輯器

用法：
  stephany-editor [檔案 ...]

欄模式快速鍵：
  Alt + 滑鼠拖曳        拉出矩形選取
  Alt + Shift + 方向鍵  從游標處展開矩形
  Ctrl + Shift + B      黏著式欄選取（不必按 Alt，適用於 Alt+拖曳被 GNOME 攔截時）
  Alt + C               欄位編輯器（整欄插入文字或遞增數列）

其他：
  Ctrl + F2 / F2        切換書籤 / 跳至下一個書籤
  Ctrl + Shift + R / P  開始停止錄製巨集 / 播放
  Ctrl + Alt + F        摺疊游標所在區塊
  F1                    完整操作說明
"""


def app_icon():
    """應用程式圖示。

    已安裝時由系統圖示主題提供（deb 會把各尺寸 PNG 裝到 hicolor）；
    從原始碼直接執行時退回讀套件內附的 SVG。
    """
    from PySide6.QtGui import QIcon

    if QIcon.hasThemeIcon(APP_ID):
        return QIcon.fromTheme(APP_ID)
    from .resources import ICON_SVG

    return QIcon(str(ICON_SVG)) if ICON_SVG.exists() else QIcon()


def configure_identity(app) -> None:
    """設定桌面環境用來辨識這個應用程式的所有欄位（F-PK-01）。"""
    from .ui.mainwindow import APP_NAME

    app.setApplicationName(APP_ID)  # X11 的 WM_CLASS
    app.setDesktopFileName(APP_ID)  # Wayland 的 app_id —— 沒有這個就會顯示成 python3
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setWindowIcon(app_icon())


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(
        prog=APP_ID,
        description=USAGE,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("files", nargs="*", help="要開啟的檔案")
    parser.add_argument(
        "--version", action="version", version=f"Stephany Editor {__version__}"
    )
    args = parser.parse_args(argv)

    from PySide6.QtWidgets import QApplication

    from .ui.mainwindow import MainWindow

    app = QApplication(sys.argv[:1])
    configure_identity(app)
    window = MainWindow(args.files)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
