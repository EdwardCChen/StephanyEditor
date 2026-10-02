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

"""Markdown 預覽面板（SRS-008）。

轉換在 `core.markdown`，這裡只管顯示：跟著哪個編輯器、何時重畫、捲到哪、
連結點了怎麼辦。兩種後端：

- **webengine**（D-01）：`QWebEngineView`。頁面外殼載入一次，之後的更新只透過
  `runJavaScript` 換掉 `#content`（D-06），捲動位置因此不會跳回頂端。
  順帶避開 `setHtml()` 的 2 MB 上限——內容從不經過 `setHtml()`。
- **textbrowser**（D-11）：沒有 QtWebEngine 時的簡易模式，顯示同一份 HTML，
  長相退回 Qt 富文字所能支援的程度。
"""

from __future__ import annotations

import json

import shiboken6

from PySide6.QtCore import QEvent, QTimer, QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QLabel, QPlainTextEdit, QTextBrowser, QVBoxLayout, QWidget

from ..core import markdown as md
from . import theme

try:
    from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineScript, QWebEngineSettings
    from PySide6.QtWebEngineWidgets import QWebEngineView
except ImportError as exc:  # D-11：沒裝 PySide6-Addons／python3-pyside6.qtwebengine*
    WEBENGINE_AVAILABLE = False
    WEBENGINE_IMPORT_ERROR = str(exc)
else:
    WEBENGINE_AVAILABLE = True
    WEBENGINE_IMPORT_ERROR = ""

NOT_MARKDOWN = '<p class="stephany-notice">目前分頁不是 Markdown 檔，沒有可預覽的內容。</p>'
NO_EDITOR = '<p class="stephany-notice">沒有開啟的分頁。</p>'


def prepare_webengine() -> None:
    """建立 QApplication **之前**呼叫。

    QtWebEngine 要求在 QCoreApplication 建立前就載入（或設好共用 OpenGL
    context），否則之後建 `QWebEngineView` 會直接中止程式。模組頂端的
    import 已經完成載入，這裡再補設屬性，讓呼叫端只要記得呼叫這一個函式。
    """
    if WEBENGINE_AVAILABLE:
        from PySide6.QtCore import QCoreApplication

        QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)


def _base_url(path: str | None) -> QUrl:
    """F-MD-06：結尾一定要有斜線，`a.png` 才會解析成目錄底下的檔案。"""
    base = md.base_dir(path)
    if base is None:
        return QUrl()
    return QUrl.fromLocalFile(base.rstrip("/\\") + "/")


def _same_document(url: QUrl, document: QUrl) -> bool:
    """`url` 是否只是 `document` 裡的錨點（例如註腳 `#fn1`）。

    不用 `QUrl.adjusted(RemoveFragment)`：PySide6 6.11 的綁定不接受這個列舉。
    """
    return url.hasFragment() and url.toString().split("#", 1)[0] == document.toString().split("#", 1)[0]


def _open_external(url: QUrl) -> bool:
    """D-10、BR-MD-4：只有外部連結交給系統；回傳是否交出去了。"""
    if md.is_external_link(url.toString()):
        QDesktopServices.openUrl(url)
        return True
    return False


if WEBENGINE_AVAILABLE:

    class _PreviewPage(QWebEnginePage):
        """攔下所有使用者點出來的導覽（D-10），只放行同一頁的錨點（註腳）。"""

        def acceptNavigationRequest(self, url, nav_type, is_main_frame):
            if nav_type != QWebEnginePage.NavigationType.NavigationTypeLinkClicked:
                return True  # 本程式自己的 setHtml()
            if _open_external(url):
                return False
            return _same_document(url, self.url())


