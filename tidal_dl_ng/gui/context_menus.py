"""Context-menu actions for the main TIDAL Downloader window.

The mixin only coordinates menus and delegates expensive work to the
application's worker thread.  API clients, queue managers, and history
services use explicit typed interfaces so failures are caught before the GUI
is launched.
"""

from __future__ import annotations

import time
import urllib.parse
from functools import partial
from typing import TYPE_CHECKING, cast

from PySide6 import QtCore, QtGui, QtWidgets
from tidalapi.album import Album
from tidalapi.artist import Artist
from tidalapi.exceptions import TidalAPIError
from tidalapi.media import Track, Video
from tidalapi.mix import Mix
from tidalapi.playlist import Playlist, UserPlaylist

from tidal_dl_ng.constants import QueueDownloadStatus
from tidal_dl_ng.helper import tidal as tidal_helper
from tidal_dl_ng.helper.gui import (
    MediaItem,
    get_results_media_item,
    get_user_list_media_item,
)
from tidal_dl_ng.helper.tidal import name_builder_artist
from tidal_dl_ng.logger import logger_gui
from tidal_dl_ng.model.gui_data import QueueDownloadItem, StatusbarMessage

if TYPE_CHECKING:
    from collections.abc import Callable

    from tidal_dl_ng.config import Settings, Tidal
    from tidal_dl_ng.gui.playlist import GuiPlaylistManager
    from tidal_dl_ng.gui.queue import GuiQueueManager
    from tidal_dl_ng.gui.search import GuiSearchManager
    from tidal_dl_ng.history import HistoryService


type SearchMediaType = type[Track | Video | Album | Artist | Playlist | Mix]

SEARCH_TYPE_MAP: dict[str, SearchMediaType] = {
    "artist": Artist,
    "album": Album,
    "track": Track,
    "video": Video,
    "playlist": Playlist,
}

SESSION_ERRORS: tuple[type[Exception], ...] = (
    AttributeError,
    OSError,
    TidalAPIError,
    TypeError,
    ValueError,
)


