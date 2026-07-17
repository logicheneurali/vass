"""VASS Plugin System — base classes and plugin manager.

A plugin is a self-contained feature module with its own manifest (plugin.json).
Plugins can be internal (never removed) or external (removable by user).
"""
import json
import logging
import os
import shutil
import sys
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Optional

from utils import get_project_root

_log = logging.getLogger(__name__)


class PluginType(Enum):
    INTERNAL = "internal"
    EXTERNAL = "external"


class Plugin(ABC):
    """Base class for all VASS plugins.

    Subclasses MUST override on_load(). All other methods are optional.
    The PluginManager populates `self.manifest` from plugin.json before
    calling any lifecycle methods.
    """

    manifest: dict = {}

    @abstractmethod
    def on_load(self, app) -> None:
        """Called once when the plugin is activated at startup.
        Receives the VASSApp instance for access to all core services.
        """
        ...

    def on_unload(self) -> None:
        """Called when the plugin is deactivated (shutdown or disable)."""

    def on_settings_change(self, settings: dict) -> None:
        """Called when settings.ini is reloaded."""

    def get_threads(self) -> list:
        """Return list of (target, args, kwargs) tuples for daemon threads.
        Example: [(self._loop, (), {"daemon": True})]
        """
        return []

    def get_gui_windows(self) -> dict:
        """Return {window_key: (QMainWindowClass, kwargs)} for menu-registered windows."""
        return {}

    def get_config_widgets(self, section: str) -> list:
        """Return list of (tab_name, QWidget) for dynamic config panels (e.g. sources_editor)."""
        return []

    def get_config_defaults(self) -> dict:
        """Return {section: {key: value}} for settings.ini defaults."""
        return {}

    def get_main_loop_hooks(self) -> list:
        """Return list of callables called once per main loop iteration.
        Each receives (frame, raw_rms, current_state) and must be fast.
        """
        return []

    def get_hook(self, name: str) -> list:
        """Return list of callables for the named hook point.
        Hook names: main_loop_frame, auto_pause_check, reset_state, etc.
        """
        return []


