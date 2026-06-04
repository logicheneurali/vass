---
name: revisione
description: Full code review mode. Analyzes all VASS source code for redundancies, security issues, code quality, readability, unused imports, dead code, and unused files. Use ONLY when the user asks for a code review/revisione/analisi del codice.
---

# Code Review Mode

## Rules

1. **Plan mode only** — no modifications without explicit user confirmation
2. **Read-only** — analysis only, never execute changes during review
3. **Comprehensive** — check every `.py` file in the project and `mcp_server/` subdirectory
4. **Report-first** — present findings organized by severity before asking about fixes

## Analysis Checklist

### Security
- [ ] Hardcoded credentials or API keys
- [ ] Command injection (shell/PowerShell string interpolation)
- [ ] Path traversal vulnerabilities
- [ ] Unsanitized user input in subprocess calls
- [ ] Missing authentication/authorization checks

### Redundancies
- [ ] Duplicated code blocks (copy-pasted logic)
- [ ] Repeated file I/O patterns
- [ ] Identical error handling in multiple places
- [ ] God classes (single class handling too many concerns)
- [ ] Methods longer than 50 lines without logical breaks

### Code Quality
- [ ] Bare `except:` clauses (silent error swallowing)
- [ ] Missing error handling for file/network operations
- [ ] Thread safety issues (shared state without locks)
- [ ] Race conditions
- [ ] Functions too long or with too many parameters
- [ ] Inconsistent naming conventions

### Dead Code
- [ ] Unused imports (Python modules)
- [ ] Unused functions/methods
- [ ] Unused variables
- [ ] Unreachable code paths
- [ ] Commented-out code blocks
- [ ] Unused files in the project directory

### Readability
- [ ] Missing docstrings on public methods
- [ ] Magic numbers without explanation
- [ ] Overly complex expressions
- [ ] Deeply nested conditionals (>3 levels)
- [ ] Non-descriptive variable names

### Locale Alignment
- [ ] All locale files (`locales/*.json`) have the same set of keys
- [ ] Compare each language against `it.json` as the reference
- [ ] Report missing keys per language
- [ ] Report extra keys not present in `it.json`
- [ ] Verify all JSON files are valid (no syntax errors)

To check alignment, run:
```python
import json, os
with open('locales/it.json', encoding='utf-8') as f: ref = json.load(f)

def count_keys(d):
    return sum(count_keys(v) if isinstance(v, dict) else 1 for v in d.values())

ref_count = count_keys(ref)
for lang in os.listdir('locales'):
    if lang.endswith('.json'):
        with open(f'locales/{lang}', encoding='utf-8') as f: lc = json.load(f)
        lc_count = count_keys(lc)
        if lc_count != ref_count: print(f'{lang}: {lc_count} != {ref_count}')
```

### VASScript Reference Documentation
- [ ] Verify `Allowed_root/VASCRIPT_REFERENCE.md` documents ALL VASScript functions
- [ ] Extract function names from `script_engine.py` (`if name == "funcname":` pattern)
- [ ] Extract documented function names from the reference (`` `funcName(` `` pattern)
- [ ] Compare lowercased: any function in code but NOT in docs → missing
- [ ] Report undocumented functions as critical (AI won't know they exist)
- [ ] Report documented functions not in code as warnings (stale docs)
- [ ] Verify each documented function has at minimum: name, description, example

To cross-reference, run:
```python
import re, os
base = os.path.dirname(os.path.abspath(__file__))  # or hardcode project root

# Extract from script_engine.py
with open(os.path.join(base, 'script_engine.py'), encoding='utf-8') as f:
    code = f.read()
code_funcs = {m.lower() for m in re.findall(r"if name == ['\"]([\w_]+)['\"]", code)}

# Extract from VASCRIPT_REFERENCE.md — match `functionName( pattern
with open(os.path.join(base, 'Allowed_root', 'VASCRIPT_REFERENCE.md'), encoding='utf-8') as f:
    ref = f.read()
doc_funcs = {m.lower() for m in re.findall(r'`(\w+)\(', ref)}

missing = code_funcs - doc_funcs
stale = doc_funcs - code_funcs

if missing:
    print(f'MISSING from VASCRIPT_REFERENCE.md: {", ".join(sorted(missing))}')
if stale:
    print(f'STALE in VASCRIPT_REFERENCE.md (not in code): {", ".join(sorted(stale))}')
if not missing and not stale:
    print('All VASScript functions documented — OK')
```

## Report Format

Present findings in this order:

### 🔴 Critical (security, crash risk)
### 🟠 High (duplication, race conditions)
### 🟡 Medium (code quality, error handling)
### 🟢 Low (style, naming)

For each finding include:
- File path and line number
- Description of the problem
- Suggested fix

## Scope

Scan all `.py` files in:
- `C:\Users\effed\Documents\Python\vass\` (root)
- `C:\Users\effed\Documents\Python\vass\mcp_server\`

Also scan for unused files in:
- `C:\Users\effed\Documents\Python\vass\` (`.py` files never imported)
- `C:\Users\effed\Documents\Python\vass\scripts\` (`.vass` files never referenced)
