import configparser
import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QListWidget, QGroupBox, QListWidgetItem,
    QLineEdit, QMessageBox, QComboBox, QSpinBox, QCheckBox,
)
from theme import (BG, FG, ENTRY_BG, ENTRY_FG, LABEL_FG, BTN_BG, BTN_FG,
                   SECTION_FG, FRAME_BORDER, BTN_DEL_BG, BTN_DEL_FG, DESCRIPTION_FG, BASE_STYLESHEET)

STYLESHEET = BASE_STYLESHEET

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE, "config", "mail.ini")


def _load():
    cfg = configparser.ConfigParser()
    if os.path.exists(CONFIG_PATH):
        cfg.read(CONFIG_PATH, encoding="utf-8")
    return cfg


def _save(cfg):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        cfg.write(f)


class MailEditor(QMainWindow):
    def __init__(self, language="en"):
        super().__init__()
        self.lang = language
        self._selected_account = None
        self._build_ui()
        self._refresh_list()

    def _t(self, path):
        from i18n import t
        return t(path, self.lang)

    def _build_ui(self):
        self.setWindowTitle("VASS - Account di posta")
        self.setStyleSheet(STYLESHEET)
        self.setMinimumSize(720, 420)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # ── Left: account list ──
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.account_list = QListWidget()
        self.account_list.currentItemChanged.connect(self._on_select)
        left_layout.addWidget(self.account_list)

        self._add_btn = QPushButton(self._t("mail_editor.add"))
        self._add_btn.clicked.connect(self._add_account)
        left_layout.addWidget(self._add_btn)

        main_layout.addWidget(left_panel, 1)

        # ── Right: form ──
        form_group = QGroupBox(self._t("mail_editor.details"))
        form_layout = QVBoxLayout(form_group)

        # Type
        type_row = QHBoxLayout()
        type_row.addWidget(QLabel(self._t("mail_editor.type")))
        self._type_cb = QComboBox()
        self._type_cb.addItems(["gmail", "imap", "pop"])
        self._type_cb.currentTextChanged.connect(self._on_type_changed)
        type_row.addWidget(self._type_cb)
        type_row.addStretch()
        form_layout.addLayout(type_row)

        # Email
        email_row = QHBoxLayout()
        email_row.addWidget(QLabel(self._t("mail_editor.email")))
        self._email_edit = QLineEdit()
        self._email_edit.setPlaceholderText("user@gmail.com")
        email_row.addWidget(self._email_edit)
        form_layout.addLayout(email_row)

        # IMAP/POP fields
        self._imap_fields = QWidget()
        imap_layout = QVBoxLayout(self._imap_fields)
        imap_layout.setContentsMargins(0, 0, 0, 0)

        user_row = QHBoxLayout()
        user_row.addWidget(QLabel(self._t("mail_editor.username")))
        self._user_edit = QLineEdit()
        self._user_edit.setPlaceholderText("nome.cognome")
        user_row.addWidget(self._user_edit)
        imap_layout.addLayout(user_row)

        pass_row = QHBoxLayout()
        pass_row.addWidget(QLabel(self._t("mail_editor.password")))
        self._pass_edit = QLineEdit()
        self._pass_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._pass_edit.setPlaceholderText("••••••••")
        pass_row.addWidget(self._pass_edit)
        imap_layout.addLayout(pass_row)

        host_row = QHBoxLayout()
        host_row.addWidget(QLabel(self._t("mail_editor.host")))
        self._host_edit = QLineEdit()
        self._host_edit.setPlaceholderText("imap.gmail.com")
        host_row.addWidget(self._host_edit)
        imap_layout.addLayout(host_row)

        port_row = QHBoxLayout()
        port_row.addWidget(QLabel(self._t("mail_editor.port")))
        self._port_spin = QSpinBox()
        self._port_spin.setRange(1, 65535)
        self._port_spin.setValue(993)
        port_row.addWidget(self._port_spin)
        port_row.addStretch()
        imap_layout.addLayout(port_row)

        ssl_row = QHBoxLayout()
        ssl_row.addWidget(QLabel(self._t("mail_editor.ssl")))
        self._ssl_cmb = QComboBox()
        self._ssl_cmb.addItems(["SSL/TLS", "STARTTLS", "Nessuna"])
        ssl_row.addWidget(self._ssl_cmb)
        ssl_row.addStretch()
        imap_layout.addLayout(ssl_row)

        auth_row = QHBoxLayout()
        auth_row.addWidget(QLabel(self._t("mail_editor.auth")))
        self._auth_cmb = QComboBox()
        self._auth_cmb.addItems(["LOGIN (default)", "PLAIN", "CRAM-MD5"])
        auth_row.addWidget(self._auth_cmb)
        auth_row.addStretch()
        imap_layout.addLayout(auth_row)

        form_layout.addWidget(self._imap_fields)

        # Sync settings
        sync_row = QHBoxLayout()
        sync_row.addWidget(QLabel(self._t("mail_editor.sync_minutes")))
        self._sync_spin = QSpinBox()
        self._sync_spin.setRange(1, 1440)
        self._sync_spin.setValue(5)
        sync_row.addWidget(self._sync_spin)
        sync_row.addStretch()
        form_layout.addLayout(sync_row)

        results_row = QHBoxLayout()
        results_row.addWidget(QLabel(self._t("mail_editor.max_results")))
        self._results_spin = QSpinBox()
        self._results_spin.setRange(1, 100)
        self._results_spin.setValue(10)
        results_row.addWidget(self._results_spin)
        results_row.addStretch()
        form_layout.addLayout(results_row)

        # Status
        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet(f"color: {DESCRIPTION_FG}; font-size: 11px;")
        form_layout.addWidget(self._status_lbl)

        # Buttons
        btn_row = QHBoxLayout()
        self._save_btn = QPushButton(self._t("mail_editor.save"))
        self._save_btn.clicked.connect(self._save_account)
        btn_row.addWidget(self._save_btn)

        self._delete_btn = QPushButton(self._t("mail_editor.delete"))
        self._delete_btn.setStyleSheet(
            f"QPushButton {{ background-color: {BTN_DEL_BG}; color: {BTN_DEL_FG}; "
            f"border-radius: 3px; padding: 6px 16px; }}"
            f"QPushButton:hover {{ background-color: #c0392b; }}")
        self._delete_btn.clicked.connect(self._delete_account)
        btn_row.addWidget(self._delete_btn)

        self._toggle_btn = QPushButton("")
        self._toggle_btn.clicked.connect(self._toggle_account)
        self._toggle_btn.setVisible(False)
        btn_row.addWidget(self._toggle_btn)
        btn_row.addStretch()
        form_layout.addLayout(btn_row)

        form_layout.addStretch()
        main_layout.addWidget(form_group, 2)

        self._on_type_changed("gmail")

    def _on_type_changed(self, stype):
        is_imap = stype in ("imap", "pop")
        self._imap_fields.setVisible(is_imap)
        if stype == "pop":
            self._port_spin.setValue(995)
        else:
            self._port_spin.setValue(993)

    def _refresh_list(self):
        self.account_list.blockSignals(True)
        self.account_list.clear()
        cfg = _load()
        active = set()
        try:
            active = {a.strip() for a in cfg.get("sources", "active", fallback="").split(",") if a.strip()}
        except Exception:
            pass

        for section in cfg.sections():
            if section == "sources":
                continue
            stype = cfg.get(section, "type", fallback="?")
            is_active = section in active
            label = f"{'[A] ' if is_active else '[ ] '}{section} ({stype})"
            item = QListWidgetItem(label, self.account_list)
            item.setData(Qt.ItemDataRole.UserRole, section)
            if self._selected_account == section:
                self.account_list.setCurrentItem(item)
        self.account_list.blockSignals(False)

    def _on_select(self, current, previous):
        if not current:
            self._selected_account = None
            self._clear_form()
            self._toggle_btn.setVisible(False)
            return
        self._selected_account = current.data(Qt.ItemDataRole.UserRole)
        self._load_account(self._selected_account)
        self._update_toggle_btn()

    def _update_toggle_btn(self):
        if not self._selected_account:
            self._toggle_btn.setVisible(False)
            return
        cfg = _load()
        active_str = cfg.get("sources", "active", fallback="")
        active = {a.strip() for a in active_str.split(",") if a.strip()}
        if self._selected_account in active:
            self._toggle_btn.setText(self._t("mail_editor.disable"))
        else:
            self._toggle_btn.setText(self._t("mail_editor.enable"))
        self._toggle_btn.setVisible(True)

    def _clear_form(self):
        self._type_cb.setCurrentIndex(0)
        self._email_edit.clear()
        self._user_edit.clear()
        self._pass_edit.clear()
        self._host_edit.clear()
        self._port_spin.setValue(993)
        self._ssl_cmb.setCurrentIndex(0)
        self._auth_cmb.setCurrentIndex(0)
        self._sync_spin.setValue(5)
        self._results_spin.setValue(10)
        self._status_lbl.setText("")

    def _load_account(self, account):
        cfg = _load()
        if not cfg.has_section(account):
            return
        stype = cfg.get(account, "type", fallback="gmail")
        self._type_cb.setCurrentText(stype)
        self._email_edit.setText(account)
        self._user_edit.setText(cfg.get(account, "username", fallback=account))
        self._host_edit.setText(cfg.get(account, "host", fallback=""))
        self._port_spin.setValue(cfg.getint(account, "port", fallback=993))
        ssl_map = {"ssl": 0, "starttls": 1, "none": 2}
        self._ssl_cmb.setCurrentIndex(ssl_map.get(cfg.get(account, "ssl", fallback="ssl"), 0))
        auth_map = {"login": 0, "plain": 1, "cram-md5": 2}
        self._auth_cmb.setCurrentIndex(auth_map.get(cfg.get(account, "auth", fallback="login"), 0))
        self._sync_spin.setValue(cfg.getint(account, "sync_minutes", fallback=5))
        self._results_spin.setValue(cfg.getint(account, "max_results", fallback=10))
        if stype in ("imap", "pop"):
            try:
                import keyring
                pw = keyring.get_password("vass", f"imap_pass_{account}")
                self._pass_edit.setText(pw or "")
            except Exception:
                self._pass_edit.setText("")
        self._update_status(account)

    def _update_status(self, account):
        msg = self._t("mail_editor.status_unknown")
        try:
            from mail.store import load
            data = load()
            msgs = [m for m in data.get("messages", []) if m.get("account") == account]
            last = msgs[0]["date"] if msgs else None
            if last:
                msg = self._t("mail_editor.status_last").replace("{time}", last[:16])
            else:
                import keyring
                token = keyring.get_password("vass", "google_token")
                msg = self._t("mail_editor.status_auth") if token else self._t("mail_editor.status_noauth")
        except Exception:
            pass
        self._status_lbl.setText(msg)

    def _add_account(self):
        self._selected_account = None
        self.account_list.clearSelection()
        self._clear_form()
        self._email_edit.setFocus()

    def _save_account(self):
        account = self._email_edit.text().strip()
        if not account:
            return
        stype = self._type_cb.currentText()
        cfg = _load()

        was_new = not cfg.has_section(account)
        if was_new:
            if "sources" not in cfg:
                cfg["sources"] = {"active": account}
            else:
                active_str = cfg.get("sources", "active", fallback="")
                existing = {a.strip() for a in active_str.split(",") if a.strip()}
                existing.add(account)
                cfg["sources"]["active"] = ", ".join(sorted(existing))

        if cfg.has_section(self._selected_account or "") and self._selected_account != account:
            cfg.remove_section(self._selected_account)
            remove_from = self._selected_account
        else:
            remove_from = None

        cfg[account] = {
            "type": stype,
            "sync_minutes": str(self._sync_spin.value()),
            "max_results": str(self._results_spin.value()),
        }
        if stype in ("imap", "pop"):
            cfg[account]["username"] = self._user_edit.text().strip() or account
            cfg[account]["host"] = self._host_edit.text().strip()
            cfg[account]["port"] = str(self._port_spin.value())
            ssl_mode = ["ssl", "starttls", "none"][self._ssl_cmb.currentIndex()]
            cfg[account]["ssl"] = ssl_mode
            auth_mode = ["login", "plain", "cram-md5"][self._auth_cmb.currentIndex()]
            cfg[account]["auth"] = auth_mode
            pw = self._pass_edit.text()
            if pw:
                try:
                    import keyring
                    keyring.set_password("vass", f"imap_pass_{account}", pw)
                except Exception as e:
                    print(f"[MailEditor] Keyring error: {e}")

        if remove_from and remove_from != account:
            active_str = cfg.get("sources", "active", fallback="")
            active = [a.strip() for a in active_str.split(",") if a.strip()]
            if remove_from in active:
                active.remove(remove_from)
                cfg["sources"]["active"] = ", ".join(active)

        _save(cfg)
        self._refresh_list()
        self._selected_account = account
        self._update_status(account)

    def _delete_account(self):
        if not self._selected_account:
            return
        account = self._selected_account
        msg = QMessageBox(self)
        msg.setWindowTitle(self._t("mail_editor.delete"))
        msg.setText(self._t("mail_editor.delete_confirm").replace("{account}", account))
        msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if msg.exec() != QMessageBox.StandardButton.Yes:
            return

        cfg = _load()
        if cfg.has_section(account):
            cfg.remove_section(account)
        active_str = cfg.get("sources", "active", fallback="")
        active = [a.strip() for a in active_str.split(",") if a.strip()]
        if account in active:
            active.remove(account)
            cfg["sources"]["active"] = ", ".join(active)
        _save(cfg)
        self._selected_account = None
        self._clear_form()
        self._refresh_list()

    def _toggle_account(self):
        if not self._selected_account:
            return
        account = self._selected_account
        cfg = _load()
        active_str = cfg.get("sources", "active", fallback="")
        active = {a.strip() for a in active_str.split(",") if a.strip()}
        if account in active:
            active.discard(account)
        else:
            active.add(account)
        cfg["sources"]["active"] = ", ".join(sorted(active))
        _save(cfg)
        self._refresh_list()
        self._update_status(account)
        self._selected_account = account
        self._update_toggle_btn()


def main():
    lang = "en"
    for i, a in enumerate(sys.argv[1:]):
        if a == "--lang":
            try:
                lang = sys.argv[i + 2]
            except IndexError:
                pass
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    editor = MailEditor(lang)
    editor.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
