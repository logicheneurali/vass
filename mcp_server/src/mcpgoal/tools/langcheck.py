import json

_MODELS = {}
_LANG_MODEL_MAP = {
    "it": "it_core_news_sm",
    "en": "en_core_web_sm",
    "de": "de_core_news_sm",
    "fr": "fr_core_news_sm",
    "es": "es_core_news_sm",
    "pt": "pt_core_news_sm",
    "ja": "ja_core_news_sm",
    "ko": "ko_core_news_sm",
    "zh": "zh_core_web_sm",
}


def _load_model(lang):
    if lang not in _MODELS:
        model_name = _LANG_MODEL_MAP.get(lang)
        if not model_name:
            return None
        print(f"[LangCheck] Downloading {model_name} model (~50 MB)...")
        import spacy
        try:
            _MODELS[lang] = spacy.load(model_name)
        except OSError:
            import subprocess, sys
            subprocess.run([sys.executable, "-m", "spacy", "download", model_name], check=True)
            _MODELS[lang] = spacy.load(model_name)
        print(f"[LangCheck] Model {model_name} ready")
    return _MODELS[lang]


async def check_language(text: str, lang: str = "it") -> str:
    if not text or not text.strip():
        return json.dumps({"status": "error", "message": "text required"})

    nlp = _load_model(lang)
    if nlp is None:
        return json.dumps({"status": "error", "message": f"language '{lang}' not supported"})

    doc = nlp(text)
    issues = []

    for sent in doc.sents:
        for token in sent:
            # -- Tier 2: Gender/number agreement between subject and verb --
            if token.dep_ in ("nsubj", "nsubjpass") and token.head.pos_ in ("VERB", "AUX"):
                if token.morph.get("Gender") and token.head.morph.get("Gender"):
                    subj_gender = token.morph.get("Gender")
                    verb_gender = token.head.morph.get("Gender")
                    if subj_gender != verb_gender:
                        issues.append({
                            "token": token.text,
                            "type": "gender_mismatch",
                            "message": f"'{token.text}' ({'/'.join(subj_gender)}) does not match verb '{token.head.text}' ({'/'.join(verb_gender)})",
                        })
                if token.morph.get("Number") and token.head.morph.get("Number"):
                    subj_num = token.morph.get("Number")
                    verb_num = token.head.morph.get("Number")
                    if subj_num != verb_num:
                        issues.append({
                            "token": token.text,
                            "type": "number_mismatch",
                            "message": f"'{token.text}' ({'/'.join(subj_num)}) does not match verb '{token.head.text}' ({'/'.join(verb_num)})",
                        })

            # -- Tier 2: Adjective-noun agreement --
            if token.pos_ == "ADJ" and token.head.pos_ in ("NOUN", "PROPN"):
                if token.morph.get("Gender") and token.head.morph.get("Gender"):
                    adj_gender = token.morph.get("Gender")
                    noun_gender = token.head.morph.get("Gender")
                    if adj_gender != noun_gender:
                        issues.append({
                            "token": token.text,
                            "type": "adj_noun_gender",
                            "message": f"Adjective '{token.text}' ({'/'.join(adj_gender)}) disagrees with '{token.head.text}' ({'/'.join(noun_gender)})",
                        })
                if token.morph.get("Number") and token.head.morph.get("Number"):
                    adj_num = token.morph.get("Number")
                    noun_num = token.head.morph.get("Number")
                    if adj_num != noun_num:
                        issues.append({
                            "token": token.text,
                            "type": "adj_noun_number",
                            "message": f"Adjective '{token.text}' ({'/'.join(adj_num)}) disagrees with '{token.head.text}' ({'/'.join(noun_num)})",
                        })

    if issues:
        return json.dumps({"status": "issues_found", "lang": lang, "issues": issues}, ensure_ascii=False)
    return json.dumps({"status": "ok", "lang": lang, "message": "No issues detected"}, ensure_ascii=False)
