"""Conversation memory management for VASS — context assembly, trimming, summarization."""
import json
import os
import threading
import time

from utils import call_with_retry, cleanup_orphan_files


class MemoryManager:
    def __init__(self, allowed_root, openai_client, system_message="",
                 language="en", memory_tokens=2000, overflow_strategy="truncate",
                 lock=None):
        self._root = allowed_root
        self._client = openai_client
        self._system_message = system_message
        self._language = language
        self._tokens = int(memory_tokens) if memory_tokens else 2000
        self._overflow = overflow_strategy
        self._lock = lock
        self._notes = []
        self._tokenizer = None
        self._summary_cache = {}
        self._ensure_files()

    def _ensure_files(self):
        dir_path = self._root
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)
            print(f"[Memory] Created directory {dir_path}")
        mem_dir = os.path.join(dir_path, "memory")
        if not os.path.exists(mem_dir):
            os.makedirs(mem_dir)
        path = os.path.join(dir_path, "memory.json")
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"history": []}, f, indent=2)
            print(f"[Memory] Created empty {path}")

    def _get_tokenizer(self):
        if self._tokenizer is not None:
            return self._tokenizer
        try:
            import tiktoken
            self._tokenizer = tiktoken.get_encoding("cl100k_base")
        except Exception:
            self._tokenizer = None
        return self._tokenizer

    def count_tokens(self, text):
        tok = self._get_tokenizer()
        if tok:
            try:
                return len(tok.encode(text))
            except Exception:
                pass
        return len(text) // 2

    def inject(self, text):
        self._notes.append(text)

    def inject_memory(self, text):
        if not text:
            return "error: text required"
        import hashlib
        from datetime import datetime, timezone
        mid = hashlib.sha256((text + str(time.time())).encode()).hexdigest()[:12]
        mf = os.path.join(self._root, "memory", f"{mid}.json")
        ts = datetime.now(timezone.utc).isoformat()
        with open(mf, "w", encoding="utf-8") as f:
            json.dump({"id": mid, "info": text, "role": "assistant", "timestamp": ts}, f, ensure_ascii=False, indent=2)
        mem_path = os.path.join(self._root, "memory.json")
        if os.path.exists(mem_path):
            with open(mem_path, encoding="utf-8") as f:
                mem_data = json.load(f)
            mem_data.setdefault("history", []).append(mid)
            if len(mem_data["history"]) > 100:
                mem_data["history"] = mem_data["history"][-100:]
            with open(mem_path, "w", encoding="utf-8") as f:
                json.dump(mem_data, f, ensure_ascii=False, indent=2)
        return mid

    def build_prompt(self, mcp=None):
        mem_path = os.path.join(self._root, "memory.json")
        mem_dir = os.path.join(self._root, "memory")
        if not os.path.exists(mem_path):
            return ""
        with open(mem_path, encoding="utf-8") as f:
            mem_data = json.load(f)
        history_ids = mem_data.get("history", [])
        if not history_ids:
            return ""
        recent = history_ids[-20:]
        parts = []
        merged_ids = set()
        for mid in recent:
            hf = os.path.join(mem_dir, f"{mid}.json")
            if not os.path.exists(hf):
                continue
            try:
                with open(hf, encoding="utf-8") as f:
                    raw = json.load(f)
                info = raw.get("info", "")
                role = raw.get("role", "system")
                if role == "system":
                    existing = raw
                else:
                    existing = None
                if existing:
                    mem_id = existing.get("id", mid)
                    merged_ids.add(mem_id)
                    if "summary_id" in existing:
                        mem = existing
                        mem["summary_id"] = existing["summary_id"]
                    parts.append(f"{role}: {info}")
                    continue
                summary_text = "No Info"
                summary_id = mem_data.get("summary_id", "")
                if summary_id:
                    sf_path = os.path.join(mem_dir, f"{summary_id}.json")
                    if os.path.exists(sf_path):
                        try:
                            with open(sf_path, encoding="utf-8") as sf:
                                summary_text = json.load(sf).get("info", "")
                        except Exception:
                            pass
                    if summary_text and summary_text != "No Info":
                        cached = self._summary_cache.get(summary_id)
                        if cached:
                            summary_text = cached
                        elif self.count_tokens(summary_text) > 500:
                            summary_text = self._compress_summary(summary_text, summary_id, mem_data)
                            if summary_text:
                                self._summary_cache[summary_id] = summary_text
                parts.append(f"summary : {summary_text}")
            except Exception:
                pass
        if merged_ids:
            try:
                cleanup_orphan_files(mem_dir, merged_ids, mem_data.get("summary_id", ""))
            except Exception:
                pass
        return "\n\n[Memory]\n" + "\n".join(parts) + "\n[/Memory]" if parts else ""

    def _compress_summary(self, summary_text, summary_id, mem_data):
        try:
            resp = call_with_retry(lambda: self._client.chat.completions.create(
                model=mem_data.get("model", "gpt-3.5-turbo"),
                messages=[{"role": "user", "content": f"Condense this summary to under 500 tokens. Output ONLY the condensed text, no markdown.\n\n{summary_text}"}],
                temperature=0.1,
                max_tokens=500,
            ), log_prefix="[Summary]")
            compressed = (resp.choices[0].message.content or "").strip()
            if compressed:
                print(f"[Summary] Compressed {len(summary_text)} -> {len(compressed)} chars")
                mem_dir = os.path.join(self._root, "memory")
                sf_path = os.path.join(mem_dir, f"{summary_id}.json")
                with open(sf_path, "w", encoding="utf-8") as sf:
                    json.dump({"info": compressed}, sf, ensure_ascii=False, indent=2)
                return compressed
        except Exception as e:
            print(f"[Summary] Compress error: {e}")
        return summary_text

    def _summarize_chunk(self, text):
        try:
            resp = call_with_retry(lambda: self._client.chat.completions.create(
                model=getattr(self, '_model', 'gpt-3.5-turbo'),
                messages=[{"role": "user", "content": f"Summarize this text concisely:\n\n{text}"}],
                temperature=0.3,
                max_tokens=500,
            ), log_prefix="[Chat]")
            return (resp.choices[0].message.content or "").strip()
        except Exception:
            return text[:1000]

    def trim_if_needed(self, messages):
        if self._overflow == "truncate":
            total = sum(self.count_tokens(m.get("content", "")) for m in messages)
            limit = self._tokens
            while total > limit and len(messages) > 2:
                removed = messages.pop(0)
                total -= self.count_tokens(removed.get("content", ""))
            return messages
        return messages

    def get_notes(self):
        return list(self._notes)

    def clear_notes(self):
        self._notes.clear()

