"""測試共用設定。

GUI 測試必須在無視窗環境下跑（CI、以及本機的批次執行），所以在任何
Qt 模組被 import 之前先把平台外掛設成 offscreen。

另外處理 PySide6 的關閉競態：如果測試結束時還有存活的 widget（尤其是
帶著執行中 QTimer 的），直譯器關閉時 QApplication 可能比 widget 先被
回收，造成 segfault——測試全過但 exit code 139。這裡在每個測試後
確定性地停掉計時器並拆掉 widget。
"""

from __future__ import annotations

import gc
import os

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
