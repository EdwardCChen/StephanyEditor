"""巨集相關對話框。規格：SRS-002 F-MC-03、F-MC-04、F-MC-05。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
)

from ..core.macro import Macro


class RunMacroDialog(QDialog):
    """播放次數（F-MC-03）。"""

    def __init__(self, parent, macro: Macro):
        super().__init__(parent)
        self.setWindowTitle("播放巨集")
        self.rb_times = QRadioButton("播放指定次數")
        self.rb_times.setChecked(True)
        self.rb_eof = QRadioButton("播放到檔尾")
        self.spin = QSpinBox()
        self.spin.setRange(1, 100_000)
        self.spin.setValue(1)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"巨集共 {len(macro)} 個步驟"))
        form = QFormLayout()
        form.addRow(self.rb_times, self.spin)
        form.addRow(self.rb_eof)
        layout.addLayout(form)
        hint = QLabel("「到檔尾」會在游標到達結尾、或偵測到巨集空轉時自動停止。")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#666;")
        layout.addWidget(hint)

        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        layout.addWidget(bb)

    @property
    def until_eof(self) -> bool:
        return self.rb_eof.isChecked()

    @property
    def count(self) -> int:
        return self.spin.value()


class MacroManagerDialog(QDialog):
    """管理已存巨集：執行、重新命名、刪除、檢視步驟（F-MC-05）。"""

    def __init__(self, parent, store, run_callback):
        super().__init__(parent)
        self.setWindowTitle("巨集管理")
        self.resize(620, 420)
        self._store = store
        self._run = run_callback

        self.list = QListWidget()
        self.steps = QTextEdit()
        self.steps.setReadOnly(True)
        self.steps.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.list)
        splitter.addWidget(self.steps)
        splitter.setSizes([200, 420])

        buttons = QHBoxLayout()
        for text, slot in (
            ("執行", self.run_selected),
            ("重新命名", self.rename_selected),
            ("刪除", self.delete_selected),
        ):
            b = QPushButton(text)
            b.clicked.connect(slot)
            buttons.addWidget(b)
        buttons.addStretch()
        close = QPushButton("關閉")
        close.clicked.connect(self.accept)
        buttons.addWidget(close)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"儲存位置：{store.path}"))
        layout.addWidget(splitter)
        layout.addLayout(buttons)

        self.list.currentTextChanged.connect(self._show_steps)
        self.list.itemDoubleClicked.connect(self.run_selected)
        self.refresh()

    def refresh(self):
        current = self.list.currentItem().text() if self.list.currentItem() else None
        self.list.clear()
        self.list.addItems(self._store.names())
        if current:
            found = self.list.findItems(current, Qt.MatchFlag.MatchExactly)
            if found:
                self.list.setCurrentItem(found[0])
        elif self.list.count():
            self.list.setCurrentRow(0)

    def _show_steps(self, name: str):
        macro = self._store.macros.get(name)
        if macro is None:
            self.steps.clear()
            return
        lines = [f"{i}. {s.describe()}" for i, s in enumerate(macro.steps, start=1)]
        self.steps.setPlainText("\n".join(lines) or "（空巨集）")

    def _selected(self) -> str | None:
        item = self.list.currentItem()
        return item.text() if item else None

    def run_selected(self):
        name = self._selected()
        if name:
            self._run(self._store.macros[name])

    def rename_selected(self):
        name = self._selected()
        if not name:
            return
        new, ok = QInputDialog.getText(self, "重新命名", "新名稱：", text=name)
        if not ok or not new.strip() or new == name:
            return
        if new in self._store.macros:
            QMessageBox.warning(self, "重新命名", f"已經有叫「{new}」的巨集了。")
            return
        self._store.rename(name, new.strip())
        self.refresh()

    def delete_selected(self):
        name = self._selected()
        if not name:
            return
        reply = QMessageBox.question(self, "刪除巨集", f"確定要刪除「{name}」嗎？")
        if reply == QMessageBox.StandardButton.Yes:
            self._store.delete(name)
            self.refresh()
