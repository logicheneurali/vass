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
        "web":       ["browse", "webfetch", "websearch", "search_places", "search_nearby", "search_news"],
        "mail":      ["search_emails", "send_email", "reply_email", "forward_email", "search_contacts"],
        "browser":   ["browser_open", "browser_read", "browser_click", "browser_fill", "browser_submit", "browser_download", "browser_back", "browser_show", "browser_check_auth"],
    "news":      ["read_news", "read_news_range", "search_news"],
    "calendar":  ["calendar_add", "calendar_list", "calendar_search"],
    "files":     ["read_file", "write_file", "readinfo", "writeinfo", "html_to_pdf"],
    "events":    ["addevent", "delevent", "listevents", "nextevent", "find_free_slot", "timer_start", "timer_list"],
    "clipboard": ["clipboardget", "clipboardset"],
    "time":      ["current_time", "to_timestamp"],
    "compute":   ["calculate"],
    "lang":      ["langcheck"],
    "idle":      ["getidle"],
    "tags":      ["savetags", "search_tags"],
}

TOOL_TO_GROUP = {}
for group, names in TOOL_GROUPS.items():
    for name in names:
        TOOL_TO_GROUP[name] = group

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
                       "backup", "cartella", "export", "import", "salvataggio",
                       "pdf", "html", "stampa", "crea documento"},
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
# Keywords that always trigger memory inclusion — evaluated before
# standalone groups. A single match forces full context injection.
# These are NOT tool groups — they only live here, not in locale JSONs.
_MEMORY_ACTIVATION_KEYWORDS = {
    "it": {"lui","lei","loro","ne","stesso","stessa","stessi","stesse",
           "tale","tali","suddetto","menzionato","continuare","prosegui",
           "riprendi","ripeti","precedente","scorso","altra","altro",
           "mio","mia","miei","mie","tuo","tua","tuoi","tue","suo","sua","suoi","sue",
           "prossimo","prossima","prossimi","prossime",
           "ricordi","ricordami",
           "ieri",
           "quel","quello","quella","quei","quegli",
           "prima","allora",
           "discussione","discussioni","discorso",
           "ho speso","ho comprato","ho pagato","ho fatto","ho detto",
           "spese","spesa","comprato","comprata","pagato","pagata",
           "acquisto","acquisti","costo","costato","prezzo","prezzi",
           "bolletta","bollette","resoconto","riepilogo","storico",
           "bilancio","totale","quanto mi","quanto ho","che hai",
           "transazione","transazioni","abbonamento","abbonamenti",
           "fattura","dottore","medico","mi hai detto","appuntamento",
           "preferito","preferita","preferenze","preferiti"},
    "en": {"he","him","she","her","they","them","continue","proceed",
           "repeat","resume","previous","earlier","above","aforementioned",
           "mentioned","another",
           "my","mine","your","yours","our","ours",
           "next",
           "remember",
           "yesterday",
           "that","those",
           "before","then",
           "discussion","discussions","discourse",
           "spent","spending","bought","purchased","paid","payment",
           "cost","price","prices","bill","bills","invoice",
           "expense","expenses","summary","report","balance",
           "how much","how many","did i","have i","transaction",
           "subscription","subscriptions","receipt",
           "doctor","appointment","favorite","preferences",
           "you told me","you said","last week","remind me","my data"},
    "de": {"er","ihn","ihm","sie","ihr","fortsetzen","weiter","wiederholen",
           "vorherige","vorher","erwähnt","besagt","obig","letzte","gestrig",
           "mein","meine","dein","deine","sein","seine",
           "nächst","nächste",
           "erinnere",
           "jener","jene",
           "damals",
           "Diskussion","Diskussionen","Diskurs",
           "ausgegeben","gekauft","bezahlt","kosten","preis","rechnung",
           "ausgaben","zusammenfassung","bericht","bilanz","wie viel",
           "habe ich","transaktion","abonnement","verlauf","beleg",
           "quittung","zahlung","arzt","termin","letztes mal",
           "letzte woche","mein konto","meine daten"},
    "fr": {"il","lui","elle","ils","elles","continuer","répéter","poursuivre",
           "reprendre","précédent","mentionné","susdit","autre","hier",
           "mon","ma","mes","ton","ta","tes","son","sa","ses",
           "prochain","prochaine",
           "souviens",
           "ce","cet","cette",
           "avant","alors",
           "discussion","discussions","discours",
           "dépensé","acheté","payé","coût","prix","facture","factures",
           "dépenses","résumé","rapport","bilan","combien","ai-je",
           "transaction","abonnement","historique","reçu","paiement",
           "achat","achats","médecin","rendez-vous","préférences",
           "tu m'as dit","la dernière fois","la semaine dernière",
           "rappelle-moi","mon compte","mes données"},
    "es": {"él","ella","ellos","ellas","continuar","repetir","proseguir",
           "retomar","anterior","mencionado","dicho","ayer","otro","otra",
           "mi","mis","tu","tus","su","sus",
           "próximo","próxima",
           "recuerdas",
           "ese","esa","esos","esas",
           "antes","entonces",
           "discusión","discusiones","discurso",
           "gastado","comprado","pagado","coste","costo","precio",
           "factura","facturas","gastos","resumen","informe",
           "balance","cuánto","cuanto","transacción","suscripción",
           "historial","recibo","pago","médico","cita",
           "me dijiste","la última vez","la semana pasada",
           "recuérdame","mi cuenta","mis datos"},
    "pt": {"ele","ela","eles","elas","continuar","repetir","prosseguir",
           "retomar","anterior","mencionado","dito","ontem","outro","outra",
           "meu","minha","meus","minhas","teu","tua","seu","sua",
           "próximo","próxima",
           "lembra",
           "esse","essa","esses","essas",
           "antes","então",
           "discussão","discussões","discurso",
           "gasto","gastos","comprado","comprou","pagou","pago",
           "custo","preço","fatura","faturas","resumo","relatório",
           "saldo","quanto","transação","assinatura","histórico",
           "recibo","pagamento","despesa","médico","consulta",
           "você me disse","última vez","semana passada",
           "minha conta","meus dados"},
    "ja": {"彼","彼女","続ける","繰り返す","最初から","もう一度","前の","昨日",
           "前述","上記",
           "私の","あなたの",
           "次",
           "覚えて",
           "その",
           "前に",
           "議論","話し合い","談話",
           "使った","買った","支払った","費用","価格","請求書",
           "支出","概要","レポート","残高","いくら","取引",
           "サブスクリプション","履歴","領収書","支払い","購入",
           "医者","予約","前回","先週","データ"},
    "ko": {"그","그녀","계속하다","반복하다","다시","이전","어제","앞서",
           "위","앞의",
           "내","나의","너의",
           "다음",
           "기억해",
           "그",
           "전에",
           "논의","토론","담화",
           "썼다","샀다","지불했다","비용","가격","청구서",
           "지출","요약","보고서","잔액","얼마","거래",
           "구독","기록","영수증","지불","구매","의사",
           "예약","지난번","지난주","데이터"},
    "zh": {"他","她","继续","重复","再来","之前的","昨天","上述","前面",
           "我的","你的",
           "下一个",
           "记得",
           "那个",
           "之前",
           "讨论","谈话","话题",
           "花了","买了","支付了","费用","价格","账单",
           "支出","摘要","报告","余额","多少","交易",
           "订阅","历史","收据","付款","购买","医生",
           "预约","上次","上周","数据"},
}


