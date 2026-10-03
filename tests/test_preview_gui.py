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

"""Markdown 預覽面板的行為測試（SRS-008）。

WebEngine 的載入與 JavaScript 都是非同步的：這裡一律「等到條件成立或逾時」，
逾時就紅燈並說明在等什麼，不用固定秒數的 sleep。

平台外掛由 conftest 決定，本檔不得自己設 QT_QPA_PLATFORM（SRS-006 D-W9）。
"""

from __future__ import annotations

import gc
import time

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QEventLoop, QTimer, QUrl
from PySide6.QtGui import QColor, QImage, QPalette

from stephany.ui import preview as preview_module
from stephany.ui.preview import MarkdownPreview

TIMEOUT = float(__import__("os").environ.get("PREVIEW_TIMEOUT", 15))  # 秒；CI 上 WebEngine 第一次起來可能要好幾秒


def wait_until(app, condition, what: str, timeout: float = TIMEOUT):
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            pytest.fail(f"等了 {timeout} 秒，{what} 仍不成立")
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
    return True


def settle(app, ms: int):
    """讓事件迴圈跑一段時間（用於「確認某件事『沒有』發生」）。"""
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def js(app, pv: MarkdownPreview, script: str):
    """在預覽頁面裡跑一段 JavaScript，同步取回結果。"""
    box = []
    pv.run_js(script, box.append)
    wait_until(app, lambda: box, f"JavaScript 回傳：{script}")
    return box[0]


def wait_rendered(app, pv: MarkdownPreview, before: int):
    wait_until(app, lambda: pv.render_count > before, "預覽完成渲染")


def make_preview(app, editor, *, webengine: bool, text: str = "", path=None):
    if webengine and not preview_module.WEBENGINE_AVAILABLE:
        pytest.skip(f"沒有 QtWebEngine：{preview_module.WEBENGINE_IMPORT_ERROR}")
    pv = MarkdownPreview(use_webengine=webengine)
    pv.resize(600, 400)
    pv.show()
    editor.setPlainText(text)
    editor.document().setModified(False)
    editor.file_path = path
    editor.show()
    before = pv.render_count
    pv.set_editor(editor)
    wait_rendered(app, pv, before)
    return pv


@pytest.fixture
def cleanup(app):
    created = []
    yield created
    for pv in created:
        pv.set_editor(None)
        pv.hide()
        pv.setParent(None)
        pv.deleteLater()
    # processEvents() 不處理 deleteLater；WebEnginePage 若活得比 profile 久，
    # 結束時 Qt 會警告並可能當掉
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    app.processEvents()
    gc.collect()


@pytest.fixture
def web(app, editor, cleanup):
    def factory(text="", path=None):
        pv = make_preview(app, editor, webengine=True, text=text, path=path)
        cleanup.append(pv)
        return pv

    return factory


@pytest.fixture
def simple(app, editor, cleanup):
    def factory(text="", path=None):
        pv = make_preview(app, editor, webengine=False, text=text, path=path)
        cleanup.append(pv)
        return pv

    return factory


LONG = "\n\n".join(f"## 第 {i} 節\n\n" + "內容 " * 40 for i in range(80))


# ----------------------------------------------------------------------
# D-01、F-MD-02：WebEngine 顯示 GitHub 風格的頁面
# ----------------------------------------------------------------------
def test_d_01_webengine_backend_is_used_when_available(web):
    pv = web("# x")
    assert pv.backend == "webengine"
    assert not pv.simple_mode_label.isVisibleTo(pv)


def test_f_md_02_renders_markdown_into_the_page(app, web):
    pv = web("# 標題\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n- [x] 完成\n")
    assert js(app, pv, "document.querySelectorAll('#content h1').length") == 1
    assert js(app, pv, "document.querySelectorAll('#content table td').length") == 2
    assert js(app, pv, "document.querySelectorAll('#content input[checked]').length") == 1


