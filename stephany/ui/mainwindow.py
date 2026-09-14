"""主視窗：分頁、選單、工具列、狀態列。"""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QAction, QActionGroup, QFont, QKeySequence, QTextOption
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QInputDialog,
    QFontDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QTabWidget,
    QWidget,
)

from ..core import document as doc_io
from ..core.macro import MacroRecorder, MacroStore, default_store_path
from .dialogs import ColumnEditorDialog, FindDialog, GoToDialog
from .editor import ColumnEditor
from .macro_dialogs import MacroManagerDialog, RunMacroDialog
from .highlighter import LANGUAGES, SimpleHighlighter, language_for

APP_NAME = "Stephany Editor"


class MainWindow(QMainWindow):
    def __init__(self, paths: list[str] | None = None):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1100, 740)
        self.setAcceptDrops(True)

        self.settings = QSettings("StephanyEditor", "StephanyEditor")
        self._find_dialog: FindDialog | None = None

        # 巨集錄製器全視窗共用一個（跨分頁），與 Notepad++ 一致（SRS-002）
        self.recorder = MacroRecorder()
        self.macro_store = MacroStore(default_store_path())
        self.macro_store.load()

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.setCentralWidget(self.tabs)

        self._build_actions()
        self._build_menus()
        self._build_toolbar()
        self._build_status_bar()
        self._restore_settings()
        if self.macro_store.load_error:  # NF-03：損毀的巨集檔不擋啟動
            self.statusBar().showMessage(self.macro_store.load_error, 8000)

        for path in paths or []:
            self.open_path(path)
        if self.tabs.count() == 0:
            self.new_tab()

    # ==================================================================
    # 分頁管理
    # ==================================================================
    def editor(self) -> ColumnEditor | None:
        return self.tabs.currentWidget()

    def new_tab(self, path: str | None = None) -> ColumnEditor:
        ed = ColumnEditor()
        ed.file_path = path
        ed.encoding = "utf-8"
        ed.eol = "\n"
        ed.highlighter = SimpleHighlighter(ed.document(), language_for(path), ed.palette())
        ed.set_tab_width(self._tab_width)
        if self._font:
            ed.apply_font(QFont(self._font))
        ed.document().modificationChanged.connect(
            lambda m, e=ed: self._update_tab_title(e)
        )
        ed.status_changed.connect(self._update_status)
        ed.block_mode_changed.connect(lambda *_: self._update_status())
        ed.bookmarks_changed.connect(self._update_status)
        ed.recorder = self.recorder  # 所有分頁共用同一個錄製器
        ed.setWordWrapMode(QTextOption.WrapMode.NoWrap)
        index = self.tabs.addTab(ed, "未命名")
        self.tabs.setCurrentIndex(index)
        self._update_tab_title(ed)
        ed.setFocus()
        return ed

    def _update_tab_title(self, ed: ColumnEditor):
        index = self.tabs.indexOf(ed)
        if index < 0:
            return
        name = Path(ed.file_path).name if ed.file_path else "未命名"
        if ed.document().isModified():
            name = "* " + name
        self.tabs.setTabText(index, name)
        self.tabs.setTabToolTip(index, ed.file_path or "")
        if ed is self.editor():
            self._update_window_title()

    def _update_window_title(self):
        ed = self.editor()
        if ed is None:
            self.setWindowTitle(APP_NAME)
            return
        path = ed.file_path or "未命名"
        mark = " *" if ed.document().isModified() else ""
        self.setWindowTitle(f"{path}{mark} — {APP_NAME}")

    def _on_tab_changed(self, *_):
        self._update_window_title()
        self._update_status()
        ed = self.editor()
        if ed is not None:
            self.act_sticky.setChecked(ed.sticky_column_mode)
            self.act_wrap.setChecked(
                ed.lineWrapMode() != ColumnEditor.LineWrapMode.NoWrap
            )

    def close_tab(self, index: int) -> bool:
        ed = self.tabs.widget(index)
        if ed is None:
            return True
        if not self._maybe_save(ed):
            return False
        self.tabs.removeTab(index)
        ed.deleteLater()
        if self.tabs.count() == 0:
            self.new_tab()
        return True

    def _maybe_save(self, ed: ColumnEditor) -> bool:
        if not ed.document().isModified():
            return True
        name = Path(ed.file_path).name if ed.file_path else "未命名"
        reply = QMessageBox.question(
            self,
            APP_NAME,
            f"「{name}」尚未儲存，要儲存嗎？",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Cancel:
            return False
        if reply == QMessageBox.StandardButton.Save:
            return self.save(ed)
        return True

    # ==================================================================
    # 檔案
    # ==================================================================
    def open_dialog(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "開啟檔案", str(Path.home()))
        for p in paths:
            self.open_path(p)

    def open_path(self, path: str, encoding: str | None = None):
        path = os.path.abspath(path)
        for i in range(self.tabs.count()):
            ed = self.tabs.widget(i)
            if ed.file_path == path and encoding is None:
                self.tabs.setCurrentIndex(i)
                return
        try:
            data = Path(path).read_bytes()
        except OSError as exc:
            QMessageBox.critical(self, APP_NAME, f"無法開啟檔案：\n{exc}")
            return
        result = doc_io.decode(data, encoding)
        ed = self.editor()
        # 目前分頁是全新的空白檔就直接用它，否則開新分頁
        if ed is None or ed.file_path or ed.document().isModified() or ed.toPlainText():
            ed = self.new_tab(path)
        ed.file_path = path
        ed.encoding = result.encoding
        ed.eol = result.eol
        ed.setPlainText(result.text)
        ed.document().setModified(False)
        ed.highlighter.set_language(language_for(path))
        self._update_tab_title(ed)
        self._update_status()

    def reopen_with_encoding(self, encoding: str):
        ed = self.editor()
        if ed is None or not ed.file_path:
            QMessageBox.information(self, APP_NAME, "請先儲存或開啟一個檔案。")
            return
        if not self._maybe_save(ed):
            return
        path = ed.file_path
        index = self.tabs.indexOf(ed)
        self.tabs.removeTab(index)
        ed.deleteLater()
        self.open_path(path, encoding)

    def save(self, ed: ColumnEditor | None = None) -> bool:
        ed = ed or self.editor()
        if ed is None:
            return False
        if not ed.file_path:
            return self.save_as(ed)
        return self._write(ed, ed.file_path)

    def save_as(self, ed: ColumnEditor | None = None) -> bool:
        ed = ed or self.editor()
        if ed is None:
            return False
        start = ed.file_path or str(Path.home() / "未命名.txt")
        path, _ = QFileDialog.getSaveFileName(self, "另存新檔", start)
        if not path:
            return False
        ed.file_path = path
        ed.highlighter.set_language(language_for(path))
        return self._write(ed, path)

    def _write(self, ed: ColumnEditor, path: str) -> bool:
        text = ed.toPlainText()
        bad = doc_io.unencodable_chars(text, ed.encoding)
        if bad:
            preview = " ".join(bad[:10])
            reply = QMessageBox.warning(
                self,
                APP_NAME,
                f"有 {len(bad)} 種字元無法用 {ed.encoding} 儲存，例如：{preview}\n\n"
                "改用 UTF-8 儲存嗎？（選「否」會把這些字換成 ?）",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                | QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Cancel:
                return False
            if reply == QMessageBox.StandardButton.Yes:
                ed.encoding = "utf-8"
        try:
            data = doc_io.encode(text, ed.encoding, ed.eol)
        except UnicodeEncodeError:
            data = doc_io.encode(
                text.encode(ed.encoding, errors="replace").decode(ed.encoding),
                ed.encoding,
                ed.eol,
            )
        try:
            Path(path).write_bytes(data)
        except OSError as exc:
            QMessageBox.critical(self, APP_NAME, f"無法儲存：\n{exc}")
            return False
        ed.document().setModified(False)
        self._update_tab_title(ed)
        self.statusBar().showMessage(f"已儲存 {path}", 3000)
        return True

    # ==================================================================
    # 動作與選單
    # ==================================================================
    def _act(self, text, slot, shortcut=None, checkable=False, tip=None):
        a = QAction(text, self)
        a.triggered.connect(slot)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        a.setCheckable(checkable)
        if tip:
            a.setToolTip(tip)
            a.setStatusTip(tip)
        return a

    def _build_actions(self):
        self.act_new = self._act("開新檔案(&N)", lambda: self.new_tab(), "Ctrl+N")
        self.act_open = self._act("開啟(&O)...", self.open_dialog, "Ctrl+O")
        self.act_save = self._act("儲存(&S)", lambda: self.save(), "Ctrl+S")
        self.act_save_as = self._act("另存新檔(&A)...", lambda: self.save_as(), "Ctrl+Shift+S")
        self.act_close_tab = self._act(
            "關閉分頁(&W)", lambda: self.close_tab(self.tabs.currentIndex()), "Ctrl+W"
        )
        self.act_quit = self._act("結束(&Q)", self.close, "Ctrl+Q")

        self.act_undo = self._act("復原", lambda: self._ed_call_normal("undo"), "Ctrl+Z")
        self.act_redo = self._act("取消復原", lambda: self._ed_call_normal("redo"), "Ctrl+Y")
        self.act_cut = self._act("剪下", lambda: self._ed_call("cut"), "Ctrl+X")
        self.act_copy = self._act("複製", lambda: self._ed_call("copy"), "Ctrl+C")
        self.act_paste = self._act("貼上", lambda: self._ed_call("paste"), "Ctrl+V")
        self.act_select_all = self._act(
            "全選", lambda: self._ed_call_normal("selectAll"), "Ctrl+A"
        )

        self.act_find = self._act("尋找 / 取代(&F)...", self.show_find, "Ctrl+F")
        self.act_goto = self._act("跳至行號(&G)...", self.show_goto, "Ctrl+G")

        self.act_sticky = self._act(
            "黏著式欄選取(&B)",
            self.toggle_sticky,
            "Ctrl+Shift+B",
            checkable=True,
            tip="開啟後直接拖曳滑鼠就是矩形選取，不必按住 Alt",
        )
        self.act_column_editor = self._act(
            "欄位編輯器(&C)...", self.show_column_editor, "Alt+C"
        )
        self.act_exit_block = self._act(
            "離開欄模式", lambda: self._ed_call("exit_block_mode"), "Esc"
        )

        # 書籤（SRS-002 F-BM-*）
        self.act_bm_toggle = self._act(
            "切換書籤(&T)", lambda: self._ed_call("perform", "bookmark_toggle"), "Ctrl+F2"
        )
        self.act_bm_next = self._act("下一個書籤(&N)", self.goto_next_bookmark, "F2")
        self.act_bm_prev = self._act("上一個書籤(&P)", self.goto_prev_bookmark, "Shift+F2")
        self.act_bm_clear = self._act(
            "清除全部書籤", lambda: self._ed_call("perform", "bookmark_clear")
        )
        self.act_bm_invert = self._act(
            "反轉書籤", lambda: self._ed_call("perform", "bookmark_invert")
        )
        self.act_bm_copy = self._act("複製書籤行", lambda: self._bookmark_lines("copy"))
        self.act_bm_cut = self._act("剪下書籤行", lambda: self._bookmark_lines("cut"))
        self.act_bm_delete = self._act("刪除書籤行", lambda: self._bookmark_lines("delete"))

        # 巨集（SRS-002 F-MC-*）
        self.act_macro_record = self._act(
            "開始錄製(&R)", self.toggle_recording, "Ctrl+Shift+R", checkable=True
        )
        self.act_macro_play = self._act("播放(&P)", self.play_current_macro, "Ctrl+Shift+P")
        self.act_macro_play_many = self._act("播放多次(&M)...", self.play_macro_dialog)
        self.act_macro_save = self._act("儲存目前巨集(&S)...", self.save_current_macro)
        self.act_macro_manage = self._act("管理巨集(&G)...", self.manage_macros)

        self.act_wrap = self._act("自動換行", self.toggle_wrap, checkable=True)
        self.act_whitespace = self._act("顯示空白與 TAB", self.toggle_whitespace, checkable=True)
        self.act_font = self._act("選擇字型(&F)...", self.choose_font)
        self.act_zoom_in = self._act("放大", lambda: self._zoom(1), "Ctrl+=")
        self.act_zoom_in.setShortcuts(
            [QKeySequence("Ctrl+="), QKeySequence("Ctrl++"), QKeySequence.StandardKey.ZoomIn]
        )
        self.act_zoom_out = self._act("縮小", lambda: self._zoom(-1), "Ctrl+-")
        self.act_zoom_reset = self._act("還原縮放", lambda: self._zoom(0), "Ctrl+0")
        self.act_ambiguous = self._act(
            "模稜兩可字元視為全形",
            self.toggle_ambiguous,
            checkable=True,
            tip="希臘字母、℃、※ 之類的字在不同字型寬度不一，依實際顯示調整",
        )
        self.act_help = self._act("欄模式操作說明(&H)", self.show_help, "F1")

    def _ed_call(self, name, *args):
        ed = self.editor()
        if ed is not None:
            getattr(ed, name)(*args)

    def _ed_call_normal(self, name, *args):
        """需要一般（非矩形）游標語意的動作，先離開欄模式再執行。"""
        ed = self.editor()
        if ed is not None:
            ed.exit_block_mode()
            getattr(ed, name)(*args)

    def _build_menus(self):
        bar = self.menuBar()

        m = bar.addMenu("檔案(&F)")
        for a in (self.act_new, self.act_open, self.act_save, self.act_save_as):
            m.addAction(a)
        m.addSeparator()
        m.addAction(self.act_close_tab)
        m.addAction(self.act_quit)

        m = bar.addMenu("編輯(&E)")
        for a in (
            self.act_undo,
            self.act_redo,
            None,
            self.act_cut,
            self.act_copy,
            self.act_paste,
            self.act_select_all,
        ):
            m.addSeparator() if a is None else m.addAction(a)

        m = bar.addMenu("搜尋(&S)")
        m.addAction(self.act_find)
        m.addAction(self.act_goto)

        m = bar.addMenu("書籤(&K)")
        for a in (
            self.act_bm_toggle,
            self.act_bm_next,
            self.act_bm_prev,
            None,
            self.act_bm_invert,
            self.act_bm_clear,
            None,
            self.act_bm_copy,
            self.act_bm_cut,
            self.act_bm_delete,
        ):
            m.addSeparator() if a is None else m.addAction(a)

        m = bar.addMenu("巨集(&M)")
        for a in (
            self.act_macro_record,
            self.act_macro_play,
            self.act_macro_play_many,
            None,
            self.act_macro_save,
            self.act_macro_manage,
        ):
            m.addSeparator() if a is None else m.addAction(a)

        m = bar.addMenu("欄模式(&B)")
        m.addAction(self.act_sticky)
        m.addAction(self.act_column_editor)
        m.addAction(self.act_exit_block)
        m.addSeparator()
        m.addAction(self.act_ambiguous)
        m.addAction(self.act_help)

        m = bar.addMenu("檢視(&V)")
        m.addAction(self.act_wrap)
        m.addAction(self.act_whitespace)
        m.addSeparator()
        m.addAction(self.act_font)
        m.addAction(self.act_zoom_in)
        m.addAction(self.act_zoom_out)
        m.addAction(self.act_zoom_reset)
        tabs = m.addMenu("TAB 寬度")
        group = QActionGroup(self)
        for width in (2, 4, 8):
            a = QAction(f"{width} 欄", self, checkable=True)
            a.setChecked(width == 4)
            a.triggered.connect(lambda _=False, w=width: self.set_tab_width(w))
            group.addAction(a)
            tabs.addAction(a)

        m = bar.addMenu("編碼(&C)")
        reopen = m.addMenu("以編碼重新開啟")
        for label, enc in doc_io.ENCODINGS.items():
            reopen.addAction(
                self._act(label, lambda _=False, e=enc: self.reopen_with_encoding(e))
            )
        convert = m.addMenu("儲存時使用的編碼")
        for label, enc in doc_io.ENCODINGS.items():
            convert.addAction(
                self._act(label, lambda _=False, e=enc: self.set_encoding(e))
            )
        eol = m.addMenu("換行字元")
        for seq, label in doc_io.EOL_NAMES.items():
            eol.addAction(self._act(label, lambda _=False, s=seq: self.set_eol(s)))

        m = bar.addMenu("語言(&L)")
        m.addAction(self._act("純文字", lambda: self.set_language(None)))
        for name in LANGUAGES:
            m.addAction(self._act(name, lambda _=False, n=name: self.set_language(n)))

    def _build_toolbar(self):
        tb = self.addToolBar("主工具列")
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        for a in (
            self.act_new,
            self.act_open,
            self.act_save,
            None,
            self.act_undo,
            self.act_redo,
            None,
            self.act_find,
            None,
            self.act_sticky,
            self.act_column_editor,
            None,
            self.act_bm_toggle,
            self.act_macro_record,
            self.act_macro_play,
        ):
            tb.addSeparator() if a is None else tb.addAction(a)

    def _build_status_bar(self):
        self.lbl_pos = QLabel("")
        self.lbl_mode = QLabel("")
        self.lbl_enc = QLabel("")
        self.lbl_warn = QLabel("")
        self.lbl_warn.setStyleSheet("color:#b00;")
        for w, stretch in ((self.lbl_pos, 3), (self.lbl_mode, 2), (self.lbl_warn, 4)):
            self.statusBar().addWidget(w, stretch)
        self.statusBar().addPermanentWidget(self.lbl_enc)
        self._update_status()

    def _update_status(self):
        ed = self.editor()
        if ed is None:
            return
        self.lbl_pos.setText(ed.status_text())
        mode = "欄模式" if ed.block_mode else ("欄選取待命" if ed.sticky_column_mode else "一般模式")
        extras = [mode]
        if self.recorder.recording:  # F-MC-08
            extras.append(f"● 錄製中（已錄 {self.recorder.pending_count} 步）")
        elif self.recorder.current:
            extras.append(f"巨集 {len(self.recorder.current)} 步")
        if len(ed.bookmarks):  # F-BM-10
            extras.append(f"書籤 {len(ed.bookmarks)}")
        self.lbl_mode.setText("   ".join(extras))
        eol_name = doc_io.EOL_NAMES.get(ed.eol, ed.eol)
        self.lbl_enc.setText(f"{ed.encoding}   {eol_name}")
        self.lbl_warn.setText(
            "" if ed.font_is_aligned else "⚠ 此字型的中文不是英文的兩倍寬，欄位可能對不齊（請改用 Noto Sans Mono CJK）"
        )

    # ==================================================================
    # 各項設定
    # ==================================================================
    def show_find(self):
        if self._find_dialog is None:
            self._find_dialog = FindDialog(self, self.editor)
        ed = self.editor()
        if ed is not None and ed.textCursor().hasSelection():
            self._find_dialog.find_edit.setText(ed.textCursor().selectedText())
        self._find_dialog.show()
        self._find_dialog.raise_()
        self._find_dialog.find_edit.setFocus()
        self._find_dialog.find_edit.selectAll()

    def show_goto(self):
        ed = self.editor()
        if ed is not None:
            GoToDialog(self, ed).exec()

    def show_column_editor(self):
        ed = self.editor()
        if ed is not None:
            ColumnEditorDialog(self, ed).exec()

    def toggle_sticky(self, checked: bool):
        ed = self.editor()
        if ed is not None:
            ed.set_sticky_column_mode(checked)
        self._update_status()

    def toggle_wrap(self, checked: bool):
        ed = self.editor()
        if ed is None:
            return
        if checked:
            ed.exit_block_mode()
            ed.setLineWrapMode(ColumnEditor.LineWrapMode.WidgetWidth)
            self.statusBar().showMessage("自動換行開啟時無法使用欄模式", 4000)
        else:
            ed.setLineWrapMode(ColumnEditor.LineWrapMode.NoWrap)

    def toggle_whitespace(self, checked: bool):
        ed = self.editor()
        if ed is None:
            return
        opt = ed.document().defaultTextOption()
        flags = opt.flags()
        if checked:
            flags |= QTextOption.Flag.ShowTabsAndSpaces
        else:
            flags &= ~QTextOption.Flag.ShowTabsAndSpaces
        opt.setFlags(flags)
        ed.document().setDefaultTextOption(opt)
        ed.viewport().update()

    def toggle_ambiguous(self, checked: bool):
        for i in range(self.tabs.count()):
            self.tabs.widget(i).set_ambiguous_wide(checked)
        self.settings.setValue("ambiguous_wide", checked)

    def choose_font(self):
        ed = self.editor()
        if ed is None:
            return
        ok, font = QFontDialog.getFont(ed.font(), self, "選擇字型")
        if ok:
            self._font = font
            self.settings.setValue("font", font.toString())
            for i in range(self.tabs.count()):
                self.tabs.widget(i).apply_font(QFont(font))
            self._update_status()

    def _zoom(self, direction: int):
        ed = self.editor()
        if ed is None:
            return
        font = QFont(ed.font())
        if direction == 0:
            font.setPointSize(12)
        else:
            font.setPointSize(max(6, min(48, font.pointSize() + direction)))
        self._font = font
        for i in range(self.tabs.count()):
            self.tabs.widget(i).apply_font(QFont(font))

    def set_tab_width(self, width: int):
        self._tab_width = width
        self.settings.setValue("tab_width", width)
        for i in range(self.tabs.count()):
            self.tabs.widget(i).set_tab_width(width)

    def set_encoding(self, encoding: str):
        ed = self.editor()
        if ed is None:
            return
        ed.encoding = encoding
        ed.document().setModified(True)
        self._update_status()

    def set_eol(self, eol: str):
        ed = self.editor()
        if ed is None:
            return
        ed.eol = eol
        ed.document().setModified(True)
        self._update_status()

    def set_language(self, name: str | None):
        ed = self.editor()
        if ed is not None:
            ed.highlighter.set_language(name)

    # ==================================================================
    # 書籤（SRS-002 F-BM-*）
    # ==================================================================
    def goto_next_bookmark(self):
        ed = self.editor()
        if ed is not None and not ed.perform("bookmark_next"):
            self.statusBar().showMessage("沒有書籤", 2000)  # BR-BM-4

    def goto_prev_bookmark(self):
        ed = self.editor()
        if ed is not None and not ed.perform("bookmark_prev"):
            self.statusBar().showMessage("沒有書籤", 2000)

    def _bookmark_lines(self, action: str):
        """F-BM-06 / 07 / 08"""
        ed = self.editor()
        if ed is None:
            return
        if not len(ed.bookmarks):
            self.statusBar().showMessage("沒有書籤", 2000)
            return
        n = len(ed.bookmarks)
        verb = {"copy": "已複製", "cut": "已剪下", "delete": "已刪除"}[action]
        ed.perform(f"bookmark_{action}_lines")  # 走命令層才錄得到（F-MC-07）
        self.statusBar().showMessage(f"{verb} {n} 行", 3000)

    # ==================================================================
    # 巨集（SRS-002 F-MC-*）
    # ==================================================================
    def toggle_recording(self, checked: bool | None = None):
        """F-MC-01"""
        if self.recorder.recording:
            macro = self.recorder.stop()
            self.act_macro_record.setChecked(False)
            self.act_macro_record.setText("開始錄製(&R)")
            self.statusBar().showMessage(f"錄製完成，共 {len(macro)} 個步驟", 4000)
        else:
            self.recorder.start()
            self.act_macro_record.setChecked(True)
            self.act_macro_record.setText("停止錄製(&R)")
            self.statusBar().showMessage("開始錄製巨集——接下來的編輯動作都會被記錄", 4000)
        self._update_status()

    def _run_macro(self, macro, count: int = 1, until_eof: bool = False):
        ed = self.editor()
        if ed is None:
            return
        if not macro or not len(macro):
            self.statusBar().showMessage("目前沒有可播放的巨集", 3000)
            return
        done, error = ed.replay(macro, count=count, until_eof=until_eof)
        if error:  # BR-MC-4
            QMessageBox.warning(
                self,
                APP_NAME,
                f"巨集在第 {done + 1} 輪停止：\n{error}\n\n已完成 {done} 輪，"
                "可用 Ctrl+Z 一次還原。",
            )
        else:
            self.statusBar().showMessage(f"巨集播放完成，共 {done} 輪", 4000)
        self._update_status()

    def play_current_macro(self):
        """F-MC-02"""
        if self.recorder.recording:  # BR-MC-5
            self.statusBar().showMessage("錄製中無法播放，請先停止錄製", 3000)
            return
        self._run_macro(self.recorder.current)

    def play_macro_dialog(self, macro=None):
        """F-MC-03"""
        if self.recorder.recording:
            self.statusBar().showMessage("錄製中無法播放，請先停止錄製", 3000)
            return
        macro = macro or self.recorder.current
        if not macro or not len(macro):
            self.statusBar().showMessage("目前沒有可播放的巨集", 3000)
            return
        dialog = RunMacroDialog(self, macro)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._run_macro(macro, count=dialog.count, until_eof=dialog.until_eof)

    def save_current_macro(self):
        """F-MC-04"""
        macro = self.recorder.current
        if not macro or not len(macro):
            self.statusBar().showMessage("目前沒有錄到任何步驟", 3000)
            return
        name, ok = QInputDialog.getText(self, "儲存巨集", "巨集名稱：")
        name = name.strip()
        if not ok or not name:
            return
        if name in self.macro_store.macros:
            reply = QMessageBox.question(
                self, "儲存巨集", f"已經有叫「{name}」的巨集，要覆蓋嗎？"
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        self.macro_store.add(macro.renamed(name))
        self.statusBar().showMessage(
            f"已儲存巨集「{name}」到 {self.macro_store.path}", 5000
        )

    def manage_macros(self):
        """F-MC-05"""
        MacroManagerDialog(self, self.macro_store, self.play_macro_dialog).exec()

    def show_help(self):
        QMessageBox.information(
            self,
            "欄模式操作說明",
            "<b>進入欄（直行）模式</b><br>"
            "• 按住 <b>Alt</b> 再用滑鼠拖曳<br>"
            "• <b>Alt+Shift+方向鍵</b> 從游標處展開<br>"
            "• <b>Ctrl+Shift+B</b> 開啟黏著式欄選取，之後直接拖曳即可"
            "（GNOME 會攔截 Alt+拖曳時就用這個）<br><br>"
            "<b>在欄模式中</b><br>"
            "• 直接打字（含注音／拼音輸入法）→ 每一行同一欄位都插入<br>"
            "• <b>Backspace / Delete</b> → 整個矩形一起刪<br>"
            "• <b>Ctrl+C / Ctrl+X / Ctrl+V</b> → 矩形複製、剪下、貼上<br>"
            "• <b>Alt+C</b> → 欄位編輯器（整欄插入文字或遞增數列）<br>"
            "• <b>Esc</b> 或按方向鍵 → 回到一般模式<br><br>"
            "<b>中文寬度</b><br>"
            "一個中文字 = 兩欄。矩形邊界切到半個中文字時，該字會變成兩個空白，"
            "這樣刪除或插入後版面仍然對齊。<br><br>"
            "<b>書籤</b><br>"
            "• <b>Ctrl+F2</b> 切換目前行的書籤，行號欄會出現藍點<br>"
            "• <b>F2</b> / <b>Shift+F2</b> 跳到下一個／上一個（到底會繞回）<br>"
            "• 書籤選單可以一次複製、剪下或刪除所有書籤行<br>"
            "• 在書籤上方插入或刪除文字時，書籤會跟著它那一行移動<br><br>"
            "<b>巨集</b><br>"
            "• <b>Ctrl+Shift+R</b> 開始／停止錄製，<b>Ctrl+Shift+P</b> 播放<br>"
            "• 「播放多次」可以指定次數或一路跑到檔尾<br>"
            "• 錄的是編輯動作本身（含中文輸入、欄模式、書籤、尋找），"
            "不是鍵盤按鍵，所以換個位置重播也會正確<br>"
            "• 整段重播算一次 <b>Ctrl+Z</b>，效果不對可以一次還原<br>"
            "• 巨集可命名儲存，下次開啟程式還在",
        )

    # ==================================================================
    # 設定存取與視窗事件
    # ==================================================================
    def _restore_settings(self):
        self._tab_width = int(self.settings.value("tab_width", 4))
        self._font = None
        saved = self.settings.value("font", "")
        if saved:
            f = QFont()
            if f.fromString(saved):
                self._font = f
        amb = self.settings.value("ambiguous_wide", False)
        self.act_ambiguous.setChecked(amb in (True, "true"))
        geom = self.settings.value("geometry")
        if geom:
            self.restoreGeometry(geom)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            if url.isLocalFile():
                self.open_path(url.toLocalFile())
        event.acceptProposedAction()

    def closeEvent(self, event):
        while self.tabs.count():
            ed = self.tabs.widget(0)
            if not self._maybe_save(ed):
                event.ignore()
                return
            self.tabs.removeTab(0)
        self.settings.setValue("geometry", self.saveGeometry())
        event.accept()