class PluginManager:
    """Discovers, loads, activates, and manages plugins."""

    def __init__(self, config_path: str = "plugins/plugins.json"):
        self._plugins: dict[str, Plugin] = {}
        self._loaded: dict[str, Plugin] = {}
        self._config_path = os.path.join(get_project_root(), config_path)
        self._config: dict[str, bool] = {}
        self._app = None  # set later via load_all()

    # ── Public API ─────────────────────────────────────────────

    def load_all(self, app) -> list[Plugin]:
        """Discover plugins, validate, load active ones. Call once at startup."""
        self._app = app
        self._load_config()
        self._discover()
        self._validate()
        return self._activate()

    def get_active(self) -> list[Plugin]:
        """Return currently loaded and active plugins."""
        return list(self._loaded.values())

    def get_loaded(self, name: str) -> Optional[Plugin]:
        return self._loaded.get(name)

    def is_active(self, name: str) -> bool:
        return name in self._loaded

    def enable(self, name: str, app) -> bool:
        """Enable a plugin at runtime (requires restart for full effect)."""
        if name not in self._plugins:
            return False
        self._config[name] = True
        self._save_config()
        if app:
            try:
                plugin = self._plugins[name]
                plugin.on_load(app)
                self._loaded[name] = plugin
                for t, a, kw in plugin.get_threads():
                    import threading
                    threading.Thread(target=t, args=a, kwargs=kw, daemon=True).start()
            except Exception as e:
                _log.error(f"Failed to enable plugin '{name}': {e}")
                return False
        return True

    def disable(self, name: str) -> bool:
        """Disable a plugin at runtime (requires restart for full effect)."""
        if name not in self._loaded:
            return False
        try:
            self._loaded[name].on_unload()
        except Exception as e:
            _log.error(f"Failed to disable plugin '{name}': {e}")
        self._config[name] = False
        self._save_config()
        del self._loaded[name]
        return True

    def remove_plugin(self, name: str) -> bool:
        """Remove an external plugin from disk."""
        plugin = self._plugins.get(name) or self._loaded.get(name)
        if not plugin:
            return False
        if plugin.manifest.get("type") != "external":
            raise ValueError(f"Cannot remove internal plugin '{name}'")

        root = os.path.join(get_project_root(), "plugins")
        src = os.path.join(root, "external", name)
        dst = os.path.join(root, "disabled", name)
        if os.path.exists(src):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.move(src, dst)
        self._config.pop(name, None)
        self._save_config()
        self._plugins.pop(name, None)
        self._loaded.pop(name, None)
        return True

    def get_all_plugins(self) -> dict[str, dict]:
        """Return {name: manifest} for all discovered plugins."""
        return {name: p.manifest.copy() for name, p in self._plugins.items()}

    def get_config_widgets(self, section: str) -> list:
        """Collect config widgets from all active plugins for a given section."""
        widgets = []
        for plugin in self._loaded.values():
            try:
                w = plugin.get_config_widgets(section)
                if w:
                    widgets.extend(w)
            except Exception as e:
                _log.error(f"Error getting config widgets from '{plugin.manifest.get('name', '?')}': {e}")
        return widgets

    def get_hooks(self, name: str) -> list:
        """Return all callables registered by active plugins for the named hook."""
        hooks = []
        for plugin in self._loaded.values():
            try:
                hooks.extend(plugin.get_hook(name))
            except Exception as e:
                _log.error(f"Error getting hook '{name}' from '{plugin.manifest.get('name', '?')}': {e}")
        return hooks

    # ── Internal ───────────────────────────────────────────────

    def _load_config(self):
        try:
            with open(self._config_path, encoding="utf-8") as f:
                self._config = json.load(f)
        except Exception:
            self._config = {}

    def _save_config(self):
        os.makedirs(os.path.dirname(self._config_path), exist_ok=True)
        with open(self._config_path, "w", encoding="utf-8") as f:
            json.dump(self._config, f, ensure_ascii=False, indent=2)

    def _discover(self):
        root = os.path.join(get_project_root(), "plugins")
        for category in ("internal", "external"):
            cat_dir = os.path.join(root, category)
            if not os.path.isdir(cat_dir):
                continue
            for name in os.listdir(cat_dir):
                plugin_dir = os.path.join(cat_dir, name)
                manifest_path = os.path.join(plugin_dir, "plugin.json")
                if not os.path.isfile(manifest_path):
                    continue
                try:
                    with open(manifest_path, encoding="utf-8") as f:
                        manifest = json.load(f)
                    manifest["_path"] = plugin_dir
                    manifest.setdefault("name", name)
                    manifest.setdefault("type", category.rstrip("s"))  # "internal" or "external"
                    self._plugins[name] = self._instantiate(name, manifest)
                    print(f"[PluginManager] Discovered: {name} ({manifest.get('type')})")
                except Exception as e:
                    print(f"[PluginManager] Error loading plugin '{name}': {e}")

    def _instantiate(self, name, manifest) -> Plugin:
        entry = manifest.get("entry_point", "plugin.py")
        cls_name = manifest.get("plugin_class", "")
        plugin_dir = manifest["_path"]
        sys.path.insert(0, os.path.dirname(plugin_dir))
        try:
            mod_name = os.path.splitext(entry)[0]
            imported = __import__(f"{name}.{mod_name}", fromlist=[cls_name])
            cls = getattr(imported, cls_name) if cls_name else None
            if cls is None:
                raise ImportError(f"plugin_class '{cls_name}' not found in {entry}")
            plugin = cls()
            plugin.manifest = manifest
            return plugin
        finally:
            if os.path.dirname(plugin_dir) in sys.path:
                sys.path.remove(os.path.dirname(plugin_dir))

    def _validate(self):
        """Check dependencies: if a dependency is missing or disabled, warn."""
        active = {name for name, enabled in self._config.items() if enabled}
        new_active = set(active)
        for name in list(self._plugins):
            if name not in active:
                continue
            plugin = self._plugins[name]
            deps = plugin.manifest.get("depends_on", [])
            missing = [d for d in deps if d not in active and d not in self._loaded]
            if missing:
                print(f"[PluginManager] Plugin '{name}' disabled: missing dependencies {missing}")
                new_active.discard(name)
                self._loaded.pop(name, None)
        for name in new_active - active:
            self._config[name] = True
        self._save_config()

    def _activate(self) -> list[Plugin]:
        activated = []
        for name, enabled in list(self._config.items()):
            if not enabled or name not in self._plugins:
                continue
            plugin = self._plugins[name]
            try:
                plugin.on_load(self._app)
                self._loaded[name] = plugin
                activated.append(plugin)
                print(f"[PluginManager] Activated: {name}")
            except Exception as e:
                print(f"[PluginManager] Failed to activate '{name}': {e}")
                import traceback
                traceback.print_exc()
        return activated
