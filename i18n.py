import json
import os

BASE = os.path.dirname(os.path.abspath(__file__))
_locale_cache = {}

def load_lang(lang):
    if lang not in _locale_cache:
        path = os.path.join(BASE, "locales", f"{lang}.json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                _locale_cache[lang] = json.load(f)
        else:
            _locale_cache[lang] = {}
    return _locale_cache[lang]

def t(path, lang="it"):
    val = load_lang(lang)
    keys = path.split(".")
    for key in keys:
        if isinstance(val, dict):
            val = val.get(key)
        else:
            return keys[-1]
    if val is None:
        return keys[-1]
    return val
