"""尋找／取代、欄位編輯器、跳至行號。"""

from __future__ import annotations

from PySide6.QtCore import QRegularExpression, Qt
from PySide6.QtGui import QTextCursor, QTextDocument
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
)


class FindDialog(QDialog):
    """尋找與取代。非強制回應（modeless），可以邊找邊編輯。"""

    def __init__(self, parent, get_editor):
        super().__init__(parent)
        self.setWindowTitle("尋找 / 取代")
        self._get_editor = get_editor
        self.setWindowFlag(Qt.WindowType.Tool)

        self.find_edit = QLineEdit()
        self.replace_edit = QLineEdit()
        self.cb_case = QCheckBox("區分大小寫")
        self.cb_word = QCheckBox("全字拼寫")
        self.cb_regex = QCheckBox("正規表示式")
        self.cb_wrap = QCheckBox("繞回檔頭繼續找")
        self.cb_wrap.setChecked(True)
        self.status = QLabel("")
        self.status.setStyleSheet("color:#666;")

        form = QFormLayout()
        form.addRow("尋找：", self.find_edit)
        form.addRow("取代為：", self.replace_edit)

        opts = QHBoxLayout()
        for cb in (self.cb_case, self.cb_word, self.cb_regex, self.cb_wrap):
            opts.addWidget(cb)
        opts.addStretch()

        buttons = QGridLayout()
        defs = [
            ("找下一個", self.find_next, 0, 0),
            ("找上一個", self.find_prev, 0, 1),
            ("全部計數", self.count_all, 0, 2),
            ("取代", self.replace_one, 1, 0),
            ("全部取代", self.replace_all, 1, 1),
            ("關閉", self.close, 1, 2),
        ]
        for text, slot, r, c in defs:
            b = QPushButton(text)
            b.clicked.connect(slot)
            buttons.addWidget(b, r, c)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(opts)
        layout.addLayout(buttons)
        layout.addWidget(self.status)
        self.find_edit.returnPressed.connect(self.find_next)

    # -- 搜尋核心 --------------------------------------------------------
    def _flags(self, backward=False):
        flags = QTextDocument.FindFlag(0)
        if self.cb_case.isChecked():
            flags |= QTextDocument.FindFlag.FindCaseSensitively
        if self.cb_word.isChecked():
            flags |= QTextDocument.FindFlag.FindWholeWords
        if backward:
            flags |= QTextDocument.FindFlag.FindBackward
        return flags

    def _needle(self):
        text = self.find_edit.text()
        if not text:
            return None
        if self.cb_regex.isChecked():
            rx = QRegularExpression(text)
            if not self.cb_case.isChecked():
                rx.setPatternOptions(
                    QRegularExpression.PatternOption.CaseInsensitiveOption
                )
            if not rx.isValid():
                self.status.setText(f"正規表示式錯誤：{rx.errorString()}")
                return None
            return rx
        return text

    def _search(self, backward=False) -> bool:
        editor = self._get_editor()
        if editor is None:
            return False
        editor.exit_block_mode()
        needle = self._needle()
        if needle is None:
            return False
        doc = editor.document()
        cursor = doc.find(needle, editor.textCursor(), self._flags(backward))
        if cursor.isNull() and self.cb_wrap.isChecked():
            start = QTextCursor(doc)
            if backward:
                start.movePosition(QTextCursor.MoveOperation.End)
            cursor = doc.find(needle, start, self._flags(backward))
        if cursor.isNull():
            self.status.setText("找不到")
            return False
        editor.setTextCursor(cursor)
        editor.ensureCursorVisible()
        self.status.setText("")
        return True

    def find_next(self):
        self._search(False)

    def find_prev(self):
        self._search(True)

    def count_all(self):
        editor = self._get_editor()
        needle = self._needle()
        if editor is None or needle is None:
            return
        doc = editor.document()
        cursor = QTextCursor(doc)
        n = 0
        while True:
            cursor = doc.find(needle, cursor, self._flags())
            if cursor.isNull():
                break
            n += 1
        self.status.setText(f"共找到 {n} 處")

    def replace_one(self):
        editor = self._get_editor()
        if editor is None:
            return
        cursor = editor.textCursor()
        if cursor.hasSelection():
            cursor.insertText(self.replace_edit.text())
        self.find_next()

    def replace_all(self):
        editor = self._get_editor()
        needle = self._needle()
        if editor is None or needle is None:
            return
        editor.exit_block_mode()
        doc = editor.document()
        cursor = QTextCursor(doc)
        cursor.beginEditBlock()
        n = 0
        find_from = QTextCursor(doc)
        while True:
            found = doc.find(needle, find_from, self._flags())
            if found.isNull():
                break
            found.insertText(self.replace_edit.text())
            find_from = found
            n += 1
        cursor.endEditBlock()
        self.status.setText(f"已取代 {n} 處")


