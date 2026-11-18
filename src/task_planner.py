"""Multi-step action planning for complex user requests.

The planner decides whether a request needs a plan (needs_plan, asked of the
main model), builds an explicit plan (make_plan), then executes it one step at
a time with a fresh context per step (run_plan).

It is deliberately free of app imports: the caller passes the OpenAI client
and, later, `ask`/`execute` callables, so the whole module is testable
without the GUI or a server.
"""
import json
import re

from utils import call_with_retry

NEEDS_PLAN_TEMPLATE = """Decide whether this user request for a voice assistant needs a multi-step plan.
Reply ONLY with JSON: {{"plan":true|false}}
- true: reaching the goal needs several distinct steps in sequence (research,
  comparisons, several tools or several independent facts).
- false: one direct answer or one single tool call is enough.
Conversation so far:
{history}
User request: {prompt}"""

_DEFAULT_PLAN = False


def _extract_json(text):
    """First JSON object in a model reply, None when there is none."""
    if not text:
        return None
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except Exception:
        return None


def _plan_flag(data):
    """Strict-ish bool from the model's {"plan": ...}; None when unusable."""
    if not isinstance(data, dict):
        return None
    val = data.get("plan")
    if isinstance(val, str):
        val = val.strip().lower() in ("true", "yes", "1")
    return bool(val) if isinstance(val, bool) else None


def needs_plan(prompt, openai_client, model, history=None, usage=None):
    """True when the MAIN model says this request needs a multi-step plan.

    Every failure resolves to False: a classifier error must never start a
    plan the request does not need — the reactive pipeline answers instead.
    """
    if not openai_client or not model:
        return _DEFAULT_PLAN
    hist = ""
    for m in (history or [])[-4:]:
        hist += f"{m.get('role', '?')}: {str(m.get('content', ''))[:200]}\n"
    msg = NEEDS_PLAN_TEMPLATE.format(history=hist or "(none)", prompt=prompt[:1500])
    try:
        resp = call_with_retry(lambda: openai_client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": msg}],
            temperature=0.0, max_tokens=60,
            extra_body={"disable_thinking": True},
        ))
        if usage is not None:
            usage.add(getattr(resp, "usage", None))
        flag = _plan_flag(_extract_json(resp.choices[0].message.content))
        if flag is None:
            print("[Plan] needs_plan unparseable -> False")
            return _DEFAULT_PLAN
        return flag
    except Exception as e:
        print(f"[Plan] needs_plan failed -> False: {e}")
        return _DEFAULT_PLAN
