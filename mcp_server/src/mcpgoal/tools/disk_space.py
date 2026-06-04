import shutil

_UNITS = ["bytes", "KB", "MB", "GB", "TB", "PB"]


async def get_disk_space(path: str = ".") -> str:
    free = shutil.disk_usage(path).free
    unit_idx = 0
    while free >= 1024 and unit_idx < len(_UNITS) - 1:
        free /= 1024
        unit_idx += 1
    return f"{free:.2f} {_UNITS[unit_idx]}"
