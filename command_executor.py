import configparser
import subprocess
import os
import difflib
import re
from urllib.parse import quote


class CommandExecutor:
    def __init__(self, commands_file="commands.ini", similarity_threshold=0.6):
        self.commands_file = commands_file
        self.similarity_threshold = similarity_threshold
        self.commands = {}
        self.load_commands()

    def load_commands(self):
        if not os.path.exists(self.commands_file):
            print(f"Commands file {self.commands_file} not found.")
            return
        config = configparser.ConfigParser()
        config.read(self.commands_file)
        self.commands.clear()
        for section in config.sections():
            for key, value in config.items(section):
                self.commands[key.lower().strip()] = value

    def reload_commands(self):
        self.load_commands()
        print(f"Commands reloaded. Total: {len(self.commands)}")

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
        for i, part in enumerate(parts):
            if i % 2 == 0:
                pattern_parts.append(re.escape(part))
            else:
                pattern_parts.append(r'(.+)')
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
                wr = difflib.SequenceMatcher(None, kw_w, tr_words[j]).quick_ratio()
                if wr > best_wr:
                    best_wr = wr
            if best_wr >= 0.6:
                matched += 1
                tr_idx += 1
        return matched / max(len(kw_words), 1)

    def find_matching_command(self, transcribed_text):
        transcribed_lower = transcribed_text.lower().strip()
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
                    if ratio > best_ratio:
                        best_ratio = ratio
                        best_keyword = keyword
                        best_vars = dict(zip(var_names, extracted))
                else:
                    if ratio > best_ratio:
                        best_ratio = ratio
                        best_keyword = keyword
                        best_vars = self._extract_vars_fuzzy(kw_lower, transcribed_lower, var_names)
            else:
                ratio = difflib.SequenceMatcher(None, transcribed_lower, kw_lower).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_keyword = keyword
                    best_vars = None

        if best_keyword and best_ratio >= self.similarity_threshold:
            cmd = self.commands[best_keyword]
            _, var_names = self._parse_variables(best_keyword.lower().strip())
            if var_names and not best_vars:
                return None, None
            param_dict = None
            if best_vars:
                fmt_vars = {
                    k: quote(v, safe='') if k.startswith('escaped_') else v
                    for k, v in best_vars.items()
                }
                cmd = cmd.format(**fmt_vars)
                param_dict = {f"param{i+1}": v for i, (k, v) in enumerate(best_vars.items())}
                var_info = ', '.join(f'{k}={v}' for k, v in best_vars.items())
                print(f"[Fuzzy] '{transcribed_text}' -> '{best_keyword}' (ratio: {best_ratio:.2f}, vars: {{{var_info}}})")
            else:
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
        import base64
        try:
            subprocess.run(
                [
                    "powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command",
                    "Add-Type -AssemblyName System.Speech; "
                    "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                    "$s.Speak('Ok')"
                ],
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            encoded = base64.b64encode(command.encode("utf-16-le")).decode("ascii")
            subprocess.run(
                [
                    "powershell", "-NoProfile", "-WindowStyle", "Hidden", "-EncodedCommand", encoded
                ],
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            print(f"Command started: {command}")
            return True
        except Exception as e:
            print(f"Unexpected error executing command: {e}")
            return False
