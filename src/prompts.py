"""Prompts, stopwords, and text compression for VASS AI interactions."""
import os
import re


MEMORY_SUMMARIZATION_PROMPT = (
    "Summarize these conversations concisely. "
    "All entries contain personal user data — extract and merge the key facts. "
    "Output only a short JSON summary with key 'summary'."
)

MCP_PROMPT = (
    "\n\nYou have MCP tools. Use them automatically for these tasks:"
    "\n- When the user asks to visit, open, download, or read a web page or URL, call browse(url) or webfetch(url)"
    "\n- When the user asks to search the web, call websearch(query)"
    "\n- browse(url): reads text from any web page (fast)"
    "\n- webfetch(url): reads JavaScript pages using a full browser (slower)"
    "\n- websearch(query): searches DuckDuckGo, returns JSON"
    "\n- read_file(path): reads files from user storage"
    "\n- write_file(path, content): writes files to user storage"
    "\n- current_time(): gets current date and time"
    "\n\nIMPORTANT: You CAN access the internet. When asked to get web content, "
    "call the tool immediately. Never reply that you cannot access websites."
)

VASSCRIPT_TOOLS_PROMPT = (
    "\n- interact(code): run VASScript code (e.g. interact(\"say('hello')\") speaks via TTS)"
)

_STOPWORDS = {
    "it": {"il","lo","la","i","gli","le","un","uno","una","l","dell","dell'",
           "di","a","da","in","con","su","per","tra","fra","del","dei","degli","della","delle",
           "e","ma","o","che","se","né","ed","non","si","ci","vi","ne",
           "è","sono","era","erano","ho","ha","hanno","sta","stanno","può","possono",
           "solo","anche","ancora","più","meno","molto","pochi","sua","loro","nostro",
           "questi","questa","questo","quelle","quelli","quella","quello"},
    "en": {"the","a","an","of","in","on","at","to","for","with","by","from","as","is","was",
           "are","were","be","been","being","have","has","had","do","does","did","will","would",
           "can","could","should","may","might","shall","it","its","and","but","or","not","no",
           "so","if","than","then","that","this","these","those","just","only","also","very",
           "some","any","each","every","all","both","few","more","most","other","such"},
    "de": {"der","die","das","ein","eine","einer","eines","einem","einen","den","dem","des",
           "in","auf","zu","von","mit","bei","für","aus","durch","gegen","ohne","um","bis",
           "ist","sind","war","waren","hat","haben","wird","werden","kann","können",
           "und","oder","aber","nicht","nur","auch","noch","schon","sehr","wie","so","als",
           "dass","wenn","weil","diese","dieser","dieses","jene","jener","jenes"},
    "es": {"el","la","los","las","un","una","unos","unas","de","del","en","con","por","para",
           "es","son","era","eran","ha","han","está","están","puede","pueden","y","o","pero",
           "no","si","que","se","lo","le","su","sus","este","esta","estos","estas","ese","esa",
           "solo","más","muy","poco","mucho","cada","todo","alguno","ninguno","otro"},
    "fr": {"le","la","les","l","un","une","des","de","du","à","au","aux","en","dans","sur",
           "par","pour","avec","sans","sous","est","sont","était","étaient","a","ont","peut",
           "peuvent","et","ou","mais","ne","pas","se","que","qui","ce","cette","ces","son","sa",
           "ses","leur","leurs","tout","tous","très","plus","moins","chaque","autre"},
    "pt": {"o","a","os","as","um","uma","uns","umas","de","do","da","dos","das","em","no","na",
           "nos","nas","com","por","para","é","são","era","eram","tem","têm","pode","podem",
           "e","ou","mas","não","se","que","este","esta","estes","estas","esse","essa","seu",
           "sua","seus","suas","todo","todos","muito","mais","menos","cada","outro","algum"},
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


def _compress_heuristic(text, lang="en"):
    stopwords = _STOPWORDS.get(lang, _STOPWORDS["en"])
    negations = _NEGATION_WORDS.get(lang, set())
    words = text.split()
    return ' '.join(w for w in words
        if w.lower().strip("',.!?;:()[]\"") not in stopwords
        or w.lower().strip("',.!?;:()[]\"") in negations)


SAVETAGS_PROMPT = (
    "IMPORTANT: After every response, you MUST call savetags() to classify "
    "the user's message with tags from this list ONLY, select only the two most relevant accordingly to the message: "
    "personal_data, health, finance, family, pets, contacts, "
    "preferences, personal_interests, purchases, orders, bills, invoices, "
    "work, education, favorite_music, food, home, "
    "personal_means_of_transport, deliveries, travel, tech, events, sales, generic. "
    "Pass them as comma-separated string: savetags('food,health')\n\n"
)


def _load_vascript_reference():
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Allowed_root", "VASCRIPT_REFERENCE.md")
    try:
        with open(path, encoding="utf-8") as f:
            content = f.read()
        return f"\n\n--- VASScript Reference ---\n{content}\n--- End Reference ---\n"
    except Exception:
        return ""