# ----------------------------------------------------------------------
# F-MD-04、D-06：自動更新，但先 debounce
# ----------------------------------------------------------------------
def test_d_06_edits_are_debounced_then_rendered(app, editor, web):
    pv = web("# 舊")
    before = pv.render_count
    editor.setPlainText("# 新")
    settle(app, pv.DEBOUNCE_MS // 3)
    assert pv.render_count == before, "debounce 時間內不該重新渲染"
    wait_rendered(app, pv, before)
    assert js(app, pv, "document.querySelector('#content h1').textContent") == "新"


def test_d_06_burst_of_edits_renders_once(app, editor, web):
    pv = web("")
    before = pv.render_count
    cursor = editor.textCursor()
    for ch in "連續打字":
        cursor.insertText(ch)
        settle(app, 20)
    wait_rendered(app, pv, before)
    settle(app, pv.DEBOUNCE_MS + 200)
    assert pv.render_count == before + 1
    assert js(app, pv, "document.getElementById('content').innerText.trim()") == "連續打字"


def test_d_06_update_does_not_reload_the_page(app, editor, web):
    """只換 #content，不重新載入整頁——否則捲動位置會跳回頂端。"""
    pv = web("# a")
    js(app, pv, "window.__marker = 1; 0")
    before = pv.render_count
    editor.setPlainText("# b")
    wait_rendered(app, pv, before)
    assert js(app, pv, "window.__marker === 1") is True


# ----------------------------------------------------------------------
# F-MD-08（D-07）：捲動依比例跟隨
# ----------------------------------------------------------------------
def scroll_ratio(app, pv):
    return js(
        app, pv,
        "window.scrollY / Math.max(1, document.documentElement.scrollHeight - window.innerHeight)",
    )


def test_f_md_08_preview_follows_editor_scroll(app, editor, web):
    pv = web(LONG)
    bar = editor.verticalScrollBar()
    assert bar.maximum() > 0
    bar.setValue(bar.maximum())
    wait_until(app, lambda: scroll_ratio(app, pv) > 0.95, "預覽捲到底")
    bar.setValue(bar.maximum() // 2)
    wait_until(app, lambda: 0.4 < scroll_ratio(app, pv) < 0.6, "預覽捲到一半")


def test_d_06_scroll_position_survives_an_update(app, editor, web):
    pv = web(LONG)
    bar = editor.verticalScrollBar()
    bar.setValue(bar.maximum() // 2)
    wait_until(app, lambda: scroll_ratio(app, pv) > 0.4, "預覽捲到一半")
    before = pv.render_count
    editor.textCursor().insertText("x")
    wait_rendered(app, pv, before)
    assert scroll_ratio(app, pv) > 0.4


# ----------------------------------------------------------------------
# D-08：頁面 JavaScript 關閉
# ----------------------------------------------------------------------
def test_d_08_scripts_in_markdown_do_not_run(app, web):
    pv = web(
        "<script>document.title = 'pwned'</script>\n\n"
        '<img src="missing.png" onerror="document.title = \'pwned\'">\n'
    )
    settle(app, 300)  # 讓破圖的 onerror 有機會觸發
    assert js(app, pv, "document.title") != "pwned"


# ----------------------------------------------------------------------
# D-10、BR-MD-4：連結
# ----------------------------------------------------------------------
@pytest.fixture
def opened(monkeypatch):
    urls = []
    monkeypatch.setattr(
        preview_module.QDesktopServices, "openUrl", lambda url: urls.append(url.toString()) or True
    )
    return urls


def link_clicked(pv, url: str) -> bool:
    from PySide6.QtWebEngineCore import QWebEnginePage

    return pv.page.acceptNavigationRequest(
        QUrl(url), QWebEnginePage.NavigationType.NavigationTypeLinkClicked, True
    )


def test_d_10_external_link_opens_in_system_browser(web, opened):
    pv = web("[x](https://example.com)")
    assert link_clicked(pv, "https://example.com") is False
    assert opened == ["https://example.com"]


def test_d_10_relative_link_is_blocked(web, opened, tmp_path):
    path = tmp_path / "a.md"
    pv = web("[x](b.md)", str(path))
    assert link_clicked(pv, QUrl.fromLocalFile(str(tmp_path / "b.md")).toString()) is False
    assert opened == []


def test_d_10_footnote_anchor_still_works(app, web, opened, tmp_path):
    path = tmp_path / "a.md"
    pv = web("x[^1]\n\n[^1]: 註", str(path))
    page_url = pv.page.url()
    page_url.setFragment("fn1")
    assert link_clicked(pv, page_url.toString()) is True
    assert opened == []


# ----------------------------------------------------------------------
# F-MD-06：相對路徑圖片
# ----------------------------------------------------------------------
def test_f_md_06_relative_image_loads_from_files_directory(app, web, tmp_path):
    image = QImage(8, 6, QImage.Format.Format_RGB32)
    image.fill(QColor("red"))
    (tmp_path / "img").mkdir()
    assert image.save(str(tmp_path / "img" / "a.png"))
    pv = web("![圖](img/a.png)", str(tmp_path / "a.md"))
    wait_until(
        app, lambda: js(app, pv, "document.images[0].naturalWidth") == 8, "相對路徑圖片載入"
    )


def test_f_md_06_switching_to_another_directory_reloads_base(app, editor, web, tmp_path):
    for sub in ("one", "two"):
        (tmp_path / sub).mkdir()
        image = QImage(3 if sub == "one" else 5, 2, QImage.Format.Format_RGB32)
        image.fill(QColor("blue"))
        image.save(str(tmp_path / sub / "a.png"))
    pv = web("![](a.png)", str(tmp_path / "one" / "x.md"))
    wait_until(app, lambda: js(app, pv, "document.images[0].naturalWidth") == 3, "第一張圖")
    before = pv.render_count
    editor.file_path = str(tmp_path / "two" / "x.md")  # 例如「另存新檔」
    pv.refresh()
    wait_rendered(app, pv, before)
    wait_until(app, lambda: js(app, pv, "document.images[0].naturalWidth") == 5, "換目錄後的圖")


# ----------------------------------------------------------------------
# F-MD-07、D-05：非 Markdown 檔
# ----------------------------------------------------------------------
def test_f_md_07_non_markdown_file_shows_notice(app, web, tmp_path):
    pv = web("# 這是 Python 註解", str(tmp_path / "a.py"))
    text = js(app, pv, "document.getElementById('content').innerText")
    assert "不是 Markdown" in text
    assert js(app, pv, "document.querySelectorAll('#content h1').length") == 0


def test_f_md_07_no_editor_shows_notice(app, web):
    pv = web("# x")
    before = pv.render_count
    pv.set_editor(None)
    wait_rendered(app, pv, before)
    assert js(app, pv, "document.querySelectorAll('#content h1').length") == 0


# ----------------------------------------------------------------------
# BR-MD-3：唯讀
# ----------------------------------------------------------------------
def test_br_md_3_preview_does_not_touch_the_document(app, editor, web):
    web("# x\n\n- [ ] 待辦")
    assert not editor.document().isModified()
    assert not editor.document().isUndoAvailable()
    assert editor.toPlainText() == "# x\n\n- [ ] 待辦"


def test_switching_editor_stops_listening_to_the_old_one(app, editor, web):
    from stephany.ui.editor import ColumnEditor

    pv = web("# 一")
    other = ColumnEditor()
    other.setPlainText("# 二")
    other.file_path = None
    try:
        before = pv.render_count
        pv.set_editor(other)
        wait_rendered(app, pv, before)
        assert js(app, pv, "document.querySelector('#content h1').textContent") == "二"
        before = pv.render_count
        editor.setPlainText("# 舊分頁被改")
        settle(app, pv.DEBOUNCE_MS + 300)
        assert pv.render_count == before
    finally:
        pv.set_editor(None)
        other.setParent(None)
        other.deleteLater()


# ----------------------------------------------------------------------
# F-MD-10：深色
# ----------------------------------------------------------------------
def dark_palette() -> QPalette:
    palette = QPalette()
    for role in (QPalette.ColorRole.Window, QPalette.ColorRole.Base):
        palette.setColor(role, QColor("#202020"))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text):
        palette.setColor(role, QColor("#eeeeee"))
    return palette


def test_f_md_10_dark_palette_gives_dark_page(app, web):
    pv = web("# x")
    assert js(app, pv, "getComputedStyle(document.body).backgroundColor") == "rgb(255, 255, 255)"
    before = pv.render_count
    pv.setPalette(dark_palette())
    wait_rendered(app, pv, before)
    assert js(app, pv, "getComputedStyle(document.body).backgroundColor") == "rgb(13, 17, 23)"


# ----------------------------------------------------------------------
# D-11：沒有 WebEngine 時的簡易模式
# ----------------------------------------------------------------------
def test_d_11_simple_mode_renders_and_says_so(simple):
    pv = simple("# 標題\n\n| a | b |\n|---|---|\n| 1 | 2 |\n")
    assert pv.backend == "textbrowser"
    assert pv.simple_mode_label.isVisibleTo(pv)
    text = pv.view.toPlainText()
    assert "標題" in text and "1" in text
    assert pv.view.document().toHtml().count("<td") >= 2


def test_d_11_simple_mode_follows_edits(app, editor, simple):
    pv = simple("# 舊")
    before = pv.render_count
    editor.setPlainText("# 新")
    wait_rendered(app, pv, before)
    assert "新" in pv.view.toPlainText()


def test_d_11_simple_mode_follows_scroll(app, editor, simple):
    pv = simple(LONG)
    bar = editor.verticalScrollBar()
    bar.setValue(bar.maximum())
    target = pv.view.verticalScrollBar()
    wait_until(app, lambda: target.maximum() > 0 and target.value() == target.maximum(), "簡易模式捲到底")


def test_d_11_simple_mode_links(simple, opened, tmp_path):
    pv = simple("[x](https://example.com) [y](b.md)", str(tmp_path / "a.md"))
    pv.view.anchorClicked.emit(QUrl("https://example.com"))
    pv.view.anchorClicked.emit(QUrl.fromLocalFile(str(tmp_path / "b.md")))
    assert opened == ["https://example.com"]
    assert "x" in pv.view.toPlainText()  # 沒有被導去別的頁面


def test_d_11_simple_mode_relative_image(app, simple, tmp_path):
    image = QImage(4, 4, QImage.Format.Format_RGB32)
    image.fill(QColor("red"))
    image.save(str(tmp_path / "a.png"))
    pv = simple("![](a.png)", str(tmp_path / "a.md"))
    from PySide6.QtGui import QTextDocument

    loaded = pv.view.document().resource(QTextDocument.ResourceType.ImageResource, QUrl("a.png"))
    assert loaded is not None and not loaded.isNull()


def test_d_11_falls_back_when_webengine_is_missing(monkeypatch, cleanup):
    monkeypatch.setattr(preview_module, "WEBENGINE_AVAILABLE", False)
    pv = MarkdownPreview()
    cleanup.append(pv)
    assert pv.backend == "textbrowser"


# ======================================================================
# 主視窗接線：F-MD-01、F-MD-05、F-MD-09
# ======================================================================
def open_preview(app, window):
    window.show()
    if not window.act_preview.isChecked():
        window.act_preview.trigger()
    wait_until(app, lambda: window.preview_dock.isVisible(), "預覽面板出現")
    pv = window.preview
    wait_until(app, lambda: pv.render_count > 0, "預覽第一次渲染")
    return pv


def test_f_md_01_action_is_in_view_menu_with_shortcut(window):
    from PySide6.QtGui import QKeySequence
    from PySide6.QtWidgets import QMenu

    action = window.act_preview
    assert action.isCheckable()
    assert action.shortcut() == QKeySequence("Ctrl+Shift+V")
    view = [m for m in window.menuBar().findChildren(QMenu) if m.title() == "檢視(&V)"]
    assert action in view[0].actions()


def test_f_md_01_shortcut_is_not_taken_by_anything_else(window):
    from PySide6.QtGui import QAction, QKeySequence

    clashes = [
        a.text() for a in window.findChildren(QAction)
        if a is not window.act_preview and QKeySequence("Ctrl+Shift+V") in a.shortcuts()
    ]
    assert clashes == []


def test_f_md_01_preview_is_off_and_not_built_by_default(window):
    """沒開預覽的人不該為 WebEngine 的啟動時間付費。"""
    assert not window.act_preview.isChecked()
    assert not window.preview_dock.isVisibleTo(window)
    assert window.preview is None


def test_f_md_01_toggle_shows_current_tab(app, window):
    window.editor().setPlainText("# 目前分頁")
    pv = open_preview(app, window)
    assert window.act_preview.isChecked()
    assert pv.current_editor() is window.editor()


def test_f_md_05_switching_tabs_switches_preview(app, window):
    first = window.editor()
    pv = open_preview(app, window)
    second = window.new_tab()
    assert pv.current_editor() is second
    window.tabs.setCurrentWidget(first)
    assert pv.current_editor() is first


def test_closing_the_panel_unchecks_and_stops_following(app, window):
    pv = open_preview(app, window)
    window.preview_dock.close()
    wait_until(app, lambda: not window.act_preview.isChecked(), "動作取消勾選")
    assert pv.current_editor() is None
    window.new_tab()
    assert pv.current_editor() is None


def test_closing_a_tab_moves_preview_to_the_remaining_one(app, window):
    first = window.editor()
    pv = open_preview(app, window)
    window.new_tab()
    window.close_tab(window.tabs.currentIndex())
    assert pv.current_editor() is first


def test_save_as_refreshes_preview(app, window, monkeypatch, tmp_path):
    import stephany.ui.mainwindow as mw

    window.editor().setPlainText("# 標題")
    pv = open_preview(app, window)
    target = tmp_path / "a.py"
    monkeypatch.setattr(mw.QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), ""))
    before = pv.render_count
    window.save_as()
    # 要立即刷新，不是等 debounce：另存時重新上色也會觸發內容變動，
    # 等滿 debounce 的話，有沒有接上「換路徑就刷新」都會變綠
    wait_until(app, lambda: pv.render_count > before, "另存後立即刷新", pv.DEBOUNCE_MS / 2000)
    if pv.backend == "webengine":
        assert "不是 Markdown" in js(app, pv, "document.getElementById('content').innerText")


