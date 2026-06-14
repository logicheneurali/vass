#!/usr/bin/env python3
"""VASS LLM Benchmark — senza MCP tools per semplicita'."""

import urllib.request, json, time, os
from datetime import datetime

LLAMACPP_URL = "http://127.0.0.1:8080"
BENCHMARK_FILE = r"C:\Users\effed\Documents\Python\benchmarks.txt"

PRESIDENTS = [
    "De Gasperi", "Pella", "Fanfani", "Scelba", "Segni", "Zoli",
    "Fanfani", "Segni", "Tambroni", "Leone", "Moro",
    "Rumor", "Colombo", "Andreotti", "Cossiga", "Forlani", "Spadolini",
    "Fanfani", "Craxi", "Goria", "De Mita", "Andreotti", "Amato", "Ciampi",
    "Berlusconi", "Dini", "Prodi", "DAlema", "Amato", "Berlusconi",
    "Prodi", "Berlusconi", "Monti", "Letta", "Renzi", "Gentiloni",
    "Conte", "Draghi", "Meloni"
]

PROMPTS = [
    ("time", "Che ora sono?"),
    ("math", "Quanto fa 2+2? Rispondi solo con il numero."),
    ("history", "Elencami i presidenti del consiglio italiani dalla nascita della repubblica italiana a oggi"),
    ("tools", "Quale e' il prossimo evento in programma? Puoi usare gli strumenti disponibili."),
]


def _call(model, prompt, max_tokens=512):
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.1,
        "stream": False,
    }
    t0 = time.time()
    req = urllib.request.Request(
        f"{LLAMACPP_URL}/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        r = urllib.request.urlopen(req, timeout=120)
        data = json.loads(r.read())
        elapsed = time.time() - t0
        choice = data.get("choices", [{}])[0]
        text = (choice.get("message", {}).get("content", "") or "").strip()
        tokens = data.get("usage", {}).get("completion_tokens", 0)
        finish = choice.get("finish_reason", "?")
        return {"ok": True, "text": text, "time": elapsed, "tokens": tokens, "finish": finish}
    except Exception as e:
        return {"ok": False, "error": str(e), "time": time.time() - t0}


def _score(prompt_key, text):
    tl = text.lower()
    if prompt_key == "time":
        return 10 if any(w in tl for w in ["ora", "sono", "time", ":"]) and len(text) > 5 else 3 if len(text) > 3 else 0
    if prompt_key == "math":
        return 10 if "4" in text.replace(" ", "") else 0
    if prompt_key == "history":
        found = sum(1 for p in PRESIDENTS if p.lower() in tl)
        return min(10, found * 10 // 20)
    if prompt_key == "tools":
        return 5 if len(text) > 10 else 0
    return 0


def run():
    out = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sep = "=" * 70
    out.append(sep)
    out.append(f"VASS LLM Benchmark - {now}")
    out.append(sep)

    try:
        r = urllib.request.urlopen(f"{LLAMACPP_URL}/v1/models", timeout=5)
        models = [m["id"] for m in json.loads(r.read()).get("data", [])]
    except Exception as e:
        out.append(f"Error fetching models: {e}")
        return "\n".join(out)

    out.append(f"Models: {len(models)}")
    out.append(f"Prompts: {len(PROMPTS)}")
    out.append(sep)

    results = []

    for mi, model in enumerate(models):
        m_header = f"[{mi+1}/{len(models)}] {model}"
        out.append(m_header)
        print(m_header, flush=True)
        mr = {"model": model, "prompts": {}}

        for pk, prompt in PROMPTS:
            r = _call(model, prompt)
            if not r["ok"]:
                out.append(f"  [{pk}] ERROR: {r['error'][:120]}")
                mr["prompts"][pk] = {"error": r["error"][:120]}
                print(f"  [{pk}] ERROR", flush=True)
                continue

            score = _score(pk, r["text"])
            tps = r["tokens"] / r["time"] if r["time"] > 0 else 0
            out.append(f"  [{pk}] {r['time']:.1f}s {r['tokens']}tk {tps:.1f}t/s score={score} finish={r['finish']}")
            out.append(f"  [{pk}] {r['text'][:200]}")
            print(f"  [{pk}] {score}/10", flush=True)
            mr["prompts"][pk] = {"time": round(r["time"], 2), "tokens": r["tokens"], "score": score}

        counts = [v.get("score", 0) for v in mr["prompts"].values()]
        mr["avg"] = round(sum(counts) / max(len(counts), 1), 1)
        out.append(f"  AVG: {mr['avg']}/10")
        out.append("")
        results.append(mr)

    out.append(sep)
    out.append("SUMMARY")
    out.append(sep)
    out.append(f"{'Model':<45} {'Score':>6} {'Time':>8}")
    out.append("-" * 62)
    for r in sorted(results, key=lambda x: x["avg"], reverse=True):
        total_time = sum(v.get("time", 0) for v in r["prompts"].values())
        out.append(f"{r['model']:<45} {r['avg']:>5.1f}/10 {total_time:>7.1f}s")

    avg_all = sum(r["avg"] for r in results) / max(len(results), 1)
    out.append("-" * 62)
    out.append(f"AVERAGE: {avg_all:.1f}/10 across {len(results)} models")
    out.append(sep)

    text = "\n".join(out)
    with open(BENCHMARK_FILE, "w", encoding="utf-8") as f:
        f.write(text)
    return text


if __name__ == "__main__":
    print(run())
