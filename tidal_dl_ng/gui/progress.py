"""Progress bars mixin for MainWindow.

Handles progress bar updates and formatting.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PySide6 import QtWidgets

if TYPE_CHECKING:
    pass


class ProgressMixin:
    """Mixin containing progress bar management methods."""

    def __init__(self) -> None:
        """Initialize the progress mixin."""
        # Type hints for progress bar attributes (defined in MainWindow)
        self.pb_list: QtWidgets.QProgressBar
        self.pb_item: QtWidgets.QProgressBar

    def on_progress_reset(self) -> None:
        """Reset progress bars to zero."""
        self.pb_list.setValue(0)
        self.pb_item.setValue(0)

    def on_progress_list(self, value: float) -> None:
        """Update the progress of the list progress bar.

        Args:
            value: Progress value (0-100).
        """
        self.pb_list.setValue(math.ceil(value))

    def on_progress_item(self, value: float) -> None:
        """Update the progress of the item progress bar.

        Args:
            value: Progress value (0-100).
        """
        self.pb_item.setValue(math.ceil(value))

    def on_progress_item_name(self, value: str) -> None:
        """Set the format of the item progress bar.

        Args:
            value: Text to display alongside percentage.
        """
        self.pb_item.setFormat(f"%p% {value}")

    def on_progress_list_name(self, value: str) -> None:
        """Set the format of the list progress bar.

        Args:
            value: Text to display alongside percentage.
        """
        self.pb_list.setFormat(f"%p% {value}")