def test_f_md_09_panel_state_survives_restart(app, window):
    import stephany.ui.mainwindow as mw

    open_preview(app, window)
    window.close()
    again = mw.MainWindow([])
    try:
        again.show()
        assert again.act_preview.isChecked()
        wait_until(app, lambda: again.preview_dock.isVisible(), "重開後預覽面板出現")
    finally:
        for index in range(again.tabs.count()):
            again.tabs.widget(index).document().setModified(False)
        again.close()
        again.setParent(None)
        again.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)


# ======================================================================
# 啟動入口：照真實啟動的組裝打開預覽不得當機
# ======================================================================
_LAUNCH_SCRIPT = r"""
import sys, tempfile, time
from pathlib import Path
from PySide6.QtCore import QEventLoop, QSettings

import stephany.ui.mainwindow as mw

tmp = tempfile.mkdtemp()  # 設定不得寫到使用者真正的位置
QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, tmp)
mw.QSettings = lambda o, a: QSettings(QSettings.Format.IniFormat, QSettings.Scope.UserScope, o, a)
mw.default_store_path = lambda: Path(tmp) / "macros.json"

from stephany.__main__ import create_app

app, window = create_app([sys.argv[1]])
window.show()

def spin(seconds, until=lambda: False):
    end = time.monotonic() + seconds
    while time.monotonic() < end and not until():
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20)
    return until()

for round_ in range(3):
    window.act_preview.trigger()  # 開
    if not spin(20, lambda: window.preview is not None and window.preview.render_count > round_):
        print("預覽沒有渲染"); sys.exit(2)
    window.editor().textCursor().insertText("x")
    spin(0.8)
    window.act_preview.trigger()  # 關
    spin(0.3)
window.editor().document().setModified(False)
window.close()
spin(0.3)
print("OK")
"""


