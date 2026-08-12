"""Email queue viewer dialog."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QSplitter,
    QPushButton, QListWidget, QListWidgetItem, QTextEdit,
    QMessageBox, QWidget, QComboBox, QLabel,
)


class QueueViewerDialog(QDialog):
    def __init__(self, language="it", select_id=None):
        super().__init__()
        self.lang = language
        self._select_id = select_id
        self._current_item = None
        self._build_ui()
        self._refresh()

    def _t(self, path):
        from i18n import t
        return t(path, self.lang)

    def _build_ui(self):
        self.setWindowTitle(self._t("queue_viewer.title"))
        self.setMinimumSize(720, 420)

        layout = QVBoxLayout(self)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        self._list = QListWidget()
        self._list.currentItemChanged.connect(self._on_select)
        splitter.addWidget(self._list)

        right = QVBoxLayout()
        self._preview = QTextEdit()
        self._preview.setReadOnly(True)
        self._preview.setStyleSheet("QTextEdit { background: #1e1e1e; color: #e0e0e0; border: 1px solid #333; }")
        right.addWidget(self._preview)

        btn_row = QHBoxLayout()

        edit_btn = QPushButton(self._t("queue_viewer.edit"))
        edit_btn.clicked.connect(self._edit)
        btn_row.addWidget(edit_btn)

        send_btn = QPushButton(self._t("queue_viewer.send"))
        send_btn.setStyleSheet(
            "QPushButton { background-color: #27ae60; color: white; border-radius: 3px; padding: 6px 16px; }"
            "QPushButton:hover { background-color: #2ecc71; }")
        send_btn.clicked.connect(self._send)
        btn_row.addWidget(send_btn)

        del_btn = QPushButton(self._t("queue_viewer.delete"))
        del_btn.setStyleSheet(
            "QPushButton { background-color: #e74c3c; color: white; border-radius: 3px; padding: 6px 16px; }"
            "QPushButton:hover { background-color: #c0392b; }")
        del_btn.clicked.connect(self._delete)
        btn_row.addWidget(del_btn)

        btn_row.addStretch()

        send_all_btn = QPushButton(self._t("queue_viewer.send_all"))
        send_all_btn.clicked.connect(self._send_all)
        btn_row.addWidget(send_all_btn)

        right.addLayout(btn_row)

        right_widget = QWidget()
        right_widget.setLayout(right)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        layout.addWidget(splitter)

    def _refresh(self):
        from mail.queue import get_all
        self._list.blockSignals(True)
        self._list.clear()
        items = get_all()
        for item in items:
            label = f"{item['subject'][:50]} → {item['to'][:40]}"
            list_item = QListWidgetItem(label)
            list_item.setData(Qt.ItemDataRole.UserRole, item["id"])
            self._list.addItem(list_item)
            if self._select_id and item["id"] == self._select_id:
                self._list.setCurrentItem(list_item)
        self._list.blockSignals(False)
        self._send_all_btn = self.findChild(QPushButton, "Invia tutto")
        send_all_text = f"Invia tutto ({len(items)})"
        for btn in self.findChildren(QPushButton):
            if "Invia tutto" in btn.text():
                btn.setText(send_all_text)

    def _on_select(self, current, previous):
        if not current:
            self._current_item = None
            self._preview.clear()
            return
        qid = current.data(Qt.ItemDataRole.UserRole)
        from mail.queue import get
        item = get(qid)
        if not item:
            return
        self._current_item = item
        self._preview.setHtml(
            f"<b>Da:</b> {item['account']}<br>"
            f"<b>A:</b> {item['to'] or 'N/D'}<br>"
            f"<b>Oggetto:</b> {item['subject']}<br>"
            f"<hr>"
            f"<pre style='white-space:pre-wrap;'>{item['body']}</pre>"
        )

    def _edit(self):
        if not self._current_item:
            return
        item = self._current_item
        dlg = QDialog(self)
        dlg.setWindowTitle(self._t("queue_viewer.edit_title"))
        dlg.setMinimumSize(500, 420)
        lo = QVBoxLayout(dlg)

        to_row = QHBoxLayout()
        to_row.addWidget(QLabel(self._t("queue_viewer.to")))
        to_cb = QComboBox()
        to_cb.setEditable(True)
        to_cb.setMinimumWidth(300)
        from mail.contacts import as_strings
        recipients = as_strings()
        for r in recipients:
            to_cb.addItem(r)
        if item["to"]:
            to_cb.setCurrentText(item["to"])
        to_row.addWidget(to_cb, 1)
        lo.addLayout(to_row)

        edit = QTextEdit()
        edit.setPlainText(item["body"])
        lo.addWidget(edit)

        btn_row = QHBoxLayout()
        save_btn = QPushButton(self._t("queue_viewer.save"))
        save_btn.clicked.connect(lambda checked, qid=item["id"], ed=edit, cb=to_cb, d=dlg:
                                  self._do_edit(qid, ed.toPlainText(), cb.currentText(), d))
        btn_row.addWidget(save_btn)
        cancel_btn = QPushButton(self._t("queue_viewer.cancel"))
        cancel_btn.clicked.connect(dlg.reject)
        btn_row.addWidget(cancel_btn)
        lo.addLayout(btn_row)
        dlg.exec()

    def _do_edit(self, qid, body, to, dlg):
        from mail.queue import update
        # Extract bare email from "Name <email>" format
        import re
        match = re.search(r'<([^>]+)>', to)
        email_only = match.group(1).strip() if match else to.strip()
        update(qid, body=body, to=email_only)
        dlg.accept()
        sel = self._list.currentRow()
        self._refresh()
        if sel < self._list.count():
            self._list.setCurrentRow(sel)

    def _send(self):
        if not self._current_item:
            return
        from mail.queue import send
        ok, msg = send(self._current_item["id"])
        if ok:
            self._current_item = None
            self._preview.clear()
            self._refresh()
        else:
            QMessageBox.warning(self, self._t("queue_viewer.error"),
                self._t("queue_viewer.send_failed").replace("{msg}", msg))

    def _delete(self):
        if not self._current_item:
            return
        reply = QMessageBox.question(self, self._t("queue_viewer.delete"),
                                      self._t("queue_viewer.delete_confirm"),
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            from mail.queue import remove
            remove(self._current_item["id"])
            self._current_item = None
            self._preview.clear()
            self._refresh()

    def _send_all(self):
        from mail.queue import get_all
        count = len(get_all())
        if count == 0:
            return
        reply = QMessageBox.question(self, self._t("queue_viewer.send_all"),
            self._t("queue_viewer.send_all_confirm").replace("{count}", str(count)),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            from mail.queue import send_all
            sent = send_all()
            QMessageBox.information(self, self._t("queue_viewer.completed"),
                self._t("queue_viewer.sent_count").replace("{sent}", str(sent)).replace("{count}", str(count)))
            self._refresh()
