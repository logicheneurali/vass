import configparser
import itertools
import subprocess
import os
import difflib
import json
import math
import re
from urllib.parse import quote
from utils import fuzzy_ratio


def _levenshtein(a, b):
    if len(a) < len(b):
        return _levenshtein(b, a)
    if len(b) == 0:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        cur = [i + 1]
        for j, cb in enumerate(b):
            cur.append(min(prev[j + 1] + 1, cur[j] + 1, prev[j] + (ca != cb)))
        prev = cur
    return prev[-1]


class CommandExecutor:
    def __init__(self, commands_file="config/commands.ini", similarity_threshold=0.6, language="en",
                 word_learning_enabled=False, app=None):
        self.commands_file = commands_file
        self.similarity_threshold = similarity_threshold
        self.language = language
        self.word_learning_enabled = word_learning_enabled
        self.app = app
        self.commands = {}
        self.scopes = {}
        self._delay_originals = {}
        self._word_weights = {}
        self._weights_path = None
        self.load_commands()
        self._load_word_weights()

    def load_commands(self):
        self._delay_originals.clear()
        if not os.path.exists(self.commands_file):
            print(f"Commands file {self.commands_file} not found.")
        else:
            config = configparser.ConfigParser()
            config.read(self.commands_file, encoding="utf-8")
            self.commands.clear()
            for section in config.sections():
                for key, value in config.items(section):
                    self._add_command(key, value)

        lang_file = f"config/commands_{self.language}.ini"
        if os.path.exists(lang_file):
            config = configparser.ConfigParser()
            config.read(lang_file, encoding="utf-8")
            for section in config.sections():
                for key, value in config.items(section):
                    self._add_command(key, value)
            print(f"Commands loaded: {len(self.commands)} total (including {lang_file})")
        else:
            print(f"Commands loaded: {len(self.commands)} total")

    def _add_command(self, key, value,variants=True,scope="command"):
        keyword = key.lower().strip()
        var_suffix = ""
        m = re.search(r'(\{\w+\}.*)$', keyword)
        if m:
            var_suffix = m.group(1)
            keyword = re.sub(r'\s*\{\w+\}.*$', '', keyword).strip()
        if not keyword:
            return
        columns = keyword.split()
        col_alternatives = []
        for col in columns:
            if "," in col:
                col_alternatives.append([a.strip() for a in col.split(",") if a.strip()])
            else:
                col_alternatives.append([col])
        for combo in itertools.product(*col_alternatives):
            cmd_keyword = " ".join(combo)
            if var_suffix:
                cmd_keyword += " " + var_suffix
            self.commands[cmd_keyword] = value
            self.scopes[cmd_keyword] = scope
            if variants==True:
                self._add_delayed_variants(cmd_keyword,value)

    _DELAY_PREPS = {
        "it": ["fra", "tra", "in"],
        "en": ["in", "after", "within"],
        "de": ["in", "nach", "innerhalb"],
        "es": ["en", "dentro", "dentro de"],
        "fr": ["dans", "apres", "d'ici"],
        "pt": ["em", "daqui a", "depois de"],
    }

    _DELAY_SUFFIX = {
        "ja": "後に",
        "ko": "후에",
        "zh": "后",
    }

    def _add_delayed_variants(self, key, value):
        lang = self.language
        suffix = self._DELAY_SUFFIX.get(lang)
        if suffix:
            delayed_kw = f"{{duration}}{suffix} {key}"
            self.commands[delayed_kw] = value
            self.scopes[delayed_kw] = "delayed_command"
            self._delay_originals[delayed_kw] = key
            return
        preps = self._DELAY_PREPS.get(lang, self._DELAY_PREPS["en"])
        for prep in preps:
            delayed_kw = f"{key} {prep} {{duration}}"
            self.commands[delayed_kw] = value
            self.scopes[delayed_kw] = "delayed_command"
            self._delay_originals[delayed_kw] = key

    def reload_commands(self):
        self.commands.clear()
        self.load_commands()
        self._load_word_weights()
        print(f"Commands reloaded. Total: {len(self.commands)}")

    # ── Word weights (adaptive learning, experimental) ─────────────────────

    def _weights_file(self):
        if self._weights_path is None:
            self._weights_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "Allowed_root", "word_weights.json")
        return self._weights_path

    def _load_word_weights(self):
        if not self.word_learning_enabled:
            return
        try:
            with open(self._weights_file(), encoding="utf-8") as f:
                self._word_weights = json.load(f)
        except Exception:
            self._word_weights = {}

    def _save_word_weights(self):
        if not self.word_learning_enabled:
            return
        try:
            os.makedirs(os.path.dirname(self._weights_file()), exist_ok=True)
            with open(self._weights_file(), "w", encoding="utf-8") as f:
                json.dump(self._word_weights, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def track_command_outcome(self, transcribed_text, success):
        if not self.word_learning_enabled or not transcribed_text:
            return
        for word in transcribed_text.lower().strip().split():
            w = re.sub(r'[^a-z0-9]', '', word)
            if len(w) < 2 or w.isdigit():
                continue
            entry = self._word_weights.get(w, {"success": 0, "fail": 0})
            if success:
                entry["success"] += 1
            else:
                entry["fail"] += 1
            usage = entry["success"] + entry["fail"]
            sr = (entry["success"] + 1) / (entry["fail"] + 1)
            entry["weight"] = round(sr * (1 + math.log(usage + 1) * 0.1), 4)
            self._word_weights[w] = entry
        self._save_word_weights()

    def correct_transcription(self, transcribed_text):
        if not self.word_learning_enabled or not self._word_weights:
            return transcribed_text
        words = transcribed_text.lower().strip().split()
        corrected = []
        changed = False
        for word in words:
            clean = re.sub(r'[^a-z0-9]', '', word)
            if clean not in self._word_weights:
                w_entry = self._word_weights.get(clean, {"weight": 1.0})
            else:
                w_entry = self._word_weights[clean]
            if w_entry.get("weight", 1.0) >= 0.8:
                corrected.append(word)
                continue
            best, best_w = None, 0
            for cand, c_entry in self._word_weights.items():
                cw = c_entry.get("weight", 1.0)
                if cw <= max(w_entry.get("weight", 1.0), 1.0):
                    continue
                if abs(len(clean) - len(cand)) > 2:
                    continue
                if _levenshtein(clean, cand) <= 2 and cw > best_w:
                    best, best_w = cand, cw
            if best:
                corrected.append(best)
                changed = True
            else:
                corrected.append(word)
        result = " ".join(corrected)
        if changed:
            print(f"[WordWeights] Corrected: '{transcribed_text.lower().strip()}' -> '{result}'")
        return result

    def get_top_weighted_prompt(self):
        if not self._word_weights:
            return ""
        sorted_words = sorted(self._word_weights.items(),
                              key=lambda x: x[1].get("weight", 1.0), reverse=True)
        top = [w for w, e in sorted_words if e.get("weight", 1.0) > 1.5][:20]
        return ", ".join(top) if top else ""

    @staticmethod
    def _parse_variables(keyword):
        parts = re.split(r'\{(\w+)\}', keyword)
        tokens = []
        var_names = []
        for i, part in enumerate(parts):
            if i % 2 == 0:
                tokens.append(('text', part))
            else:
                tokens.append(('var', part))
                var_names.append(part)
        return tokens, var_names

    @staticmethod
    def _keyword_to_pattern(keyword):
        parts = re.split(r'\{(\w+)\}', keyword)
        pattern_parts = []
        var_indices = [i for i in range(1, len(parts), 2)]
        last_var = var_indices[-1] if var_indices else -1
        for i, part in enumerate(parts):
            if i % 2 == 0:
                pattern_parts.append(re.escape(part))
            elif i == last_var:
                pattern_parts.append(r'(.+)')
            else:
                pattern_parts.append(r'([^ ]+)')
        return '^' + ''.join(pattern_parts) + '$'

    @staticmethod
    def _strip_variables(keyword):
        return re.sub(r'\{(\w+)\}', '', keyword).strip()

    def _score_var_keyword(self, fixed_kw, transcribed):
        kw_words = fixed_kw.split()
        tr_words = transcribed.split()
        matched = 0
        tr_idx = 0
        for kw_w in kw_words:
            best_wr = 0
            for j in range(tr_idx, min(tr_idx + 3, len(tr_words))):
                wr = difflib.SequenceMatcher(None, kw_w, tr_words[j]).ratio()
                if wr > best_wr:
                    best_wr = wr
            if best_wr >= 0.75:
                matched += 1
                tr_idx += 1
        return matched / max(len(kw_words), 1)

    def find_matching_command(self, transcribed_text):
        transcribed_lower = re.sub(r'[,!?;:]', ' ', transcribed_text.lower()).strip()
        transcribed_lower = re.sub(r'\.$', '', transcribed_lower)
        transcribed_lower = re.sub(r'\s+', ' ', transcribed_lower)
        transcribed_lower = self.correct_transcription(transcribed_lower)
        if not transcribed_lower:
            return None

        best_keyword = None
        best_ratio = 0.0
        best_vars = None

        for keyword, command in self.commands.items():
            kw_lower = keyword.lower().strip()
            tokens, var_names = self._parse_variables(kw_lower)

            if var_names:
                stripped = self._strip_variables(kw_lower)
                ratio = self._score_var_keyword(stripped, transcribed_lower)
                pattern = self._keyword_to_pattern(kw_lower)
                m = re.match(pattern, transcribed_lower)
                if m:
                    extracted = m.groups()
                    curr_scope = self.scopes.get(keyword, "command")
                    if ratio > best_ratio or (ratio == best_ratio and curr_scope == "delayed_command" and self.scopes.get(best_keyword, "command") != "delayed_command"):
                        best_ratio = ratio
                        best_keyword = keyword
                        best_vars = dict(zip(var_names, extracted))
                else:
                    ratio *= 0.6
                    curr_scope = self.scopes.get(keyword, "command")
                    if ratio > best_ratio or (ratio == best_ratio and curr_scope == "delayed_command" and self.scopes.get(best_keyword, "command") != "delayed_command"):
                        best_ratio = ratio
                        best_keyword = keyword
                        best_vars = self._extract_vars_fuzzy(kw_lower, transcribed_lower, var_names)
            else:
                ratio = fuzzy_ratio(transcribed_lower, kw_lower)
                curr_scope = self.scopes.get(keyword, "command")
                if ratio > best_ratio or (ratio == best_ratio and curr_scope == "delayed_command" and self.scopes.get(best_keyword, "command") != "delayed_command"):
                    best_ratio = ratio
                    best_keyword = keyword
                    best_vars = None

        if best_keyword and best_ratio >= self.similarity_threshold:
            cmd = self.commands[best_keyword]
            scope = self.scopes.get(best_keyword, "command")
            if scope == "delayed_command":
                duration_text = best_vars.get("duration", "") if best_vars else ""
                original_key = self._delay_originals.get(best_keyword, "")
                if not duration_text or not original_key:
                    return None, None
                for k, v in best_vars.items():
                    if k != "duration":
                        original_key = original_key.replace(f"{{{k}}}", v)
                return ("__delayed__", {"duration": duration_text, "original_key": original_key})
            _, var_names = self._parse_variables(best_keyword.lower().strip())
            if var_names and not best_vars:
                return None, None
            param_dict = None
            if best_vars:
                fmt_vars = {
                    k: quote(v, safe='') if k.startswith('escaped_') else v
                    for k, v in best_vars.items()
                }
                try:
                    cmd = cmd.format(**fmt_vars)
                except KeyError:
                    return None, None
                param_dict = {f"param{i+1}": v for i, v in enumerate(fmt_vars.values())}
                for i, word in enumerate(transcribed_text.strip().split(), start=1):
                    param_dict[f"cword{i}"] = word
                var_info = ', '.join(f'{k}={v}' for k, v in best_vars.items())
                print(f"[Fuzzy] '{transcribed_text}' -> '{best_keyword}' (ratio: {best_ratio:.2f}, vars: {{{var_info}}})")
            else:
                param_dict = {}
                for i, word in enumerate(transcribed_text.strip().split(), start=1):
                    param_dict[f"cword{i}"] = word
                print(f"[Fuzzy] '{transcribed_text}' -> '{best_keyword}' (ratio: {best_ratio:.2f})")
            return cmd, param_dict
        return None, None

    @staticmethod
    def _extract_vars_fuzzy(keyword, transcribed, var_names):
        stripped = re.sub(r'\{(\w+)\}', '', keyword).strip()
        kw_words = stripped.split()
        tr_words = transcribed.split()

        sm = difflib.SequenceMatcher(None, kw_words, tr_words)
        tr_used = [False] * len(tr_words)
        for op, ak, ak_end, bk, bk_end in sm.get_opcodes():
            if op == 'equal':
                for i in range(bk, bk_end):
                    tr_used[i] = True

        unused_words = [tr_words[i] for i, used in enumerate(tr_used) if not used]

        if not var_names:
            return None

        if len(unused_words) < len(var_names):
            return None

        base = len(unused_words) // len(var_names)
        rem = len(unused_words) % len(var_names)
        var_values = []
        idx = 0
        for v in range(len(var_names)):
            take = base + (1 if v < rem else 0)
            var_values.append(' '.join(unused_words[idx:idx + take]))
            idx += take

        return dict(zip(var_names, var_values))

    def execute_command(self, command):
        import sys
        try:
            print(f"[Security] execute_command() executing: {command[:200]}")
            if sys.platform == "win32":
                subprocess.run(
                    ["powershell", "-NoProfile", "-WindowStyle", "Hidden",
                     "-Command", command],
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
            else:
                import shlex
                subprocess.run(
                    shlex.split(command), shell=False,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
            print(f"Command started: {command}")
            return True
        except Exception as e:
            print(f"Unexpected error executing command: {e}")
            return False