def test_preview_survives_the_real_startup_wiring(tmp_path):
    """回歸：安裝版一打開預覽就 segfault。

    原因是 `__main__` 為了接 Finder 開檔，把 Python 物件掛成**整個 app 的
    事件過濾器**——每個物件的每個事件都要經過 Python，PySide 得把接收者
    包成 Python 物件；WebEngine 大量建立又銷毀內部物件，包到正在解構的
    物件時就當掉。單元測試不走 `main()` 的組裝，所以一直沒抓到。

    在子程序裡跑：segfault 會直接殺掉整個 pytest。
    """
    import os
    import subprocess
    import sys
    from pathlib import Path

    if not preview_module.WEBENGINE_AVAILABLE:
        pytest.skip(f"沒有 QtWebEngine：{preview_module.WEBENGINE_IMPORT_ERROR}")
    doc = tmp_path / "a.md"
    doc.write_text("# 標題\n\n| a | b |\n|---|---|\n| 1 | 2 |\n", encoding="utf-8")
    root = Path(__file__).resolve().parents[1]
    env = dict(os.environ, PYTHONPATH=str(root))
    result = subprocess.run(
        [sys.executable, "-c", _LAUNCH_SCRIPT, str(doc)],
        capture_output=True, text=True, timeout=120, env=env, cwd=str(tmp_path),
    )
    assert result.returncode == 0 and "OK" in result.stdout, (
        f"結束碼 {result.returncode}（-11／139 是 segfault）\n"
        f"stdout:\n{result.stdout[-2000:]}\nstderr:\n{result.stderr[-2000:]}"
    )
