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

from . import APP_ID, __version__, platforms  # noqa: F401  APP_ID 供他處 import

#: Qt 自己那些字串要用的翻譯檔（SRS-005 D-09）。本程式介面一律繁體中文。
QT_TRANSLATION = "qtbase_zh_TW"

_CTRL = platforms.mod("Ctrl")
_ALT = platforms.mod("Alt")
_SHIFT = platforms.mod("Shift")

def _keys(sequence: str) -> str:
    """把 `Ctrl+Shift+C` 這種可攜寫法排成本平台看得懂的字樣。"""
    return " + ".join(platforms.mod(part) for part in sequence.split("+"))


def _column_editor_key() -> str:
    """欄位編輯器在**這個平台**實際按得到的鍵。

    寫死 `Alt+C` 的話，Windows 使用者會讀到一個被選單助憶鍵吃掉的鍵，
    macOS 使用者讀到的則是會打出 `ç` 的鍵——印一個按不到的鍵比不印還糟
    （SRS-006 F-WIN-08、SRS-005 D-05）。
    """
    extra = platforms.extra_shortcuts("column_editor")
    return _keys(extra[0]) if extra else f"{_ALT} + C"


#: 修飾鍵依平台顯示（macOS 是 ⌘ / ⌥），與實際綁定的鍵一致（SRS-005 D-05）
_USAGE_KEYS = (
    ("欄模式快速鍵：", None),
    (f"{_ALT} + 滑鼠拖曳", "拉出矩形選取"),
    (f"{_ALT} + {_SHIFT} + 方向鍵", "從游標處展開矩形"),
    (f"{_CTRL} + {_SHIFT} + B", f"黏著式欄選取（不必按 {_ALT}）"),
    (_column_editor_key(), "欄位編輯器（整欄插入文字或遞增數列）"),
    ("", None),
    ("其他：", None),
    (f"{_CTRL} + F2 / F2", "切換書籤 / 跳至下一個書籤"),
    (f"{_CTRL} + {_SHIFT} + R / P", "開始停止錄製巨集 / 播放"),
    (f"{_CTRL} + {_ALT} + F", "摺疊游標所在區塊"),
    ("F1", "完整操作說明"),
)


def _usage() -> str:
    """組出說明文字。

    各平台的修飾鍵字樣寬度不同（`Ctrl` 是 4 欄、`⌘` 是 1 欄），寫死空白數
    在 macOS 上就會歪掉——改用專案自己的顯示寬度計算來補齊，順便讓這段
    文字跟編輯器用的是同一套欄寬規則。
    """
    from .core.widths import display_width

    width = max(display_width(key) for key, desc in _USAGE_KEYS if desc)
    lines = []
    for key, desc in _USAGE_KEYS:
        if desc is None:
            lines.append(key)
        else:
            lines.append(f"  {key}{' ' * (width - display_width(key) + 2)}{desc}")
    return (
        "Stephany Editor — 支援中文欄（直行）模式的文字編輯器\n\n"
        "用法：\n  stephany-editor [檔案 ...]\n\n" + "\n".join(lines) + "\n"
    )


USAGE = _usage()


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

    # X11 的 WM_CLASS。macOS 沒有 WM_CLASS，身分一律由 .app 的 Info.plist
    # 提供（SRS-005 D-01），這裡改用人看得懂的名稱當作從原始碼執行時的退路。
    app.setApplicationName(APP_NAME if platforms.IS_MAC else APP_ID)
    app.setDesktopFileName(APP_ID)  # Wayland 的 app_id —— 沒有這個就會顯示成 python3
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setWindowIcon(app_icon())
    # Windows 的第三種身分宣告：沒有它，工作列會把本程式跟其他 Python
    # 程式分到同一組（SRS-006 D-W1）。非 Windows 平台是 no-op。
    platforms.set_app_user_model_id()


def install_translations(app):
    """載入 Qt 內附字串的繁體中文翻譯（SRS-005 D-09、F-MAC-12）。

    介面文字大多是本專案自己寫的，但有一批不是：macOS 的應用程式選單
    （「關於 X」「結束 X」「服務」「隱藏 X」…）是 Qt 依平台慣例自己組出來的，
    `QMessageBox` 的 OK／Cancel 按鈕也一樣。沒載入翻譯時它們會是英文，夾在
    一整排中文選單裡特別突兀。

    翻譯檔隨 Qt 一起安裝，找不到就安靜略過——少了它只是那幾個字變英文，
    不是啟動不了。

    必須在建立主視窗（也就是建立選單列）之前呼叫；選單列一旦建好就來不及了。

    回傳裝上的 `QTranslator`，沒有翻譯檔可用時回傳 None。
    """
    from PySide6.QtCore import QLibraryInfo, QTranslator

    translator = QTranslator(app)  # 以 app 為 parent，才不會被回收掉
    path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if not translator.load(QT_TRANSLATION, path):
        return None
    return translator if app.installTranslator(translator) else None


def _make_file_open_relay():
    """接住 macOS 的 `QFileOpenEvent`（SRS-005 D-07、F-MAC-04）。

    在 Finder 雙擊檔案、或把檔案拖到 Dock 圖示上時，macOS 不是用命令列參數
    傳檔名，而是送一個事件給已經在跑的程序。這個事件可能比主視窗還早到
    （冷啟動時就是這樣），所以先排隊，等視窗建好再一次補開。
    """
    from PySide6.QtCore import QEvent, QObject

    class FileOpenRelay(QObject):
        def __init__(self):
            super().__init__()
            self.pending: list[str] = []
            self.window = None

        def eventFilter(self, obj, event):
            if event.type() == QEvent.Type.FileOpen:
                url = event.url()
                path = event.file() or (
                    url.toLocalFile() if url.isLocalFile() else ""
                )
                if path:
                    self.deliver(path)
                return True
            return False

        def deliver(self, path: str) -> None:
            """已經有視窗就直接開新分頁，否則排隊等視窗建好。"""
            if self.window is None:
                self.pending.append(path)
                return
            self.window.open_path(path)
            self.window.raise_()
            self.window.activateWindow()

        def attach(self, window) -> None:
            self.window = window
            pending, self.pending = self.pending, []
            for path in pending:
                window.open_path(path)

    return FileOpenRelay()


def _cli_files(argv: list[str]) -> list[str]:
    """去掉 LaunchServices 可能塞進來的程序序號參數（例如 -psn_0_12345）。"""
    return [a for a in argv if not a.startswith("-psn_")]


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
    args = parser.parse_args(_cli_files(argv))

    from PySide6.QtWidgets import QApplication

    from .ui.mainwindow import MainWindow

    app = QApplication(sys.argv[:1])
    configure_identity(app)
    install_translations(app)  # 必須早於 MainWindow —— 選單列建好就來不及了

    # 事件過濾器必須在建視窗之前就掛上，冷啟動時的開檔事件才接得到
    relay = _make_file_open_relay()
    app.installEventFilter(relay)
    app.processEvents()

    window = MainWindow(args.files + relay.pending)
    relay.attach(window)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
