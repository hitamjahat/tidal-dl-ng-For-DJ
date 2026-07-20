"""GUI module for TIDAL Downloader Next Generation.

This package provides the main window and all GUI-related functionality
organized into manageable components.
"""

from tidal_dl_ng.gui.activate import gui_activate
from tidal_dl_ng.gui.main_window import MainWindow

__all__ = [
    "MainWindow",
    "gui_activate",
]
