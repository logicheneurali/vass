"""Reusable smooth-scrolling QScrollArea subclass.

Provides:
- smooth animated wheel scrolling (each wheel notch glides instead of jumping),
- animated programmatic scrolling (QPropertyAnimation, OutCubic easing),
- a convenience to animate the view toward a child widget.

Use anywhere a QScrollArea is created:
    from smooth_scroll import SmoothScrollArea
"""
from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtWidgets import QScrollArea


class SmoothScrollArea(QScrollArea):
    """QScrollArea with smooth wheel scrolling and animated programmatic scrolls."""

    WHEEL_STEP = 40       # pixels per wheel notch (animated)
    WHEEL_DURATION = 180  # ms for a wheel glide
    DURATION = 250        # ms for programmatic animations

    def __init__(self, parent=None):
        super().__init__(parent)
        self._animation = None     # programmatic scrolls
        self._wheel_anim = None    # wheel glides

    # ── helpers ────────────────────────────────────────────────

    def _stop_animation(self):
        for attr in ("_animation", "_wheel_anim"):
            a = getattr(self, attr)
            if a is not None:
                try:
                    a.stop()
                except Exception:
                    pass
                setattr(self, attr, None)

    def stop_animation(self):
        self._stop_animation()

    def _anim_to(self, attr, target, duration, easing):
        bar = self.verticalScrollBar()
        target = max(bar.minimum(), min(bar.maximum(), int(target)))
        old = getattr(self, attr)
        if old is not None:
            try:
                old.stop()
            except Exception:
                pass
        anim = QPropertyAnimation(bar, b"value", self)
        anim.setDuration(max(1, int(duration)))
        anim.setStartValue(bar.value())
        anim.setEndValue(target)
        anim.setEasingCurve(easing)
        anim.finished.connect(lambda a=attr: setattr(self, a, None))
        setattr(self, attr, anim)
        anim.start()

    # ── wheel: animated glide, no per-notch jumps ──────────────

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta == 0:
            super().wheelEvent(event)
            return
        bar = (self.horizontalScrollBar()
               if event.modifiers() & Qt.KeyboardModifier.ShiftModifier
               else self.verticalScrollBar())
        # retarget from the live position so consecutive notches flow together
        self._anim_to("_wheel_anim",
                      bar.value() - int(delta / 120 * self.WHEEL_STEP),
                      self.WHEEL_DURATION, QEasingCurve.Type.OutCubic)
        event.accept()

    # ── animated programmatic scrolling ─────────────────────────

    def animate_to(self, value, duration=None):
        self._stop_animation()
        self._anim_to("_animation", value, duration or self.DURATION,
                      QEasingCurve.Type.OutCubic)

    def scroll_to_widget(self, widget):
        """Animate the view until `widget` is at the top of the viewport."""
        from PySide6.QtCore import QPoint
        pos = widget.mapTo(self.viewport(), QPoint(0, 0))
        self.animate_to(self.verticalScrollBar().value() + pos.y())
