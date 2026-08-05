"""Prompts, stopwords, and text compression for VASS AI interactions."""
import os
import re


MEMORY_SUMMARIZATION_PROMPT = (
    "Summarize these conversations concisely. "
    "All entries contain personal user data — extract and merge the key facts. "
    "Include dates in YYYY-MM-DD format for all events, purchases, payments, and deadlines. "
    "Be specific with amounts, names, and dates. No fluff. "
    "Output only a short JSON summary with key 'summary'."
)

MCP_PROMPT = (
    "\n\nYou have tools available for web and file access — see the attached tool list below."
    "\n\nHOW TO SEARCH (decision tree — choose the right path):"
    "\n1. USER GAVE A URL: call webfetch(url) or browse(url) directly. Do NOT search first."
    "\n2. USER NAMED A SITE + wants specific info: use websearch with 'site:domain.com' operator."
    "\n   Example: user says 'find me a 4K monitor on asus.com' -> websearch('site:asus.com 4K monitor')"
    "\n   Example: user says 'check prices on amazon.it' -> websearch('site:amazon.it product name')"
    "\n3. USER WANTS TO BROWSE A CATALOG: call webfetch(site_homepage) first, "
    "\n   extract product links, then webfetch each product page. Chain calls."
    "\n4. GENERIC WEB SEARCH (no site mentioned): websearch(query) -> evaluate results -> "
    "\n   webfetch the 2-3 most promising URLs -> compose answer from full pages."
    "\n\nFILE TOOLS:"
    "\n- read_file(path): reads any file from the user's storage"
    "\n- write_file(path, content): writes content to a file. Use this to save search results, notes, or data."
    "\n  Always call write_file when the user asks you to save, store, or write data to a file."
    "\n- html_to_pdf(html, filename): creates a PDF from HTML content. Use when asked to create a document, report, or PDF."
    "\n  The html must be a complete HTML document. The filename is without extension (auto-renames if exists)."
    "\n\nCRITICAL RULES:"
    "\n- NEVER answer from search snippets alone. Always webfetch the best results first."
    "\n- When a user mentions a specific website, ALWAYS use 'site:domain.com' in the search query."
    "\n- If the first search is insufficient, try alternative keywords or broader queries."
    "\n- You CAN access the internet. Call tools immediately. Never say you cannot browse websites."
    "\n- When asked to write/save/store data, ALWAYS use write_file. Do not just describe the data — write it."
    "\n- When asked to reply/send/forward an email: use search_emails() + reply_email(). Never write email text yourself."
)

VASSCRIPT_TOOLS_PROMPT = (
    "\n- interact(code): run VASScript code (e.g. interact(\"say('hello')\") speaks via TTS)"
)


def append_tool_descriptions(base_prompt, tools):
    parts = [base_prompt]
    for t in tools:
        fn = t.get("function", t)
        name = fn.get("name", "")
        desc = fn.get("description", "")
        if name:
            parts.append(f"\n- {name}: {desc}")
    return "".join(parts)

