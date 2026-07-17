"""Playlist Manager Dialog - UI for managing track membership in playlists.

This module provides a modal dialog for users to quickly add/remove tracks
from their playlists without leaving the application.

Design:
- Displays all user playlists as checkboxes
- Pre-populated with current membership state from cache
- Handles add/remove transactions with rollback on error
- Provides visual feedback (loading spinner, success/error notifications)
"""

from __future__ import annotations

from typing import cast

from PySide6 import QtCore, QtGui, QtWidgets
from requests.exceptions import RequestException
from tidalapi.media import Track
from tidalapi.session import Session

from tidal_dl_ng.gui.playlist_membership import ThreadSafePlaylistCache
from tidal_dl_ng.helper.playlist_api import (
    add_track_to_playlist,
    remove_track_from_playlist,
)
from tidal_dl_ng.logger import logger_gui
from tidal_dl_ng.worker import Worker


class PlaylistManagerDialog(QtWidgets.QDialog):
    """Modal dialog for managing track membership in playlists.

    Displays current user playlists with checkboxes indicating whether
    the track is currently in each playlist. Users can check/uncheck
    to add/remove tracks with immediate visual feedback.

    Features:
    - Thread-safe API calls (no main thread blocking)
    - Optimistic UI updates with rollback on error
    - Toast notifications for user feedback
    - Alphabetical playlist sorting

    Example:
        dialog = PlaylistManagerDialog(
            track=track,
            cache=cache,
            session=tidal.session,
            threadpool=main_window.threadpool,
            parent=main_window
        )
        dialog.playlist_changed.connect(on_playlist_changed)
        dialog.exec()
    """

    # Signals
    playlist_added: QtCore.Signal = QtCore.Signal(
        str, str
    )  # track_id, playlist_id
    playlist_removed: QtCore.Signal = QtCore.Signal(str, str)
    transaction_finished: QtCore.Signal = QtCore.Signal(
        str, str, bool, bool, str
    )
    # playlist_id, track_id, is_checked, success, message

    def __init__(
        self,
        track: Track,
        cache: ThreadSafePlaylistCache,
        session: Session,
        threadpool: QtCore.QThreadPool,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        """Initialize the playlist manager dialog.

        Args:
            track: The track to manage playlists for
            cache: Thread-safe playlist cache with pre-loaded data
            session: Authenticated Tidal session for API calls
            threadpool: QThreadPool for background tasks
            parent: Parent widget
        """
        super().__init__(parent)
        self.track: Track = track
        self.cache: ThreadSafePlaylistCache = cache
        self.session: Session = session
        self.threadpool: QtCore.QThreadPool = threadpool

        # Store current states for rollback
        self._original_states: dict[str, bool] = {}
        self._pending_tasks: dict[str, Worker] = {}

        # Import the generated UI here to avoid circular dependency and ensure availability
        from tidal_dl_ng.ui.dialog_playlist_manager import (
            Ui_DialogPlaylistManager,
        )

        # Use compiled .ui
        self.ui = Ui_DialogPlaylistManager()
        self.ui.setupUi(self)  # type: ignore[no-untyped-call]

        self.transaction_finished.connect(self._on_transaction_finished)

        # Set dynamic title with track name
        track_title: str = getattr(self.track, "name", "Unknown Track")
        self.ui.labelTitle.setText(
            f'Gérer les playlists pour : <b><span style="color:#1e88e5;">{track_title}</span></b>'
        )

        # Populate playlists list into verticalLayoutList
        self._populate_playlists_ui()

        # Expose container layout for tests
        self.container_layout = self.ui.verticalLayoutList

    def _populate_playlists_ui(self) -> None:
        """Populate dialog with user playlists from cache.

        Fetches all playlists from cache, sorts alphabetically,
        and creates checkbox items with current membership state.
        """
        # Get all playlist IDs from cache
        all_playlist_ids: set[str] = self.cache.get_all_playlists()

        # Hide empty label if we have playlists
        self.ui.labelEmpty.setVisible(len(all_playlist_ids) == 0)
        if not all_playlist_ids:
            return

        # Sort playlists alphabetically by name/ID
        sorted_playlist_ids: list[str] = sorted(
            all_playlist_ids,
            key=lambda pid: str(
                self.cache.get_playlist_metadata(pid).get("name", pid)
            ).lower(),
        )

        # Create checkbox for each playlist
        track_id: str = str(self.track.id)

        for playlist_id in sorted_playlist_ids:
            # Get playlist info
            metadata = self.cache.get_playlist_metadata(playlist_id)
            playlist_name: str = str(
                metadata.get("name", f"Playlist {playlist_id}")
            )
            item_count: int = int(metadata.get("item_count", 0))

            # Check if track is in this playlist
            is_in_playlist: bool = self.cache.is_track_in_playlist(
                track_id, playlist_id
            )
            self._original_states[playlist_id] = is_in_playlist

            # Row widget
            row_widget = QtWidgets.QWidget()
            row_layout = QtWidgets.QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(8)

            # Checkbox
            checkbox: QtWidgets.QCheckBox = QtWidgets.QCheckBox()
            checkbox.setChecked(is_in_playlist)
            checkbox.setProperty("playlist_id", playlist_id)

            def _on_state_changed(
                _state: int,
                cbox: QtWidgets.QCheckBox = checkbox,
                pid: str = playlist_id,
            ) -> None:
                self._on_playlist_checkbox_toggled(cbox, pid)

            checkbox.stateChanged.connect(_on_state_changed)
            row_layout.addWidget(checkbox)

            # Playlist name
            name_label: QtWidgets.QLabel = QtWidgets.QLabel(playlist_name)
            row_layout.addWidget(name_label)

            # Item count
            count_label: QtWidgets.QLabel = QtWidgets.QLabel(f"({item_count})")
            count_label.setStyleSheet("color: gray; font-size: 0.85em;")
            row_layout.addWidget(count_label)

            # Stretch
            row_layout.addStretch()

            self.ui.verticalLayoutList.insertWidget(
                self.ui.verticalLayoutList.count() - 1, row_widget
            )  # before spacer

    def _on_playlist_checkbox_toggled(
        self,
        checkbox: QtWidgets.QCheckBox,
        playlist_id: str,
    ) -> None:
        """Bridge Qt signal to typed state-change handler."""
        state = (
            QtCore.Qt.CheckState.Checked.value
            if checkbox.isChecked()
            else QtCore.Qt.CheckState.Unchecked.value
        )
        self._on_playlist_checkbox_changed(checkbox, playlist_id, state)

    def _on_playlist_checkbox_changed(
        self, checkbox: QtWidgets.QCheckBox, playlist_id: str, state: int
    ) -> None:
        """Handle checkbox state change for a playlist.

        Implements transactional logic:
        1. Disable checkbox and show spinner
        2. Make API call (POST/DELETE)
        3. On success: update cache, re-enable
        4. On error: rollback state, show toast

        Args:
            checkbox: The checkbox widget
            playlist_id: ID of the playlist
            state: Qt CheckState (2=checked, 0=unchecked)
        """
        is_checked: bool = state == QtCore.Qt.CheckState.Checked.value

        # Save previous state for rollback
        previous_state: bool = not is_checked

        # Disable UI during transaction
        checkbox.setEnabled(False)

        # Start transaction
        track_id: str = str(self.track.id)

        if is_checked:
            # Add track to playlist
            worker_ctor = cast(object, Worker)
            worker: Worker = worker_ctor(  # type: ignore[operator]
                self._api_add_track_to_playlist,
                track_id,
                playlist_id,
                previous_state,
            )
        else:
            # Remove track from playlist
            worker_ctor = cast(object, Worker)
            worker = worker_ctor(  # type: ignore[operator]
                self._api_remove_track_from_playlist,
                track_id,
                playlist_id,
                previous_state,
            )

        # Store worker reference for potential cancellation
        self._pending_tasks[f"{playlist_id}"] = worker
        self.threadpool.start(cast(QtCore.QRunnable, worker))

    def _api_add_track_to_playlist(
        self,
        track_id: str,
        playlist_id: str,
        previous_state: bool,
    ) -> None:
        """API call to add track to playlist (runs in worker thread).

        Args:
            track_id: Track UUID
            playlist_id: Playlist UUID
            checkbox: Checkbox widget to update on completion
            previous_state: Previous checkbox state for rollback
        """
        try:
            # Use centralized API helper
            add_track_to_playlist(self.session, playlist_id, track_id)

            # Success: update cache and UI
            self.cache.add_track_to_playlist(track_id, playlist_id)
            self.transaction_finished.emit(
                playlist_id, track_id, True, True, ""
            )

        except RequestException:
            self.transaction_finished.emit(
                playlist_id,
                track_id,
                True,
                False,
                "Impossible d'ajouter à la playlist",
            )

        except Exception:
            self.transaction_finished.emit(
                playlist_id,
                track_id,
                True,
                False,
                "Erreur lors de la modification",
            )

    def _api_remove_track_from_playlist(
        self,
        track_id: str,
        playlist_id: str,
        previous_state: bool,
    ) -> None:
        """API call to remove track from playlist (runs in worker thread).

        Args:
            track_id: Track UUID
            playlist_id: Playlist UUID
            checkbox: Checkbox widget to update on completion
            previous_state: Previous checkbox state for rollback
        """
        try:
            # Use centralized API helper
            remove_track_from_playlist(self.session, playlist_id, track_id)

            # Success: update cache and UI
            self.cache.remove_track_from_playlist(track_id, playlist_id)
            self.transaction_finished.emit(
                playlist_id, track_id, False, True, ""
            )

        except RequestException:
            self.transaction_finished.emit(
                playlist_id,
                track_id,
                False,
                False,
                "Impossible de retirer de la playlist",
            )

        except Exception:
            self.transaction_finished.emit(
                playlist_id,
                track_id,
                False,
                False,
                "Erreur lors de la modification",
            )

    def _find_playlist_checkbox(
        self, playlist_id: str
    ) -> QtWidgets.QCheckBox | None:
        """Find the checkbox associated with a playlist id."""
        for checkbox in self.findChildren(QtWidgets.QCheckBox):
            if str(checkbox.property("playlist_id")) == playlist_id:
                return checkbox
        return None

    def _on_transaction_finished(
        self,
        playlist_id: str,
        track_id: str,
        is_checked: bool,
        success: bool,
        message: str,
    ) -> None:
        """Handle API transaction completion on the GUI thread."""
        checkbox = self._find_playlist_checkbox(playlist_id)
        previous_state = self._original_states.get(playlist_id, False)

        if checkbox is not None:
            checkbox.blockSignals(True)
            checkbox.setChecked(is_checked if success else previous_state)
            checkbox.blockSignals(False)
            checkbox.setEnabled(True)

        if success:
            self._original_states[playlist_id] = is_checked
            if is_checked:
                self.playlist_added.emit(track_id, playlist_id)
            else:
                self.playlist_removed.emit(track_id, playlist_id)
        else:
            self._show_error_notification(message)

        self._pending_tasks.pop(playlist_id, None)

    def _show_error_notification(self, message: str) -> None:
        """Show a non-intrusive error notification.

        Args:
            message: Error message to display

        TODO: Integrate with app's notification system (Toast/Snackbar)
        """
        logger_gui.debug(f"PlaylistManagerDialog notification: {message}")

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        """Handle dialog close event.

        Cancels any pending operations.

        Args:
            event: Close event
        """
        # Cancel pending tasks (Worker doesn't have built-in abort, but we can clean up references)
        self._pending_tasks.clear()
        super().closeEvent(event)
