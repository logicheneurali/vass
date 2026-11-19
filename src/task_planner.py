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
from datetime import date, timedelta

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


_PLACEHOLDER = re.compile(r"\{\{|\}\}|\w+\([^()]*\)\s*$")


def clean_args(args):
    """Args a real tool may receive.

    The plan model sometimes emits template placeholders ({{tomorrow_date}})
    or pseudo-calls (tomorrow_date(current_date)) as argument values. A real
    tool must never execute those (observed: calculate() failed with
    "Unsupported syntax: Call"), so such values are dropped: model output is
    not trusted input.
    """
    if not isinstance(args, dict):
        return None
    return {k: v for k, v in args.items()
            if not (isinstance(v, str) and _PLACEHOLDER.search(v))}


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
    "always pick the narrowest tool that answers the step, and judge by its "
    "description: to find news about a TOPIC or a person use the keyword "
    "search (e.g. search_news), not a date-range scan; use a date-range tool "
    "only when the step is about a PERIOD itself; "
    "when a step genuinely needs a period, split it into successive steps - "
    "one month per step - instead of one oversized query, and when a step "
    "needs several items, one item per step; "
    "'last N months/days' means the N units BEFORE the current date: always "
    "compute those dates backward from the date in the context, never plan "
    "or query dates in the future; never use a tool to compute dates, write "
    "the literal ISO date in 'args'; if a tool reports that data is missing "
    "for part of the period, plan what is available and say in the final "
    "answer which part is not covered; "
    "'tool' must be one of the listed tools or null when the step is pure "
    "text work; if no tool can retrieve what the step needs, use null and "
    "answer from the memory and context instead of inventing a call; "
    "'args' must be a complete JSON object when 'tool' is set, "
    "with literal values only: never templates like {{today}}, never "
    "function calls like tomorrow_date(x); "
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
# Text kept per executed step. Later steps and the final summary see only the
# state block, so 400 chars would discard most of a tool result; 2000 keeps a
# useful slice while 12 steps stay well inside the context window.
_OUTCOME_CHARS = 2000



def _shift_month(d, k):
    """d shifted by k months, clamped to the target month's last day."""
    m = d.month - 1 + k
    y = d.year + m // 12
    m = m % 12 + 1
    while True:
        try:
            return date(y, m, d.day)
        except ValueError:
            d = d.replace(day=d.day - 1)


