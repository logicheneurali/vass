import os
import sys

import configparser
from PySide6.QtCore import Qt, QFileSystemWatcher
from PySide6.QtGui import QKeySequence, QShortcut
from code_editor import CodeEditor
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QListWidget, QLineEdit, QGroupBox,
    QMessageBox, QInputDialog, QMenu,
    QDialog, QCheckBox,
)
from theme import (BG, FG, ENTRY_BG, ENTRY_FG, LABEL_FG, BTN_BG, BTN_FG,
                   SECTION_FG, FRAME_BORDER, BTN_DEL_BG, BTN_DEL_FG, BASE_STYLESHEET)

STYLESHEET = BASE_STYLESHEET

SCRIPT_DIR = os.path.join(get_project_root(), "scripts")

TEMPLATES = {
    "add": 'add($a, $b)',
    "add_event": 'add_event("2026-06-15", "14:30", "60", "Riunione")',
    "add_event ricorsivo": 'add_event("2026-06-15", "08:00", "5", "Pillola", "1d")',
    "ai": 'ai("prompt")',
    "ai_raw": 'ai_raw("prompt")',
    "ai → say": '$risultato = ai("prompt")\nsay($risultato)',
    "clipboard_get": 'clipboard_get()',
    "clipboard_set": 'clipboard_set("testo da copiare")',
    "close": 'close("notepad")',
    "close con timeout": 'close("firefox", 10)',
    "contains": 'contains($testo, "cerca")',
    "delete_event": 'delete_event("riunione")',
    "div": 'div($a, $b)',
    "equals": 'equals($a, $b)',
    "exit": 'exit()',
    "fetch_json": '$dati = fetch_json("https://api.example.com/data")\nsay($dati)',
    "fetch_text": '$contenuto = fetch_text("https://example.com")\nsay($contenuto)',
    "filter_json": '$lista = filter_json($dati, "- {titolo} ({anno})")',
    "filter_json con filtro": '$filtro = filter_json($dati, "{nome}: {email}", "citta=Roma")',
    "filter_json con filtro numerico": '$risultati = filter_json($dati, "{nome}", "eta>=18")',
    "form": 'form("Titolo", "nome: text: Mario", "età: number: 30", "paese: select: Italia,Francia,Spagna", "attivo: checkbox: true", "note: textarea")',
    "gcal_add": 'gcal_add("Riunione", "2026-06-15T14:00:00", "2026-06-15T15:00:00", "Sala A")',
    "gcal_search": '$eventi = gcal_search("dentista")\nsay($eventi)',
    "gcal_today": '$eventi = gcal_today()\nsay($eventi)',
    "gcal_tomorrow": '$eventi = gcal_tomorrow()\nsay($eventi)',
    "get_datetime": 'get_datetime()',
    "get_idle": '$idle = get_idle()\nif_greater($idle.idle_seconds, 600, say("Inattivo da " + trim($idle.idle_seconds) + "s"), say("Attivo"))',
    "get_weather": '$tt = get_weather("Milano")\nsay("A {$tt.city} ci sono {$tt.temperature} gradi, percepiti {$tt.feels_like}")',
    "google_home_ask": '$risposta = google_home_ask("che tempo fa domani?")\nsay($risposta)',
    "google_home_command": 'google_home_command("accendi le luci", false)',
    "if_contains": 'if_contains($variabile, "testo", say("vero"), say("falso"))',
    "if_empty": 'if_empty($variabile, say("vuoto"), say("pieno"))',
    "if_equals": 'if_equals($a, $b, say("uguali"), say("diversi"))',
    "if_greater": 'if_greater($x, 10, say("maggiore"), say("minore"))',
    "if_greater_equal": 'if_greater_equal($x, 100, say("almeno 100"), say("meno di 100"))',
    "if_less": 'if_less($x, 5, say("minore"), say("maggiore"))',
    "if_less_equal": 'if_less_equal($x, 50, say("al massimo 50"), say("sopra 50"))',
    "inject": 'inject("L\'utente preferisce il tema scuro")',
    "inject_memory": 'inject_memory("Informazione importante da ricordare")',
    "launch_app": 'launch_app("firefox")',
    "launch_app con args": 'launch_app("notepad", "C:\\\\file.txt")',
    "len": 'len($testo)',
    "listen": 'listen()',
    "listen → say": '$testo = listen()\nsay($testo)',
    "list_apps": '$apps = list_apps()\nsay("Trovate " + trim(len($apps)) + " app")',
    "list_events": 'list_events("2026-12-31")',
    "list_events → pretty_events": '\n'.join([
        '$e = list_events("2026-12-31")',
        '$p = pretty_events($e)',
        'say($p)',
    ]),
    "mul": 'mul($a, $b)',
    "notify": 'notify("Operazione completata", 5)',
    "pretty_events": 'pretty_events($json_eventi)',
    "read_info": 'read_info("id_file")',
    "read_state": 'read_state("ventilatore")',
    "remove_event": 'remove_event("riunione")',
    "run": 'run("echo hello")',
    "save_tags": 'save_tags("food,health,pets")',
    "say": 'say("testo")',
    "say_async": 'say_async("testo in background")',
    "screen_click": 'screen_click($_sx, $_sy)',
    "screen_click (posizione corrente)": 'screen_click()',
    "screen_highlight": 'screen_highlight($x, $y, $w, $h, 1.0)',
    "screen_search": 'screen_search("testo da cercare")',
    "screen_search → click": (
        '$risultati = screen_search("Cerca")\n'
        'if_empty($risultati, exit(), "")\n'
        'screen_click($_sx, $_sy)'
    ),
    "screen_search → highlight": (
        '$risultati = screen_search("Cerca")\n'
        'if_empty($risultati, exit(), "")\n'
        'screen_highlight($_sx, $_sy, $_sw, $_sh, 1.0)'
    ),
    "screen_search → listen → screen_search": (
        '$richiesta = listen("Cosa vuoi cercare?")\n'
        'say("Cerco $richiesta")\n'
        '$risultati = screen_search($richiesta)\n'
        'if_empty($risultati, say("Non trovato"), screen_highlight($_sx, $_sy, $_sw, $_sh, 3.0))'
    ),
    "search_web": '$risultati = search_web("python tutorial")\nsay($risultati)',
    "send_text": 'send_text("Hello World")',
    "set_active_window": 'set_active_window("notepad")',
    "sub": 'sub($a, $b)',
    "timer_cancel": 'timer_cancel("id_timer")',
    "timer_list": '$lista = timer_list()\nsay($lista)',
    "timer_start": 'timer_start("1h30m")',
    "to_num": 'to_num($x)',
    "trim": 'trim($testo)',
    "wait": 'wait(2)',
    "web → riassunto": (
        '$html = ai("vai su https://esempio.it e riassumi il contenuto")\n'
        'say($html)\n'
        '$riassunto = ai("riassumi in italiano: {html}")\n'
        'say($riassunto)'
    ),
    "write_info": 'write_info("dati da salvare")',
    "write_state": 'write_state("ventilatore", "acceso")',
}