def needs_memory(prompt, lang="it"):
    """Return True if the prompt likely needs conversation history.

    Returns False only when the prompt is certifiably standalone
    (matches compute/time/lang tool keywords), meaning it's safe to
    skip memory injection.  Defaults to True (conservative).
    """
    keywords = load_keywords(lang)
    prompt_lower = prompt.lower()

    # 1. Memory activation keywords → SI memory needed (prevale su standalone)
    ctx = _MEMORY_ACTIVATION_KEYWORDS.get(lang, _MEMORY_ACTIVATION_KEYWORDS["en"])
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
    result = groups or {"web"}
    print(f"[ToolGroups] prompt='{prompt[:80]}' lang={lang} -> {sorted(result)}")
    return result


def select_tool_groups_ai(prompt, tools, openai_client, model):
    """Ask AI which tools it needs. Returns set of group names. Falls back to empty set."""
    if not openai_client or not model:
        return set()
    tool_names = sorted(set(t["function"]["name"] for t in (tools or [])))
    if not tool_names:
        return set()
    tool_list = ", ".join(tool_names)

    msg = (
        f"User request: \"{prompt[:500]}\"\n\n"
        f"Available tools: {tool_list}\n\n"
        f"Return ONLY the tool names needed, comma-separated. Nothing else.\n"
        f"If no tools are needed, return 'none'."
    )
    try:
        resp = openai_client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": msg}],
            temperature=0.1,
            max_tokens=100,
            extra_body={"disable_thinking": True},
        )
        text = resp.choices[0].message.content.lower()
        requested = {t.strip() for t in text.split(",") if t.strip() and t.strip() != "none"}
        groups = {TOOL_TO_GROUP[t] for t in requested if t in TOOL_TO_GROUP}
        if groups:
            print(f"[ToolGroups-AI] prompt='{prompt[:60]}' -> {sorted(groups)}")
        return groups
    except Exception as e:
        print(f"[ToolGroups-AI] Error: {e}")
        return set()


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