class ContextMenusMixin:
    """Provide context menus for results, lists, and download queues."""

    tidal: Tidal
    settings: Settings
    s_statusbar_message: QtCore.SignalInstance
    tr_results: QtWidgets.QTreeView
    tr_queue_download: QtWidgets.QTreeWidget
    tr_lists_user: QtWidgets.QTreeWidget
    proxy_tr_results: QtCore.QSortFilterProxyModel
    model_tr_results: QtGui.QStandardItemModel
    history_service: HistoryService
    playlist_manager: GuiPlaylistManager
    queue_manager: GuiQueueManager
    search_manager: GuiSearchManager
    cb_search_type: QtWidgets.QComboBox
    l_search: QtWidgets.QLineEdit

    thread_it: Callable[[Callable[[str], None], str], None]
    on_mark_track_as_not_downloaded: Callable[[str, QtCore.QModelIndex], None]
    on_mark_track_as_downloaded: Callable[[Track, QtCore.QModelIndex], None]

    _ALBUM_FETCH_MAX_RETRIES: int = 2

    def _ensure_session_valid(self) -> bool:
        """Ensure the current TIDAL session is authenticated.

        Returns:
            bool: ``True`` when the session is valid or recovered.
        """
        try:
            if self.tidal.session.check_login():
                return True
        except SESSION_ERRORS:
            logger_gui.warning(
                "Session check failed; trying token re-login.",
                exc_info=True,
            )

        try:
            if self.tidal.login_token():
                logger_gui.info("Session recovered via stored token.")
                return True
        except SESSION_ERRORS:
            logger_gui.exception("Token-based session recovery failed.")

        self.s_statusbar_message.emit(
            StatusbarMessage(
                message="Session expired - please login again.",
                timeout=5000,
            ),
        )
        return False

    def menu_context_tree_results(self, point: QtCore.QPoint) -> None:
        """Show actions for the result row under ``point``.

        Args:
            point (QtCore.QPoint): Position where the context menu was opened.

        Returns:
            None: The menu is shown synchronously and then destroyed.
        """
        index = self.tr_results.indexAt(point)
        if not index.isValid():
            return

        media = get_results_media_item(
            index,
            self.proxy_tr_results,
            self.model_tr_results,
        )
        menu = QtWidgets.QMenu(self.tr_results)

        if isinstance(media, Track | Video) and media.album:
            menu.addAction(
                "Download Full Album",
                partial(self.thread_download_album_from_track, point),
            )

        if isinstance(media, Track):
            track_id = str(media.id)
            if self.history_service.is_downloaded(track_id):
                menu.addAction(
                    "Mark as Not Downloaded",
                    partial(
                        self.on_mark_track_as_not_downloaded,
                        track_id,
                        index,
                    ),
                )
            else:
                menu.addAction(
                    "Mark as Downloaded",
                    partial(
                        self.on_mark_track_as_downloaded,
                        media,
                        index,
                    ),
                )

        menu.addAction(
            "Copy Share URL",
            partial(self.on_copy_url_share, self.tr_results, point),
        )
        menu.exec(self.tr_results.mapToGlobal(point))

    def menu_context_queue_download(self, point: QtCore.QPoint) -> None:
        """Show removal actions for a waiting queue item.

        Args:
            point (QtCore.QPoint): Position where the context menu was opened.

        Returns:
            None: No menu is shown when the point has no actionable item.
        """
        if (item := self.tr_queue_download.itemAt(point)) is None:
            return

        if item.text(0) != QueueDownloadStatus.Waiting:
            return

        menu = QtWidgets.QMenu(self.tr_queue_download)
        menu.addAction(
            "Remove from Queue",
            partial(self.on_queue_download_remove_item, item),
        )
        menu.exec(self.tr_queue_download.mapToGlobal(point))

    def on_queue_download_remove_item(
        self,
        item: QtWidgets.QTreeWidgetItem,
    ) -> None:
        """Remove one top-level waiting item from the download queue.

        Args:
            item (QtWidgets.QTreeWidgetItem): Queue item to remove.

        Returns:
            None: The item is removed when it belongs to the queue.
        """
        if (index := self.tr_queue_download.indexOfTopLevelItem(item)) >= 0:
            self.tr_queue_download.takeTopLevelItem(index)
            logger_gui.info("Removed item from download queue.")

    def on_copy_url_share(
        self,
        tree_target: QtWidgets.QTreeWidget | QtWidgets.QTreeView,
        point: QtCore.QPoint | None = None,
    ) -> None:
        """Copy the selected media item's share URL to the clipboard.

        Args:
            tree_target (QTreeWidget | QTreeView): Source tree widget.
            point (QPoint | None): Position of the selected item.

        Returns:
            None: A status-bar message describes success or missing data.
        """
        if point is None:
            return

        media: MediaItem
        if isinstance(tree_target, QtWidgets.QTreeWidget):
            if (item := tree_target.itemAt(point)) is None:
                return
            media = get_user_list_media_item(item)
        else:
            index = tree_target.indexAt(point)
            if not index.isValid():
                return
            media = get_results_media_item(
                index,
                self.proxy_tr_results,
                self.model_tr_results,
            )

        if not (url_share := self._share_url(media)):
            self.s_statusbar_message.emit(
                StatusbarMessage(
                    message="No share URL available.", timeout=2000
                ),
            )
            return

        clipboard = QtWidgets.QApplication.clipboard()
        clipboard.clear()
        clipboard.setText(url_share)
        self.s_statusbar_message.emit(
            StatusbarMessage(message="Share URL copied.", timeout=1500),
        )

    @staticmethod
    def _share_url(media: MediaItem) -> str:
        """Return a validated share URL from a supported media object.

        Args:
            media (MediaItem): Selected TIDAL media object or list label.

        Returns:
            str: Share URL, or an empty string when unavailable.
        """
        share_url = cast("object", getattr(media, "share_url", None))
        return share_url if isinstance(share_url, str) else ""

    def thread_download_list_media(self, point: QtCore.QPoint) -> None:
        """Queue media from the selected list on the GUI thread.

        Args:
            point (QtCore.QPoint): Position of the selected list item.

        Returns:
            None: The manager starts expensive download work separately.
        """
        self.playlist_manager.on_download_list_media(point)

    def thread_download_album_from_track(
        self,
        point: QtCore.QPoint,
    ) -> None:
        """Schedule loading the full album for a selected track.

        Args:
            point (QtCore.QPoint): Position of the selected result row.

        Returns:
            None: Album loading is delegated to the worker infrastructure.
        """
        if (album_id := self._album_id_at(point)) is not None:
            self.thread_it(self._download_album_by_id, album_id)

    def on_download_album_from_track(self, point: QtCore.QPoint) -> None:
        """Load a selected track's album and add it to the queue.

        Args:
            point (QtCore.QPoint): Position of the selected result row.

        Returns:
            None: Status and logging report success or failure.
        """
        if (album_id := self._album_id_at(point)) is not None:
            self._download_album_by_id(album_id)

    def _album_id_at(self, point: QtCore.QPoint) -> str | None:
        """Resolve an album ID from a result row on the GUI thread.

        Args:
            point (QtCore.QPoint): Position of the selected result row.

        Returns:
            str | None: Normalized TIDAL album ID, if available.
        """
        index = self.tr_results.indexAt(point)
        if not index.isValid():
            return None

        media = get_results_media_item(
            index,
            self.proxy_tr_results,
            self.model_tr_results,
        )
        if not isinstance(media, Track) or media.album is None:
            logger_gui.warning(
                "Could not retrieve album information from the selected track."
            )
            return None

        album_id = media.album.id
        if not isinstance(album_id, int | str) or not album_id:
            logger_gui.warning("The selected track has no valid album ID.")
            return None

        return str(album_id)

    def _download_album_by_id(self, album_id: str) -> None:
        """Load one album in a worker and schedule its GUI queue insertion.

        Args:
            album_id (str): Normalized TIDAL album identifier.

        Returns:
            None: The queue update is posted back to the Qt GUI thread.
        """
        try:
            if not self._ensure_session_valid():
                return

            album = self.tidal.session.album(album_id)
            queue_item = self.queue_manager.media_to_queue_download_model(
                album,
            )
            if queue_item is None:
                logger_gui.warning(
                    "Failed to create a queue item for album ID %s.",
                    album_id,
                )
                return
            self._enqueue_item_on_gui_thread(queue_item)
        except SESSION_ERRORS:
            logger_gui.exception("Could not fetch the full album from TIDAL.")

    def _enqueue_item_on_gui_thread(
        self,
        queue_item: QueueDownloadItem,
    ) -> None:
        """Post one queue insertion to the queue widget's Qt thread.

        Args:
            queue_item (QueueDownloadItem): Prepared download queue entry.

        Returns:
            None: Qt invokes the queue manager asynchronously.
        """
        QtCore.QTimer.singleShot(
            0,
            self.tr_queue_download,
            partial(self.queue_manager.queue_download_media, queue_item),
        )

    def on_download_all_albums_from_playlist(
        self,
        point: QtCore.QPoint,
    ) -> None:
        """Fetch every unique album in a playlist or mix and queue it.

        Args:
            point (QtCore.QPoint): Position of the selected list item.

        Returns:
            None: Progress and failures are reported through the logger/status
                bar.
        """
        try:
            if (item := self.tr_lists_user.itemAt(point)) is None:
                logger_gui.error("Please select a playlist or mix.")
                return

            media_list = get_user_list_media_item(item)
            if not isinstance(media_list, Playlist | Mix):
                logger_gui.error("Please select a playlist or mix.")
                return

            list_name = self._media_list_name(media_list)
            logger_gui.info("Fetching all tracks from: %s", list_name)
            if not self._ensure_session_valid():
                return
            media_items = tidal_helper.items_results_all(
                self.tidal.session,
                media_list,
            )
            album_ids = self._extract_album_ids_from_tracks(media_items)

            if not album_ids:
                logger_gui.warning("No albums found in this playlist.")
                return

            logger_gui.info(
                "Found %s unique albums. Loading with rate limiting.",
                len(album_ids),
            )
            if not (albums := self._load_albums_with_rate_limiting(album_ids)):
                logger_gui.error("Failed to load any albums from playlist.")
                return

            self._queue_loaded_albums(albums)
            message = f"Added {len(albums)} albums to download queue"
            self.s_statusbar_message.emit(
                StatusbarMessage(message=message, timeout=3000),
            )
            logger_gui.info(message)
        except SESSION_ERRORS as error:
            error_message = f"Error downloading albums from playlist: {error}"
            logger_gui.exception(error_message)
            self.s_statusbar_message.emit(
                StatusbarMessage(message=error_message, timeout=3000),
            )

    @staticmethod
    def _media_list_name(media_list: Playlist | UserPlaylist | Mix) -> str:
        """Return a display name for a playlist or mix.

        Args:
            media_list (Playlist | UserPlaylist | Mix): Media list object.

        Returns:
            str: Human-readable list name with a safe fallback.
        """
        if isinstance(media_list, Mix):
            return media_list.title or "Unknown list"
        return media_list.name or "Unknown list"

    def _extract_album_ids_from_tracks(
        self,
        media_items: list[object],
    ) -> dict[str, Album]:
        """Extract unique album objects from track and video results.

        Args:
            media_items (list[object]): Items returned by a TIDAL list.

        Returns:
            dict[str, Album]: Unique albums keyed by normalized TIDAL ID.
        """
        album_ids: dict[str, Album] = {}
        for media_item in media_items:
            if not isinstance(media_item, Track | Video):
                continue
            if (album := media_item.album) is None:
                continue
            album_id = album.id
            if isinstance(album_id, int | str) and album_id:
                album_ids[str(album_id)] = album
        return album_ids

    def _load_albums_with_rate_limiting(
        self,
        album_ids: dict[str, Album],
    ) -> dict[str, Album]:
        """Load albums with configurable batching and retry behavior.

        Args:
            album_ids (dict[str, Album]): Album objects keyed by TIDAL ID.

        Returns:
            dict[str, Album]: Albums successfully loaded from TIDAL.
        """
        albums: dict[str, Album] = {}
        batch_size = max(self.settings.data.api_rate_limit_batch_size, 1)
        delay_sec = max(self.settings.data.api_rate_limit_delay_sec, 0.0)
        if not self._ensure_session_valid():
            return albums

        for index, album_id in enumerate(album_ids, start=1):
            if index > 1 and (index - 1) % batch_size == 0:
                logger_gui.info(
                    "Rate limiting after %s albums; pausing for %s seconds.",
                    index - 1,
                    delay_sec,
                )
                time.sleep(delay_sec)

            for attempt in range(1, self._ALBUM_FETCH_MAX_RETRIES + 1):
                try:
                    album = self.tidal.session.album(album_id)
                    albums[album_id] = album
                    logger_gui.debug(
                        "Loaded album %s/%s: %s - %s",
                        index,
                        len(album_ids),
                        name_builder_artist(album),
                        album.name,
                    )
                    break
                except SESSION_ERRORS as error:
                    if not self._handle_album_load_error(error, album_id):
                        return albums

                    if attempt >= self._ALBUM_FETCH_MAX_RETRIES:
                        logger_gui.warning(
                            "Skipping album %s after %s failed attempt(s).",
                            album_id,
                            attempt,
                        )
                        break

                    logger_gui.info(
                        "Retrying album %s (attempt %s/%s).",
                        album_id,
                        attempt + 1,
                        self._ALBUM_FETCH_MAX_RETRIES,
                    )
                    time.sleep(1)

        logger_gui.info("Successfully loaded %s albums.", len(albums))
        return albums

    def _handle_album_load_error(
        self,
        error: Exception,
        album_id: str,
    ) -> bool:
        """Handle one album load error and decide whether to continue.

        Args:
            error (Exception): Error raised while loading an album.
            album_id (str): TIDAL album identifier being loaded.

        Returns:
            bool: ``True`` to retry/continue, ``False`` to stop processing.
        """
        if self._is_authentication_error(error):
            logger_gui.error("Authentication error: %s", error)
            if self._ensure_session_valid():
                logger_gui.info(
                    "Session recovered after authentication error."
                )
                return True

            logger_gui.error(
                "Your session has expired. Please restart the application "
                "and login again.",
            )
            self.s_statusbar_message.emit(
                StatusbarMessage(
                    message="Session expired - please restart and login.",
                    timeout=5000,
                ),
            )
            return False

        logger_gui.warning("Failed to load album %s: %s", album_id, error)
        logger_gui.info(
            "Some albums may be unavailable because of region restrictions "
            "or removal from TIDAL.",
        )
        return True

    @staticmethod
    def _is_authentication_error(error: Exception) -> bool:
        """Identify common authentication failures without a Tidal helper.

        Args:
            error (Exception): Error raised by the TIDAL client or requests.

        Returns:
            bool: ``True`` when the message indicates expired credentials.
        """
        error_text = str(error).lower()
        return any(
            marker in error_text
            for marker in ("401", "oauth", "token", "unauthorized")
        )

    def _queue_loaded_albums(self, albums: dict[str, Album]) -> None:
        """Convert loaded albums to queue items and enqueue them.

        Args:
            albums (dict[str, Album]): Albums to prepare and enqueue.

        Returns:
            None: Queue manager receives every successfully converted album.
        """
        logger_gui.info("Preparing queue items for %s albums.", len(albums))
        queue_items: list[tuple[QueueDownloadItem, Album]] = []
        for album in albums.values():
            queue_item = self.queue_manager.media_to_queue_download_model(
                album,
            )
            if queue_item is not None:
                queue_items.append((queue_item, album))
                logger_gui.debug(
                    "Prepared: %s - %s",
                    name_builder_artist(album),
                    album.name,
                )

        logger_gui.info("Adding %s albums to queue.", len(queue_items))
        for queue_item, album in queue_items:
            self._enqueue_item_on_gui_thread(queue_item)
            logger_gui.info(
                "Added: %s - %s",
                name_builder_artist(album),
                album.name,
            )

    def on_search_in_app(self, search_term: str, search_type: str) -> None:
        """Schedule a search using the selected in-app media category.

        Args:
            search_term (str): Text or TIDAL URL to search.
            search_type (str): Category name from the search menu.

        Returns:
            None: Search manager performs the request asynchronously.
        """
        self.l_search.setText(search_term)
        search_category = SEARCH_TYPE_MAP.get(search_type.casefold())
        if search_category is None:
            current_data = cast("object", self.cb_search_type.currentData())
            search_category = next(
                (
                    media_type
                    for media_type in SEARCH_TYPE_MAP.values()
                    if current_data is media_type
                ),
                None,
            )

        if search_category is not None:
            for index in range(self.cb_search_type.count()):
                item_data = cast("object", self.cb_search_type.itemData(index))
                if item_data is search_category:
                    self.cb_search_type.setCurrentIndex(index)
                    break

        self.search_manager.search_populate_results(
            search_term,
            search_category,
        )

    def on_search_in_browser(self, search_term: str, search_type: str) -> None:
        """Open a URL for the requested media category in the browser.

        Args:
            search_term (str): Text to URL-encode into the query.
            search_type (str): Category name from the search menu.

        Returns:
            None: Qt delegates opening the URL to the default browser.
        """
        safe_term = urllib.parse.quote(search_term)
        search_path_map: dict[str, str] = {
            "artist": "artists",
            "album": "albums",
            "track": "tracks",
            "video": "videos",
            "playlist": "playlists",
        }
        if search_path := search_path_map.get(search_type.casefold()):
            url = QtCore.QUrl(
                f"https://listen.tidal.com/search/{search_path}?q={safe_term}",
            )
        else:
            url = QtCore.QUrl(
                f"https://listen.tidal.com/search?q={safe_term}",
            )

        QtGui.QDesktopServices.openUrl(url)
