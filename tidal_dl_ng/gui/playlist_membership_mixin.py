"""Playlist Membership Mixin for MainWindow.

Integrates the playlist membership management system into the main window,
handling initialization, signal connections, and UI updates.
"""

from __future__ import annotations

from typing import Any

from PySide6 import QtCore
from tidalapi.media import Track

from tidal_dl_ng.gui.dialog_playlist_manager import PlaylistManagerDialog
from tidal_dl_ng.gui.playlist_membership import (
    PlaylistCellState,
    PlaylistColumnDelegate,
    PlaylistContextLoader,
    ThreadSafePlaylistCache,
)
from tidal_dl_ng.logger import logger_gui
from tidal_dl_ng.model.gui_data import StatusbarMessage


class PlaylistMembershipMixin:
    """Mixin for playlist membership management integration into MainWindow."""

    PLAYLISTS_COLUMN: int = 9
    OBJ_COLUMN: int = 1

    # Attributes provided by MainWindow runtime composition.
    tr_results: Any
    proxy_tr_results: Any
    model_tr_results: Any
    tidal: Any
    threadpool: Any
    s_statusbar_message: Any

    # Type hints
    playlist_cache: ThreadSafePlaylistCache
    playlist_loader: PlaylistContextLoader | None
    playlist_column_delegate: PlaylistColumnDelegate

    # Signals for playlist events
    s_playlist_cache_ready: QtCore.Signal = QtCore.Signal(dict)
    s_playlist_loader_error: QtCore.Signal = QtCore.Signal(str)
    s_playlist_loader_progress: QtCore.Signal = QtCore.Signal(int, int)

    def init_playlist_membership_manager(self) -> None:
        """Initialize the playlist membership management system.

        Sets up:
        - Thread-safe cache for track→playlist mappings
        - Background worker for loading playlists
        - Custom delegate for the playlists column
        - Signal connections
        """
        # 1. Create thread-safe cache
        self.playlist_cache = ThreadSafePlaylistCache()

        # 2. Store worker reference (will be recreated on each results change)
        self.playlist_loader: PlaylistContextLoader | None = None

        # 3. Create custom delegate for playlists column
        self.playlist_column_delegate = PlaylistColumnDelegate(
            parent=self.tr_results
        )
        self.playlist_column_delegate.set_cache(self.playlist_cache)
        self.playlist_column_delegate.set_obj_column_index(self.OBJ_COLUMN)
        self.playlist_column_delegate.button_clicked.connect(
            self.on_playlist_column_button_clicked
        )

        # 5. Attach delegate to the results table (column 9 = playlists)
        # Note: Column indices: 0=index, 1=obj, 2=artist, 3=title, 4=album,
        #       5=duration, 6=quality, 7=date, 8=downloaded, 9=playlists

        # Diagnostic: check if column 9 exists
        if hasattr(self, "model_tr_results") and self.model_tr_results:
            col_count: int = int(self.model_tr_results.columnCount())
            if col_count <= self.PLAYLISTS_COLUMN:
                logger_gui.error(
                    f"Playlists column {self.PLAYLISTS_COLUMN} is missing. "
                    f"Model has {col_count} columns."
                )

        self.tr_results.setItemDelegateForColumn(
            self.PLAYLISTS_COLUMN,
            self.playlist_column_delegate,
        )

        # Configure column width and appearance
        self.tr_results.setColumnWidth(self.PLAYLISTS_COLUMN, 60)

        # Make sure column is visible
        if self.tr_results.isColumnHidden(self.PLAYLISTS_COLUMN):
            self.tr_results.setColumnHidden(self.PLAYLISTS_COLUMN, False)

        self.tr_results.setColumnHidden(self.OBJ_COLUMN, True)

        # 6. Connect model signals to trigger preloading
        if hasattr(self, "model_tr_results") and self.model_tr_results:
            self.model_tr_results.modelReset.connect(
                self.on_results_layout_changed
            )
            self.model_tr_results.layoutChanged.connect(
                self.on_results_layout_changed
            )

            # Initialize states for any existing rows
            existing_rows = self.model_tr_results.rowCount()
            if existing_rows > 0:
                for r in range(existing_rows):
                    self.playlist_column_delegate.set_cell_state(
                        r,
                        PlaylistCellState.READY,
                    )
        else:
            logger_gui.error(
                "model_tr_results is unavailable; playlist state signals not connected."
            )

        # 7. Launch initial playlist loading immediately
        self._load_playlists()

    def connect_playlist_signals(self) -> None:
        """Connect playlist-related signals (called from main signal setup)."""
        # Signal connections already done in init_playlist_membership_manager

    def _load_playlists(self) -> None:
        """Load user playlists in background.

        Creates a new worker and launches it in the threadpool.
        """
        # Purge ENTIRE cache (tracks + metadata) to ensure first-load starts clean
        # et éviter que des métadonnées obsolètes n'influencent l'affichage.
        if hasattr(self, "playlist_cache") and self.playlist_cache:
            self.playlist_cache.clear()

        # Indiquer explicitement au délégué que le cache n'est pas prêt
        # afin d'afficher le spinner au lieu des compteurs.
        if (
            hasattr(self, "playlist_column_delegate")
            and self.playlist_column_delegate
        ):
            self.playlist_column_delegate.set_cache_ready(False)

        tidal_session = getattr(self.tidal, "session", None)
        user = getattr(tidal_session, "user", None)
        user_id = getattr(user, "id", None)

        if tidal_session is None or user_id is None:
            logger_gui.warning(
                "Cannot load playlists: TIDAL session or user ID is unavailable."
            )
            self.s_statusbar_message.emit(
                StatusbarMessage(
                    message="Please login to TIDAL first.",
                    timeout=4000,
                )
            )
            return

        self.playlist_loader = PlaylistContextLoader(
            session=tidal_session,
            user_id=str(user_id),
            max_workers=5,
        )

        # Connect signals for this worker instance
        self.playlist_loader.signals.started.connect(
            self.on_playlist_loader_started
        )
        self.playlist_loader.signals.cache_ready.connect(
            self.on_playlist_cache_ready
        )
        self.playlist_loader.signals.metadata_ready.connect(
            self.on_playlist_metadata_ready
        )
        self.playlist_loader.signals.error.connect(
            self.on_playlist_loader_error
        )
        self.playlist_loader.signals.progress.connect(
            self.on_playlist_loader_progress
        )
        self.playlist_loader.signals.finished.connect(
            self.on_playlist_loader_finished
        )

        # Start loading playlists in background
        self.threadpool.start(self.playlist_loader)

    def on_results_layout_changed(self) -> None:
        """Handle when new results are displayed in the main table."""
        # Initialize READY states for all visible rows
        try:
            rows = self.model_tr_results.rowCount()
            for r in range(rows):
                self.playlist_column_delegate.set_cell_state(
                    r,
                    PlaylistCellState.READY,
                )
        except Exception as e:
            logger_gui.warning(f"Failed to initialize cell states: {e}")

        # Force repaint to show buttons only after the cache is ready.
        cache_ready = bool(
            getattr(self.playlist_column_delegate, "cache_ready", False)
            or getattr(self.playlist_column_delegate, "is_cache_ready", False)
            or getattr(self.playlist_column_delegate, "_cache_ready", False)
        )
        if cache_ready:
            try:
                self.tr_results.viewport().update()
                self.tr_results.viewport().repaint()
            except RuntimeError:
                pass

    def on_playlist_loader_started(self) -> None:
        """Called when playlist loader starts."""
        # Silent

    def on_playlist_cache_ready(self, cache: dict[str, set[str]]) -> None:
        """Called when playlist cache is ready.

        Args:
            cache: Dict[track_id, Set[playlist_id]] from worker
        """
        # Update cache WITHOUT clearing (metadata was already loaded)
        # NOTE: We don't call clear() because metadata_ready signal was already
        # emitted and stored. We only update track→playlist mapping.
        self.playlist_cache.update_from_dict(cache)

        # Initialize cell states for all current rows as READY
        try:
            rows = self.model_tr_results.rowCount()
            for r in range(rows):
                self.playlist_column_delegate.set_cell_state(
                    r,
                    PlaylistCellState.READY,
                )
        except Exception as e:
            logger_gui.warning(f"Failed to initialize cell states: {e}")

        # Notify delegate that cache is ready (stops animation timer)
        self.playlist_column_delegate.set_cache_ready(True)

        # Force complete repaint of the table to show buttons instead of spinners
        self.tr_results.viewport().update()
        self.tr_results.viewport().repaint()

    def on_playlist_metadata_ready(
        self,
        metadata: dict[str, dict[str, Any]],
    ) -> None:
        """Receive playlist metadata and store it in the cache.

        Args:
            metadata: Dict[playlist_id, {name: str, item_count: int}]
        """
        try:
            for pid, info in metadata.items():
                name = str(info.get("name", pid))
                count = int(info.get("item_count", 0))
                self.playlist_cache.set_playlist_metadata(pid, name, count)
            logger_gui.debug(f"Stored metadata for {len(metadata)} playlists")
        except Exception as e:
            logger_gui.warning(f"Failed to store playlist metadata: {e}")

    def on_playlist_loader_error(self, error_msg: str) -> None:
        """Handle playlist loader error.

        Args:
            error_msg: Error description
        """
        logger_gui.warning(f"Playlist loader error: {error_msg}")

        # Show user-friendly notification
        self.s_statusbar_message.emit(
            StatusbarMessage(
                message=f"Playlist loading error: {error_msg}",
                timeout=5000,
            )
        )

    def on_playlist_loader_progress(self, current: int, total: int) -> None:
        """Handle playlist loader progress.

        Args:
            current: Number of playlists processed
            total: Total number of playlists
        """
        # Silent - no need to spam logs

    def on_playlist_loader_finished(self) -> None:
        """Handle playlist loader finished (success or error)."""
        # Silent

    def on_playlist_column_button_clicked(
        self, index: QtCore.QModelIndex
    ) -> None:
        """Handle click on playlist column button.

        Opens the playlist manager dialog for the clicked track.

        Args:
            index: QModelIndex of the cell clicked
        """
        # Map proxy index to source index if using proxy model
        if isinstance(self.tr_results.model(), type(self.proxy_tr_results)):
            source_index = self.proxy_tr_results.mapToSource(index)
        else:
            source_index = index

        # Get the track object from the model
        obj_item = self.model_tr_results.item(
            source_index.row(), self.OBJ_COLUMN
        )
        if not obj_item:
            logger_gui.warning("Failed to get track object from model")
            return

        track = obj_item.data(QtCore.Qt.ItemDataRole.UserRole)
        if not isinstance(track, Track):
            logger_gui.warning(
                f"Cell does not contain Track object: {type(track)}"
            )
            return

        # Create and show the dialog
        dialog = PlaylistManagerDialog(
            track=track,
            cache=self.playlist_cache,
            session=self.tidal.session,
            threadpool=self.threadpool,
            parent=self.tr_results.window(),
        )

        # Connect signals for tracking changes
        dialog.playlist_added.connect(self.on_track_added_to_playlist)
        dialog.playlist_removed.connect(self.on_track_removed_from_playlist)

        # Show dialog modally
        dialog.exec()

    def on_track_added_to_playlist(
        self, track_id: str, playlist_id: str
    ) -> None:
        """Handle track added to playlist.

        Args:
            track_id: Track UUID
            playlist_id: Playlist UUID
        """
        # Silent - update handled by dialog

    def on_track_removed_from_playlist(
        self, track_id: str, playlist_id: str
    ) -> None:
        """Handle track removed from playlist.

        Args:
            track_id: Track UUID
            playlist_id: Playlist UUID
        """
        # Silent - update handled by dialog
