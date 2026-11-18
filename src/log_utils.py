import os


def rotate_if_needed(filepath, max_bytes=500_000, backups=2):
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


def open_crash_log(filepath, encoding="utf-8"):
    """Open a crash log for appending, rotating it first so it stays bounded."""
    rotate_if_needed(filepath, max_bytes=500_000, backups=2)
    return open(filepath, "a", encoding=encoding)