class MarkdownPreview(QWidget):
    """跟著一個編輯器顯示它的 Markdown 預覽。"""

    DEBOUNCE_MS = 300  # D-06

    #: 每完成一次內容更新就發出（測試與之後的接線用）
    rendered = Signal()

    def __init__(self, parent=None, use_webengine: bool | None = None):
        super().__init__(parent)
        if use_webengine is None:
            use_webengine = WEBENGINE_AVAILABLE
        self.backend = "webengine" if use_webengine else "textbrowser"
        self.render_count = 0
        self._editor: QPlainTextEdit | None = None
        self._ratio = 0.0
        self._shell_key = None  # (基準 URL, 深色)：變了才需要重載整頁
        self._shell_ready = False
        self._pending = ""

        self.simple_mode_label = QLabel(
            "簡易模式：找不到 QtWebEngine，長相與 GitHub 會有差異。"
        )
        self.simple_mode_label.setWordWrap(True)
        self.simple_mode_label.setContentsMargins(6, 4, 6, 4)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(self.DEBOUNCE_MS)
        self._timer.timeout.connect(self.refresh)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.simple_mode_label)

        if self.backend == "webengine":
            self.view = QWebEngineView(self)
            self.page = _PreviewPage(self.view)
            self.view.setPage(self.page)
            settings = self.page.settings()
            # D-08：頁面自己的 JS 一律不跑；本程式的更新走 ApplicationWorld
            settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, False)
            # D-09：README 上的 badge 等遠端圖片要看得到
            settings.setAttribute(
                QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
            )
            self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
            self.page.loadFinished.connect(self._on_shell_loaded)
            self.simple_mode_label.hide()
        else:
            self.view = QTextBrowser(self)
            self.page = None
            self.view.setOpenLinks(False)  # D-10：自己決定點了怎麼辦
            self.view.anchorClicked.connect(self._on_anchor_clicked)
        layout.addWidget(self.view, 1)

    # ------------------------------------------------------------------
    # 跟著哪個編輯器
    # ------------------------------------------------------------------
    def set_editor(self, editor: QPlainTextEdit | None) -> None:
        """F-MD-05：換成另一個分頁。立即更新，不等 debounce。"""
        if self._editor is not None:
            self._editor.document().contentsChanged.disconnect(self._schedule)
            self._editor.verticalScrollBar().valueChanged.disconnect(self._on_editor_scrolled)
            self._editor.verticalScrollBar().rangeChanged.disconnect(self._on_editor_scrolled)
        self._editor = editor
        if editor is not None:
            editor.document().contentsChanged.connect(self._schedule)
            editor.verticalScrollBar().valueChanged.connect(self._on_editor_scrolled)
            editor.verticalScrollBar().rangeChanged.connect(self._on_editor_scrolled)
            self._ratio = self._editor_ratio()
        self.refresh()

    def current_editor(self) -> QPlainTextEdit | None:
        return self._editor

    def _schedule(self) -> None:
        self._timer.start()  # 重新計時：連續打字只在停手後畫一次

    def _editor_ratio(self) -> float:
        bar = self._editor.verticalScrollBar()
        return bar.value() / bar.maximum() if bar.maximum() > 0 else 0.0

    def _on_editor_scrolled(self, *_):
        """F-MD-08（D-07）：比例跟隨。"""
        if self._editor is None:
            return
        self._ratio = self._editor_ratio()
        self._apply_scroll()

    # ------------------------------------------------------------------
    # 渲染
    # ------------------------------------------------------------------
    def _current(self) -> tuple[str, str | None]:
        """（HTML 片段, 檔案路徑）"""
        ed = self._editor
        if ed is None:
            return NO_EDITOR, None
        path = getattr(ed, "file_path", None)
        if not md.is_markdown(path):
            return NOT_MARKDOWN, path
        return md.render(ed.toPlainText()), path

    def refresh(self) -> None:
        """立刻依目前編輯器的內容更新預覽。"""
        self._timer.stop()
        body, path = self._current()
        dark = theme.is_dark(self.palette())
        if self.backend == "textbrowser":
            self._render_simple(body, path, dark)
            return
        key = (_base_url(path).toString(), dark)
        if key != self._shell_key:
            # 基準目錄或深淺色變了：重載外殼（內容等載入完成後再放進去）
            self._shell_key = key
            self._shell_ready = False
            self._pending = body
            self.page.setHtml(md.page("", dark), _base_url(path))
            return
        if not self._shell_ready:
            self._pending = body  # 外殼還在載入，等它好了再放
            return
        self._inject(body)

    def _on_shell_loaded(self, ok: bool) -> None:
        self._shell_ready = True
        self._inject(self._pending)

    def _inject(self, body: str) -> None:
        script = (
            f"document.getElementById('content').innerHTML = {json.dumps(body)};"
            + self._scroll_script()
        )
        self.run_js(script, lambda _result: self._done())

    def _scroll_script(self) -> str:
        return (
            "window.scrollTo(0, %r * Math.max(0, document.documentElement.scrollHeight"
            " - window.innerHeight)); 0" % self._ratio
        )

    def _render_simple(self, body: str, path: str | None, dark: bool) -> None:
        view = self.view
        view.document().setBaseUrl(_base_url(path))
        view.setHtml(md.page(body, dark))
        self._apply_scroll()
        self._done()

    def _done(self) -> None:
        # runJavaScript 的回呼是非同步的：面板可能已經被刪了（關分頁、關視窗）
        # 回呼才回來，這時對已刪除的 C++ 物件發信號會丟 TypeError
        if not shiboken6.isValid(self):
            return
        self.render_count += 1
        self.rendered.emit()

    def _apply_scroll(self) -> None:
        if self.backend == "textbrowser":
            bar = self.view.verticalScrollBar()
            bar.setValue(round(self._ratio * bar.maximum()))
        elif self._shell_ready:
            self.run_js(self._scroll_script())

    def run_js(self, script: str, callback=None) -> None:
        """在隔離的 ApplicationWorld 執行（D-08：頁面自己的 JS 是關的）。"""
        world = QWebEngineScript.ScriptWorldId.ApplicationWorld
        if callback is None:
            self.page.runJavaScript(script, world)
        else:
            self.page.runJavaScript(script, world, callback)

    # ------------------------------------------------------------------
    def _on_anchor_clicked(self, url: QUrl) -> None:
        """簡易模式的連結（D-10）。"""
        if _open_external(url):
            return
        if url.hasFragment() and (
            not url.toString().split("#", 1)[0]
            or _same_document(url, self.view.document().baseUrl())
        ):
            self.view.scrollToAnchor(url.fragment())

    def changeEvent(self, event):
        """F-MD-10：系統切換深淺色時跟著換。"""
        super().changeEvent(event)
        if event.type() in (
            QEvent.Type.PaletteChange, QEvent.Type.ApplicationPaletteChange
        ) and hasattr(self, "view"):  # 建構途中就可能收到
            self.refresh()
