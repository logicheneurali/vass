"""MCP tool group definitions and keyword-based selection.

Groups MCP tools into functional categories.  When the AI is called,
only tools whose group keywords match the user prompt are sent,
keeping the context budget manageable for smaller models.

Shared by VASScript ai() and main AI fallback — zero redundancy.
"""
import os
import json
from utils import fuzzy_match_word

# Groups whose requests are always self-contained (no memory needed)
STANDALONE_GROUPS = {"compute", "time", "lang"}

# ── Group definitions ─────────────────────────────────────────────
# Map of group name → list of MCP tool names belonging to that group.
# interact, script, execute are excluded — they require allow_ai_scripts.
TOOL_GROUPS = {
    "web":       ["browse", "webfetch", "websearch"],
    "calendar":  ["calendar_add", "calendar_list", "calendar_search"],
    "files":     ["read_file", "write_file", "readinfo", "writeinfo"],
    "events":    ["addevent", "delevent", "listevents", "nextevent"],
    "clipboard": ["clipboardget", "clipboardset"],
    "time":      ["current_time", "to_timestamp"],
    "compute":   ["calculate"],
    "lang":      ["langcheck"],
    "idle":      ["getidle"],
    "tags":      ["savetags"],
}

# ── Keyword loading ───────────────────────────────────────────────
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _default_keywords():
    """Fallback keyword set (Italian) when locale file is missing."""
    return {
        "web":       {"cerca", "internet", "sito", "online", "pagina",
                       "ricerca", "naviga", "trovami", "collegamento",
                       "url", "link", "browser", "consulta", "apri", "leggi"},
        "calendar":  {"calendario", "evento", "appuntamento", "agenda",
                       "programma", "pianifica", "organizza", "impegno",
                       "ricorrenza", "fissare", "prenotare", "incontro",
                       "riunione", "scadenza", "promemoria"},
        "files":     {"file", "salva", "scrivi", "leggi", "documento",
                       "archivia", "registra", "appunto", "nota", "testo",
                       "backup", "cartella", "export", "import", "salvataggio"},
        "events":    {"evento", "eventi", "promemoria", "sveglia", "notifica",
                       "programma", "avviso", "alert", "reminder", "scadenza",
                       "timer", "appuntamento", "orario", "data", "pianifica",
                       "ricorda"},
        "time":      {"ora", "data", "tempo", "orario", "oggi", "quando",
                       "adesso", "attuale", "corrente", "timestamp", "fuso",
                       "periodo", "giorno", "mese", "anno"},
        "compute":   {"calcola", "somma", "calcolo", "quanto", "matematica",
                       "moltiplica", "dividi", "aggiungi", "sottrai",
                       "operazione", "formula", "risultato", "equazione",
                       "conta", "numero",
                       "+", "-", "*", "/", "%", "^", "=", "<", ">",
                       "piu", "piu'", "meno", "per", "diviso",
                       "radice", "quadrato"},
        "lang":      {"lingua", "traduci", "grammatica", "correggi", "testo",
                       "spelling", "ortografia", "sintassi", "vocabolario",
                       "dizionario", "verifica", "analizza", "frase",
                       "parola", "linguaggio"},
        "clipboard": {"copia", "incolla", "appunti", "clipboard", "testo",
                       "duplica", "ritaglia", "trasferisci", "sposta",
                       "buffer", "memorizza", "temporaneo", "riporta",
                       "inserisci", "prendi"},
        "idle":      {"inattivo", "fermo", "pausa", "idle", "attivita",
                       "riposo", "stop", "bloccato", "assente", "sessione",
                       "utente", "lavoro", "schermo", "computer", "stato"},
        "tags":      {"tag", "etichetta", "categoria", "classifica",
                        "memoria", "argomento", "tipo", "gruppo", "genere",
                        "chiave", "catalogare", "organizzare", "ricordare",
                        "contesto", "tema"},
    }


