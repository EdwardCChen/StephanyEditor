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

"""測試共用設定。

GUI 測試必須在無視窗環境下跑（CI、以及本機的批次執行），所以在任何
Qt 模組被 import 之前先把平台外掛設成 offscreen——**Windows 除外**。

Windows 的 offscreen 外掛不載入系統字型：實測 `QFontDatabase.families()`
回傳 0 筆（Linux 與 macOS 都不是這樣）。在那底下，所有字型不變量的測試
都會走 `pytest.skip`，CI 顯示全綠，但欄模式最重要的前提「中文 = 半形 × 2」
一次都沒被驗過。Windows 因此改用原生平台外掛（SRS-006 D-W9）。

另外處理 PySide6 的關閉競態：如果測試結束時還有存活的 widget（尤其是
帶著執行中 QTimer 的），直譯器關閉時 QApplication 可能比 widget 先被
回收，造成 segfault——測試全過但 exit code 139。這裡在每個測試後
確定性地停掉計時器並拆掉 widget。
"""

from __future__ import annotations

import gc
import os

# 這個判斷刻意不 import stephany.platforms：conftest 會在收集測試前執行，
# 保持它只相依標準函式庫最不容易出事。判斷式與 platforms.IS_WINDOWS 相同。
if os.name != "nt":
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402


@pytest.fixture(scope="session")
def app():
    from PySide6.QtWidgets import QApplication

    instance = QApplication.instance() or QApplication([])
    yield instance
    # QClipboard.setMimeData() 會把 QMimeData 的所有權轉給剪貼簿；若關閉時
    # 剪貼簿還握著它，會與 Python 端的參照重複釋放而 segfault。先清空。
    instance.clipboard().clear()
    for widget in list(instance.topLevelWidgets()):
        widget.close()
        widget.setParent(None)
    instance.processEvents()
    gc.collect()


@pytest.fixture
def editor(app):
    """一個乾淨的編輯器，測試結束後確實拆除。"""
    from stephany.ui.editor import ColumnEditor

    ed = ColumnEditor()
    ed.resize(800, 600)
    yield ed
    ed.exit_block_mode()  # 停掉游標閃爍與自動捲動計時器
    ed.hide()
    ed.setParent(None)
    del ed
    app.processEvents()
    gc.collect()


@pytest.fixture
def window(app, tmp_path, monkeypatch):
    """一個主視窗，設定檔與巨集檔都導到暫存目錄，不污染使用者的 ~/.config。"""
    from PySide6.QtCore import QSettings

    import stephany.ui.mainwindow as mw

    QSettings.setPath(
        QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path)
    )
    monkeypatch.setattr(mw, "default_store_path", lambda: tmp_path / "macros.json")
    win = mw.MainWindow([])
    yield win
    for index in range(win.tabs.count()):
        win.tabs.widget(index).document().setModified(False)
    win.close()
    win.setParent(None)
    del win
    app.processEvents()
    gc.collect()
