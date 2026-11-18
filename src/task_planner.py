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
import time

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


PLAN_SYSTEM = (
    "You are the planner for VASS, a voice assistant. Given a user goal and "
    "the tools available, output a short plan as JSON ONLY.\n"
    # Braces are doubled: this template is filled in with .format(max_steps=…).
    'Schema: {{"goal":"...","steps":[{{"id":1,"action":"one concrete action",'
    '"tool":"tool_name"|null,"args":{{...}}|null,"expect":"what this step must '
    'produce"}}]}}\n'
    "Rules: between 2 and {max_steps} steps; each step does ONE thing; "
    "'tool' must be one of the listed tools or null when the step is pure "
    "text work; 'args' must be a complete JSON object when 'tool' is set; "
    "no prose, no markdown, no comments outside the JSON."
)

STEP_SYSTEM = (
    "You are executing one step of a plan for VASS, a voice assistant. "
    "Work only on the step given. Report the concrete result of this step in "
    "a few plain sentences, in the user's language. No preamble, no plan "
    "review, no markdown."
)

REVIEW_SYSTEM = (
    "You review the progress of a plan for VASS. Reply ONLY with JSON: "
    '{"status":"done"|"continue"|"replan"|"fail","reason":"one short line"}\n'
    "- done: the goal is reached, no further step is needed.\n"
    "- continue: the next planned step is still the right one.\n"
    "- replan: the remaining steps are wrong or obsolete for the current "
    "state.\n"
    "- fail: the goal cannot be reached with the current state."
)

_DEFAULT_VERDICT = "continue"


def _normalise(data, max_steps):
    """Validate a raw plan dict; returns a clean plan or None."""
    if not isinstance(data, dict):
        return None
    raw_steps = data.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        return None
    steps = []
    for i, s in enumerate(raw_steps[:max_steps], 1):
        if not isinstance(s, dict) or not str(s.get("action", "")).strip():
            continue
        tool = s.get("tool")
        tool = tool if isinstance(tool, str) and tool else None
        args = s.get("args")
        steps.append({"id": i,
                      "action": str(s["action"]).strip()[:300],
                      "tool": tool,
                      "args": args if isinstance(args, dict) else None,
                      "expect": str(s.get("expect", "")).strip()[:300]})
    if not steps:
        return None
    return {"goal": str(data.get("goal", "")).strip()[:500], "steps": steps}


def make_plan(prompt, history, tools, *, ask, max_steps=12):
    """Build a multi-step plan for a request. Returns a plan dict or None.

    ask(messages, max_tokens) -> str is supplied by the caller (main model).
    None means "no usable plan": the caller falls back to the reactive loop.
    """
    tool_names = ", ".join(sorted(
        t.get("function", {}).get("name", "") for t in (tools or [])
        if t.get("function", {}).get("name"))) or "(none)"
    hist = ""
    for m in (history or [])[-4:]:
        hist += f"{m.get('role', '?')}: {str(m.get('content', ''))[:200]}\n"
    user = (f"Tools available: {tool_names}\n"
            f"Conversation so far:\n{hist or '(none)'}\n"
            f"User request: {prompt[:2000]}")
    messages = [{"role": "system",
                 "content": PLAN_SYSTEM.format(max_steps=max_steps)},
                {"role": "user", "content": user}]
    plan = _normalise(_extract_json(ask(messages, max_tokens=1200)), max_steps)
    if plan:
        return plan
    # One repair attempt with the parse error spelled out, then give up.
    repair = [{"role": "system", "content": PLAN_SYSTEM.format(max_steps=max_steps)},
              {"role": "user", "content": user + "\n\nYour previous reply was "
               "not valid plan JSON. Output ONLY the JSON object."}]
    return _normalise(_extract_json(ask(repair, max_tokens=1200)), max_steps)
