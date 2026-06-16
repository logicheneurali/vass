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
        if os.path.exists(pw):
            subprocess.Popen([pw] + sys.argv, env=env,
                             creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW)
        else:
            subprocess.Popen([sys.executable] + sys.argv, env=env,
                             creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW)
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
import main

if __name__ == "__main__":
    if not _DEBUG_MODE and sys.stdout.isatty():
        _detach_console()
    main.main()
