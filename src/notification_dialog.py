"""Notification dialog for VASS — shows grouped notifications with type filtering."""
import webbrowser

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextBrowser,
)

from theme import (BG, FG, BTN_BG, BTN_FG, LABEL_FG, BTN_DEL_BG, SECTION_FG,
                   FRAME_BORDER, ENTRY_BG, BASE_STYLESHEET)


TYPE_ICONS = {
    "rss": "\U0001f4f0", "timer": "\u23f0", "event": "\U0001f4c5",
    "schedule": "\U0001f4cb", "mail": "\U0001f4e7", "auth": "\U0001f511",
    "script": "\U0001f4dc",
}

TYPE_COLORS = {
    "rss": BTN_BG, "timer": "#e74c3c", "event": "#f1c40f",
    "schedule": "#f39c12", "mail": "#3498db", "auth": "#e74c3c",
    "script": "#9b59b6",
}


class NotificationDialog:
    """Modal dialog showing notifications grouped by type with clickable filter badges."""

    def __init__(self, parent, notifs, notification_manager,
                 rss_reader=None, t_fn=None):
        self._parent = parent
        self._notifs = notifs
        self._notification_manager = notification_manager
        self._rss_reader = rss_reader
        self._t = t_fn or (lambda k: k.split(".")[-1])
        self._selected_types = set()
        self._type_btns = {}
        self._dlg = None
        self._browser = None

    def exec(self):
        self._mark_seen()
        self._selected_types.clear()
        self._dlg = self._build_dialog()
        self._dlg.exec()
        return self._dlg

    def _mark_seen(self):
        if not self._rss_reader:
            return
        guids = []
        for n in self._notifs:
            data = n.get("data")
            if isinstance(data, dict) and data.get("type") == "rss":
                guid = data.get("guid", "")
                if guid:
                    guids.append(guid)
        if guids:
            self._rss_reader.mark_guids_seen(guids)

    def _build_dialog(self):
        dlg = QDialog(self._parent)
        dlg.setWindowTitle(self._t("gui.notifications"))
        dlg.resize(440, 480)
        dlg.setMinimumSize(360, 320)
        dlg.setStyleSheet(BASE_STYLESHEET)

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        all_notifs = self._notifs
        unread_notifs = [n for n in all_notifs if not n.get("read", False)]

        type_counts = {}
        unread_by_type = {}
        for n in all_notifs:
            data = n.get("data") or {}
            t = data.get("type", "other")
            if t not in type_counts:
                type_counts[t] = 0
                unread_by_type[t] = 0
            type_counts[t] += 1
            if not n.get("read", False):
                unread_by_type[t] += 1

        header = self._build_header(all_notifs, type_counts, unread_by_type, dlg)
        layout.addLayout(header)

        self._browser = QTextBrowser()
        self._browser.setOpenExternalLinks(False)
        self._browser.setOpenLinks(False)
        self._browser.setStyleSheet(
            f"background-color: #252525; color: {FG};"
            f"border: 1px solid {FRAME_BORDER}; border-radius: 4px;"
            f"padding: 8px; font-size: 12px;"
            "QScrollBar:vertical { background: #252525; width: 10px; }"
            f"QScrollBar::handle:vertical {{ background: {ENTRY_BG}; border-radius: 4px; min-height: 20px; }}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }"
        )
        self._browser.anchorClicked.connect(self._on_link_clicked)
        self._refresh_html(unread_notifs, all_notifs)
        layout.addWidget(self._browser, 1)

        btn_row = QHBoxLayout()
        mark_btn = QPushButton(self._t("gui.mark_read"))
        mark_btn.clicked.connect(lambda: self._notification_manager.mark_all_read())
        mark_btn.clicked.connect(dlg.close)
        btn_row.addWidget(mark_btn)
        btn_row.addStretch()
        close_btn = QPushButton(self._t("gui.close"))
        close_btn.setStyleSheet(
            f"background-color: transparent; color: {LABEL_FG};"
            f"border: 1px solid {FRAME_BORDER}; border-radius: 3px; padding: 5px 16px;"
        )
        close_btn.clicked.connect(dlg.close)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        return dlg

    def _build_header(self, all_notifs, type_counts, unread_by_type, dlg):
        header = QHBoxLayout()
        title_lbl = QLabel(self._t("gui.notifications"))
        title_lbl.setStyleSheet(
            f"font-weight: bold; font-size: 14px; color: {SECTION_FG};"
        )
        header.addWidget(title_lbl)
        shown_types = {t: c for t, c in unread_by_type.items() if c > 0}
        if not shown_types:
            shown_types = type_counts
        self._type_btns.clear()
        for t, count in shown_types.items():
            if count <= 0:
                continue
            icon = TYPE_ICONS.get(t, "")
            color = TYPE_COLORS.get(t, "#888888")
            btn = QPushButton(f"{icon} {count}")
            btn.setFlat(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(
                f"QPushButton {{ background-color: {color}; color: {BTN_FG}; "
                f"border-radius: 8px; padding: 2px 8px; font-size: 11px; font-weight: bold; }}"
            )
            def make_handler(typ, b):
                return lambda: self._on_type_toggle(typ, b, all_notifs)
            btn.clicked.connect(make_handler(t, btn))
            self._type_btns[t] = btn
            header.addWidget(btn)
        header.addStretch()
        return header

    def _on_type_toggle(self, typ, btn, all_notifs):
        self._selected_types.symmetric_difference_update({typ})
        unread_notifs = [n for n in all_notifs if not n.get("read", False)]
        self._refresh_html(unread_notifs, all_notifs)
        self._update_badge_styles(btn)

    def _refresh_html(self, unread_notifs, all_notifs):
        filtered = unread_notifs
        if self._selected_types:
            filtered = [n for n in filtered
                        if (n.get("data") or {}).get("type", "other") in self._selected_types]
        self._update_badge_styles(None)
        html = self._build_html(filtered)
        self._browser.setHtml(html)

    def _update_badge_styles(self, exclude_btn):
        for t, btn in self._type_btns.items():
            if btn is exclude_btn:
                continue
            color = TYPE_COLORS.get(t, "#888888")
            if not self._selected_types:
                btn.setStyleSheet(
                    f"QPushButton {{ background-color: {color}; color: {BTN_FG}; "
                    f"border-radius: 8px; padding: 2px 8px; font-size: 11px; font-weight: bold; }}"
                )
            elif t in self._selected_types:
                btn.setStyleSheet(
                    f"QPushButton {{ background-color: {color}; color: {BTN_FG}; "
                    f"border: 2px solid #ffffff; border-radius: 8px; padding: 2px 8px; "
                    f"font-size: 11px; font-weight: bold; }}"
                )
            else:
                btn.setStyleSheet(
                    f"QPushButton {{ background-color: {color}; color: {BTN_FG}; "
                    f"border-radius: 8px; padding: 2px 8px; font-size: 11px; font-weight: bold; opacity: 0.35; }}"
                )

    def _build_html(self, items):
        parts = ['<html><body style="background-color:#252525; color:#e0e0e0; margin:0;">']
        if not items:
            parts.append(
                f'<p style="color:{LABEL_FG}; text-align:center; padding:20px;">'
                f'{self._t("gui.no_notifications")}</p>'
            )
        else:
            for i, n in enumerate(items):
                data = n.get("data") or {}
                ntype = data.get("type", "other")
                icon = TYPE_ICONS.get(ntype, "\u25cf")
                icon_color = TYPE_COLORS.get(
                    ntype, self._notification_manager.color_for(n["priority"])
                )
                ts = n.get("ts", "")
                txt = n.get("text", "")
                escaped_txt = txt.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
                if ntype == "rss":
                    link = data.get("link", "")
                    escaped_link = link.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
                    parts.append(
                        f'<div style="padding:6px 0;">'
                        f'<span style="color:{icon_color};">{icon}</span> '
                        f'<span style="color:{LABEL_FG}; font-size:11px;">{ts}</span> '
                        f'<span style="color:{FG};">{escaped_txt}</span><br>'
                        f'<a href="{escaped_link}" style="color:{BTN_BG}; font-size:11px; text-decoration:none;">'
                        f'{self._t("rss.read_article")}</a></div>'
                    )
                elif ntype == "mail" and data.get("link"):
                    link = data.get("link", "")
                    escaped_link = link.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
                    parts.append(
                        f'<div style="padding:6px 0;">'
                        f'<span style="color:{icon_color};">{icon}</span> '
                        f'<span style="color:{LABEL_FG}; font-size:11px;">{ts}</span> '
                        f'<span style="color:{FG};">{escaped_txt}</span><br>'
                        f'<a href="{escaped_link}" style="color:{BTN_BG}; font-size:11px; text-decoration:none;">'
                        f'{self._t("notifications.read_online")}</a></div>'
                    )
                else:
                    parts.append(
                        f'<div style="padding:6px 0;">'
                        f'<span style="color:{icon_color};">{icon}</span> '
                        f'<span style="color:{LABEL_FG}; font-size:11px;">{ts}</span> '
                        f'<span style="color:{FG};">{escaped_txt}</span></div>'
                    )
                if i < len(items) - 1:
                    parts.append(
                        f'<hr style="border: none; border-top: 1px solid {FRAME_BORDER}; margin: 4px 0;">'
                    )
        parts.append('</body></html>')
        return "".join(parts)

    def _on_link_clicked(self, qurl):
        url = qurl.toString()
        if self._dlg:
            self._dlg.accept()
        webbrowser.open(url)
