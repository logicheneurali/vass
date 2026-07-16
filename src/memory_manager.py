"""Memory management for VASS — conversation history, tags, classification, and trimming."""
import json
import os
import threading
import time
from utils import get_project_root, get_path, log_exc


class MemoryManager:
    def __init__(self, app):
        self._app = app
        self._pending_classify = []       # {content, entry_id, source}
        self._memory_sources = {}          # loaded from memory_sources.json
        self._summary_cache = {}           # compressed summary cache
        self._trim_lock = threading.Lock()

    @property
    def _ai_lock(self):
        return self._app._ai_lock

    def load_sources(self):
        """Load source toggle state and files config."""
        path = get_path("Allowed_root", "memory_sources.json")
        try:
            with open(path, encoding="utf-8") as f:
                self._memory_sources = json.load(f)
        except Exception:
            self._memory_sources = {"email": False, "calendar": False,
                                     "events": False, "timers": False}
        self._load_files_config()

    def _load_files_config(self):
        """Load files folder list and scan settings."""
        path = get_path("Allowed_root", "memory_files_config.json")
        try:
            with open(path, encoding="utf-8") as f:
                self._files_config = json.load(f)
        except Exception:
            self._files_config = {"folders": [], "interval_minutes": 60, "max_file_size_kb": 500}

    def is_source_enabled(self, source):
        return self._memory_sources.get(source, False)

    def start_deferred_loop(self):
        threading.Thread(target=self._classify_deferred_loop, daemon=True).start()

    def build_content(self, prompt, mcp=None, tools=None):
        """Return conversation history + external tagged data as context string."""
        content = self._build_memory_content(mcp, tools)
        external = self._build_external_memory_content(prompt)
        if external:
            content += external
        return content

    def classify_message(self, user_message):
        self._classify_message(user_message)

    def enqueue_external(self, content, entry_id, source):
        self._enqueue_classify(content, entry_id, source)

    def trim_if_needed(self, force=False):
        self._trim_memory_if_needed(force)

    # ── Internal methods ────────────────────────────────────────────────

    def _build_memory_content(self, mcp=None, tools=None):
        if self._app.memory_mode == "none":
            return ""
        root = get_project_root()
        mem_path = os.path.join(root, "Allowed_root", "memory.json")
        if not os.path.exists(mem_path):
            return ""
        try:
            with open(mem_path, encoding="utf-8") as f:
                mem_data = json.load(f)
        except Exception:
            return ""
        parts = []
        if self._app.memory_mode == "full":
            summary_text = "No Info"
            summary_id = mem_data.get("summary_id", "")
            if summary_id:
                sf_path = os.path.join(root, "Allowed_root", "memory", f"{summary_id}.json")
                if os.path.exists(sf_path):
                    try:
                        with open(sf_path, encoding="utf-8") as sf:
                            summary_text = json.load(sf).get("info", "")
                    except Exception:
                        log_exc()
                if summary_text and summary_text != "No Info":
                    if summary_text.startswith("writeinfo("):
                        try:
                            inner = summary_text[len("writeinfo("):]
                            if inner.startswith("'") and inner.endswith("')"):
                                inner = inner[1:-2]
                            summary_text = json.loads(inner).get("summary", summary_text)
                        except Exception:
                            log_exc()
                    cached = self._summary_cache.get(summary_id)
                    if cached:
                        summary_text = cached
                    elif self._app._count_tokens(summary_text) > 1000:
                        summary_text = self._compress_summary(summary_text, summary_id, mem_data)
                        if summary_text:
                            self._summary_cache[summary_id] = summary_text
            parts.append(f"summary : {summary_text}")
        for vid in mem_data.get("history", []):
            hf_path = os.path.join(root, "Allowed_root", "memory", f"{vid}.json")
            if os.path.exists(hf_path):
                try:
                    with open(hf_path, encoding="utf-8") as hf:
                        entry = json.load(hf).get("info", "")
                    entry_data = json.loads(entry)
                    role = "user" if entry_data.get("role") == "user" else "assistant"
                    parts.append(f"{role}: {entry_data['content']}")
                except Exception:
                    log_exc()
        if parts:
            return "\n\nPrevious conversations:\n" + "\n".join(parts)
        return ""

    def _build_external_memory_content(self, prompt):
        """Return tagged entries from active external sources matching prompt keywords."""
        root = get_project_root()
        tags_path = os.path.join(root, "Allowed_root", "memory_tags.json")
        if not os.path.exists(tags_path):
            return ""
        try:
            with open(tags_path, encoding="utf-8") as f:
                tags_data = json.load(f)
        except Exception:
            return ""
        active = {src for src, en in self._memory_sources.items() if en}
        if not active:
            return ""

        ai_tags = self._classify_prompt_tags(prompt)
        tagged_entries = tags_data.get("entries", [])
        matches = []
        for entry in tagged_entries:
            src = entry.get("source", "chat")
            if src == "chat" or src not in active:
                continue
            entry_tags = entry.get("tags", [])
            if ai_tags:
                if any(t in ai_tags for t in entry_tags):
                    matches.append(entry)
            else:
                prompt_lower = prompt.lower()
                if any(t in prompt_lower or t.replace("_", " ") in prompt_lower for t in entry_tags):
                    matches.append(entry)
        if not matches:
            return ""

        matches.sort(key=lambda e: e.get("relevance", 0), reverse=True)
        max_entries = self._memory_sources.get("max_external_entries", 3)
        top = self._hybrid_rank(matches, prompt, max_entries)
        parts = []
        mem_dir = os.path.join(root, "Allowed_root", "memory")
        for entry in top:
            content = ""
            hf = os.path.join(mem_dir, f"{entry.get('id', '')}.json")
            if os.path.exists(hf):
                try:
                    with open(hf, encoding="utf-8") as hfp:
                        info = json.loads(json.load(hfp).get("info", "{}"))
                    content = info.get("content", "")
                except Exception:
                    log_exc()
            if not content:
                content = entry.get("content", "")
            if not content:
                continue
            content = content[:200].strip()
            tags_str = ", ".join(entry.get("tags", []))
            src = entry.get("source", entry.get("source", "unknown"))
            parts.append(f"[{src}] [{tags_str}]: {content}")
        if parts:
            return "\n\nRelevant stored information (use if helpful):\n" + "\n".join(parts)
        return ""

    def _classify_prompt_tags(self, prompt):
        """Use AI to identify relevant memory tags from user prompt.
        Returns set of tag names, or empty set if AI unavailable."""
        try:
            import sys as _sys
            _mcp_src = get_path("mcp_server", "src")
            if _mcp_src not in _sys.path:
                _sys.path.insert(0, _mcp_src)
            from mcpgoal.tools.memory_tags import TAG_WEIGHTS
            tag_list = ", ".join(sorted(TAG_WEIGHTS.keys()))
            classify_prompt = (
                f"Classify this user request with 1-3 comma-separated tags ONLY from: {tag_list}\n\n"
                f"Request: \"{prompt[:500]}\"\n\n"
                f"Return ONLY 1-3 most relevant tags, nothing else.\n"
                f"Example: I have a headache -> health\n"
                f"Example: what did I spend on Amazon? -> finance,purchases\n"
                f"Example: tell me a story -> generic"
            )
            resp = self._app.openai_client.chat.completions.create(
                model=self._app.ai_model,
                messages=[{"role": "user", "content": classify_prompt}],
                temperature=0.1,
                max_tokens=50,
                extra_body={"disable_thinking": True}
            )
            raw = (resp.choices[0].message.content or "").strip().lower()
            tags = {t.strip() for t in raw.split(",") if t.strip() and t.strip() in TAG_WEIGHTS}
            if tags:
                print(f"[Memory] Prompt tags classified: {tags}")
            return tags
        except Exception as e:
            print(f"[Memory] Prompt tag classification failed: {e}")
            return set()

    @staticmethod
    def _hybrid_rank(matches, prompt, max_entries):
        import datetime
        prompt_words = set(prompt.lower().split())
        if not prompt_words:
            return matches[:max_entries]

        today = datetime.date.today()
        scored = []
        for entry in matches:
            tag_score = entry.get("relevance", 0)

            ts = entry.get("ts", "")
            try:
                days = (today - datetime.datetime.strptime(ts, "%Y-%m-%d %H:%M").date()).days
            except Exception:
                days = 90
            recency = 1.0 + (0.5 * max(0, 1.0 - days / 365.0))

            content = (entry.get("content", "") or "").lower()
            kw_overlap = len(prompt_words & set(content.split()))
            kw_score = min(kw_overlap * 1.5, 15)

            final = tag_score * recency + kw_score
            scored.append((entry, final))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [entry for entry, _ in scored[:max_entries]]

    def _compress_summary(self, summary_text, summary_id, mem_data):
        import json as _json
        from utils import call_with_retry
        try:
            prompt = (
                "Condense this summary to under 500 tokens. "
                "Keep ALL key facts, names, dates, preferences. "
                "Output ONLY the condensed text, no JSON, no commentary.\n\n"
                f"{summary_text}"
            )
            timeout = max(20, len(summary_text) // 25)
            resp = call_with_retry(lambda: self._app.openai_client.chat.completions.create(
                model=self._app.ai_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=1000,
                timeout=timeout,
                extra_body={"disable_thinking": True}
            ), log_prefix="[Summary]")
            compressed = (resp.choices[0].message.content or "").strip()
            if compressed:
                print(f"[Summary] Compressed {len(summary_text)} -> {len(compressed)} chars")
                root = get_project_root()
                mem_dir = os.path.join(root, "Allowed_root", "memory")
                sf_path = os.path.join(mem_dir, f"{summary_id}.json")
                with open(sf_path, "w", encoding="utf-8") as sf:
                    _json.dump({"info": compressed}, sf, ensure_ascii=False, indent=2)
                return compressed
        except Exception as e:
            print(f"[Summary] Compression failed: {e}")
        return summary_text

    def _classify_message(self, user_message):
        print(f"[Classify] Starting classification for: {user_message[:80]}...")
        try:
            import sys as _sys
            _mcp_src = get_path("mcp_server", "src")
            if _mcp_src not in _sys.path:
                _sys.path.insert(0, _mcp_src)
            from mcpgoal.tools.memory_tags import _refresh_weights, TAG_WEIGHTS
            root = get_project_root()
            _refresh_weights(os.path.join(root, "Allowed_root"))
            from utils import init_mcp
            mcp, _ = init_mcp(self._app.mcp_server_url, timeout=30)
            if not mcp:
                print("[Classify] MCP not available")
                return
        except Exception as e:
            print(f"[Classify] Init error: {e}")
            return

        entry_id = ""
        assistant_text = ""
        history = []
        root = get_project_root()
        mem_path = os.path.join(root, "Allowed_root", "memory.json")
        mem_dir = os.path.join(root, "Allowed_root", "memory")
        try:
            with open(mem_path, encoding="utf-8") as f:
                mem_data = json.load(f)
            history = mem_data.get("history", [])
            if len(history) >= 2:
                entry_id = history[-1]
                user_id = history[-2]
                for vid, role_label in [(user_id, "user"), (entry_id, "assistant")]:
                    hf = os.path.join(mem_dir, f"{vid}.json")
                    if os.path.exists(hf):
                        try:
                            with open(hf, encoding="utf-8") as hfp:
                                info = json.loads(json.load(hfp).get("info", "{}"))
                            if info.get("role") == "assistant":
                                assistant_text = info.get("content", "")
                        except Exception:
                            log_exc()
            elif history:
                entry_id = history[-1]
        except Exception:
            log_exc()

        tag_list = ", ".join(sorted(TAG_WEIGHTS.keys()))
        if assistant_text:
            classify_prompt = (
                f"Classify this conversation with 1-2 comma-separated tags ONLY from: {tag_list}\n\n"
                f"User: \"{user_message[:400]}\"\n"
                f"Assistant: \"{assistant_text[:400]}\"\n\n"
                f"Rules:\n"
                f"- Return ONLY 1-2 most relevant tags, nothing else.\n"
                f"- If the conversation is generic/chatty, return ONLY 'generic'.\n"
                f"- Example travel chat: travel,personal_interests\n"
                f"- Example health question: health\n"
                f"- Example small talk: generic"
            )
        else:
            classify_prompt = (
                f"Classify this user message with 1-2 comma-separated tags ONLY from: {tag_list}\n\n"
                f"Message: \"{user_message[:500]}\"\n\n"
                f"Rules:\n"
                f"- Return ONLY 1-2 most relevant tags, nothing else.\n"
                f"- If the message is generic/chatty, return ONLY 'generic'.\n"
                f"- Example travel chat: travel,personal_interests\n"
                f"- Example health question: health\n"
                f"- Example small talk: generic"
            )
        try:
            resp = self._app.openai_client.chat.completions.create(
                model=self._app.ai_model,
                messages=[{"role": "user", "content": classify_prompt}],
                temperature=0.1,
                max_tokens=50,
                extra_body={"disable_thinking": True}
            )
            raw = (resp.choices[0].message.content or "").strip().lower()
            tags = [t.strip() for t in raw.split(",") if t.strip() and t.strip() in TAG_WEIGHTS][:2]
            if tags:
                tags_str = ",".join(tags)
                result = mcp.call_tool("savetags", {"tags": tags_str, "entry_id": entry_id})
                content = result.get("content", [{}])[0].get("text", str(result))
                print(f"[Classify] Tags: {tags} -> {content} (AI response)")
                if len(history) >= 2:
                    user_entry_id = history[-2]
                    mcp.call_tool("savetags", {"tags": tags_str, "entry_id": user_entry_id})
                    print(f"[Classify] Also tagged user entry {user_entry_id}")
            else:
                print(f"[Classify] AI returned unusable tags: '{raw}'")
        except Exception as e:
            print(f"[Classify] Error: {e}")

    def _trim_memory_if_needed(self, force=False):
        if not self._trim_lock.acquire(blocking=False):
            print("[Memory] Trim skipped: previous trim in progress, retrying in 30s")
            threading.Thread(target=lambda: (time.sleep(30), self._trim_memory_if_needed()), daemon=True).start()
            return
        try:
            from utils import call_with_retry
            root = get_project_root()
            path = os.path.join(root, "Allowed_root", "memory.json")
            mem_dir = os.path.join(root, "Allowed_root", "memory")
            if not os.path.exists(path):
                return

            try:
                with open(path, encoding="utf-8") as f:
                    old = json.load(f)
            except Exception:
                return

            history_ids = old.get("history", [])
            summary_id = old.get("summary_id", "")
            if not history_ids:
                return

            total_size = os.path.getsize(path)
            for vid in history_ids:
                hf_path = os.path.join(mem_dir, f"{vid}.json")
                if os.path.exists(hf_path):
                    total_size += os.path.getsize(hf_path)
            if summary_id:
                sf_path = os.path.join(mem_dir, f"{summary_id}.json")
                if os.path.exists(sf_path):
                    total_size += os.path.getsize(sf_path)
            allowed_root = os.path.join(root, "Allowed_root")
            tags_path = os.path.join(allowed_root, "memory_tags.json")
            if os.path.exists(tags_path):
                total_size += os.path.getsize(tags_path)

            threshold = self._app.memory_tokens * 2
            if total_size < threshold and not force:
                return
            if force:
                print(f"[Memory] Force compressing (size={total_size})")
            else:
                print(f"[Memory] Total size {total_size} > threshold {threshold}, compressing...")
            mtime_before = os.path.getmtime(path)

            tagged_ids = set()
            min_rel = 10
            if os.path.exists(tags_path):
                try:
                    with open(tags_path, encoding="utf-8") as f:
                        tags_data = json.load(f)
                    # Load actual min_relevance from tags_config.json
                    cfg_path = os.path.join(allowed_root, "tags_config.json")
                    if os.path.exists(cfg_path):
                        with open(cfg_path, encoding="utf-8") as cf:
                            min_rel = json.load(cf).get("min_relevance", 10)
                    tagged_ids = {e["id"] for e in tags_data.get("entries", [])
                                  if e.get("relevance", 0) >= min_rel}
                except Exception:
                    log_exc()

            def _find_entry(vid):
                hf_path = os.path.join(mem_dir, f"{vid}.json")
                if os.path.exists(hf_path):
                    return hf_path
                archive_root = os.path.join(mem_dir, "archive")
                if os.path.isdir(archive_root):
                    for month_dir in os.listdir(archive_root):
                        candidate = os.path.join(archive_root, month_dir, f"{vid}.json")
                        if os.path.exists(candidate):
                            return candidate
                return None

            # Sort tagged IDs by relevance descending (most important first)
            id_relevance = {e["id"]: e.get("relevance", 0) for e in tags_data.get("entries", [])}
            tagged_ids_list = sorted(tagged_ids, key=lambda vid: id_relevance.get(vid, 0), reverse=True)
            if not tagged_ids_list:
                return

            history_content = []
            external_content = []
            for vid in tagged_ids_list[:100]:
                entry_path = _find_entry(vid)
                if entry_path:
                    try:
                        with open(entry_path, encoding="utf-8") as hf:
                            entry = json.load(hf).get("info", "")
                        history_content.append(json.loads(entry))
                    except Exception:
                        log_exc()
                else:
                    # External entry (email, event, timer) — use content from tags
                    for te in tags_data.get("entries", []):
                        if te.get("id") == vid and te.get("source", "chat") != "chat":
                            content = te.get("content", "")
                            if content:
                                external_content.append(
                                    {"role": te.get("source", "external"),
                                     "content": content})
                            break
            all_content = history_content + external_content

            if not all_content:
                print(f"[Memory] Trim skipped: no content to summarize ({len(tagged_ids_list)} tagged, min_relevance={min_rel})")
                return

            old_summary = ""
            summary_id = old.get("summary_id", "")
            if summary_id:
                sf_path = os.path.join(mem_dir, f"{summary_id}.json")
                if os.path.exists(sf_path):
                    try:
                        with open(sf_path, encoding="utf-8") as sf:
                            old_summary = json.load(sf).get("info", "")
                    except Exception:
                        log_exc()

            from prompts import MEMORY_SUMMARIZATION_PROMPT
            prompt = MEMORY_SUMMARIZATION_PROMPT
            prompt += f"\n\nTagged conversations ({len(history_content)} entries):\n" + json.dumps(history_content, ensure_ascii=False)
            if external_content:
                prompt += f"\n\nTagged external data ({len(external_content)} entries):\n" + json.dumps(external_content, ensure_ascii=False)
            prompt += "\n\nReturn ONLY a JSON object with your summary. Example: {\"summary\": \"...\"}"

            print(f"[Memory] Summarization request -> prompt_len={len(prompt)}, entries={len(history_content)}")
            resp = call_with_retry(lambda: self._app.openai_client.chat.completions.create(
                model=self._app.ai_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                extra_body={"disable_thinking": True}
            ))
            summary_text = (resp.choices[0].message.content or "").strip()
            print(f"[Memory] Summarization response -> {summary_text[:200]}")
            if not summary_text:
                print("[Memory] Trim: AI returned empty summary, skipping")
                return
            if summary_text.startswith("writeinfo("):
                try:
                    inner = summary_text[len("writeinfo("):]
                    if inner.startswith("'") and inner.endswith("')"):
                        inner = inner[1:-2]
                    summary_text = inner
                except Exception:
                    log_exc()
            try:
                parsed = json.loads(summary_text)
                if isinstance(parsed, dict) and "summary" in parsed:
                    summary_text = parsed["summary"]
                elif isinstance(parsed, str):
                    summary_text = parsed
            except (json.JSONDecodeError, ValueError):
                pass

            if os.path.getmtime(path) != mtime_before:
                print("[Memory] Trim: file modified during compression, skipping write")
                return

            new_sid = str(int(time.time() * 1000))
            sf_path = os.path.join(mem_dir, f"{new_sid}.json")
            with open(sf_path, "w", encoding="utf-8") as sf:
                json.dump({"info": summary_text}, sf, ensure_ascii=False, indent=2)

            new_history_ids = history_ids[-6:]
            new_data = {"history": new_history_ids, "summary_id": new_sid}
            with open(path, "w", encoding="utf-8") as f:
                json.dump(new_data, f, ensure_ascii=False, indent=2)

            referenced = set(new_history_ids) | {new_sid} | tagged_ids
            if summary_id:
                referenced.add(summary_id)
            now_ts = time.time()
            archive_date = time.strftime("%Y-%m", time.localtime(now_ts))
            archive_dir = os.path.join(mem_dir, "archive", archive_date)
            os.makedirs(archive_dir, exist_ok=True)
            import shutil
            for fname in os.listdir(mem_dir):
                if fname.endswith(".json"):
                    fid = fname[:-5]
                    if fid not in referenced:
                        try:
                            src = os.path.join(mem_dir, fname)
                            dst = os.path.join(archive_dir, fname)
                            shutil.move(src, dst)
                        except OSError:
                            pass

            archive_root = os.path.join(mem_dir, "archive")
            if os.path.isdir(archive_root):
                cutoff_ts = now_ts - (180 * 86400)
                for entry in os.listdir(archive_root):
                    entry_path = os.path.join(archive_root, entry)
                    if os.path.isdir(entry_path):
                        try:
                            entry_date = time.mktime(time.strptime(entry, "%Y-%m"))
                            if entry_date < cutoff_ts:
                                shutil.rmtree(entry_path)
                                print(f"[Memory] Cleaned old archive: {entry}")
                        except (ValueError, OSError):
                            pass

            # Clean orphan tag entries pointing to archived/nonexistent files
            if tags_data:
                valid_entries = []
                for te in tags_data.get("entries", []):
                    tid = te.get("id", "")
                    src = te.get("source", "chat")
                    if src == "chat" and tid not in referenced:
                        continue
                    valid_entries.append(te)
                removed = len(tags_data.get("entries", [])) - len(valid_entries)
                if removed > 0:
                    tags_data["entries"] = valid_entries
                    tags_path2 = os.path.join(allowed_root, "memory_tags.json")
                    with open(tags_path2, "w", encoding="utf-8") as f:
                        json.dump(tags_data, f, ensure_ascii=False, indent=2)
                    print(f"[Memory] Cleaned {removed} orphan tag entries")

            print(f"[Memory] Trimmed to {os.path.getsize(path)} bytes, {len(new_history_ids)} history entries kept")
        except Exception as e:
            print(f"[Memory] Trim failed: {e}")
        finally:
            self._trim_lock.release()

    def _classify_deferred_loop(self):
        """Process pending classify queue every 60s, only when AI is idle."""
        time.sleep(10)
        while self._app.running:
            time.sleep(60)
            if self._ai_lock.locked() or self._app.state == "waiting":
                continue
            if not self._pending_classify:
                continue
            batch = self._pending_classify[:5]
            del self._pending_classify[:5]
            for item in batch:
                try:
                    self._classify_external_entry(
                        item["content"], item["entry_id"], item["source"])
                except Exception as e:
                    print(f"[Classify] Deferred error: {e}")

    def _classify_external_entry(self, content, entry_id, source):
        """Classify external content and save tags. Falls back to keyword matching."""
        print(f"[Classify] External: source={source} id={entry_id} content_len={len(content)}")
        try:
            import sys as _sys, os as _os
            _mcp_src = _os.path.join(_os.path.dirname(_os.path.dirname(
                _os.path.abspath(__file__))), "mcp_server", "src")
            if _mcp_src not in _sys.path:
                _sys.path.insert(0, _mcp_src)
            from mcpgoal.tools.memory_tags import _refresh_weights, TAG_WEIGHTS, MIN_RELEVANCE
            root = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
            _refresh_weights(_os.path.join(root, "Allowed_root"))
            from utils import init_mcp
            mcp, _ = init_mcp(self._app.mcp_server_url, timeout=30)
            if not mcp:
                print("[Classify] MCP not available, using keyword fallback")
                tags = self._classify_keyword_fallback(content, TAG_WEIGHTS)
                if tags:
                    mcp2, _ = init_mcp(self._app.mcp_server_url, timeout=10)
                    if mcp2:
                        mcp2.call_tool("savetags",
                                       {"tags": ",".join(tags), "entry_id": entry_id,
                                        "source": source})
                return
        except Exception as e:
            print(f"[Classify] Init error: {e}")
            return

        tag_list = ", ".join(sorted(TAG_WEIGHTS.keys()))
        classify_prompt = (
            f"Classify this {source} content with 1-2 comma-separated tags ONLY from: {tag_list}\n\n"
            f"Content: \"{content[:500]}\"\n\n"
            f"Rules:\n"
            f"- Return ONLY 1-2 most relevant tags, nothing else.\n"
            f"- If content is generic/unclassifiable, return ONLY 'generic'.\n"
            f"- Example: travel,personal_interests\n"
            f"- Example: health\n"
            f"- Example: generic"
        )
        try:
            resp = self._app.openai_client.chat.completions.create(
                model=self._app.ai_model,
                messages=[{"role": "user", "content": classify_prompt}],
                temperature=0.1,
                max_tokens=50,
                extra_body={"disable_thinking": True}
            )
            raw = (resp.choices[0].message.content or "").strip().lower()
            tags = [t.strip() for t in raw.split(",")
                    if t.strip() and t.strip() in TAG_WEIGHTS][:2]
            if tags:
                tags_str = ",".join(tags)
                relevance = sum(TAG_WEIGHTS.get(t, 0) for t in tags)
                if relevance >= MIN_RELEVANCE:
                    summary = self._summarize_external(content, source)
                else:
                    summary = content[:300]
                    print(f"[Classify] Summary skipped: relevance {relevance} < {MIN_RELEVANCE}")
                result = mcp.call_tool("savetags",
                    {"tags": tags_str, "entry_id": entry_id, "source": source,
                     "content": summary[:300]})
                content_out = result.get("content", [{}])[0].get("text", str(result))
                print(f"[Classify] External tags: {tags} -> {content_out}")
            else:
                print(f"[Classify] External: AI returned unusable: '{raw}', fallback to keyword")
                tags = self._classify_keyword_fallback(content, TAG_WEIGHTS)
                if tags:
                    mcp.call_tool("savetags",
                        {"tags": ",".join(tags), "entry_id": entry_id, "source": source,
                         "content": content[:300]})
        except Exception as e:
            print(f"[Classify] External error: {e}, fallback to keyword")
            try:
                import sys as _sys2, os as _os2
                _mcp_src2 = _os2.path.join(_os2.path.dirname(_os2.path.dirname(
                    _os2.path.abspath(__file__))), "mcp_server", "src")
                if _mcp_src2 not in _sys2.path:
                    _sys2.path.insert(0, _mcp_src2)
                from mcpgoal.tools.memory_tags import TAG_WEIGHTS as TW2
                tags = self._classify_keyword_fallback(content, TW2)
                if tags:
                    mcp2, _ = init_mcp(self._app.mcp_server_url, timeout=10)
                    if mcp2:
                        mcp2.call_tool("savetags",
                            {"tags": ",".join(tags), "entry_id": entry_id, "source": source})
            except Exception:
                log_exc()

    def _summarize_external(self, content, source):
        """Generate a concise 1-2 sentence summary with key facts from external content."""
        try:
            source_label = {"email": "email", "events": "event", "calendar": "calendar event",
                            "files": "file", "timers": "timer"}.get(source, source)
            summary_prompt = (
                f"Summarize this {source_label} in 1-2 sentences. "
                f"Extract key facts: dates (in YYYY-MM-DD format), amounts, names, actions, decisions. "
                f"Be specific with numbers and dates. No fluff, no commentary. "
                f"Output ONLY the summary, nothing else.\n\n{content[:2000]}"
            )
            resp = self._app.openai_client.chat.completions.create(
                model=self._app.ai_model,
                messages=[{"role": "user", "content": summary_prompt}],
                temperature=0.1,
                max_tokens=200,
                extra_body={"disable_thinking": True}
            )
            summary = (resp.choices[0].message.content or "").strip()
            if summary:
                print(f"[Classify] Summary ({len(summary)} chars): {summary[:120]}...")
                return summary
        except Exception as e:
            print(f"[Classify] Summary failed: {e}")
        return content[:300]

    def _classify_keyword_fallback(self, content, tag_weights):
        """Keyword-based tag assignment when AI is unavailable."""
        content_lower = content.lower()
        matches = []
        for tag, weight in tag_weights.items():
            if tag == "generic":
                continue
            if tag in content_lower or tag.replace("_", " ") in content_lower:
                matches.append((tag, weight))
        if not matches:
            return ["generic"]
        matches.sort(key=lambda x: -x[1])
        return [m[0] for m in matches[:2]]

    def _enqueue_classify(self, content, entry_id, source):
        """Add content to pending classify queue. Drops oldest if queue full."""
        if not self.is_source_enabled(source):
            return
        if len(self._pending_classify) >= 100:
            self._pending_classify.pop(0)
        self._pending_classify.append(
            {"content": content, "entry_id": entry_id, "source": source})
