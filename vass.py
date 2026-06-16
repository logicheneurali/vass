import sys
import os

os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

_DEBUG_MODE = "--debug" in sys.argv


def _detach_console():
    if os.environ.get("VASS_DETACHED"):
        return
    env = os.environ.copy()
    env["VASS_DETACHED"] = "1"
    if sys.platform == "win32":
        import subprocess
        pw = sys.executable.replace("python.exe", "pythonw.exe")
        exe = pw if os.path.exists(pw) else sys.executable
        subprocess.Popen([exe] + sys.argv, env=env, close_fds=True,
                         creationflags=0x00000008)
        sys.exit(0)
    elif sys.platform == "darwin":
        import subprocess
        subprocess.Popen([sys.executable] + sys.argv, env=env,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
        sys.exit(0)
    else:
        import subprocess
        subprocess.Popen(["nohup", sys.executable] + sys.argv, env=env,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
        sys.exit(0)


sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
try:
    import main
except ImportError as e:
    msg = f"Missing dependencies ({e}).\nRun: pip install -r requirements.txt"
    try:
        if sys.stdout is None or not sys.stdout.isatty():
            if sys.platform == "win32":
                import ctypes
                ctypes.windll.user32.MessageBoxW(0, msg, "VASS - Errore", 0x10)
            elif sys.platform == "darwin":
                import subprocess
                subprocess.run(["osascript", "-e", f'display dialog "{msg}" with title "VASS - Errore" buttons {{"OK"}}'], timeout=5)
            else:
                import subprocess
                subprocess.run(["notify-send", "VASS - Errore", msg], timeout=5)
    except Exception:
        pass
    print(msg)
    sys.exit(1)

if __name__ == "__main__":
    if not _DEBUG_MODE and sys.stdout and sys.stdout.isatty():
        _detach_console()
    main.main()
