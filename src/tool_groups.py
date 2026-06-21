"""MCP tool group definitions and keyword-based selection.

Groups MCP tools into functional categories.  When the AI is called,
only tools whose group keywords match the user prompt are sent,
keeping the context budget manageable for smaller models.

Shared by VASScript ai() and main AI fallback — zero redundancy.
"""
import os
import json

# ── Group definitions ─────────────────────────────────────────────
# Map of group name → list of MCP tool names belonging to that group.
# interact, script, execute are excluded — they require allow_ai_scripts.
TOOL_GROUPS = {
    "web":       ["browse", "webfetch", "websearch"],
    "calendar":  ["calendar_add", "calendar_list", "calendar_search"],
    "files":     ["read_file", "write_file", "readinfo", "writeinfo"],
    "events":    ["addevent", "delevent", "listevents"],
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
        "events":    {"evento", "promemoria", "sveglia", "notifica",
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
        if any(w in prompt_lower for w in words):
            groups.add(group_name)
    return groups or {"web"}


def resolve_tool_names(group_names, all_tools, debug=False):
    """Convert group names to filtered OpenAI tool list."""
    names = set()
    for g in group_names:
        names.update(TOOL_GROUPS.get(g, []))
    tools = [t for t in all_tools if t["function"]["name"] in names]
    if debug:
        tool_names = [t["function"]["name"] for t in tools] if tools else []
        print(f"[Debug] Tool groups: {sorted(group_names) or 'none'} -> {len(tool_names)} tools: {', '.join(tool_names) or 'none'}")
    return tools
