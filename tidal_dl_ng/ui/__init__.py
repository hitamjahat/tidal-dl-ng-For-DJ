"""UI package initializer.

- Ensures that `tidal_dl_ng.ui.dialog_playlist_manager` exposes both the generated
  `Ui_DialogPlaylistManager` and the implementation `PlaylistManagerDialog`.
- Does not modify generated UI .py files; composes at import time.
"""

from __future__ import annotations

import importlib
from types import ModuleType

# Import generated UI module
_ui_mod: ModuleType = importlib.import_module("tidal_dl_ng.ui.dialog_playlist_manager")

# Attach the implementation class from gui
try:
    from tidal_dl_ng.gui.dialog_playlist_manager import PlaylistManagerDialog as _ImplDialog
except Exception:
    _ImplDialog = None

if _ImplDialog is not None:
    _ui_mod.PlaylistManagerDialog = _ImplDialog

# Re-export for convenience when importing from the package
if _ImplDialog is not None:
    PlaylistManagerDialog = _ImplDialog

try:
    from tidal_dl_ng.ui.dialog_playlist_manager import Ui_DialogPlaylistManager as _UiClass
except Exception:
    _UiClass = None

if _UiClass is not None:
    Ui_DialogPlaylistManager = _UiClass

__all__ = [name for name in ("PlaylistManagerDialog", "Ui_DialogPlaylistManager") if name in globals()]