def _split_date_ranges(steps, max_steps):
    """One step per month for any tool call whose date range is over ~2 months.

    Multi-step exists to beat the context limit, but the plan model does not
    chunk reliably (live: one read_news_range call for six months with
    max_chars=5000, most of the data discarded). Chunking is enforced here so
    every step retrieves a slice the next steps and the summary can actually
    use. At most max_steps-1 retrieval steps are produced, leaving room for
    the analysis steps the plan already has.
    """
    others = sum(1 for st in steps
                 if not (isinstance(st.get("args"), dict)
                         and st["args"].get("from_date")
                         and st["args"].get("to_date")))
    out = []
    for step in steps:
        if not step.get("tool"):
            # A text step whose args merely mention dates must not be split:
            # live, eight do-nothing steps ate the budget of the retrieval.
            out.append(step)
            continue
        args = step.get("args") or {}
        try:
            d0 = date.fromisoformat(str(args.get("from_date")))
            d1 = date.fromisoformat(str(args.get("to_date")))
        except (TypeError, ValueError):
            out.append(step)
            continue
        if d1 <= d0 or (d1 - d0).days <= 62:
            out.append(step)
            continue
        months = []
        start = d0
        while start < d1:
            months.append(start)
            start = _shift_month(start, 1)
        # Reserve the plan's own non-date steps: the whole plan must stay
        # within max_steps (live: 14 steps against a cap of 12).
        budget = max(1, max_steps - others)
        group = -(-len(months) // budget)          # ceil
        merged = [months[i] for i in range(0, len(months), group)]
        pieces = []
        for i, start in enumerate(merged):
            end = (merged[i + 1] - timedelta(days=1)
                   if i + 1 < len(merged) else d1)
            pieces.append((start, end))
        for i, (start, end) in enumerate(pieces, 1):
            piece = dict(step)
            piece["args"] = {**args,
                             "from_date": start.isoformat(),
                             "to_date": end.isoformat()}
            piece["action"] = f"{step['action']} [{i}/{len(pieces)}]"
            out.append(piece)
    for i, step in enumerate(out, 1):
        step["id"] = i
    return out


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
    steps = _split_date_ranges(steps, max_steps)[:max_steps]
    for i, step in enumerate(steps, 1):
        step["id"] = i
    return {"goal": str(data.get("goal", "")).strip()[:500], "steps": steps}


def make_plan(prompt, history, tools, *, ask, max_steps=12, context="",
              memory=""):
    """Build a multi-step plan for a request. Returns a plan dict or None.

    ask(messages, max_tokens) -> str is supplied by the caller (main model).
    `context` is the compact session context the reactive prompt always has
    (persona + current date); `memory` is the gated memory/profile text. Both
    inform the plan only: steps see compact outcomes, never the raw history.
    None means "no usable plan": the caller falls back to the reactive loop.
    """
    # Signatures, not bare names: without parameter names the model guesses
    # them (live: read_news_range(start_date, end_date) vs from_date/to_date).
    sigs = []
    for t in (tools or []):
        fn = t.get("function", {}) or {}
        name = fn.get("name")
        if not name:
            continue
        args = list(((fn.get("parameters") or {}).get("properties") or {}))
        sig = f"{name}({', '.join(args)})" if args else name
        # A one-line description lets the model tell tools apart: with names
        # only it picked read_news_range for an expenses question.
        desc = " ".join(str(fn.get("description") or "").split())[:120]
        sigs.append(f"{sig}: {desc}" if desc else sig)
    tool_names = ", ".join(sorted(sigs)) or "(none)"
    hist = ""
    for m in (history or [])[-4:]:
        hist += f"{m.get('role', '?')}: {str(m.get('content', ''))[:200]}\n"
    user = ((f"Context:\n{context}\n\n" if context else "")
            + (f"Memory:\n{memory}\n\n" if memory else "")
            + f"Tools available: {tool_names}\n"
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


def _state_block(state):
    """Compact outcome of the steps already executed (never the raw chat)."""
    if not state:
        return "- (none yet)"
    return "\n".join(f"- {s['id']}: {s['action']} -> {s['outcome']}"
                     for s in state)


def _step_messages(goal, state, step, context=""):
    """Fresh messages for one step: role + context + goal + compact state.

    The user's conversation history is deliberately absent: a plan of a dozen
    steps must never grow past the context window. The session context
    (persona + date) is identical in every step.
    """
    user = (f"Goal: {goal}\n\nCompleted steps:\n{_state_block(state)}\n\n"
            f"Now execute ONLY this step ({step['id']}): {step['action']}\n"
            f"Expected result: {step.get('expect', '')}"
            + (f"\n\nSession context:\n{context}" if context else ""))
    return [{"role": "system", "content": STEP_SYSTEM},
            {"role": "user", "content": user}]


def _verdict(text):
    """'done'|'continue'|'replan'|'fail' from a review reply."""
    if not text:
        return _DEFAULT_VERDICT
    data = _extract_json(text)
    if isinstance(data, dict):
        status = str(data.get("status", "")).lower()
        if status in ("done", "continue", "replan", "fail"):
            return status
    found = re.search(r"\b(done|continue|replan|fail)\b", text.lower())
    return found.group(1) if found else _DEFAULT_VERDICT


def _review(ask, goal, state, index, total, remaining=None):
    """Ask whether the plan is finished. A broken review never kills a plan.

    `remaining` lists the planned steps not yet executed: the reviewer must
    see them, otherwise it replans away retrieval steps that are still valid
    (live: six monthly reads were replaced by one oversized search).
    """
    rest = "\n".join(f"- {s.get('id')}: {s.get('action', '')} "
                      f"(tool={s.get('tool')})"
                      for s in (remaining or [])) or "- (none)"
    user = (f"Goal: {goal}\n\nSteps executed: {index}/{total}\n\n"
            f"{_state_block(state)}\n\nRemaining planned steps:\n{rest}")
    try:
        text = ask([{"role": "system", "content": REVIEW_SYSTEM},
                    {"role": "user", "content": user}], max_tokens=120)
    except Exception as e:
        print(f"[Plan] review failed ({e}) -> continue")
        return _DEFAULT_VERDICT
    return _verdict(text)


def _replan(ask, goal, state, steps, max_steps, context="", memory=""):
    """Rebuild the remaining steps from the current state. None = give up."""
    user = ((f"Context:\n{context}\n\n" if context else "")
            + (f"Memory:\n{memory}\n\n" if memory else "")
            + f"Goal: {goal}\n\nSteps already executed:\n{_state_block(state)}\n\n"
            f"Steps still planned: "
            f"{', '.join(str(s['id']) for s in steps) or '(none)'}\n\n"
            "Produce the remaining plan as JSON only, starting from the "
            "current state (do not repeat completed steps).")
    messages = [{"role": "system",
                 "content": PLAN_SYSTEM.format(max_steps=max_steps)},
                {"role": "user", "content": user}]
    try:
        data = _extract_json(ask(messages, max_tokens=1200))
    except Exception as e:
        print(f"[Plan] replan failed: {e}")
        return None
    return _normalise(data, max_steps)


def _outcome(status, goal, state, done, total):
    # With replans the executed count can exceed one segment's length: the
    # reported total must never read "7/5".
    return {"status": status, "goal": goal, "state": state,
            "steps_done": done, "steps_total": max(total, done)}


def run_plan(plan, *, ask, execute, on_step=None, should_abort=None,
             max_steps=12, max_replans=3, budget_seconds=600, start=None,
             context="", plan_memory=""):
    """Execute a plan step by step with fresh context per step.

    ask(messages, max_tokens) -> str        one main-model completion
    execute(messages, step) -> str          run one step (tool or elaboration)
    on_step(i, n, action)                   progress callback (UI)
    should_abort() -> bool                  checked before step and review

    Returns an _outcome() dict; "aborted" means the user stopped us,
    "stopped" a hard limit (steps/time), "failed" the plan itself.
    """
    start = time.time() if start is None else start
    goal = plan.get("goal", "")
    steps = list(plan.get("steps") or [])
    state = []
    replans = 0
    consecutive_failures = 0
    executed = 0                 # total across replans: max_steps is a hard cap
    done_index = 0
    while True:
        total = len(steps)
        broke_for_replan = False
        for index, step in enumerate(steps, 1):
            if executed >= max_steps or time.time() - start > budget_seconds:
                return _outcome("stopped", goal, state, done_index, total)
            if should_abort and should_abort():
                return _outcome("aborted", goal, state, done_index, total)
            if on_step:
                on_step(index, total, step.get("action", ""))
            failed = False
            try:
                result = execute(_step_messages(goal, state, step, context), step)
            except Exception as e:
                result = f"step failed: {e}"
                failed = True
                print(f"[Plan] step {index} raised: {e}")
            result = str(result or "").strip()
            # A raised step or a tool error is a failure too, not a result.
            failed = failed or not result or result.startswith(("Error:", "step failed:"))
            state.append({"id": step.get("id", index),
                          "action": step.get("action", ""),
                          "outcome": result[:_OUTCOME_CHARS]})
            executed += 1
            done_index = executed
            consecutive_failures = consecutive_failures + 1 if failed else 0
            if consecutive_failures >= 3:
                return _outcome("failed", goal, state, done_index, total)
            if should_abort and should_abort():
                return _outcome("aborted", goal, state, done_index, total)
            verdict = _review(ask, goal, state, index, total, steps[index:])
            print(f"[Plan] review after step {index}: {verdict}")
            if verdict == "replan" and any(s.get("tool") for s in steps[index:]):
                # Planned tool steps are still pending: replanning now would
                # discard them (live: remaining months dropped for one
                # oversized search). Replan is allowed once they have run.
                print("[Plan] replan deferred: tool steps remain")
                verdict = "continue"
            if verdict == "done":
                return _outcome("done", goal, state, done_index, total)
            if verdict == "fail":
                return _outcome("failed", goal, state, done_index, total)
            if verdict == "replan":
                if replans >= max_replans:
                    return _outcome("failed", goal, state, done_index, total)
                replans += 1
                new_plan = _replan(ask, goal, state, steps, max_steps,
                                   context, plan_memory)
                if not new_plan:
                    return _outcome("failed", goal, state, done_index, total)
                steps = list(new_plan["steps"])
                goal = new_plan.get("goal") or goal
                broke_for_replan = True
                break
        if not broke_for_replan:
            # The reviewer said "continue" after the last step: there is
            # nothing left to continue with, so the plan is finished.
            return _outcome("done", goal, state, done_index, total)
