"""Updates mixin for MainWindow.

Handles application update checking and version dialog display.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from PySide6 import QtCore

from tidal_dl_ng import update_available as check_update_available
from tidal_dl_ng.dialog import DialogVersion

if TYPE_CHECKING:
    from PySide6 import QtWidgets

    from tidal_dl_ng.gui.main_window import MainWindow
    from tidal_dl_ng.model.meta import ReleaseLatest


class UpdatesMixin(QtCore.QObject):
    """Mixin containing update checking and version dialog methods.

    This mixin is combined into :class:`MainWindow` via multiple
    inheritance. It relies on the ``s_update_show`` signal defined on the
    owning window to decouple the update check from the dialog display.
    """

    if TYPE_CHECKING:
        # Declared for type checkers; provided by the owning MainWindow.
        s_update_show: QtCore.Signal
        _main_window: MainWindow

    def on_update_check(self, on_startup: bool = True) -> None:
        """Check for application updates and request the dialog.

        Args:
            on_startup: When ``True`` the dialog is only shown if a newer
                release is actually available. When ``False`` (manual check)
                the dialog is always shown, even when up to date.
        """
        is_available, info = check_update_available()

        should_show = is_available if on_startup else True
        if should_show:
            was_triggered_by_check = True
            self.s_update_show.emit(was_triggered_by_check, is_available, info)

    def on_version(
        self,
        update_check: bool = False,
        is_available: bool = False,
        update_info: ReleaseLatest | None = None,
    ) -> None:
        """Show the version information dialog.

        Args:
            update_check: Whether the dialog was opened from an update check.
            is_available: Whether a newer release is available.
            update_info: Metadata of the latest release, if known.
        """
        parent = cast("QtWidgets.QWidget", self)
        DialogVersion(
            parent,
            update_check=update_check,
            update_available=is_available,
            update_info=update_info,
        )
