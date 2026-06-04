from pathlib import Path


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
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"Written {len(content)} bytes to {target}"
