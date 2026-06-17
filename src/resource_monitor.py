import time
import psutil


def _get_gpu():
    try:
        import sys as _sys
        import subprocess as _sp
        _orig = _sp.Popen
        def _patched(*a, **kw):
            if _sys.platform == "win32" and "creationflags" not in kw:
                kw["creationflags"] = _sp.CREATE_NO_WINDOW
            return _orig(*a, **kw)
        _sp.Popen = _patched
        import GPUtil
        _sp.Popen = _orig
        gpus = GPUtil.getGPUs()
        _sp.Popen = _orig
        return gpus[0] if gpus else None
    except Exception:
        return None


def check_resources(config):
    cpu_pct = psutil.cpu_percent(interval=0.5)
    ram_pct = psutil.virtual_memory().percent
    ok = cpu_pct < config.get("cpu_max", 80) and ram_pct < config.get("ram_max", 80)
    status = {"cpu": cpu_pct, "ram": ram_pct}

    gpu = _get_gpu()
    if gpu:
        gpu_pct = gpu.load * 100
        vram_pct = gpu.memoryUsed / gpu.memoryTotal * 100 if gpu.memoryTotal > 0 else 0
        status["gpu"] = gpu_pct
        status["vram"] = vram_pct
        ok = ok and gpu_pct < config.get("gpu_max", 80) and vram_pct < config.get("vram_max", 80)

    return ok, status


def wait_for_resources(config, timeout=300, cancel_check=None, on_status=None):
    start = time.time()
    while True:
        if cancel_check and cancel_check():
            print("[Resources] Cancelled by user")
            return False
        ok, s = check_resources(config)
        if ok:
            if on_status:
                on_status(s)
            return True
        if on_status:
            on_status(s)
        elapsed = time.time() - start
        if elapsed > timeout:
            print(f"[Resources] Timeout after {elapsed:.0f}s, proceeding anyway")
            return True
        msg = f"[Resources] Waiting ({elapsed:.0f}s): CPU={s['cpu']:.0f}% RAM={s['ram']:.0f}%"
        if "gpu" in s:
            msg += f" GPU={s['gpu']:.0f}% VRAM={s['vram']:.0f}%"
        print(msg)
        time.sleep(3)
