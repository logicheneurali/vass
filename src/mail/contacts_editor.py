"""Contacts editor — manage private_mail_contacts.json."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLineEdit, QLabel, QMessageBox, QInputDialog,
)
from PySide6.QtGui import QFont
from theme import BASE_STYLESHEET, BTN_DEL_BG, BTN_DEL_FG


class ContactsDialog(QDialog):
    def __init__(self, parent=None, lang="it"):
        super().__init__(parent)
        self.lang = lang
        self.setWindowTitle(self._t("contacts_editor.title"))
        self.setMinimumSize(450, 350)
        self.setStyleSheet(BASE_STYLESHEET)

        layout = QVBoxLayout(self)

        self._list = QListWidget()
        layout.addWidget(self._list)

        btn_row = QHBoxLayout()
        add_btn = QPushButton(self._t("contacts_editor.add"))
        add_btn.clicked.connect(self._add)
        btn_row.addWidget(add_btn)

        del_btn = QPushButton(self._t("contacts_editor.remove"))
        del_btn.setStyleSheet(
            f"QPushButton {{ background-color: {BTN_DEL_BG}; color: {BTN_DEL_FG}; border: none; border-radius: 3px; padding: 6px 12px; font-weight: bold; }}"
            f"QPushButton:hover {{ background-color: #7e2424; }}")
        del_btn.clicked.connect(self._delete)
        btn_row.addWidget(del_btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._refresh()

    def _t(self, path):
        from i18n import t
        return t(path, self.lang)

    def _refresh(self):
        from mail.contacts import get_all
        self._list.clear()
        for c in get_all():
            text = f"{c['display_name']} <{c['email']}>" if c['display_name'] != c['email'] else c['email']
            self._list.addItem(text)

    def _add(self):
        dlg = QDialog(self)
        dlg.setWindowTitle(self._t("contacts_editor.add_title"))
        dlg.setMinimumWidth(350)
        dlg.setStyleSheet(BASE_STYLESHEET)
        lo = QVBoxLayout(dlg)

        lo.addWidget(QLabel(self._t("contacts_editor.email")))
        email_edit = QLineEdit()
        email_edit.setPlaceholderText(self._t("contacts_editor.email_placeholder"))
        lo.addWidget(email_edit)

        lo.addWidget(QLabel(self._t("contacts_editor.display_name")))
        name_edit = QLineEdit()
        name_edit.setPlaceholderText(self._t("contacts_editor.name_placeholder"))
        lo.addWidget(name_edit)

        btn_row = QHBoxLayout()
        save_btn = QPushButton(self._t("contacts_editor.save"))
        save_btn.clicked.connect(lambda: self._do_add(
            email_edit.text().strip(), name_edit.text().strip(), dlg))
        btn_row.addWidget(save_btn)
        cancel_btn = QPushButton(self._t("contacts_editor.cancel"))
        cancel_btn.clicked.connect(dlg.reject)
        btn_row.addWidget(cancel_btn)
        lo.addLayout(btn_row)
        dlg.exec()

    def _do_add(self, email, name, dlg):
        if not email:
            return
        from mail.contacts import add
        add(email, name)
        dlg.accept()
        self._refresh()

    def _delete(self):
        row = self._list.currentRow()
        if row < 0:
            return
        text = self._list.currentItem().text()
        reply = QMessageBox.question(self, self._t("contacts_editor.remove"),
            self._t("contacts_editor.remove_confirm").replace("{name}", text),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            # Remove by rebuilding the contacts list minus this one
            from mail.contacts import get_all
            allc = get_all()
            if row < len(allc):
                to_remove = allc[row]
                # Rebuild contacts file without this one
                import json, os
                from utils import get_project_root, encrypt_fields
                path = os.path.join(get_project_root(), "Allowed_root", "private_mail_contacts.json")
                remaining = [c for c in allc if c['email'] != to_remove['email']]
                data = {"version": 1, "contacts": []}
                for c in remaining:
                    encrypted = encrypt_fields(
                        {"email": c['email'], "display_name": c.get('display_name', c['email'])},
                        keep_plain=set())
                    data["contacts"].append(encrypted)
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            self._refresh()