class ScriptsEditor(QMainWindow):
    def __init__(self, language="en"):
        super().__init__()
        self.lang = language
        self._scripts = []
        self._current_file = None
        self._dirty = False
        self._build_ui()
        self._load_allow_ai_setting()
        self._refresh_list()
        self._update_title()

    def _t(self, path):
        from i18n import t
        return t(path, self.lang)

    def _settings_path(self):
        return os.path.join(get_project_root(), "config", "settings.ini")

    def _load_allow_ai_setting(self):
        try:
            import configparser
            cfg = configparser.ConfigParser()
            cfg.read(self._settings_path(), encoding="utf-8")
            val = cfg.get("ai", "allow_ai_scripts", fallback="false").lower() == "true"
            self._allow_ai_cb.setChecked(val)
        except Exception:
            self._allow_ai_cb.setChecked(False)

    def _on_allow_ai_changed(self, state):
        try:
            import configparser
            cfg = configparser.ConfigParser()
            cfg.read(self._settings_path(), encoding="utf-8")
            if "ai" not in cfg:
                cfg.add_section("ai")
            cfg.set("ai", "allow_ai_scripts", "true" if state == Qt.CheckState.Checked.value else "false")
            os.makedirs(os.path.dirname(self._settings_path()), exist_ok=True)
            with open(self._settings_path(), "w", encoding="utf-8") as f:
                cfg.write(f)
        except Exception:
            pass

    def _scripts_dir(self):
        if not os.path.exists(SCRIPT_DIR):
            os.makedirs(SCRIPT_DIR)
        return SCRIPT_DIR

    def _list_scripts(self):
        d = self._scripts_dir()
        return sorted(
            f for f in os.listdir(d)
            if f.endswith(".vass") and os.path.isfile(os.path.join(d, f))
        )

    def _on_dir_changed(self, path):
        old_set = set(self._scripts)
        new_list = self._list_scripts()
        new_set = set(new_list)
        if old_set == new_set:
            return
        self._scripts = new_list
        self.list_widget.blockSignals(True)
        current = self.list_widget.currentItem()
        current_name = current.text() if current else None
        self.list_widget.clear()
        for s in self._scripts:
            self.list_widget.addItem(s)
        if current_name and current_name in self._scripts:
            items = self.list_widget.findItems(current_name, Qt.MatchFlag.MatchExactly)
            if items:
                self.list_widget.setCurrentItem(items[0])
        elif self._scripts:
            self.list_widget.setCurrentRow(0)
        self.list_widget.blockSignals(False)

    def _refresh_list(self):
        self._scripts = self._list_scripts()
        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        for s in self._scripts:
            self.list_widget.addItem(s)
        self.list_widget.blockSignals(False)

    def _update_title(self):
        name = self._current_file or ""
        star = " *" if self._dirty else ""
        self.setWindowTitle(self._t("scripts_editor.title") + f"{star}  —  {name}")
        self.save_btn.setEnabled(self._dirty)

    def _build_ui(self):
        self.resize(1000, 550)
        self.setMinimumSize(900, 450)
        self.setStyleSheet(BASE_STYLESHEET)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        left_group = QGroupBox(self._t("scripts_editor.left_panel"))
        left_group.setFixedWidth(200)
        left_layout = QVBoxLayout(left_group)

        self.list_widget = QListWidget()
        self.list_widget.currentTextChanged.connect(self._on_select)
        left_layout.addWidget(self.list_widget)

        btn_new = QPushButton(self._t("scripts_editor.buttons.new"))
        btn_new.setStyleSheet(f"background-color: {BTN_BG}; color: {BTN_FG};")
        btn_new.clicked.connect(self._new_script)
        left_layout.addWidget(btn_new)

        btn_del = QPushButton(self._t("scripts_editor.buttons.delete"))
        btn_del.setStyleSheet(f"background-color: {BTN_DEL_BG}; color: {BTN_DEL_FG};")
        btn_del.clicked.connect(self._delete_script)
        left_layout.addWidget(btn_del)

        btn_perm = QPushButton(self._t("scripts_editor.buttons.permissions"))
        btn_perm.setStyleSheet(f"background-color: {BTN_BG}; color: {BTN_FG};")
        btn_perm.clicked.connect(self._manage_permissions)
        left_layout.addWidget(btn_perm)

        self._allow_ai_cb = QCheckBox(self._t("scripts_editor.allow_ai_scripts"))
        self._allow_ai_cb.setStyleSheet(f"color: {LABEL_FG};")
        self._allow_ai_cb.stateChanged.connect(self._on_allow_ai_changed)
        left_layout.addWidget(self._allow_ai_cb)

        layout.addWidget(left_group, 1)

        self._watcher = QFileSystemWatcher()
        self._watcher.addPath(self._scripts_dir())
        self._watcher.directoryChanged.connect(self._on_dir_changed)

        right_group = QGroupBox(self._t("scripts_editor.right_panel"))
        right_layout = QVBoxLayout(right_group)

        self.editor = CodeEditor()
        self.editor.textChanged.connect(self._on_text_changed)
        right_layout.addWidget(self.editor)

        ai_row = QHBoxLayout()
        self.ai_input = QLineEdit()
        self.ai_input.setPlaceholderText(self._t("scripts_editor.ask_ai_placeholder"))
        self.ai_input.setStyleSheet(
            "QLineEdit { background: #2d2d2d; color: #e0e0e0; border: 1px solid #3c3c3c; "
            "border-radius: 4px; padding: 4px 8px; }"
        )
        ai_row.addWidget(self.ai_input)
        self.ai_btn = QPushButton(self._t("scripts_editor.ask_ai"))
        self.ai_btn.setStyleSheet(f"background-color: {BTN_BG}; color: {BTN_FG};")
        self.ai_btn.clicked.connect(self._ask_ai)
        self.ai_btn.setFixedWidth(120)
        ai_row.addWidget(self.ai_btn)
        right_layout.addLayout(ai_row)

        btn_row = QHBoxLayout()

        tpl_btn = QPushButton(self._t("scripts_editor.buttons.template"))
        tpl_btn.setStyleSheet(f"background-color: {BTN_BG}; color: {BTN_FG};")
        tpl_menu = QMenu()
        for label, code in TEMPLATES.items():
            action = tpl_menu.addAction(label)
            action.triggered.connect(lambda checked, c=code: self._insert_template(c))
        tpl_btn.clicked.connect(
            lambda: tpl_menu.exec(tpl_btn.mapToGlobal(tpl_btn.rect().bottomLeft()))
        )
        btn_row.addWidget(tpl_btn)

        btn_row.addStretch()

        self.save_btn = QPushButton(self._t("scripts_editor.buttons.save"))
        self.save_btn.setStyleSheet(f"background-color: {BTN_BG}; color: {BTN_FG};")
        self.save_btn.clicked.connect(self._save)
        self.save_btn.setEnabled(False)
        btn_row.addWidget(self.save_btn)

        self.test_btn = QPushButton(self._t("scripts_editor.buttons.test"))
        self.test_btn.setStyleSheet(f"background-color: {BTN_BG}; color: {BTN_FG};")
        self.test_btn.clicked.connect(self._test_script)
        btn_row.addWidget(self.test_btn)

        right_layout.addLayout(btn_row)

        layout.addWidget(right_group, 2)

        help_group = QGroupBox(self._t("scripts_editor.functions_panel"))
        help_group.setFixedWidth(200)
        help_layout = QVBoxLayout(help_group)

        self.func_list = QListWidget()
        func_names = sorted(k for k in TEMPLATES.keys() if "→" not in k)
        self.func_list.addItems(func_names)
        self.func_list.currentTextChanged.connect(self._on_func_select)
        self.func_list.itemDoubleClicked.connect(self._insert_func)
        help_layout.addWidget(self.func_list)

        self.func_help = QLabel(self._t("scripts_editor.select_function"))
        self.func_help.setStyleSheet(f"color: {LABEL_FG}; font-size: 11px;")
        self.func_help.setWordWrap(True)
        self.func_help.setAlignment(Qt.AlignmentFlag.AlignTop)
        help_layout.addWidget(self.func_help)

        layout.addWidget(help_group)

        self._load_func_reference()

        QShortcut(QKeySequence("Ctrl+S"), self, self._save)

    def _load_func_reference(self):
        import re, os
        self._func_ref = {}
        ref_path = os.path.join(get_project_root(), "Allowed_root", "VASCRIPT_REFERENCE.md")
        if not os.path.exists(ref_path):
            return
        with open(ref_path, encoding="utf-8") as f:
            content = f.read()
        # Parse each ### section
        for match in re.finditer(r'### \*\*`([^`]+)`\*\*\n(.*?)(?=\n### |\n## |\Z)', content, re.DOTALL):
            func_sig = match.group(1)
            body = match.group(2).strip()
            func_name = func_sig.split("(")[0].strip()
            self._func_ref[func_name] = func_sig + "\n" + body

    def _insert_template(self, code):
        self.editor.insertPlainText(code + "\n")

    def _on_func_select(self, name):
        if name and hasattr(self, '_func_ref') and name in self._func_ref:
            self.func_help.setText(self._func_ref[name])
        else:
            self.func_help.setText(self._t("scripts_editor.select_function"))

    def _insert_func(self, item):
        name = item.text()
        if name and name in TEMPLATES:
            code = TEMPLATES[name].split("\n")[0]
            self.editor.insertPlainText(code)

    def _ask_ai(self):
        prompt = self.ai_input.text().strip()
        if not prompt:
            return

        from openai import OpenAI
        from utils import get_project_root, call_with_retry

        cfg = configparser.ConfigParser()
        cfg.read(self._settings_path(), encoding="utf-8")
        ai_url = cfg.get("ai", "url", fallback="http://127.0.0.1:8080/v1")
        api_key = cfg.get("ai", "api_key", fallback="")
        ai_model = cfg.get("ai", "model", fallback="Qwen3-8B-Q4_K_M")

        try:
            client = OpenAI(base_url=ai_url, api_key=api_key or "not-needed")
        except Exception as e:
            QMessageBox.critical(self, "AI Error", f"Failed to create AI client:\n{e}")
            return

        ref_path = os.path.join(get_project_root(),
                                 "Allowed_root", "VASCRIPT_REFERENCE.md")
        reference_text = ""
        try:
            with open(ref_path, encoding="utf-8") as f:
                reference_text = f.read()
        except Exception:
            reference_text = "(reference not found)"

        func_lines = []
        for name, code in sorted(TEMPLATES.items()):
            func_lines.append(f"{name} → {code.split(chr(10))[0]}")
        funcs_block = "\n".join(func_lines)

        system_msg = (
            "You are a VASScript code generator. Given a user's request, "
            "write ONLY the VASScript code that accomplishes the task. "
            "Do NOT include explanations, markdown, or surrounding backticks. "
            "Use comments (lines starting with #) sparingly.\n\n"
            "VASScript Reference:\n" + reference_text + "\n\n"
            "Available functions:\n" + funcs_block
        )

        self.ai_btn.setEnabled(False)
        self.ai_btn.setText(self._t("scripts_editor.ask_ai_loading"))
        QApplication.processEvents()

        try:
            resp = call_with_retry(
                lambda: client.chat.completions.create(
                    model=ai_model,
                    messages=[
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.3,
                    max_tokens=2000,
                ),
                log_prefix="[ScriptsEditor AI]"
            )
            code = resp.choices[0].message.content.strip()
        except Exception as e:
            self.ai_btn.setEnabled(True)
            self.ai_btn.setText(self._t("scripts_editor.ask_ai"))
            QMessageBox.critical(self, "AI Error", f"AI request failed:\n{e}")
            return
        finally:
            self.ai_btn.setEnabled(True)
            self.ai_btn.setText(self._t("scripts_editor.ask_ai"))

        if not code:
            QMessageBox.warning(self, "AI", "AI returned an empty response.")
            return

        self.editor.setPlainText(code)
        self.ai_input.clear()

    def _on_text_changed(self):
        self._dirty = True
        self._update_title()

    def _on_select(self, name):
        if self._dirty:
            reply = QMessageBox.question(
                self, "Salvare?", "Salvare le modifiche prima di cambiare script?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
            )
            if reply == QMessageBox.Yes:
                self._save()
            elif reply == QMessageBox.Cancel:
                self.list_widget.blockSignals(True)
                self.list_widget.setCurrentRow(
                    self._scripts.index(self._current_file)
                    if self._current_file in self._scripts else -1
                )
                self.list_widget.blockSignals(False)
                return

        if not name:
            self._current_file = None
            self.editor.blockSignals(True)
            self.editor.setPlainText("")
            self.editor.blockSignals(False)
            self._dirty = False
            self._update_title()
            return

        path = os.path.join(self._scripts_dir(), name)
        try:
            with open(path, encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            QMessageBox.critical(self, "Errore", f"Impossibile leggere {name}:\n{e}")
            return

        self.editor.blockSignals(True)
        self.editor.setPlainText(content)
        self.editor.blockSignals(False)
        self._current_file = name
        self._dirty = False
        self._update_title()

    def _save(self):
        if not self._current_file:
            QMessageBox.information(self, "Info", "Nessun file selezionato.")
            return
        path = os.path.join(self._scripts_dir(), self._current_file)
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.editor.toPlainText())
        except Exception as e:
            QMessageBox.critical(self, "Errore", f"Salvataggio fallito:\n{e}")
            return
        self._dirty = False
        self._update_title()
        script_name = os.path.splitext(self._current_file)[0]
        try:
            import keyring
            keyring.delete_password("vass-auth", script_name)
        except Exception:
            pass

    def _test_script(self):
        code = self.editor.toPlainText().strip()
        if not code:
            QMessageBox.information(self, "Info", "L'editor è vuoto.")
            return
        import json, time, uuid, os
        queue_path = os.path.join(self._scripts_dir(), "exec_queue.json")
        result_path = os.path.join(self._scripts_dir(), "exec_result.json")
        request_id = uuid.uuid4().hex[:12]
        request = {"id": request_id, "code": code, "timeout": 60}
        for rp in [queue_path, result_path]:
            if os.path.exists(rp):
                try:
                    os.remove(rp)
                except OSError:
                    pass
        with open(queue_path, "w", encoding="utf-8") as f:
            json.dump(request, f)
        deadline = time.time() + 60
        result = None
        while time.time() < deadline:
            if os.path.exists(result_path):
                try:
                    with open(result_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if data.get("id") == request_id:
                        result = data.get("result", {})
                        break
                except (json.JSONDecodeError, OSError):
                    pass
            time.sleep(0.3)
        for rp in [queue_path, result_path]:
            if os.path.exists(rp):
                try:
                    os.remove(rp)
                except OSError:
                    pass
        if result is None:
            QMessageBox.warning(self, "Test", "Timeout (60s). VASS potrebbe non essere in esecuzione.")
        elif result.get("status") == "ok":
            QMessageBox.information(self, "Test", "Script eseguito con successo.")
        else:
            QMessageBox.critical(self, "Test", f"Errore: {result.get('detail', result.get('message', 'sconosciuto'))}")

    def _new_script(self):
        name, ok = QInputDialog.getText(self, "Nuovo script", "Nome (senza .vass):")
        if not ok or not name.strip():
            return
        name = name.strip()
        if not name.endswith(".vass"):
            name += ".vass"
        path = os.path.join(self._scripts_dir(), name)
        if os.path.exists(path):
            QMessageBox.critical(self, "Errore", f"{name} esiste già.")
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"# {name}\n")
        except Exception as e:
            QMessageBox.critical(self, "Errore", f"Creazione fallita:\n{e}")
            return
        self._refresh_list()
        items = self.list_widget.findItems(name, Qt.MatchFlag.MatchExactly)
        if items:
            self.list_widget.setCurrentItem(items[0])

    def _delete_script(self):
        name = self._current_file
        if not name:
            return
        reply = QMessageBox.question(
            self, "Elimina", f"Eliminare {name}?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        script_name = os.path.splitext(name)[0]
        try:
            import keyring
            keyring.delete_password("vass-auth", script_name)
        except Exception:
            pass
        path = os.path.join(self._scripts_dir(), name)
        try:
            os.remove(path)
        except Exception as e:
            QMessageBox.critical(self, "Errore", f"Eliminazione fallita:\n{e}")
            return
        self._current_file = None
        self.editor.blockSignals(True)
        self.editor.setPlainText("")
        self.editor.blockSignals(False)
        self._dirty = False
        self._refresh_list()
        self._update_title()

    def _manage_permissions(self):
        import json
        try:
            import keyring
        except ImportError:
            QMessageBox.information(self, "Info", "keyring non disponibile.")
            return

        candidates = set(self._scripts)
        candidates.add("inline")
        entries = []
        for name in sorted(candidates):
            raw = keyring.get_password("vass-auth", name.replace(".vass", ""))
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if data:
                parts = []
                if data.get("_all_"):
                    parts.append("tutto")
                else:
                    for fn in ("ai", "say", "run"):
                        if data.get(fn):
                            parts.append(fn)
                entries.append((name.replace(".vass", ""), ", ".join(parts) or "sconosciuto"))

        if not entries:
            QMessageBox.information(self, self._t("scripts_editor.permissions.title"),
                self._t("scripts_editor.permissions.no_permissions"))
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(self._t("scripts_editor.permissions.title"))
        dlg.resize(400, 300)
        dlg.setStyleSheet(self.styleSheet())
        layout = QVBoxLayout(dlg)

        layout.addWidget(QLabel(self._t("scripts_editor.permissions.stored")))

        list_w = QListWidget()
        for sname, funcs in entries:
            list_w.addItem(f"{sname}  →  {funcs}")
        layout.addWidget(list_w)

        btn_row = QHBoxLayout()
        revoke_btn = QPushButton(self._t("scripts_editor.permissions.revoke"))
        revoke_btn.setStyleSheet(f"background-color: {BTN_DEL_BG}; color: {BTN_DEL_FG};")
        btn_row.addWidget(revoke_btn)

        revoke_all_btn = QPushButton(self._t("scripts_editor.permissions.revoke_all"))
        revoke_all_btn.setStyleSheet(f"background-color: {BTN_DEL_BG}; color: {BTN_DEL_FG};")
        btn_row.addWidget(revoke_all_btn)

        btn_row.addStretch()
        close_btn = QPushButton(self._t("scripts_editor.permissions.close"))
        close_btn.setStyleSheet(f"background-color: {BTN_BG}; color: {BTN_FG};")
        close_btn.clicked.connect(dlg.accept)
        btn_row.addWidget(close_btn)

        layout.addLayout(btn_row)

        def do_revoke():
            curr = list_w.currentItem()
            if not curr:
                return
            sname = curr.text().split("  →  ")[0]
            reply = QMessageBox.question(dlg, self._t("scripts_editor.permissions.revoke"),
                self._t("scripts_editor.permissions.revoke_confirm").replace("{name}", sname),
                QMessageBox.Yes | QMessageBox.No)
            if reply != QMessageBox.Yes:
                return
            try:
                keyring.delete_password("vass-auth", sname)
            except Exception:
                pass
            list_w.takeItem(list_w.row(curr))
            if list_w.count() == 0:
                dlg.accept()
                QMessageBox.information(self, self._t("scripts_editor.permissions.title"),
                    self._t("scripts_editor.permissions.all_revoked"))

        def do_revoke_all():
            reply = QMessageBox.question(dlg, self._t("scripts_editor.permissions.revoke_all"),
                self._t("scripts_editor.permissions.revoke_all_confirm"),
                QMessageBox.Yes | QMessageBox.No)
            if reply != QMessageBox.Yes:
                return
            for sname, _ in entries:
                try:
                    keyring.delete_password("vass-auth", sname)
                except Exception:
                    pass
            dlg.accept()
            QMessageBox.information(self, "Permessi", "Tutti i permessi sono stati revocati.")

        revoke_btn.clicked.connect(do_revoke)
        revoke_all_btn.clicked.connect(do_revoke_all)
        dlg.exec()

    def closeEvent(self, event):
        if self._dirty:
            reply = QMessageBox.question(
                self, self._t("scripts_editor.close.title"),
                self._t("scripts_editor.close.message"),
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
            )
            if reply == QMessageBox.Yes:
                self._save()
            elif reply == QMessageBox.Cancel:
                event.ignore()
                return
        event.accept()


if __name__ == "__main__":
    lang = "en"
    for i, a in enumerate(sys.argv[1:]):
        if a == "--lang" and i + 1 < len(sys.argv[1:]):
            lang = sys.argv[i + 2]
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    editor = ScriptsEditor(language=lang)
    editor.show()
    sys.exit(app.exec())
