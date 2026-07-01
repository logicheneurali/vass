#!/usr/bin/env python
"""Setup Google OAuth2 credentials for Calendar + Gmail integration.
Usage: python src/setup_google.py              (GUI wizard)
       python src/setup_google.py --cli        (Terminal)
       python src/setup_google.py --export FILE
       python src/setup_google.py --import FILE
       python src/setup_google.py --reset
"""

import sys, os, json, base64, hashlib, getpass, argparse

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CRED_DIR = os.path.join(BASE, "credentials")
CLIENT_SECRET_PATH = os.path.join(CRED_DIR, "google_client_secret.json")
KEYRING_SERVICE = "vass"
KEYRING_CLIENT = "google_client_secret"
KEYRING_TOKEN = "google_token"

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/assistant-sdk-prototype",
]


def _derive_key(password):
    return base64.urlsafe_b64encode(hashlib.sha256(password.encode()).digest())


def _keyring_get(key):
    try:
        import keyring
        return keyring.get_password(KEYRING_SERVICE, key)
    except Exception:
        return None


def _keyring_set(key, value):
    import keyring
    keyring.set_password(KEYRING_SERVICE, key, value)


def _keyring_delete(key):
    import keyring
    try:
        keyring.delete_password(KEYRING_SERVICE, key)
    except Exception:
        pass


def _t(path, lang="en"):
    try:
        sys.path.insert(0, os.path.join(BASE, "src"))
        from i18n import t
        result = t(path, lang)
        if result == path.split(".")[-1]:
            with open("C:/Temp/sg_debug.txt", "a", encoding="utf-8") as f:
                f.write(f"FALLBACK: path={path} lang={lang} result={result}\n")
        return result
    except Exception as e:
        try:
            with open("C:/Temp/sg_debug.txt", "a", encoding="utf-8") as f:
                import traceback
                f.write(f"ERROR: path={path} lang={lang} {e}\n")
                f.write(f"sys.path={sys.path[:3]}\n")
                traceback.print_exc(file=f)
        except Exception:
            pass
        return path.split(".")[-1].replace("_", " ").title()


def _load_client_secret():
    if os.path.exists(CLIENT_SECRET_PATH):
        with open(CLIENT_SECRET_PATH, encoding="utf-8") as f:
            data = json.load(f)
        _keyring_set(KEYRING_CLIENT, json.dumps(data))
        os.remove(CLIENT_SECRET_PATH)
        return data, True
    existing = _keyring_get(KEYRING_CLIENT)
    if existing:
        return json.loads(existing), False
    return None, False


def is_google_configured():
    return bool(_keyring_get(KEYRING_CLIENT)) and bool(_keyring_get(KEYRING_TOKEN))


def _oauth_flow(client_json):
    from google_auth_oauthlib.flow import InstalledAppFlow
    flow = InstalledAppFlow.from_client_config(client_json, SCOPES)
    creds = flow.run_local_server(port=0)
    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes,
        "expiry": creds.expiry.isoformat() if creds.expiry else None,
    }
    _keyring_set(KEYRING_TOKEN, json.dumps(token_data))


# ── CLI ────────────────────────────────────────────────────────────────────────

def do_export(filepath):
    client = _keyring_get(KEYRING_CLIENT)
    token = _keyring_get(KEYRING_TOKEN)
    if not client and not token:
        print("Nessuna credenziale in keyring. Esegui prima il setup.")
        return
    pw = getpass.getpass("Password esportazione: ")
    pw2 = getpass.getpass("Ripeti password: ")
    if pw != pw2 or not pw:
        print("Password non corrispondente o vuota.")
        return
    from cryptography.fernet import Fernet
    f = Fernet(_derive_key(pw))
    data = json.dumps({"client_secret": client or "", "token": token or ""}).encode()
    with open(filepath, "wb") as fp:
        fp.write(f.encrypt(data))
    print(f"Credenziali esportate in {filepath}")


