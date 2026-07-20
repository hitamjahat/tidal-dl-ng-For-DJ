"""Updates mixin for MainWindow.

Handles application update checking.
"""

from tidal_dl_ng import update_available as check_update_available
from tidal_dl_ng.dialog import DialogVersion
from tidal_dl_ng.model.meta import ReleaseLatest


class UpdatesMixin:
    """Mixin containing update checking methods."""

    def on_update_check(self, on_startup: bool = True) -> None:
        """Check for application updates and emit update signals."""
        is_available, info = check_update_available()

        if (on_startup and is_available) or not on_startup:
            self.s_update_show.emit(True, is_available, info)

    def on_version(
        self,
        update_check: bool = False,
        is_available: bool = False,
        update_info: ReleaseLatest | None = None,
    ) -> None:
        """Show the version information dialog."""
        DialogVersion(
            self,
            update_check=update_check,
            update_available=is_available,
            update_info=update_info,
        )