# ── Memory classification ────────────────────────────────────────
# Keywords for anaphora/context detection per language.
# These are NOT tool groups — they only live here, not in locale JSONs.
_ANAPHORA_KEYWORDS = {
    "it": {"lui","lei","loro","ne","stesso","stessa","stessi","stesse",
           "tale","tali","suddetto","menzionato","continuare","prosegui",
           "riprendi","ripeti","precedente","scorso","altra","altro",
           "mio","mia","miei","mie","tuo","tua","tuoi","tue","suo","sua","suoi","sue",
           "prossimo","prossima","prossimi","prossime",
           "ricordi","ricordami",
           "ieri",
           "quel","quello","quella","quei","quegli",
           "prima","allora",
           "discussione","discussioni","discorso"},
    "en": {"he","him","she","her","they","them","continue","proceed",
           "repeat","resume","previous","earlier","above","aforementioned",
           "mentioned","another",
           "my","mine","your","yours","our","ours",
           "next",
           "remember",
           "yesterday",
           "that","those",
           "before","then",
           "discussion","discussions","discourse"},
    "de": {"er","ihn","ihm","sie","ihr","fortsetzen","weiter","wiederholen",
           "vorherige","vorher","erwähnt","besagt","obig","letzte","gestrig",
           "mein","meine","dein","deine","sein","seine",
           "nächst","nächste",
           "erinnere",
           "jener","jene",
           "damals",
           "Diskussion","Diskussionen","Diskurs"},
    "fr": {"il","lui","elle","ils","elles","continuer","répéter","poursuivre",
           "reprendre","précédent","mentionné","susdit","autre","hier",
           "mon","ma","mes","ton","ta","tes","son","sa","ses",
           "prochain","prochaine",
           "souviens",
           "ce","cet","cette",
           "avant","alors",
           "discussion","discussions","discours"},
    "es": {"él","ella","ellos","ellas","continuar","repetir","proseguir",
           "retomar","anterior","mencionado","dicho","ayer","otro","otra",
           "mi","mis","tu","tus","su","sus",
           "próximo","próxima",
           "recuerdas",
           "ese","esa","esos","esas",
           "antes","entonces",
           "discusión","discusiones","discurso"},
    "pt": {"ele","ela","eles","elas","continuar","repetir","prosseguir",
           "retomar","anterior","mencionado","dito","ontem","outro","outra",
           "meu","minha","meus","minhas","teu","tua","seu","sua",
           "próximo","próxima",
           "lembra",
           "esse","essa","esses","essas",
           "antes","então",
           "discussão","discussões","discurso"},
    "ja": {"彼","彼女","続ける","繰り返す","最初から","もう一度","前の","昨日",
           "前述","上記",
           "私の","あなたの",
           "次",
           "覚えて",
           "その",
           "前に",
           "議論","話し合い","談話"},
    "ko": {"그","그녀","계속하다","반복하다","다시","이전","어제","앞서",
           "위","앞의",
           "내","나의","너의",
           "다음",
           "기억해",
           "그",
           "전에",
           "논의","토론","담화"},
    "zh": {"他","她","继续","重复","再来","之前的","昨天","上述","前面",
           "我的","你的",
           "下一个",
           "记得",
           "那个",
           "之前",
           "讨论","谈话","话题"},
}


def needs_memory(prompt, lang="it"):
    """Return True if the prompt likely needs conversation history.

    Returns False only when the prompt is certifiably standalone
    (matches compute/time/lang tool keywords), meaning it's safe to
    skip memory injection.  Defaults to True (conservative).
    """
    keywords = load_keywords(lang)
    prompt_lower = prompt.lower()

    # 1. Anaphora/context keywords → SI memory needed (prevale su standalone)
    ctx = _ANAPHORA_KEYWORDS.get(lang, _ANAPHORA_KEYWORDS["en"])
    if any(w in prompt_lower for w in ctx) or fuzzy_match_word(prompt_lower, ctx):
        return True

    # 2. Standalone group match → NO memory needed
    for group in STANDALONE_GROUPS:
        words = keywords.get(group, [])
        if any(w in prompt_lower for w in words) or fuzzy_match_word(prompt_lower, words):
            return False

    # 3. Default: conservative
    return True


def load_keywords(lang):
    """Load keywords from locale file, fall back to Italian defaults."""
    path = os.path.join(BASE, "locales", f"{lang}.json")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("tool_groups", _default_keywords())
    except Exception:
        return _default_keywords()


# ── Selection logic ──────────────────────────────────────────────

def select_tool_groups(prompt, lang="it"):
    """Return set of group names whose keywords match the prompt."""
    keywords = load_keywords(lang)
    prompt_lower = prompt.lower()
    groups = set()
    for group_name, words in keywords.items():
        if group_name not in TOOL_GROUPS:
            continue
        if any(w in prompt_lower for w in words) or fuzzy_match_word(prompt_lower, words):
            groups.add(group_name)
    return groups or {"web"}


def resolve_tool_names(group_names, all_tools, debug=False):
    """Convert group names to filtered OpenAI tool list."""
    if not all_tools:
        return []
    names = set()
    for g in group_names:
        names.update(TOOL_GROUPS.get(g, []))
    tools = [t for t in all_tools if t["function"]["name"] in names]
    if debug:
        tool_names = [t["function"]["name"] for t in tools] if tools else []
        print(f"[Debug] Tool groups: {sorted(group_names) or 'none'} -> {len(tool_names)} tools: {', '.join(tool_names) or 'none'}")
    return tools


def load_tool_name(tool_name, lang="it"):
    """Return (display_name, description) for a tool, localized."""
    data = load_keywords(lang)
    # load_keywords returns the tool_groups dict; locale has a separate tool_names section
    # Re-read the locale file for tool_names specifically
    path = os.path.join(BASE, "locales", f"{lang}.json")
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        info = raw.get("tool_names", {}).get(tool_name)
        if info:
            return info.get("name", tool_name), info.get("desc", "")
    except Exception:
        pass
    return tool_name, ""
