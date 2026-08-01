import os
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_ICONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons", "lucide")

def _render(name, color, size, padding=0):
    svg_path = os.path.join(_ICONS_DIR, f"{name}.svg")
    if not os.path.exists(svg_path):
        return None, None
    with open(svg_path, encoding="utf-8") as f:
        svg_data = f.read()
    svg_data = svg_data.replace("currentColor", color)
    byte_array = svg_data.encode("utf-8")
    r = QSvgRenderer(byte_array)
    double = size * 2
    pixmap = QPixmap(double, double)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    if padding:
        p2 = padding * 2
        r.render(painter, QRectF(p2, p2, double - p2 * 2, double - p2 * 2))
    else:
        r.render(painter)
    painter.end()
    return pixmap, pixmap.copy()

def icon(name, color="#e0e0e0", size=24, padding=0):
    pixmap, _ = _render(name, color, size, padding)
    if pixmap is None:
        return QIcon()
    ico = QIcon(pixmap)
    return ico

def icon_dual(name, color, hover_color, size=24):
    """Icon with different normal and hover colors."""
    normal, hover = _render(name, color, size)
    if normal is None:
        return QIcon()
    ico = QIcon()
    ico.addPixmap(normal, QIcon.Mode.Normal)
    ico.addPixmap(hover, QIcon.Mode.Active)
    return ico

def pixmap(name, color="#e0e0e0", size=24):
    pixmap, _ = _render(name, color, size)
    if pixmap is None:
        return None
    return pixmap.copy().scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
