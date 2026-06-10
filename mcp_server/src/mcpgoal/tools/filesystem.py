from pathlib import Path

_PROTECTED_FILES = {"events.json", "schedule.json", "memory.json", "memory_tags.json"}


def _resolve_safe(path: str, allowed_root: str) -> Path:
    root = Path(allowed_root).resolve()
    target = (root / path).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise PermissionError(f"Access denied: path outside allowed root ({allowed_root})")
    return target


async def read_file(path: str, allowed_root: str = "") -> str:
    target = _resolve_safe(path, allowed_root)
    if not target.is_file():
        raise FileNotFoundError(f"File not found: {target}")
    return target.read_text(encoding="utf-8")


async def write_file(path: str, content: str, allowed_root: str = "") -> str:
    target = _resolve_safe(path, allowed_root)
    if target.name in _PROTECTED_FILES:
        raise PermissionError(f"Cannot overwrite protected file '{target.name}'. Use a dedicated tool (e.g., addevent for events.json).")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"Written {len(content)} bytes to {target}"
