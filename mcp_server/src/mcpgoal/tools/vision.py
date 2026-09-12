"""MCP tools: evaluate images/SVGs with the multimodal (vision) AI model.

These tools are registered by the MCP server ONLY when `vision_enabled` is
true (i.e. the active model reports image input support). They read the image
file (or render the SVG to PNG), send it to the SAME `[ai] url`/`model` as a
`data:image/png;base64` content part, and return the model's analysis.
Paths are restricted to Allowed_root (incl. private_svg/).
"""
import base64
import io
import json
import os
from pathlib import Path

_ROOT = None


def _root():
    global _ROOT
    if _ROOT is None:
        p = Path(__file__).resolve()
        for _ in range(6):
            p = p.parent
            if (p / "Allowed_root").is_dir():
                _ROOT = str(p)
                break
    return _ROOT


def _ai_config():
    import configparser
    cfg = configparser.ConfigParser()
    cfg.read(os.path.join(_root(), "config", "settings.ini"), encoding="utf-8")
    return {
        "url": cfg.get("ai", "url", fallback="http://127.0.0.1:8080/v1").rstrip("/"),
        "model": cfg.get("ai", "model", fallback=""),
    }


def _resolve(path):
    if not path:
        return None
    root = _root() or ""
    allowed = os.path.join(root, "Allowed_root")
    p = path if os.path.isabs(path) else os.path.join(allowed, path)
    p = os.path.abspath(p)
    if not p.startswith(allowed):
        return None
    return p


def _image_to_b64(path):
    from PIL import Image
    if os.path.getsize(path) > 5 * 1024 * 1024:
        raise ValueError("image too large (>5MB)")
    img = Image.open(path)
    w, h = img.size
    max_dim = 1024
    if max(w, h) > max_dim:
        r = max_dim / max(w, h)
        img = img.resize((max(1, int(w * r)), max(1, int(h * r))))
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def _svg_to_b64(path):
    if os.path.getsize(path) > 2 * 1024 * 1024:
        raise ValueError("SVG too large (>2MB)")
    from PySide6.QtCore import QByteArray, QBuffer, QIODevice
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer
    with open(path, "rb") as f:
        data = f.read()
    renderer = QSvgRenderer(QByteArray(data))
    size = renderer.defaultSize()
    if size.isEmpty():
        size = renderer.viewBoxF().size()
    w = max(64, min(1024, int(size.width() or 512)))
    h = max(64, min(1024, int(size.height() or 512)))
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(0)
    painter = QPainter(img)
    renderer.render(painter)
    painter.end()
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    encoded = base64.b64encode(bytes(buf.data())).decode()
    buf.close()
    return encoded


def _multimodal(instruction, image_b64):
    cfg = _ai_config()
    if not cfg["model"]:
        return json.dumps({"status": "error", "message": "no AI model configured"},
                          ensure_ascii=False)
    from openai import OpenAI
    client = OpenAI(base_url=cfg["url"], api_key="not-needed")
    content = [{"type": "text",
                "text": instruction or "Descrivi in dettaglio questa immagine."}]
    content.append({"type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{image_b64}"}})
    resp = client.chat.completions.create(
        model=cfg["model"],
        messages=[{"role": "user", "content": content}],
        temperature=0.2,
    )
    return (resp.choices[0].message.content or "").strip()


def _err(message):
    return json.dumps({"status": "error", "message": message}, ensure_ascii=False)


def evaluate_image(path: str, instruction: str = "") -> str:
    p = _resolve(path)
    if not p:
        return _err("path must be inside Allowed_root")
    if not os.path.isfile(p):
        return _err("file not found")
    try:
        image_b64 = _image_to_b64(p)
    except Exception as e:
        return _err(f"cannot read image: {e}")
    try:
        out = _multimodal(instruction, image_b64)
    except Exception as e:
        return _err(f"vision request failed: {e}")
    return json.dumps({"status": "ok", "path": p, "analysis": out},
                      ensure_ascii=False)


def evaluate_svg(path: str, instruction: str = "") -> str:
    p = _resolve(path)
    if not p:
        return _err("path must be inside Allowed_root")
    if not os.path.isfile(p):
        return _err("file not found")
    try:
        image_b64 = _svg_to_b64(p)
    except Exception as e:
        return _err(f"cannot render SVG: {e}")
    try:
        out = _multimodal(instruction, image_b64)
    except Exception as e:
        return _err(f"vision request failed: {e}")
    return json.dumps({"status": "ok", "path": p, "analysis": out},
                      ensure_ascii=False)
