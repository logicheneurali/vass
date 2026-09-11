"""VASS GUI — thin entry point.

All classes are defined in separate modules.
"""

from gui_splash import SplashScreen
from gui_widgets import WaveformPlayer, VolumeTopBar, MemoryBar, _ChatLineEdit, _CompactWidget
from gui_infopanel import InfoPanel
from gui_main import VassGUI
from gui_plugins import PluginManagerDialog, PluginSettingsDialog, PluginUiDialog

# Backward compat: also export as VASSGUI (uppercase)
VASSGUI = VassGUI

from gui_main import BASE, SRC, SVG_PATH, VERSION_PATH
from gui_main import _is_wayland, _get_window_pos, _try_system_move

from theme import BG, BTN_BG, BTN_FG, LABEL_FG, BTN_DEL_BG, BTN_DEL_FG, ENTRY_BG, DESCRIPTION_FG, FRAME_BORDER, FG, BASE_STYLESHEET
from icons import icon, icon_dual, pixmap
from smooth_scroll import SmoothScrollArea
from activity_tracker import get_tracker, CATEGORY_COLORS

__all__ = [
    'SplashScreen', 'WaveformPlayer', 'VolumeTopBar', 'MemoryBar',
    '_ChatLineEdit', '_CompactWidget', 'InfoPanel', 'VassGUI', 'VASSGUI',
    'PluginManagerDialog', 'PluginSettingsDialog', 'PluginUiDialog',
    'BASE', 'SRC', 'SVG_PATH', 'VERSION_PATH',
    '_is_wayland', '_get_window_pos', '_try_system_move',
    'BG', 'BTN_BG', 'BTN_FG', 'LABEL_FG', 'BTN_DEL_BG', 'BTN_DEL_FG',
    'ENTRY_BG', 'DESCRIPTION_FG', 'FRAME_BORDER', 'FG', 'BASE_STYLESHEET',
    'icon', 'icon_dual', 'pixmap',
    'SmoothScrollArea',
    'get_tracker', 'CATEGORY_COLORS',
]