_STOPWORDS = {
    "it": {"il","lo","la","i","gli","le","l","dell","dell'",
           "di","a","da","con","su","del","dei","degli","della","delle",
           "e","ma","o","che","se","né","ed","non","si","ci","vi","ne",
           "è","sono","era","erano","ho","ha","hanno","sta","stanno","può","possono",
           "solo","anche","ancora","sua","loro","nostro",
           "questi","questa","questo","quelle","quelli","quella","quello"},
    "en": {"the","a","an","of","on","at","to","for","with","from","as","is","was",
           "are","were","be","been","being","have","has","had","do","does","did","will","would",
           "can","could","should","may","might","shall","it","its","and","but","or","not","no",
           "so","if","than","then","that","this","these","those","just","only","also","very",
           "some","any","each","every","all","both","other","such"},
    "de": {"der","die","das","ein","eine","einer","eines","einem","einen","den","dem","des",
           "auf","zu","von","mit","bei","für","aus","gegen","ohne","um","bis",
           "ist","sind","war","waren","hat","haben","wird","werden","kann","können",
           "und","oder","aber","nicht","nur","auch","noch","schon","wie","so","als",
           "dass","wenn","weil","diese","dieser","dieses","jene","jener","jenes"},
    "es": {"el","la","los","las","de","del","con","para",
           "es","son","era","eran","ha","han","está","están","puede","pueden","y","o","pero",
           "no","si","que","se","lo","le","su","sus","este","esta","estos","estas","ese","esa",
           "solo","alguno","ninguno","otro"},
    "fr": {"le","la","les","l","des","de","du","à","au","aux","en","dans","sur",
           "pour","avec","sans","sous","est","sont","était","étaient","a","ont","peut",
           "peuvent","et","ou","mais","ne","pas","se","que","qui","ce","cette","ces","son","sa",
           "ses","leur","leurs","autre"},
    "pt": {"o","a","os","as","de","do","da","dos","das","em","no","na",
           "nos","nas","com","para","é","são","era","eram","tem","têm","pode","podem",
           "e","ou","mas","não","se","que","este","esta","estes","estas","esse","essa","seu",
           "sua","seus","suas","outro","algum"},
    "ja": {"は","が","を","に","で","の","へ","と","から","まで","より","です","ます","した",
           "して","する","いる","ある","ない","こと","もの","ため","よう","そう","これ","それ",
           "あれ","この","その","あの","ここ","そこ","あそこ"},
    "ko": {"은","는","이","가","을","를","에","의","에서","으로","로","과","와","입니다","한다",
           "하는","하고","있는","있다","없다","것","수","그","이","저","이런","그런","저런","여기",
           "거기","저기","에서","까지","부터"},
    "zh": {"的","了","是","在","和","也","就","都","这","那","个","种","之","以","及","与",
           "或","但","不","很","更","最","还","要","会","能","可以","对","向","从","被","把",
           "上","下","中","里","而","已","其","此","该","什么","怎么","哪","哪里"},
}


# Words that must NEVER be removed, even if they appear in _STOPWORDS,
# because they carry semantic negation that would invert meaning.
_NEGATION_WORDS = {
    "it": {"non", "né", "neanche", "nemmeno", "senza"},
    "en": {"not", "no", "neither", "nor", "without", "never"},
    "de": {"nicht", "kein", "keine", "keiner", "weder", "noch", "ohne"},
    "fr": {"ne", "pas", "ni", "sans", "jamais", "aucun"},
    "es": {"no", "ni", "sin", "nunca", "jamás", "ningún"},
    "pt": {"não", "nem", "sem", "nunca", "jamais", "nenhum"},
    "ja": {"ない", "ません", "ず", "ぬ"},
    "ko": {"안", "못", "않", "없다"},
    "zh": {"不", "没", "无", "别", "非"},
}

# Words that must NEVER be removed, even if they appear in _STOPWORDS,
# because they are negation markers, math operators, quantifiers, or
# temporal references essential to meaning.
_PROTECTED_WORDS = {
    "it": {"più", "meno", "molto", "pochi", "per", "diviso", "volte",
           "uno", "una", "un", "fra", "tra", "in"},
    "en": {"more", "most", "few", "less", "over", "by", "times",
           "fra", "tra", "in"},
    "de": {"sehr", "mehr", "mal", "durch",
           "fra", "tra", "in"},
    "fr": {"plus", "moins", "très", "peu", "beaucoup", "chaque", "tout",
            "par", "fois", "tous", "plusieurs",
            "un", "une",
            "fra", "tra", "in"},
    "es": {"más", "menos", "muy", "poco", "mucho", "cada", "todo",
            "por", "veces",
            "un", "una", "unos", "unas",
            "fra", "tra", "in"},
    "pt": {"mais", "menos", "muito", "cada", "todo", "todos", "por", "vezes",
           "um", "uma", "uns", "umas",
           "fra", "tra", "in"},
    "ja": {"fra", "tra", "in"},
    "ko": {"fra", "tra", "in"},
    "zh": {"fra", "tra", "in"},
}


def _compress_heuristic(text, lang="en"):
    stopwords = _STOPWORDS.get(lang, _STOPWORDS["en"])
    protected = _NEGATION_WORDS.get(lang, set()) | _PROTECTED_WORDS.get(lang, set())
    words = text.split()
    return ' '.join(w for w in words
        if w.lower().strip("',.!?;:()[]\"") not in stopwords
        or w.lower().strip("',.!?;:()[]\"") in protected)




def _load_vascript_reference():
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Allowed_root", "VASCRIPT_REFERENCE.md")
    try:
        with open(path, encoding="utf-8") as f:
            content = f.read()
        return f"\n\n--- VASScript Reference ---\n{content}\n--- End Reference ---\n"
    except Exception:
        return ""
