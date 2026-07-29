"""Noise Auto-Pause Plugin — socket-based, standalone process.
Connects to VASS PluginServer via TCP. Receives audio data,
runs DSP noise detection, sends pause/resume commands.
"""
import configparser
import json
import os
import socket
import time


class NoiseAutoPause:
    def __init__(self):
        self._host = "localhost"
        self._port = 8765
        self._sock = None
        self._running_nf = None
        self._noise_high_since = None
        self._paused_since = None
        self._pause_samples = []
        self._resume_cooldown = 0.0
        self._config = self._load_config()
        self._last_check_time = 0.0

    def _load_config(self) -> dict:
        cfg = configparser.ConfigParser()
        ini_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "settings.ini")
        if not os.path.exists(ini_path):
            example = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "settings.example.ini")
            if os.path.exists(example):
                import shutil
                shutil.copy(example, ini_path)
        if os.path.exists(ini_path):
            cfg.read(ini_path, encoding="utf-8")
        return {
            "threshold": cfg.getfloat("noise", "threshold", fallback=0.002),
            "duration": cfg.getfloat("noise", "duration", fallback=5),
        }

    def _load_manifest(self) -> dict:
        manifest_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "plugin_manifest.json")
        with open(manifest_path, encoding="utf-8") as f:
            return json.load(f)

    def run(self):
        manifest = self._load_manifest()
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self._sock.connect((self._host, self._port))
        except ConnectionRefusedError:
            print("[NoisePlugin] VASS not running (port not open). Exiting.")
            return

        hello = json.dumps({
            "type": "hello",
            "name": manifest["name"],
            "version": manifest["version"],
            "min_app": manifest["min_app"],
            "subscribe": manifest["subscriptions"],
        }) + "\n"
        self._sock.sendall(hello.encode("utf-8"))
        print(f"[NoisePlugin] Connected to VASS on {self._host}:{self._port}")

        buf = b""
        while True:
            try:
                data = self._sock.recv(4096)
            except (ConnectionResetError, OSError):
                print("[NoisePlugin] Disconnected. Exiting.")
                break
            if not data:
                print("[NoisePlugin] Server closed connection. Exiting.")
                break
            buf += data
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                try:
                    msg = json.loads(line.decode("utf-8"))
                except json.JSONDecodeError:
                    continue
                self._on_message(msg)

        self._sock.close()

    def _on_message(self, msg):
        msg_type = msg.get("type", "")
        if msg_type == "error":
            print(f"[NoisePlugin] Server error: {msg.get('msg', 'unknown')}")
        elif msg_type == "audio":
            self._on_audio(msg)
        elif msg_type == "state":
            self._on_state(msg)

    def _on_audio(self, data):
        rms = float(data.get("rms", 0))
        noise_floor = float(data.get("noise_floor", 0))
        threshold = self._config["threshold"]
        duration = self._config["duration"]
        adaptive = max(threshold, noise_floor * 2.0)

        if self._paused_since is not None:
            self._handle_paused(rms, adaptive, duration, noise_floor)
            return

        if time.time() < self._resume_cooldown:
            return

        if not data.get("listening", False):
            return

        self._detect_noise(rms, adaptive, duration)

    def _detect_noise(self, rms, adaptive, duration):
        if self._running_nf is None:
            self._running_nf = rms
        else:
            self._running_nf = 0.99 * self._running_nf + 0.01 * rms

        if self._running_nf > adaptive:
            if self._noise_high_since is None:
                self._noise_high_since = time.time()
            if time.time() - self._noise_high_since >= duration:
                print(f"[NoisePlugin] Auto-pausing: NF {self._running_nf:.6f} "
                      f"> {adaptive:.6f} for {duration}s")
                self._send_cmd("set_state", {
                    "state": "paused", "source": "noise_auto_pause"})
                self._paused_since = time.time()
                self._pause_samples = []
                self._noise_high_since = None
                self._running_nf = None
        else:
            self._noise_high_since = None

    def _handle_paused(self, rms, adaptive, duration, noise_floor):
        elapsed = time.time() - self._paused_since

        if elapsed < duration:
            self._pause_samples.append(rms)
            return

        now = time.time()
        if now - self._last_check_time < duration:
            self._pause_samples.append(rms)
            return

        self._last_check_time = now

        if len(self._pause_samples) < 20:
            self._pause_samples.append(rms)
            return

        avg = sum(self._pause_samples) / len(self._pause_samples)
        self._pause_samples = []

        if avg < adaptive:
            print(f"[NoisePlugin] Resuming: avg rms {avg:.6f} < {adaptive:.6f}")
            self._send_cmd("set_state", {
                "state": "listening", "source": "noise_auto_pause"})
            self._running_nf = avg
            self._noise_high_since = None
            self._paused_since = None
            self._resume_cooldown = time.time() + 2.0
        else:
            print(f"[NoisePlugin] Still noisy: avg rms {avg:.6f} >= {adaptive:.6f}")
            self._paused_since = time.time()

    def _on_state(self, data):
        state = data.get("state", "")
        if state != "paused":
            self._running_nf = None
            self._noise_high_since = None
            self._paused_since = None
            self._pause_samples = []

    def _send_cmd(self, cmd, params=None):
        msg = json.dumps({
            "type": "cmd", "cmd": cmd, **(params or {})
        }) + "\n"
        try:
            self._sock.sendall(msg.encode("utf-8"))
        except Exception as e:
            print(f"[NoisePlugin] Send failed: {e}")


if __name__ == "__main__":
    plugin = NoiseAutoPause()
    plugin.run()