def do_import(filepath):
    if not os.path.exists(filepath):
        print(f"File non trovato: {filepath}")
        return
    pw = getpass.getpass("Password importazione: ")
    from cryptography.fernet import Fernet
    try:
        f = Fernet(_derive_key(pw))
        with open(filepath, "rb") as fp:
            data = json.loads(f.decrypt(fp.read()))
    except Exception:
        print("Password errata o file corrotto.")
        return
    if data.get("client_secret"):
        _keyring_set(KEYRING_CLIENT, data["client_secret"])
    if data.get("token"):
        _keyring_set(KEYRING_TOKEN, data["token"])
    print("Credenziali importate con successo.")


def do_reset():
    _keyring_delete(KEYRING_CLIENT)
    _keyring_delete(KEYRING_TOKEN)
    print("Credenziali Google rimosse dal keyring.")


def do_setup_cli():
    client, deleted = _load_client_secret()
    if not client:
        print(f"File non trovato: {CLIENT_SECRET_PATH}")
        print("1. Vai su https://console.cloud.google.com")
        print("2. Crea/Seleziona un progetto")
        print("3. Abilita Google Calendar API e Gmail API")
        print("4. Crea credenziali OAuth2 (Desktop application)")
        print("5. Scarica il JSON e salvalo come:")
        print(f"   {CLIENT_SECRET_PATH}")
        return
    if deleted:
        print("Trovato google_client_secret.json -> salvato in keyring -> file rimosso.")
    print("Avvio autenticazione Google...")
    _oauth_flow(client)
    print("Setup completato!")


# ── GUI Wizard ─────────────────────────────────────────────────────────────────