class ColumnEditorDialog(QDialog):
    """對應 Notepad++ 的 Column Editor：在矩形每一行插入文字或遞增數列。"""

    def __init__(self, parent, editor):
        super().__init__(parent)
        self.setWindowTitle("欄位編輯器")
        self._editor = editor

        self.rb_text = QRadioButton("插入文字")
        self.rb_num = QRadioButton("插入遞增數列")
        self.rb_text.setChecked(True)
        self.text_edit = QLineEdit()

        self.initial = QSpinBox()
        self.initial.setRange(-1_000_000, 1_000_000)
        self.initial.setValue(1)
        self.increase = QSpinBox()
        self.increase.setRange(-1_000_000, 1_000_000)
        self.increase.setValue(1)
        self.repeat = QSpinBox()
        self.repeat.setRange(1, 10_000)
        self.repeat.setValue(1)
        self.base = QComboBox()
        self.base.addItems(["十進位", "十六進位", "八進位", "二進位"])
        self.cb_zeros = QCheckBox("補前導零")

        text_box = QGroupBox()
        tl = QFormLayout(text_box)
        tl.addRow(self.rb_text)
        tl.addRow("文字：", self.text_edit)

        num_box = QGroupBox()
        nl = QFormLayout(num_box)
        nl.addRow(self.rb_num)
        nl.addRow("起始值：", self.initial)
        nl.addRow("增量：", self.increase)
        nl.addRow("每個重複：", self.repeat)
        nl.addRow("進位：", self.base)
        nl.addRow(self.cb_zeros)

        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        hint = QLabel("先用欄模式選取一個矩形範圍，再開啟這個對話框。")
        hint.setStyleSheet("color:#666;")
        layout.addWidget(hint)
        layout.addWidget(text_box)
        layout.addWidget(num_box)
        layout.addWidget(bb)

    def accept(self):
        editor = self._editor
        if not editor.block_mode:
            QMessageBox.information(self, "欄位編輯器", "請先用欄模式選取範圍。")
            return
        if self.rb_text.isChecked():
            editor.column_insert_text(self.text_edit.text())
        else:
            base = {0: 10, 1: 16, 2: 8, 3: 2}[self.base.currentIndex()]
            editor.column_insert_numbers(
                self.initial.value(),
                self.increase.value(),
                self.repeat.value(),
                base,
                self.cb_zeros.isChecked(),
            )
        super().accept()


class GoToDialog(QDialog):
    def __init__(self, parent, editor):
        super().__init__(parent)
        self.setWindowTitle("跳至行號")
        self._editor = editor
        self.spin = QSpinBox()
        self.spin.setRange(1, max(1, editor.blockCount()))
        self.spin.setValue(editor.textCursor().blockNumber() + 1)
        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        layout = QFormLayout(self)
        layout.addRow(f"行號 (1 - {editor.blockCount()})：", self.spin)
        layout.addRow(bb)

    def accept(self):
        editor = self._editor
        editor.exit_block_mode()
        cur = editor.textCursor()
        blk = editor.document().findBlockByNumber(self.spin.value() - 1)
        cur.setPosition(blk.position())
        editor.setTextCursor(cur)
        editor.ensureCursorVisible()
        super().accept()
