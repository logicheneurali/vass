"""Permanent memory viewer/editor for VASS — manage tagged conversation entries."""
import sys, os, json
from PySide6.QtCore import Qt, QUrl, QTimer
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                                QHBoxLayout, QLabel, QPushButton, QCheckBox,
                                QMessageBox, QMenu, QDialog)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEnginePage

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALLOWED = os.path.join(BASE, "Allowed_root")
TAGS_PATH = os.path.join(ALLOWED, "memory_tags.json")
MEM_DIR = os.path.join(ALLOWED, "memory")

from theme import BG, FG, BTN_BG, BASE_STYLESHEET
ACCENT = BTN_BG
TAG_BG = "#3d3d3d"


def _t(path, lang="en"):
    try:
        from i18n import t
        return t(path, lang)
    except Exception:
        return path.split(".")[-1].replace("_", " ").title()


def _load_tags():
    if os.path.exists(TAGS_PATH):
        with open(TAGS_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"entries": []}


def _save_tags_data(data):
    os.makedirs(ALLOWED, exist_ok=True)
    with open(TAGS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _load_entry_content(entry_id):
    hf = os.path.join(MEM_DIR, f"{entry_id}.json")
    if os.path.exists(hf):
        try:
            with open(hf, encoding="utf-8") as f:
                data = json.load(f)
            info = json.loads(data.get("info", "{}"))
            return info.get("content", "(empty)"), info.get("role", "system")
        except Exception:
            pass
    return "(not available)", "system"


def _load_tag_weights():
    cfg_path = os.path.join(ALLOWED, "tags_config.json")
    if os.path.exists(cfg_path):
        with open(cfg_path, encoding="utf-8") as f:
            return json.load(f).get("tags", {})
    from tag_manager import _DEFAULT_TAGS, save_tags_config
    save_tags_config(_DEFAULT_TAGS, 10)
    return dict(_DEFAULT_TAGS)


def _load_min_relevance():
    cfg_path = os.path.join(ALLOWED, "tags_config.json")
    if os.path.exists(cfg_path):
        with open(cfg_path, encoding="utf-8") as f:
            return json.load(f).get("min_relevance", 10)
    return 10


class SourcesDialog(QDialog):
    def __init__(self, parent=None, lang="en"):
        super().__init__(parent)
        self.lang = lang
        self.setWindowTitle(_t("memory_editor.sources_title", lang))
        self.setFixedSize(350, 240)
        self.setStyleSheet(f"QDialog {{ background-color: {BG}; }}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        sources_path = os.path.join(ALLOWED, "memory_sources.json")
        try:
            with open(sources_path, encoding="utf-8") as f:
                self._sources = json.load(f)
        except Exception:
            self._sources = {"email": False, "calendar": False,
                             "events": False, "timers": False}

        self._checkboxes = {}
        for key, label_key in [("email", "sources_email"), ("calendar", "sources_calendar"),
                                ("events", "sources_events"), ("timers", "sources_timers")]:
            cb = QCheckBox(_t(f"memory_editor.{label_key}", lang))
            cb.setChecked(self._sources.get(key, False))
            cb.setStyleSheet(f"color: {FG}; spacing: 8px;")
            self._checkboxes[key] = cb
            layout.addWidget(cb)

        desc = QLabel(_t("memory_editor.sources_description", lang))
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(desc)

        layout.addStretch()
        btn_row = QHBoxLayout()
        cancel_btn = QPushButton(_t("memory_editor.dialog_cancel", lang))
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton(_t("memory_editor.dialog_save", lang))
        save_btn.setStyleSheet(f"background-color: {ACCENT}; font-weight: bold;")
        save_btn.clicked.connect(self._save)
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

    def _save(self):
        sources_path = os.path.join(ALLOWED, "memory_sources.json")
        for key, cb in self._checkboxes.items():
            self._sources[key] = cb.isChecked()
        os.makedirs(ALLOWED, exist_ok=True)
        with open(sources_path, "w", encoding="utf-8") as f:
            json.dump(self._sources, f, ensure_ascii=False, indent=2)
        print(f"[MemoryEditor] Sources saved: {self._sources}")
        QMessageBox.information(self, _t("memory_editor.sources_title", self.lang),
                                _t("memory_editor.sources_saved", self.lang))
        self.accept()


class _MemPage(QWebEnginePage):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._callback = None

    def set_callback(self, cb):
        self._callback = cb

    def acceptNavigationRequest(self, url, _type, is_main_frame):
        if url.scheme() == "vass" and self._callback:
            self._callback(url.toString())
            return False
        return True


class MemoryEditor(QMainWindow):
    def __init__(self, language="en"):
        super().__init__()
        self.lang = language
        self._data = _load_tags()
        self._dirty = False
        self._tag_weights = _load_tag_weights()
        self._min_relevance = _load_min_relevance()
        self._build_ui()
        self._reload_data()
        self._rebuild_content()
        self._show_map = False

    def _tl(self, key):
        return _t(key, self.lang)

    def _build_ui(self):
        self.setWindowTitle(self._tl("memory_editor.title"))
        self.resize(800, 600)
        self.setStyleSheet(BASE_STYLESHEET)
        self.setMinimumSize(600, 400)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        page = _MemPage(self)
        page.set_callback(self._on_vass_link)
        self.browser = QWebEngineView()
        self.browser.setPage(page)
        self.browser.setStyleSheet("background-color: transparent;")
        page.setBackgroundColor(Qt.GlobalColor.transparent)
        layout.addWidget(self.browser, 1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        tags_btn = QPushButton(self._tl("memory_editor.manage_tags"))
        tags_btn.clicked.connect(self._open_tag_manager)
        btn_row.addWidget(tags_btn)
        sources_btn = QPushButton(self._tl("memory_editor.sources"))
        sources_btn.clicked.connect(self._open_sources_dialog)
        btn_row.addWidget(sources_btn)
        self._map_btn = QPushButton(self._tl("memory_editor.map"))
        self._map_btn.setCheckable(True)
        self._map_btn.clicked.connect(self._toggle_map_view)
        btn_row.addWidget(self._map_btn)
        btn_row.addStretch()
        self.save_btn = QPushButton(self._tl("memory_editor.save"))
        self.save_btn.clicked.connect(self._save)
        self.save_btn.setStyleSheet(f"QPushButton {{ background-color: {ACCENT}; font-weight: bold; }}"
                                    "QPushButton:disabled { background-color: #2d2d2d; color: #666; }")
        self.save_btn.setEnabled(False)
        btn_row.addWidget(self.save_btn)
        layout.addLayout(btn_row)

    def _rebuild_content(self):
        self._scroll_y = self.browser.page().scrollPosition().y()

        entries = self._data.get("entries", [])
        entries = [e for e in entries if e.get("relevance", 0) >= self._min_relevance]
        if not entries:
            self.browser.setHtml(f'<div style="color:#888; text-align:center; padding:40px;">'
                                 f'{self._escape_html(self._tl("memory_editor.no_entries"))}</div>',
                                 QUrl("vass://local/"))
            return

        lines = ['<!DOCTYPE html><html><head><meta charset="utf-8"><style>',
                '::-webkit-scrollbar { width: 10px; }',
                '::-webkit-scrollbar-track { background: #1e1e1e; }',
                '::-webkit-scrollbar-thumb { background: #2d2d2d; border-radius: 4px; }',
                '::-webkit-scrollbar-button { display: none; }',
                 'body { margin: 12px; }',
                 'a { color:#ccc; text-decoration:none; font-size:11px; }',
                 'a:hover { color:#fff; }',
                 '.entry-card { background:#252525; border:1px solid #3a3a3a; padding:14px; margin-bottom:12px; }',
                 '.flex-row { display:flex; align-items:center; }',
                 '.spacer { flex:1; }',
                 '</style></head>',
                 f'<body style="background-color:{BG}; color:{FG}; font-family:Segoe UI; font-size:13px;">']

        _src_icons = {"chat": "\U0001F4AC", "email": "\U0001F4E7",
                       "calendar": "\U0001F4C5", "events": "\U0001F4CC", "timers": "\u23F0"}

        for i, entry in enumerate(entries):
            date_str = entry.get("ts", "?")
            tags = entry.get("tags", [])
            relevance = entry.get("relevance", 0)
            src = entry.get("source", "chat")
            src_icon = _src_icons.get(src, "\U0001F4AC")
            eid = entry.get("id", "")
            content, _role = _load_entry_content(eid)
            if content == "(not available)":
                content = entry.get("content", "(nessun contenuto)")
            safe_content = self._escape_html(content[:600])

            lines.append(f'<div class="entry-card">')
            lines.append(f'<div style="margin-bottom:8px;">')
            lines.append(f'<span style="color:#888; font-size:11px;">[{date_str}]</span> ')
            lines.append(f'<span style="color:#aaa; font-size:11px;">{src_icon} {self._tl("memory_editor.relevance_label")}: {relevance}</span>')
            lines.append(f'</div>')
            lines.append(f'<div style="white-space:pre-wrap; margin-bottom:14px; font-size:12px;">{safe_content}</div>')
            lines.append(f'<div class="flex-row" style="margin-top:8px;">')
            lines.append(f'<div>')
            for tag in tags:
                weight = self._tag_weights.get(tag, "?")
                known = tag in self._tag_weights
                if known:
                    lines.append(f'<a href="vass:rmtag:{eid}:{tag}" style="display:inline-block; background:{TAG_BG}; border-radius:3px; padding:3px 8px; margin:2px; font-size:11px;">'
                                 f'{tag} ({weight}) &times;</a>')
                else:
                    lines.append(f'<span style="display:inline-block; background:#444; color:#888; border-radius:3px; padding:3px 8px; margin:2px; font-size:11px;">'
                                 f'{tag} ({weight})</span>')
            lines.append(f'<a href="vass:addtag:{eid}" style="display:inline-block; color:{ACCENT}; font-size:11px; margin:2px;">+ {self._tl("memory_editor.add_tag_button")}</a>')
            lines.append(f'</div>')
            lines.append(f'<a href="vass:delentry:{eid}" style="color:#e74c3c; font-size:11px; white-space:nowrap;">{self._tl("memory_editor.delete_entry")}</a>')
            lines.append(f'</div>')
            lines.append(f'</div>')

        lines.append('</body></html>')
        self.browser.setHtml("\n".join(lines), QUrl("vass://local/"))
        if hasattr(self, '_scroll_y') and self._scroll_y > 0:
            QTimer.singleShot(50, lambda: self.browser.page().runJavaScript(
                f"window.scrollTo(0, {self._scroll_y});"))

    def _on_vass_link(self, href):
        if ":" not in href:
            return
        _, _, rest = href.partition(":")
        parts = rest.split(":", 2)
        action = parts[0]
        if action == "rmtag" and len(parts) >= 3:
            self._remove_tag(parts[1], parts[2])
        elif action == "addtag" and len(parts) >= 2:
            self._show_add_tag_menu(parts[1])
        elif action == "delentry" and len(parts) >= 2:
            self._delete_entry(parts[1])
        elif action == "bubble" and len(parts) >= 2:
            from urllib.parse import unquote
            tag = unquote(parts[1])
            self._show_bubble_detail(tag)
        elif action == "closepanel":
            self._show_bubble_map()

    def _find_entry_idx(self, eid):
        """Find entry index by ID. Returns None if not found."""
        entries = self._data.get("entries", [])
        for i, e in enumerate(entries):
            if e.get("id") == eid:
                return i
        return None

    def _remove_tag(self, eid, tag):
        idx = self._find_entry_idx(eid)
        if idx is None:
            return
        entry = self._data["entries"][idx]
        tags = entry.get("tags", [])
        if tag in tags:
            tags.remove(tag)
            if not tags:
                tags = ["generic"]
            entry["tags"] = tags
            entry["relevance"] = sum(self._tag_weights.get(t, 0) for t in tags)
            self._mark_dirty()
            self._rebuild_content()

    def _show_add_tag_menu(self, eid):
        idx = self._find_entry_idx(eid)
        if idx is None:
            return
        menu = QMenu(self)
        current_tags = set(self._data["entries"][idx].get("tags", []))
        for tag, weight in sorted(self._tag_weights.items(), key=lambda x: -x[1]):
            if tag not in current_tags:
                action = menu.addAction(f"{tag} ({weight})")
                action.triggered.connect(lambda checked, t=tag, e=eid: self._add_tag(e, t))
        if menu.actions():
            menu.exec(self.mapToGlobal(self.rect().center()))

    def _add_tag(self, eid, tag):
        idx = self._find_entry_idx(eid)
        if idx is None:
            return
        entry = self._data["entries"][idx]
        tags = entry.get("tags", [])
        if tag not in tags:
            tags.append(tag)
            entry["tags"] = tags
            entry["relevance"] = sum(self._tag_weights.get(t, 0) for t in tags)
            self._mark_dirty()
            self._rebuild_content()

    def _delete_entry(self, eid):
        idx = self._find_entry_idx(eid)
        if idx is None:
            return
        entry = self._data["entries"][idx]
        desc = entry.get("content", entry.get("description", "?"))[:50]
        msg = QMessageBox(self)
        msg.setWindowTitle(self._tl("memory_editor.delete_entry"))
        msg.setText(self._tl("memory_editor.delete_confirm").replace("{item}", desc))
        msg.setIcon(QMessageBox.Icon.Question)
        yes_btn = msg.addButton(self._tl("memory_editor.dialog_yes"), QMessageBox.ButtonRole.YesRole)
        msg.addButton(self._tl("memory_editor.dialog_no"), QMessageBox.ButtonRole.NoRole)
        msg.exec()
        if msg.clickedButton() == yes_btn:
            del self._data["entries"][idx]
            self._mark_dirty()
            self._rebuild_content()

    def _mark_dirty(self):
        self._dirty = True
        self.save_btn.setEnabled(True)

    def _save(self):
        _save_tags_data(self._data)
        self._dirty = False
        self.save_btn.setEnabled(False)

    def _check_unsaved_and_close(self):
        if self._dirty:
            msg = QMessageBox(self)
            msg.setWindowTitle(self._tl("memory_editor.unsaved_title"))
            msg.setText(self._tl("memory_editor.unsaved_changes"))
            msg.setIcon(QMessageBox.Icon.Question)
            save_btn = msg.addButton(self._tl("memory_editor.dialog_save"), QMessageBox.ButtonRole.AcceptRole)
            discard_btn = msg.addButton(self._tl("memory_editor.dialog_discard"), QMessageBox.ButtonRole.DestructiveRole)
            cancel_btn = msg.addButton(self._tl("memory_editor.dialog_cancel"), QMessageBox.ButtonRole.RejectRole)
            msg.exec()
            clicked = msg.clickedButton()
            if clicked == save_btn:
                self._save()
                self.close()
            elif clicked == discard_btn:
                self.close()
        else:
            self.close()

    def _open_tag_manager(self):
        from tag_manager import TagManager
        dlg = TagManager(self, self.lang)
        if dlg.exec():
            self._tag_weights = dlg.tags
            self._rebuild_content()

    def _open_sources_dialog(self):
        dlg = SourcesDialog(self, self.lang)
        dlg.exec()

    def _toggle_map_view(self, checked):
        self._show_map = checked
        if checked:
            self._show_bubble_map()
        else:
            self._reload_data()
            self._rebuild_content()

    def _reload_data(self):
        self._data = _load_tags()
        self._tag_weights = _load_tag_weights()
        self._min_relevance = _load_min_relevance()

    def _show_bubble_map(self):
        entries = self._data.get("entries", [])
        entries = [e for e in entries if e.get("relevance", 0) >= self._min_relevance]
        if not entries:
            self.browser.setHtml(
                f'<div style="color:#888; text-align:center; padding:40px;">'
                f'{self._escape_html(self._tl("memory_editor.no_entries"))}</div>',
                QUrl("vass://local/"))
            return

        import json as _json
        entries_json = _json.dumps(entries, ensure_ascii=False)
        weights_json = _json.dumps(self._tag_weights, ensure_ascii=False)

        # Build sorted tag list for sidebar
        tag_counts = {}
        for e in entries:
            for t in e.get("tags", []):
                tag_counts[t] = tag_counts.get(t, 0) + 1
        sorted_tags = sorted(tag_counts.items(), key=lambda x: (-x[1], x[0]))
        tags_html = ""
        for tag, count in sorted_tags:
            tags_html += (
                f'<div class="tag-row" onclick="window.location.href=\'vass:bubble:'
                f'{self._escape_html(tag)}\'" title="{self._escape_html(tag)} ({count})">'
                f'<span class="tag-name">{self._escape_html(tag)}</span>'
                f'<span class="tag-count">{count}</span></div>')

        # Localized strings for JS
        map_title_fmt = _json.dumps(self._tl("memory_editor.map_title"))
        map_subtitle = _json.dumps(self._tl("memory_editor.map_subtitle"))
        map_tooltip_fmt = _json.dumps(self._tl("memory_editor.map_tooltip"))
        sidebar_label = self._tl("memory_editor.map_sidebar")

        html = f'''<!DOCTYPE html><html><head><meta charset="utf-8"><style>
::-webkit-scrollbar {{ width: 6px; }}
::-webkit-scrollbar-track {{ background: #1e1e1e; }}
::-webkit-scrollbar-thumb {{ background: #3a3a3a; border-radius: 3px; }}
body {{ margin: 0; overflow: hidden;
       background: #0d1117; font-family: "Segoe UI", sans-serif;
       display: flex; height: 100vh; }}
#sidebar {{ flex: 0 0 180px; background: #111122; border-right: 1px solid #1a1a3a;
           overflow-y: auto; padding: 8px 0; }}
#sidebar h4 {{ color: #888; font-size: 11px; margin: 0; padding: 8px 12px 4px 12px;
              text-transform: uppercase; letter-spacing: 1px; }}
.tag-row {{ display: flex; justify-content: space-between; align-items: center;
           padding: 5px 12px; cursor: pointer; font-size: 12px;
           color: #aaa; border-left: 3px solid transparent; }}
.tag-row:hover {{ color: #e0e0e0; background: rgba(255,255,255,0.05);
                 border-left-color: #0f3460; }}
.tag-row.active {{ color: #e94560; background: rgba(233,69,96,0.1);
                  border-left-color: #e94560; }}
.tag-name {{ flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.tag-count {{ color: #666; font-size: 10px; margin-left: 6px; }}
#map-area {{ flex: 1; position: relative; overflow: hidden;
            background: radial-gradient(ellipse at center, #1a1a2e 0%, #0d1117 80%); }}
canvas {{ display: block; }}
#tooltip {{ position: fixed; pointer-events: none; display: none;
           background: #252525; color: #e0e0e0; padding: 8px 12px;
           border: 1px solid #3a3a3a; border-radius: 4px; font-size: 12px;
           z-index: 10; white-space: nowrap; }}
</style></head><body>
<div id="sidebar"><h4>{self._escape_html(sidebar_label)}</h4>{tags_html}</div>
<div id="map-area"><canvas id="map"></canvas></div>
<div id="tooltip"></div>
<script>
const entries = {entries_json};
const weights = {weights_json};
const canvas = document.getElementById("map");
const ctx = canvas.getContext("2d");
const tooltip = document.getElementById("tooltip");
const mapArea = document.getElementById("map-area");

const tagData = {{}};
for (const e of entries) {{
    const tags = e.tags || [];
    for (const t of tags) {{
        if (!tagData[t]) tagData[t] = {{ tag: t, count: 0, totalRel: 0, entries: [], sources: new Set() }};
        tagData[t].count++;
        tagData[t].totalRel += e.relevance || 0;
        tagData[t].entries.push(e);
        if (e.source) tagData[t].sources.add(e.source);
    }}
}}
const bubbles = Object.values(tagData);
const totalEntries = entries.length;
const uniqueTags = bubbles.length;

const K = 18;
let maxRel = 0;
for (const b of bubbles) {{
    b.r = Math.min(120, Math.max(20, Math.sqrt(b.count) * K));
    b.avgRel = b.count > 0 ? b.totalRel / b.count : 0;
    if (b.avgRel > maxRel) maxRel = b.avgRel;
}}

function getColor(avgRel) {{
    const ratio = maxRel > 0 ? Math.min(1, avgRel / maxRel) : 0;
    const stops = [
        {{pos:0.0, r:0x34, g:0x98, b:0xdb}},
        {{pos:0.25, r:0x1a, g:0xbc, b:0x9c}},
        {{pos:0.5, r:0xf1, g:0xc4, b:0x0f}},
        {{pos:0.75, r:0xe6, g:0x7e, b:0x22}},
        {{pos:1.0, r:0xe7, g:0x4c, b:0x3c}}
    ];
    let lo = stops[0], hi = stops[stops.length-1];
    for (let i = 0; i < stops.length-1; i++) {{
        if (ratio >= stops[i].pos && ratio <= stops[i+1].pos) {{
            lo = stops[i]; hi = stops[i+1]; break;
        }}
    }}
    const t = (ratio - lo.pos) / (hi.pos - lo.pos || 0.001);
    const r = Math.round(lo.r + (hi.r - lo.r) * t);
    const g = Math.round(lo.g + (hi.g - lo.g) * t);
    const b = Math.round(lo.b + (hi.b - lo.b) * t);
    return `rgb(${{r}},${{g}},${{b}})`;
}}

for (const b of bubbles) b.color = getColor(b.avgRel);

function resize() {{
    canvas.width = mapArea.clientWidth;
    canvas.height = mapArea.clientHeight;
}}
resize();
window.addEventListener("resize", () => {{ resize(); step(30); draw(); }});

let cx = 0, cy = 0;
function resetLayout() {{
    cx = canvas.width / 2;
    cy = canvas.height / 2;
    const sorted = [...bubbles].sort((a, b) => a.tag.localeCompare(b.tag));
    const baseR = Math.max(60, Math.min(cx, cy) * 0.25);
    for (let i = 0; i < sorted.length; i++) {{
        const angle = (i / sorted.length) * Math.PI * 2;
        sorted[i].x = cx + Math.cos(angle) * baseR;
        sorted[i].y = cy + Math.sin(angle) * baseR;
        sorted[i].vx = 0;
        sorted[i].vy = 0;
    }}
}}
resetLayout();

function step(iterations) {{
    const centerGravity = 0.01;
    const repulsion = 800;
    const damping = 0.9;
    for (let i = 0; i < iterations; i++) {{
        for (const b of bubbles) {{
            let fx = 0, fy = 0;
            fy += (cy - b.y) * centerGravity * (b.r / 50);
            fx += (cx - b.x) * centerGravity * (b.r / 50);
            for (const o of bubbles) {{
                if (o === b) continue;
                let dx = b.x - o.x;
                let dy = b.y - o.y;
                let dist = Math.sqrt(dx * dx + dy * dy) || 1;
                let minDist = b.r + o.r + 8;
                if (dist < minDist) {{
                    let force = repulsion / (dist * dist);
                    fx += (dx / dist) * force * damping;
                    fy += (dy / dist) * force * damping;
                }}
            }}
            if (!b.vx) b.vx = 0;
            if (!b.vy) b.vy = 0;
            b.vx = (b.vx + fx) * damping;
            b.vy = (b.vy + fy) * damping;
            b.x += b.vx;
            b.y += b.vy;
            b.x = Math.max(b.r, Math.min(canvas.width - b.r, b.x));
            b.y = Math.max(b.r + 40, Math.min(canvas.height - b.r - 10, b.y));
        }}
    }}
}}
step(80);

let hovered = null;
let activeTag = null;

function draw() {{
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = "#e0e0e0";
    ctx.font = "14px 'Segoe UI', sans-serif";
    const titleText = {map_title_fmt}.replace("{total}", totalEntries).replace("{tags}", uniqueTags);
    ctx.fillText(titleText, 16, 30);
    ctx.fillStyle = "#888";
    ctx.font = "11px 'Segoe UI', sans-serif";
    ctx.fillText({map_subtitle}, 16, 48);

    const sorted = [...bubbles].sort((a,b) => b.r - a.r);
    for (const b of sorted) {{
        const isHover = (b === hovered);
        const isActive = (b === activeTag);
        const r = isHover ? b.r * 1.15 : b.r;

        const grad = ctx.createRadialGradient(b.x, b.y, r*0.7, b.x, b.y, r);
        grad.addColorStop(0, b.color);
        grad.addColorStop(1, "rgba(0,0,0,0.3)");
        ctx.beginPath();
        ctx.arc(b.x, b.y, r, 0, Math.PI * 2);
        ctx.fillStyle = grad;
        ctx.fill();

        if (isActive) {{
            ctx.strokeStyle = "#e94560";
            ctx.lineWidth = 3;
        }} else if (isHover) {{
            ctx.strokeStyle = "rgba(255,255,255,0.6)";
            ctx.lineWidth = 2;
        }} else {{
            ctx.strokeStyle = "rgba(255,255,255,0.15)";
            ctx.lineWidth = 1;
        }}
        ctx.stroke();

        ctx.fillStyle = "#ffffff";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        if (r > 30) {{
            ctx.font = Math.min(16, Math.max(9, r*0.35)) + "px 'Segoe UI', sans-serif";
            ctx.fillText(b.tag, b.x, b.y - 4);
            ctx.font = Math.max(8, r*0.22) + "px 'Segoe UI', sans-serif";
            ctx.fillStyle = "rgba(255,255,255,0.7)";
            ctx.fillText(b.count, b.x, b.y + 12);
        }} else {{
            ctx.font = "10px 'Segoe UI', sans-serif";
            ctx.fillText(b.count, b.x, b.y);
        }}
        ctx.textAlign = "start";
        ctx.textBaseline = "alphabetic";
    }}
}}

canvas.addEventListener("mousemove", (e) => {{
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left, my = e.clientY - rect.top;
    let found = null;
    for (const b of bubbles) {{
        const dx = mx - b.x, dy = my - b.y;
        if (Math.sqrt(dx*dx + dy*dy) < b.r) {{ found = b; break; }}
    }}
    if (found !== hovered) {{
        hovered = found;
        draw();
        if (found) {{
            tooltip.style.display = "block";
            tooltip.style.left = (e.clientX + 15) + "px";
            tooltip.style.top = (e.clientY - 10) + "px";
            const icons = {{chat:"\\ud83d\\udcac", email:"\\ud83d\\udce7", calendar:"\\ud83d\\udcc5", events:"\\ud83d\\udccc", timers:"\\u23f0"}};
            const sources = [...found.sources].map(s => icons[s] || s).join(" ");
            const tipText = {map_tooltip_fmt}.replace("{tag}", found.tag).replace("{count}", found.count).replace("{rel}", Math.round(found.avgRel));
            tooltip.innerHTML = tipText + "<br>" + sources;
        }} else {{
            tooltip.style.display = "none";
        }}
    }}
}});

canvas.addEventListener("click", (e) => {{
    if (hovered) {{
        activeTag = hovered;
        draw();
        window.location.href = "vass:bubble:" + encodeURIComponent(hovered.tag);
    }}
}});

draw();
</script></body></html>'''
        self.browser.setHtml(html, QUrl("vass://local/"))

    def _show_bubble_detail(self, tag):
        entries = self._data.get("entries", [])
        entries = [e for e in entries if e.get("relevance", 0) >= self._min_relevance]
        tagged = [e for e in entries if tag in e.get("tags", [])]
        tagged.sort(key=lambda e: e.get("ts", ""), reverse=True)

        import json as _json
        entries_json = _json.dumps(entries, ensure_ascii=False)
        weights_json = _json.dumps(self._tag_weights, ensure_ascii=False)
        tagged_json = _json.dumps(tagged, ensure_ascii=False)

        source_icons = {"chat": "\U0001F4AC", "email": "\U0001F4E7",
                        "calendar": "\U0001F4C5", "events": "\U0001F4CC", "timers": "\u23F0"}

        # Build sorted tag list for sidebar
        tag_counts = {}
        for e in entries:
            for t in e.get("tags", []):
                tag_counts[t] = tag_counts.get(t, 0) + 1
        sorted_tags = sorted(tag_counts.items(), key=lambda x: (-x[1], x[0]))
        tags_html = ""
        for tname, count in sorted_tags:
            active_cls = " active" if tname == tag else ""
            tags_html += (
                f'<div class="tag-row{active_cls}" onclick="window.location.href=\'vass:bubble:'
                f'{self._escape_html(tname)}\'" title="{self._escape_html(tname)} ({count})">'
                f'<span class="tag-name">{self._escape_html(tname)}</span>'
                f'<span class="tag-count">{count}</span></div>')

        sidebar_label = self._tl("memory_editor.map_sidebar")

        cards_html = ""
        for entry in tagged:
            ts = entry.get("ts", "?")
            entry_tags = entry.get("tags", [])
            relevance = entry.get("relevance", 0)
            src = entry.get("source", "chat")
            icon = source_icons.get(src, "\U0001F4AC")
            content, _role = _load_entry_content(entry.get("id", "?"))
            if content == "(not available)":
                content = entry.get("content", "(nessun contenuto)")
            safe_content = self._escape_html(content[:200])
            dot_color = "#27ae60" if relevance > 20 else ("#f1c40f" if relevance > 10 else "#888")
            tags_badges = " ".join(
                f'<span class="tag-badge">{self._escape_html(t)}</span>'
                for t in entry_tags)
            cards_html += f'''
<div class="entry-card">
<div class="ts">{icon} {self._escape_html(ts)}</div>
<div class="content"><span class="relevance-dot" style="background:{dot_color};"></span>{safe_content}</div>
<div class="tags-row">{tags_badges}</div>
</div>'''

        html = f'''<!DOCTYPE html><html><head><meta charset="utf-8"><style>
::-webkit-scrollbar {{ width: 8px; }}
::-webkit-scrollbar-track {{ background: #1e1e1e; }}
::-webkit-scrollbar-thumb {{ background: #3a3a3a; border-radius: 4px; }}
body {{ margin: 0; background: #0d1117; font-family: "Segoe UI", sans-serif;
       color: #e0e0e0; display: flex; height: 100vh; }}
#sidebar {{ flex: 0 0 160px; background: #111122; border-right: 1px solid #1a1a3a;
           overflow-y: auto; padding: 8px 0; }}
#sidebar h4 {{ color: #888; font-size: 11px; margin: 0; padding: 8px 12px 4px 12px;
              text-transform: uppercase; letter-spacing: 1px; }}
.tag-row {{ display: flex; justify-content: space-between; align-items: center;
           padding: 4px 10px; cursor: pointer; font-size: 11px;
           color: #aaa; border-left: 3px solid transparent; }}
.tag-row:hover {{ color: #e0e0e0; background: rgba(255,255,255,0.05);
                 border-left-color: #0f3460; }}
.tag-row.active {{ color: #e94560; background: rgba(233,69,96,0.1);
                  border-left-color: #e94560; }}
.tag-name {{ flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
.tag-count {{ color: #666; font-size: 10px; margin-left: 6px; }}
#map-area {{ flex: 0 0 50%; position: relative; overflow: hidden;
            background: radial-gradient(ellipse at center, #1a1a2e 0%, #0d1117 80%); }}
#panel {{ flex: 1; background: #1a1a2e; border-left: 1px solid #0f3460;
          overflow-y: auto; padding: 16px; }}
#panel-header {{ margin-bottom: 16px; }}
#panel-header h3 {{ margin: 0 0 4px 0; font-size: 15px; }}
#panel-header .meta {{ color: #888; font-size: 12px; margin-bottom: 8px; }}
.close-btn {{ float: right; background: transparent; border: none; color: #888;
            font-size: 18px; cursor: pointer; }}
.close-btn:hover {{ color: #e0e0e0; }}
.entry-card {{ background: #252525; border: 1px solid #3a3a3a; border-radius: 4px;
              padding: 12px; margin-bottom: 10px; font-size: 12px; }}
.entry-card .ts {{ color: #888; font-size: 11px; margin-bottom: 4px; }}
.entry-card .content {{ margin-top: 6px; white-space: pre-wrap; }}
.entry-card .tags-row {{ margin-top: 8px; display: flex; flex-wrap: wrap; gap: 4px; }}
.tag-badge {{ background: #3d3d3d; border-radius: 3px; padding: 2px 6px; font-size: 10px; }}
.relevance-dot {{ display: inline-block; width: 8px; height: 8px; border-radius: 50%;
                 margin-right: 6px; }}
</style></head><body>
<div id="sidebar"><h4>{self._escape_html(sidebar_label)}</h4>{tags_html}</div>
<div id="map-area">
<canvas id="map" style="width:100%;height:100%;"></canvas>
</div>
<div id="panel">
<div id="panel-header">
<button class="close-btn" onclick="window.location.href='vass:closepanel'">&times;</button>
<h3>{self._escape_html(tag)}</h3>
<div class="meta">{self._tl("memory_editor.map_items").replace("{count}", str(len(tagged)))}</div>
</div>
<div id="entries">
{cards_html}
</div>
</div>
<script>
const entries = {entries_json};
const weights = {weights_json};
const ACTIVE_TAG = {_json.dumps(tag)};
const canvas = document.getElementById("map");
const ctx = canvas.getContext("2d");
const mapArea = document.getElementById("map-area");

function resize() {{
    canvas.width = mapArea.clientWidth;
    canvas.height = mapArea.clientHeight;
}}

const tagData = {{}};
for (const e of entries) {{
    const tags = e.tags || [];
    for (const t of tags) {{
        if (!tagData[t]) tagData[t] = {{ tag: t, count: 0, totalRel: 0, sources: new Set() }};
        tagData[t].count++;
        tagData[t].totalRel += e.relevance || 0;
        if (e.source) tagData[t].sources.add(e.source);
    }}
}}
const bubbles = Object.values(tagData);
const K = 18;
let maxRel = 0;
for (const b of bubbles) {{
    b.r = Math.min(120, Math.max(20, Math.sqrt(b.count) * K));
    b.avgRel = b.count > 0 ? b.totalRel / b.count : 0;
    if (b.avgRel > maxRel) maxRel = b.avgRel;
}}
function getColor(avgRel) {{
    const ratio = maxRel > 0 ? Math.min(1, avgRel / maxRel) : 0;
    const stops = [
        {{pos:0.0, r:0x34, g:0x98, b:0xdb}}, {{pos:0.25, r:0x1a, g:0xbc, b:0x9c}},
        {{pos:0.5, r:0xf1, g:0xc4, b:0x0f}}, {{pos:0.75, r:0xe6, g:0x7e, b:0x22}},
        {{pos:1.0, r:0xe7, g:0x4c, b:0x3c}}
    ];
    let lo = stops[0], hi = stops[stops.length-1];
    for (let i = 0; i < stops.length-1; i++) {{
        if (ratio >= stops[i].pos && ratio <= stops[i+1].pos) {{ lo = stops[i]; hi = stops[i+1]; break; }}
    }}
    const t = (ratio - lo.pos) / (hi.pos - lo.pos || 0.001);
    return `rgb(${{Math.round(lo.r+(hi.r-lo.r)*t)}},${{Math.round(lo.g+(hi.g-lo.g)*t)}},${{Math.round(lo.b+(hi.b-lo.b)*t)}})`;
}}
for (const b of bubbles) b.color = getColor(b.avgRel);

function layout() {{
    const cx = canvas.width / 2, cy = canvas.height / 2;
    const sorted = [...bubbles].sort((a, b) => a.tag.localeCompare(b.tag));
    const baseR = Math.max(50, Math.min(cx, cy) * 0.2);
    for (let i = 0; i < sorted.length; i++) {{
        const angle = (i / sorted.length) * Math.PI * 2;
        sorted[i].x = cx + Math.cos(angle) * baseR;
        sorted[i].y = cy + Math.sin(angle) * baseR;
        sorted[i].vx = 0;
        sorted[i].vy = 0;
    }}
    for (let i = 0; i < 60; i++) {{
        for (const b of bubbles) {{
            let fx = 0, fy = 0;
            fy += (cy - b.y) * 0.01 * (b.r / 50);
            fx += (cx - b.x) * 0.01 * (b.r / 50);
            for (const o of bubbles) {{
                if (o === b) continue;
                const dx = b.x - o.x, dy = b.y - o.y;
                const dist = Math.sqrt(dx*dx + dy*dy) || 1;
                const minDist = b.r + o.r + 6;
                if (dist < minDist) {{
                    const force = 600 / (dist * dist);
                    if (!b.vx) b.vx = 0; if (!b.vy) b.vy = 0;
                    b.vx = (b.vx + (dx/dist) * force) * 0.85;
                    b.vy = (b.vy + (dy/dist) * force) * 0.85;
                    b.x += b.vx; b.y += b.vy;
                    b.x = Math.max(b.r, Math.min(canvas.width - b.r, b.x));
                    b.y = Math.max(b.r + 30, Math.min(canvas.height - b.r - 10, b.y));
                }}
            }}
        }}
    }}
}}
layout();

function draw() {{
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    for (const b of [...bubbles].sort((a,b) => b.r - a.r)) {{
        const isActive = (b.tag === ACTIVE_TAG);
        const grad = ctx.createRadialGradient(b.x, b.y, b.r*0.7, b.x, b.y, b.r);
        grad.addColorStop(0, isActive ? "#e94560" : b.color);
        grad.addColorStop(1, "rgba(0,0,0,0.3)");
        ctx.beginPath();
        ctx.arc(b.x, b.y, b.r, 0, Math.PI*2);
        ctx.fillStyle = grad;
        ctx.fill();
        ctx.strokeStyle = isActive ? "#e94560" : "rgba(255,255,255,0.15)";
        ctx.lineWidth = isActive ? 2 : 1;
        ctx.stroke();
        ctx.fillStyle = "#fff";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        if (b.r > 25) {{
            ctx.font = Math.min(16, Math.max(9, b.r*0.35)) + "px 'Segoe UI',sans-serif";
            ctx.fillText(b.tag, b.x, b.y - 3);
            ctx.font = Math.max(8, b.r*0.22) + "px 'Segoe UI',sans-serif";
            ctx.fillStyle = "rgba(255,255,255,0.7)";
            ctx.fillText(b.count, b.x, b.y + 12);
        }} else {{
            ctx.font = "10px 'Segoe UI',sans-serif";
            ctx.fillText(b.count, b.x, b.y);
        }}
        ctx.textAlign = "start";
        ctx.textBaseline = "alphabetic";
    }}
}}

canvas.addEventListener("click", (e) => {{
    const mx = e.clientX - canvas.getBoundingClientRect().left;
    const my = e.clientY - canvas.getBoundingClientRect().top;
    for (const b of bubbles) {{
        const dx = mx - b.x, dy = my - b.y;
        if (Math.sqrt(dx*dx + dy*dy) < b.r) {{
            window.location.href = "vass:bubble:" + encodeURIComponent(b.tag);
            return;
        }}
    }}
}});

resize();
layout();
draw();
window.addEventListener("resize", () => {{ resize(); layout(); draw(); }});
</script></body></html>'''
        self.browser.setHtml(html, QUrl("vass://local/"))

    def closeEvent(self, event):
        self._check_unsaved_and_close()
        event.ignore()

    @staticmethod
    def _escape_html(text):
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def main():
    lang = "en"
    for i, a in enumerate(sys.argv[1:]):
        if a == "--lang" and i + 1 < len(sys.argv[1:]):
            lang = sys.argv[i + 2]
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    editor = MemoryEditor(language=lang)
    editor.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
