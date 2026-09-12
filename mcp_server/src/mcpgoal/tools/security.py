"""MCP tools: read-only local security checks + CVE lookup + consent-gated remediation.

Thin adapters over the security_monitor plugin's `security_scanner` module.
The scanner is located lazily (guarded import): if the plugin directory is
missing, the tools return a clear error instead of breaking the MCP server.
"""
import json
import os
import sys
from pathlib import Path

_SCANNER = None


def _find_scanner():
    global _SCANNER
    if _SCANNER is not None:
        return _SCANNER
    # climb from this file up to the project root, then into plugins/external/
    p = Path(__file__).resolve()
    for _ in range(7):
        p = p.parent
        cand = p / "plugins" / "external" / "security_monitor" / "security_scanner.py"
        if cand.exists():
            plugin_dir = str(cand.parent)
            if plugin_dir not in sys.path:
                sys.path.insert(0, plugin_dir)
            import security_scanner
            _SCANNER = security_scanner
            return _SCANNER
    return None


def _missing():
    return json.dumps({
        "status": "error",
        "message": "security_monitor plugin not installed "
                   "(plugins/external/security_monitor/security_scanner.py missing)",
    }, ensure_ascii=False)


def security_scan() -> str:
    sc = _find_scanner()
    if sc is None:
        return _missing()
    return json.dumps(sc.build_report(sc.default_config()),
                      ensure_ascii=False, default=str)


def security_check_cve(packages_json: str = "") -> str:
    sc = _find_scanner()
    if sc is None:
        return _missing()
    pkgs = []
    if packages_json:
        try:
            pkgs = json.loads(packages_json)
        except Exception:
            pkgs = []
    if not pkgs:
        pkgs = sc.collect_installed_software()
    return json.dumps(sc.query_cve(pkgs), ensure_ascii=False, default=str)


def security_status() -> str:
    sc = _find_scanner()
    if sc is None:
        return _missing()
    rep = sc.load_last_report()
    if rep is None:
        return json.dumps({"status": "no report yet, run security_scan"},
                          ensure_ascii=False)
    return json.dumps(rep, ensure_ascii=False, default=str)


def security_remediate(item_json: str) -> str:
    sc = _find_scanner()
    if sc is None:
        return _missing()
    try:
        item = json.loads(item_json) if item_json else {}
    except Exception:
        item = {}
    if not item:
        return json.dumps({"status": "error", "message": "no issue specified"},
                          ensure_ascii=False)
    cmd = sc.remediation_suggestion(item)
    if not cmd:
        return json.dumps({"status": "error",
                           "message": "no automated remediation available "
                                      "for this issue (manual steps required)"},
                          ensure_ascii=False)
    rc, out, err = sc.run_command(cmd, timeout=600)
    return json.dumps({"status": "ok" if rc == 0 else "error",
                       "command": cmd, "exit_code": rc,
                       "output": (out or err or "")[-800:]},
                      ensure_ascii=False)