def do_setup_gui(lang="en"):
    from PySide6.QtWidgets import (QApplication, QWizard, QWizardPage, QLabel,
                                   QVBoxLayout, QPushButton, QFileDialog, QProgressBar,
                                   QCheckBox, QTextBrowser, QLineEdit)
    from PySide6.QtCore import Qt

    was_running = QApplication.instance() is not None
    app = QApplication.instance() or QApplication(sys.argv)

    wizard = QWizard()
    wizard.setWindowTitle(_t("setup_google.title", lang))
    wizard.resize(620, 480)
    wizard.setStyleSheet(
        "QWidget { background-color: #1a1a2e; color: #e0e0e0; font-family: 'Segoe UI', sans-serif; font-size: 14px; }"
        "QLabel { background: transparent; }"
        "QLineEdit { background-color: #16213e; border: 1px solid #0f3460; border-radius: 4px; padding: 6px 10px; }"
        "QPushButton { background-color: #0f3460; color: #e0e0e0; border: none; border-radius: 4px; padding: 8px 20px; font-size: 13px; }"
        "QPushButton:hover { background-color: #1a5276; }"
        "QPushButton:pressed { background-color: #16213e; }"
        "QPushButton:disabled { background-color: #333344; color: #777788; }"
        "QProgressBar { border: 1px solid #0f3460; border-radius: 4px; text-align: center; background-color: #16213e; }"
        "QProgressBar::chunk { background-color: #e94560; border-radius: 3px; }"
        "QCheckBox { spacing: 8px; }"
        "QCheckBox::indicator { width: 18px; height: 18px; border: 1px solid #0f3460; border-radius: 3px; background-color: #16213e; }"
        "QCheckBox::indicator:checked { background-color: #e94560; }"
        "QTextBrowser { background-color: #0d1117; border: 1px solid #0f3460; border-radius: 4px; }"
        "QWizard QLabel#pageTitle { font-size: 16px; font-weight: bold; color: #e94560; }"
    )

    result_data = {"success": False, "message": ""}

    # Page 1: Welcome
    page1 = QWizardPage()
    page1.setTitle(_t("setup_google.page1.title", lang))
    l1 = QVBoxLayout(page1)
    text = _t("setup_google.page1.text", lang).format(path=CLIENT_SECRET_PATH)
    text = text.replace("https://console.cloud.google.com",
                        '<a href="https://console.cloud.google.com" style="color:#e94560;">https://console.cloud.google.com</a>')
    text = text.replace("https://console.cloud.google.com/apis/credentials/consent",
                        '<a href="https://console.cloud.google.com/apis/credentials/consent" style="color:#e94560;">OAuth consent screen</a>')
    text = text.replace("https://console.cloud.google.com/apis/credentials",
                        '<a href="https://console.cloud.google.com/apis/credentials" style="color:#e94560;">Credentials</a>')
    lbl = QTextBrowser()
    lbl.setOpenExternalLinks(True)
    lbl.setHtml(f'<body style="background-color:#0d1117;color:#e0e0e0;font-size:14px;">{text.replace(chr(10), "<br>")}</body>')
    lbl.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    lbl.setMinimumHeight(350)
    l1.addWidget(lbl)
    l1.addStretch()
    wizard.addPage(page1)

    # Page 2: Select file
    page2 = QWizardPage()
    page2.setTitle(_t("setup_google.page2.title", lang))
    l2 = QVBoxLayout(page2)
    page2.lbl_status = QLabel(_t("setup_google.page2.status", lang))
    page2.lbl_status.setWordWrap(True)
    l2.addWidget(page2.lbl_status)

    def _select_file():
        path, _ = QFileDialog.getOpenFileName(wizard, _t("setup_google.select_json", lang), CRED_DIR, "JSON (*.json)")
        if path:
            try:
                with open(path, encoding="utf-8") as f:
                    json.load(f)
                import shutil
                os.makedirs(CRED_DIR, exist_ok=True)
                shutil.copy(path, CLIENT_SECRET_PATH)
                page2.lbl_status.setText(_t("setup_google.page2.ok", lang).format(path=path))
                wizard.button(QWizard.WizardButton.NextButton).setEnabled(True)
            except Exception as e:
                page2.lbl_status.setText(_t("setup_google.page2.error", lang) + f"\n{e}")

    btn = QPushButton(_t("setup_google.select_json", lang))
    btn.clicked.connect(_select_file)
    l2.addWidget(btn)
    l2.addStretch()

    client, _ = _load_client_secret()
    if client:
        page2.lbl_status.setText(_t("setup_google.page2.already_configured", lang))
        wizard.button(QWizard.WizardButton.NextButton).setEnabled(True)
    else:
        wizard.button(QWizard.WizardButton.NextButton).setEnabled(False)

    wizard.addPage(page2)

    # Page 3: Authorize
    page3 = QWizardPage()
    page3.setTitle(_t("setup_google.page3.title", lang))
    l3 = QVBoxLayout(page3)
    page3.lbl_status = QLabel(_t("setup_google.page3.status", lang))
    page3.lbl_status.setWordWrap(True)
    l3.addWidget(page3.lbl_status)
    page3.progress = QProgressBar()
    page3.progress.setRange(0, 0)
    page3.progress.setVisible(False)
    l3.addWidget(page3.progress)

    def _authorize():
        page3.lbl_status.setText(_t("setup_google.page3.authorizing", lang))
        page3.progress.setVisible(True)
        btn_auth.setEnabled(False)
        wizard.repaint()
        import threading
        thread_result = {"success": False, "message": ""}

        def _run():
            try:
                client, _ = _load_client_secret()
                if not client:
                    raise Exception(_t("setup_google.page3.no_client", lang))
                _oauth_flow(client)
                thread_result["success"] = True
                thread_result["message"] = _t("setup_google.page4.ok", lang)
            except Exception as e:
                thread_result["success"] = False
                thread_result["message"] = _t("setup_google.page3.error", lang) + f"\n{e}"

        t = threading.Thread(target=_run, daemon=True)
        t.start()

        from PySide6.QtCore import QTimer
        def _poll():
            if t.is_alive():
                QTimer.singleShot(200, _poll)
                return
            result_data["success"] = thread_result["success"]
            result_data["message"] = thread_result["message"]
            page3.progress.setVisible(False)
            btn_auth.setEnabled(True)
            wizard.next()
        QTimer.singleShot(200, _poll)

    btn_auth = QPushButton(_t("setup_google.page3.authorize", lang))
    btn_auth.clicked.connect(_authorize)
    l3.addWidget(btn_auth)
    l3.addStretch()
    wizard.addPage(page3)

    # Page 4: Result
    page4 = QWizardPage()
    page4.setTitle(_t("setup_google.page4.title", lang))
    l4 = QVBoxLayout(page4)
    page4.lbl_result = QLabel("")
    page4.lbl_result.setWordWrap(True)
    l4.addWidget(page4.lbl_result)
    l4.addStretch()
    wizard.addPage(page4)

    # Page 5: Google Home (optional, skippable)
    page5 = QWizardPage()
    page5.setTitle(_t("setup_google.page5.title", lang))
    l5 = QVBoxLayout(page5)

    try:
        client, _ = _load_client_secret()
        project_id = client.get("installed", {}).get("project_id", "???") if client else "???"
    except Exception:
        project_id = "???"

    info = _t("setup_google.page5.info", lang).replace("{project_id}", project_id)
    lbl_info = QTextBrowser()
    lbl_info.setOpenExternalLinks(True)
    lbl_info.setHtml(f'<body style="background-color:#0d1117;color:#e0e0e0;font-size:14px;">{info.replace(chr(10), "<br>")}</body>')
    lbl_info.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    lbl_info.setMinimumHeight(250)
    l5.addWidget(lbl_info)

    lbl_model = QLabel(_t("setup_google.page5.model_id", lang))
    l5.addWidget(lbl_model)
    page5.input_model = QLineEdit()
    page5.input_model.setPlaceholderText("vass-desktop")
    l5.addWidget(page5.input_model)

    lbl_device = QLabel(_t("setup_google.page5.device_id", lang))
    l5.addWidget(lbl_device)
    page5.input_device = QLineEdit()
    page5.input_device.setPlaceholderText("vass-desktop-01")
    l5.addWidget(page5.input_device)

    page5.skip_cb = QCheckBox(_t("setup_google.page5.skip", lang))
    l5.addWidget(page5.skip_cb)

    l5.addStretch()
    wizard.addPage(page5)

    def _on_finish():
        model_id = page5.input_model.text().strip()
        device_id = page5.input_device.text().strip()
        if not page5.skip_cb.isChecked() and (model_id or device_id):
            try:
                settings_path = os.path.join(BASE, "config", "settings.ini")
                if os.path.exists(settings_path):
                    import configparser
                    cfg = configparser.ConfigParser()
                    cfg.read(settings_path, encoding="utf-8")
                    if "google" not in cfg:
                        cfg.add_section("google")
                    cfg.set("google", "google_home_model_id", model_id)
                    cfg.set("google", "google_home_device_id", device_id)
                    with open(settings_path, "w", encoding="utf-8") as f:
                        cfg.write(f)
                    print("[Setup] Google Home model/device saved to settings.ini")
            except Exception as e:
                print(f"[Setup] Failed to save Google Home config: {e}")

    wizard.finished.connect(_on_finish)

    def _show_result():
        color = "#27ae60" if result_data["success"] else "#e94560"
        page4.lbl_result.setStyleSheet(f"color: {color}; font-size: 13px;")
        page4.lbl_result.setText(result_data["message"])

    wizard.currentIdChanged.connect(lambda _id: _show_result() if _id == 3 else None)

    wizard.show()
    if not was_running:
        app.exec()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Setup credenziali Google")
    parser.add_argument("--cli", action="store_true", help="Usa terminale invece della GUI")
    parser.add_argument("--export", metavar="FILE", help="Esporta credenziali in un file criptato")
    parser.add_argument("--import", metavar="FILE", dest="import_file", help="Importa credenziali da un file criptato")
    parser.add_argument("--reset", action="store_true", help="Rimuovi credenziali dal keyring")
    parser.add_argument("--lang", default="it", help="Lingua (default: it)")
    args = parser.parse_args()

    if args.export:
        do_export(args.export)
    elif args.import_file:
        do_import(args.import_file)
    elif args.reset:
        do_reset()
    elif args.cli:
        do_setup_cli()
    else:
        do_setup_gui(lang=args.lang)
