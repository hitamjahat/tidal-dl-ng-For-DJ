"""History management mixin for MainWindow.

Handles download history and duplicate prevention.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6 import QtCore
from tidalapi.media import Track

from tidal_dl_ng.dialog import DialogPreferences
from tidal_dl_ng.dialog_history import DialogHistory
from tidal_dl_ng.logger import logger_gui
from tidal_dl_ng.model.gui_data import StatusbarMessage

if TYPE_CHECKING:
    from tidal_dl_ng.config import Settings


class HistoryMixin:
    """Mixin containing download history management methods."""

    DOWNLOADED_COLUMN: int = 8

    # Attributes provided by MainWindow runtime composition.
    history_service: Any
    proxy_tr_results: Any
    model_tr_results: Any
    settings: Settings
    s_settings_save: Any
    s_statusbar_message: Any
    apply_settings: Any
    _init_dl: Any

    @staticmethod
    def _track_source_info(track: Track) -> tuple[str, str | None, str | None]:
        """Resolve source metadata for a track history entry."""
        source_type = "track"
        source_id: str | None = None
        source_name: str | None = None

        album = getattr(track, "album", None)
        album_id = getattr(album, "id", None) if album else None
        album_name = getattr(album, "name", None) if album else None

        if album_id is not None:
            source_type = "album"
            source_id = str(album_id)
            source_name = str(album_name) if album_name else None
        else:
            track_id = getattr(track, "id", None)
            track_name = getattr(track, "name", None)
            if track_id is not None:
                source_id = str(track_id)
            if track_name:
                source_name = str(track_name)

        return source_type, source_id, source_name

    def on_view_history(self) -> None:
        """Open the download history dialog."""
        DialogHistory(history_service=self.history_service, parent=self)

    def on_toggle_duplicate_prevention(self, enabled: bool) -> None:
        """Toggle duplicate download prevention on or off."""
        self.history_service.update_settings(preventDuplicates=enabled)
        status_msg = "enabled" if enabled else "disabled"
        logger_gui.info(f"Duplicate download prevention {status_msg}")
        self.s_statusbar_message.emit(
            StatusbarMessage(
                message=f"Duplicate prevention {status_msg}.",
                timeout=2500,
            )
        )

    def on_mark_track_as_downloaded(
        self, track: Track, index: QtCore.QModelIndex
    ) -> None:
        """Mark a track as downloaded in history."""
        track_id_raw = getattr(track, "id", None)
        if track_id_raw is None:
            logger_gui.warning(
                "Cannot mark track as downloaded: track.id is missing."
            )
            return

        track_id = str(track_id_raw)
        source_type, source_id, source_name = self._track_source_info(track)

        try:
            self.history_service.add_track_to_history(
                track_id=track_id,
                source_type=source_type,
                source_id=source_id,
                source_name=source_name,
            )
        except Exception:
            logger_gui.exception(
                f"Failed to add track to history (track_id={track_id})."
            )
            self.s_statusbar_message.emit(
                StatusbarMessage(
                    message="Failed to mark track as downloaded.",
                    timeout=3000,
                )
            )
            return

        self._update_downloaded_column(index, True)
        logger_gui.info(
            f"Marked track as downloaded: {getattr(track, 'name', track_id)}"
        )

    def on_mark_track_as_not_downloaded(
        self, track_id: str, index: QtCore.QModelIndex
    ) -> None:
        """Remove a track from download history."""
        if not track_id:
            logger_gui.warning("Cannot unmark track: empty track_id.")
            return

        success = self.history_service.remove_track_from_history(track_id)

        if success:
            self._update_downloaded_column(index, False)
            logger_gui.info(f"Unmarked track (ID: {track_id})")

    def _update_downloaded_column(
        self, index: QtCore.QModelIndex, is_downloaded: bool
    ) -> None:
        """Update the Downloaded? column for a specific index."""
        if not index.isValid():
            logger_gui.debug(
                "Skipping downloaded marker update for invalid index."
            )
            return

        source_index = self.proxy_tr_results.mapToSource(index)

        item = self.model_tr_results.itemFromIndex(source_index)
        if not item:
            return

        row = item.row()
        parent = item.parent()

        downloaded_item = (
            self.model_tr_results.item(row, self.DOWNLOADED_COLUMN)
            if parent is None
            else parent.child(row, self.DOWNLOADED_COLUMN)
        )

        if downloaded_item:
            if is_downloaded:
                downloaded_item.setText("✅")
                downloaded_item.setTextAlignment(
                    QtCore.Qt.AlignmentFlag.AlignCenter
                )
            else:
                downloaded_item.setText("")

    def on_preferences(self) -> None:
        """Open the preferences dialog."""
        DialogPreferences(
            settings=self.settings,
            settings_save=self.s_settings_save,
            parent=self,
        )

    def on_settings_save(self) -> None:
        """Save settings and re-apply them to the GUI."""
        self.settings.save()
        self.apply_settings(self.settings)
        self._init_dl()
