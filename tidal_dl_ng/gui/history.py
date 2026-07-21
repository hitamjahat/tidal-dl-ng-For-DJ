"""Coordinate download-history actions for the main application window.

The mixin connects history services to dialogs, status messages, and the
results model. Persistent history work remains in :mod:`tidal_dl_ng.history`,
while dialog construction remains in the dedicated dialog modules.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from PySide6 import QtCore, QtGui, QtWidgets

from tidal_dl_ng.dialog import DialogPreferences
from tidal_dl_ng.dialog_history import DialogHistory
from tidal_dl_ng.logger import logger_gui
from tidal_dl_ng.model.gui_data import StatusbarMessage

if TYPE_CHECKING:
    from typing import Protocol

    from tidalapi.media import Track

    from tidal_dl_ng.config import Settings
    from tidal_dl_ng.helper.gui import HumanProxyModel
    from tidal_dl_ng.history import HistoryService

    class _HistorySignalOwner(Protocol):
        """Describe Qt signals supplied by the concrete main window."""

        @property
        def s_settings_save(self) -> QtCore.SignalInstance:
            """Return the application-settings save signal.

            Raises:
                NotImplementedError: Protocol properties have no runtime
                    implementation.
            """
            raise NotImplementedError

        @property
        def s_statusbar_message(self) -> QtCore.SignalInstance:
            """Return the main-window status-message signal.

            Raises:
                NotImplementedError: Protocol properties have no runtime
                    implementation.
            """
            raise NotImplementedError


DOWNLOADED_MARKER: str = "\N{WHITE HEAVY CHECK MARK}"
STATUS_TIMEOUT_SHORT_MS: int = 2_500
STATUS_TIMEOUT_ERROR_MS: int = 3_000

HISTORY_WRITE_ERRORS: tuple[type[Exception], ...] = (
    OSError,
    TypeError,
    ValueError,
)


class HistoryMixin:
    """Coordinate history operations supplied by the main window.

    The concrete main window supplies the service, item models, settings,
    Qt signals, and settings-application callbacks declared below.
    """

    DOWNLOADED_COLUMN: int = 8

    history_service: HistoryService
    proxy_tr_results: HumanProxyModel
    model_tr_results: QtGui.QStandardItemModel
    settings: Settings

    @staticmethod
    def _track_source_info(
        track: Track,
    ) -> tuple[str, str | None, str | None]:
        """Resolve the most useful source metadata for a track.

        Album metadata identifies normal search results. If album metadata
        is unavailable, the track itself becomes the source so manually
        marked items still have a useful identity and label.

        Args:
            track (Track): TIDAL track being added to history.

        Returns:
            tuple[str, str | None, str | None]: Source type, source ID, and
                human-readable source name.
        """
        album = track.album
        if album is not None and album.id is not None:
            album_name = album.name or None
            return "album", str(album.id), album_name

        track_id = None if track.id is None else str(track.id)
        track_name = track.name or None
        return "track", track_id, track_name

    def on_view_history(self) -> None:
        """Open the modal download-history dialog.

        Returns:
            None: The dialog owns the interaction until it closes.
        """
        DialogHistory(
            history_service=self.history_service,
            parent=self._dialog_parent(),
        )

    def on_toggle_duplicate_prevention(self, enabled: bool) -> None:
        """Persist the duplicate-download prevention preference.

        Args:
            enabled (bool): Whether previously downloaded tracks should be
                skipped.

        Returns:
            None: Success or failure is reported through the status bar.
        """
        try:
            self.history_service.update_settings(
                prevent_duplicates=enabled,
            )
        except HISTORY_WRITE_ERRORS:
            logger_gui.exception(
                "Failed to update duplicate prevention (enabled=%s).",
                enabled,
            )
            self._show_status(
                "Failed to update duplicate prevention.",
                STATUS_TIMEOUT_ERROR_MS,
            )
            return

        state = "enabled" if enabled else "disabled"
        logger_gui.info("Duplicate download prevention %s", state)
        self._show_status(
            f"Duplicate prevention {state}.",
            STATUS_TIMEOUT_SHORT_MS,
        )

    def on_mark_track_as_downloaded(
        self,
        track: Track,
        index: QtCore.QModelIndex,
    ) -> None:
        """Add a track to history and update its results-model marker.

        Args:
            track (Track): TIDAL track to record.
            index (QModelIndex): Proxy-model index for the track row.

        Returns:
            None: The model is updated only after persistence succeeds.
        """
        if track.id is None:
            logger_gui.warning(
                "Cannot mark track as downloaded: track.id is missing.",
            )
            self._show_status(
                "Cannot mark a track without an ID.",
                STATUS_TIMEOUT_ERROR_MS,
            )
            return

        track_id = str(track.id)
        source_type, source_id, source_name = self._track_source_info(track)

        try:
            self.history_service.add_track_to_history(
                track_id=track_id,
                source_type=source_type,
                source_id=source_id,
                source_name=source_name,
            )
        except HISTORY_WRITE_ERRORS:
            logger_gui.exception(
                "Failed to add track to history (track_id=%s).",
                track_id,
            )
            self._show_status(
                "Failed to mark track as downloaded.",
                STATUS_TIMEOUT_ERROR_MS,
            )
            return

        self._update_downloaded_column(index, is_downloaded=True)
        logger_gui.info(
            "Marked track as downloaded: %s",
            track.name or track_id,
        )

    def on_mark_track_as_not_downloaded(
        self,
        track_id: str,
        index: QtCore.QModelIndex,
    ) -> None:
        """Remove a track from history and clear its model marker.

        Args:
            track_id (str): TIDAL track ID to remove.
            index (QModelIndex): Proxy-model index for the track row.

        Returns:
            None: The marker is cleared only when an entry was removed.
        """
        if not track_id:
            logger_gui.warning("Cannot unmark track: empty track_id.")
            self._show_status(
                "Cannot unmark a track without an ID.",
                STATUS_TIMEOUT_ERROR_MS,
            )
            return

        try:
            removed = self.history_service.remove_track_from_history(
                track_id,
            )
        except HISTORY_WRITE_ERRORS:
            logger_gui.exception(
                "Failed to remove track from history (track_id=%s).",
                track_id,
            )
            self._show_status(
                "Failed to mark track as not downloaded.",
                STATUS_TIMEOUT_ERROR_MS,
            )
            return

        if not removed:
            logger_gui.debug(
                "Track was not present in history (track_id=%s).",
                track_id,
            )
            return

        self._update_downloaded_column(index, is_downloaded=False)
        logger_gui.info("Unmarked track (track_id=%s)", track_id)

    def _update_downloaded_column(
        self,
        index: QtCore.QModelIndex,
        *,
        is_downloaded: bool,
    ) -> None:
        """Update the downloaded marker for a results-model row.

        Args:
            index (QModelIndex): Proxy-model index identifying the row.
            is_downloaded (bool): Whether to show the downloaded marker.

        Returns:
            None: Invalid or missing model items are safely ignored.
        """
        if not index.isValid():
            logger_gui.debug(
                "Skipping downloaded marker update for invalid index.",
            )
            return

        source_index = self.proxy_tr_results.mapToSource(index)
        if not source_index.isValid():
            logger_gui.debug(
                "Skipping downloaded marker update: no source index.",
            )
            return

        downloaded_index = source_index.siblingAtColumn(
            self.DOWNLOADED_COLUMN,
        )
        if not downloaded_index.isValid():
            logger_gui.debug(
                "Skipping downloaded marker update: column item is missing.",
            )
            return

        downloaded_item = self.model_tr_results.itemFromIndex(
            downloaded_index,
        )
        downloaded_item.setText(
            DOWNLOADED_MARKER if is_downloaded else "",
        )
        downloaded_item.setTextAlignment(
            QtCore.Qt.AlignmentFlag.AlignCenter,
        )

    def on_preferences(self) -> None:
        """Open the modal application-preferences dialog.

        Returns:
            None: The dialog emits the supplied save signal when accepted.
        """
        DialogPreferences(
            settings=self.settings,
            settings_save=self._signal_owner().s_settings_save,
            parent=self._dialog_parent(),
        )

    def on_settings_save(self) -> None:
        """Persist settings, reapply them, and rebuild download services.

        Returns:
            None: Persistence failures are logged and shown in the status bar.
        """
        try:
            self.settings.save()
        except HISTORY_WRITE_ERRORS:
            logger_gui.exception("Failed to save application settings.")
            self._show_status(
                "Failed to save application settings.",
                STATUS_TIMEOUT_ERROR_MS,
            )
            return

        self.apply_settings(self.settings)
        self._init_dl()

    def apply_settings(self, settings: Settings) -> None:
        """Apply settings through the concrete main-window implementation.

        Args:
            settings (Settings): Persisted application settings.

        Raises:
            NotImplementedError: If no concrete window implementation exists.
        """
        message = "The concrete window must implement apply_settings()."
        raise NotImplementedError(message)

    def _init_dl(self) -> None:
        """Rebuild download services in the concrete main window.

        Raises:
            NotImplementedError: If no concrete window implementation exists.
        """
        message = "The concrete window must implement _init_dl()."
        raise NotImplementedError(message)

    def _show_status(self, message: str, timeout: int) -> None:
        """Emit a transient main-window status message.

        Args:
            message (str): User-facing status text.
            timeout (int): Display duration in milliseconds.

        Returns:
            None: The main-window signal handles presentation.
        """
        self._signal_owner().s_statusbar_message.emit(
            StatusbarMessage(message=message, timeout=timeout),
        )

    def _signal_owner(self) -> _HistorySignalOwner:
        """Return a structural view of main-window history signals.

        Returns:
            _HistorySignalOwner: Typed access to Qt signal instances supplied
                by the concrete QObject-based main window.
        """
        return cast("_HistorySignalOwner", self)

    def _dialog_parent(self) -> QtWidgets.QWidget | None:
        """Return this mixin's concrete Qt widget for dialog ownership.

        Returns:
            QWidget | None: The concrete main window, or ``None`` when the
                mixin is used by a non-widget test double.
        """
        if isinstance(self, QtWidgets.QWidget):
            return self

        logger_gui.warning(
            "HistoryMixin is not attached to a QWidget; dialog is unowned.",
        )
        return None
