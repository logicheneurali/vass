"""Notifications editor — configure NotificationRouter actions per event type."""
import configparser
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QComboBox,
    QPushButton, QLabel, QMessageBox,
)
from theme import BASE_STYLESHEET

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

EVENT_LABELS = {
    "default": "notif_editor.default",
    "email": "notif_editor.email",
    "timer": "notif_editor.timer",
    "schedule": "notif_editor.schedule",
    "event_reminder": "notif_editor.event_reminder",
    "plugins": "notif_editor.plugins",
    "ai_error": "notif_editor.ai_error",
    "ai_ready": "notif_editor.ai_ready",
}

ACTION_LABELS = {
    "tts": "notif_editor.tts",
    "notification": "notif_editor.notification",
    "both": "notif_editor.both",
    "none": "notif_editor.none",
}


class NotificationsEditor(QDialog):
    def __init__(self, lang="it", parent=None):
        super().__init__(parent)
        self._lang = lang
        from i18n import t
        self._t = t
        self.setWindowTitle(t("notif_editor.title", lang))
        self.setMinimumSize(480, 380)
        self.setStyleSheet(BASE_STYLESHEET)

        self._ini_path = os.path.join(BASE, "config", "notifications.ini")
        if not os.path.exists(self._ini_path):
            example = self._ini_path.replace(".ini", ".example.ini")
            if os.path.exists(example):
                import shutil
                shutil.copy(example, self._ini_path)

        layout = QVBoxLayout(self)

        header = QLabel(t("notif_editor.subtitle", lang))
        header.setWordWrap(True)
        layout.addWidget(header)

        self._combos = {}
        grid = QGridLayout()
        row = 0
        self._cfg = configparser.ConfigParser()
        self._cfg.read(self._ini_path, encoding="utf-8")
        for event in EVENT_LABELS:
            label = t(EVENT_LABELS[event], lang)
            grid.addWidget(QLabel(label), row, 0)
            combo = QComboBox()
            for action in ("tts", "notification", "both", "none"):
                combo.addItem(t(ACTION_LABELS[action], lang), action)
            current = self._cfg.get(event, "action", fallback="both").strip().lower()
            idx = combo.findData(current)
            combo.setCurrentIndex(idx if idx >= 0 else combo.findData("both"))
            self._combos[event] = combo
            grid.addWidget(combo, row, 1)
            row += 1
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        save_btn = QPushButton(t("notif_editor.save", lang))
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(save_btn)
        cancel_btn = QPushButton(t("notif_editor.cancel", lang))
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def _save(self):
        for event, combo in self._combos.items():
            action = combo.currentData()
            if not self._cfg.has_section(event):
                self._cfg.add_section(event)
            self._cfg.set(event, "action", action)
        try:
            with open(self._ini_path, "w", encoding="utf-8") as f:
                self._cfg.write(f)
        except Exception as e:
            from i18n import t
            QMessageBox.warning(self, t("notif_editor.error", self._lang), str(e))
            return
        from i18n import t
        QMessageBox.information(
            self, t("notif_editor.title", self._lang),
            t("notif_editor.saved", self._lang))
        app = getattr(self.parent(), "app", None) if self.parent() else None
        if app is not None and hasattr(app, "notification_router"):
            app.notification_router.reload()
        self.accept()


def open_editor(lang="it", parent=None):
    dlg = NotificationsEditor(lang=lang, parent=parent)
    dlg.exec()
