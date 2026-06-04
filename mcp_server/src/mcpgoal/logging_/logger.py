from datetime import datetime
from pathlib import Path
import os


def _rotate_if_needed(filepath, max_bytes=1_000_000, backups=2):
    if not os.path.exists(filepath):
        return
    size = os.path.getsize(filepath)
    if size < max_bytes:
        return
    for i in range(backups - 1, -1, -1):
        src = f"{filepath}.{i}" if i > 0 else filepath
        dst = f"{filepath}.{i + 1}"
        if os.path.exists(src):
            if os.path.exists(dst):
                os.remove(dst)
            os.rename(src, dst)
    open(filepath, "w").close()


class RequestLogger:
    def __init__(self, ip: str, log_dir: str = "LOG") -> None:
        safe_name = ip.replace(":", "_").replace(".", "_").replace("/", "_")
        log_path = Path(log_dir) / f"{safe_name}_requests.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        _rotate_if_needed(str(log_path), 1_000_000)
        self._file = open(str(log_path), "a", encoding="utf-8")

    def log(self, tool: str, params: str, status: str, result: str = "") -> None:
        ts = datetime.now().isoformat()
        line = f"[{ts}] {tool}({params}) -> {status}"
        if result:
            preview = result[:200].replace("\n", "\\n")
            line += f" | {preview}"
        self._file.write(line + "\n")
        self._file.flush()
        if status == "error":
            detail = result[:200] if result else "unknown"
            print(f"[MCP] ERROR {tool}({params}): {detail}", flush=True)

    def close(self) -> None:
        self._file.close()
