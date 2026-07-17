"""Context menus mixin for MainWindow.

Handles context menu creation and actions.
"""

import time
import urllib.parse
from typing import TYPE_CHECKING, Any, cast

from PySide6 import QtCore, QtGui, QtWidgets
from requests.exceptions import HTTPError
from tidalapi.album import Album
from tidalapi.artist import Artist
from tidalapi.media import Track, Video
from tidalapi.mix import Mix
from tidalapi.playlist import Playlist, UserPlaylist

from tidal_dl_ng.constants import QueueDownloadStatus
from tidal_dl_ng.helper import tidal as tidal_helper
from tidal_dl_ng.helper.gui import (
    get_results_media_item,
    get_user_list_media_item,
)
from tidal_dl_ng.helper.tidal import name_builder_artist
from tidal_dl_ng.logger import logger_gui
from tidal_dl_ng.model.gui_data import StatusbarMessage

if TYPE_CHECKING:
    from tidal_dl_ng.config import Settings, Tidal


class ContextMenusMixin:
    """Mixin containing context menu methods."""

    # Attributes provided by MainWindow at runtime.
    tidal: "Tidal"
    settings: "Settings"
    s_statusbar_message: Any
    tr_results: QtWidgets.QTreeView
    tr_queue_download: QtWidgets.QTreeWidget
    tr_lists_user: QtWidgets.QTreeWidget
    proxy_tr_results: Any
    model_tr_results: QtGui.QStandardItemModel
    history_service: Any
    playlist_manager: Any
    queue_manager: Any
    search_manager: Any
    cb_search_type: QtWidgets.QComboBox
    l_search: QtWidgets.QLineEdit

    # Methods provided by MainWindow / other mixins.
    thread_it: Any
    on_mark_track_as_not_downloaded: Any
    on_mark_track_as_downloaded: Any

    _ALBUM_FETCH_MAX_RETRIES: int = 2

    def _ensure_session_valid(self) -> bool:
        """Ensure the current TIDAL session is authenticated.

        Returns:
            bool: True when session is valid or recovered, False otherwise.
        """
        try:
            if self.tidal.session.check_login():
                return True
        except Exception:
            logger_gui.warning(
                "Session check failed. Trying token re-login..."
            )

        try:
            if self.tidal.login_token():
                logger_gui.info("Session recovered via stored token.")
                return True
        except Exception:
            logger_gui.exception("Token-based session recovery failed.")

        self.s_statusbar_message.emit(
            StatusbarMessage(
                message="Session expired - please login again.", timeout=5000
            )
        )
        return False

    def menu_context_tree_results(self, point: QtCore.QPoint) -> None:
        """Show context menu for results tree."""
        index = self.tr_results.indexAt(point)

        if not index.isValid():
            return

        media = get_results_media_item(
            index, self.proxy_tr_results, self.model_tr_results
        )

        menu = QtWidgets.QMenu()

        if (
            isinstance(media, Track | Video)
            and hasattr(media, "album")
            and media.album
        ):
            menu.addAction(
                "Download Full Album",
                lambda: self.thread_download_album_from_track(point),
            )

        if isinstance(media, Track):
            track_id = str(media.id)
            is_downloaded = self.history_service.is_downloaded(track_id)

            if is_downloaded:
                menu.addAction(
                    "✖️ Mark as Not Downloaded",
                    lambda: self.on_mark_track_as_not_downloaded(
                        track_id, index
                    ),
                )
            else:
                menu.addAction(
                    "✅ Mark as Downloaded",
                    lambda: self.on_mark_track_as_downloaded(media, index),
                )

        menu.addAction(
            "Copy Share URL",
            lambda: self.on_copy_url_share(self.tr_results, point),
        )

        menu.exec(self.tr_results.mapToGlobal(point))

    def menu_context_queue_download(self, point: QtCore.QPoint) -> None:
        """Show context menu for download queue."""
        item = self.tr_queue_download.itemAt(point)

        if not item:
            return

        menu = QtWidgets.QMenu()

        status = item.text(0)
        if status == QueueDownloadStatus.Waiting:
            menu.addAction(
                "🗑️ Remove from Queue",
                lambda: self.on_queue_download_remove_item(item),
            )

        if menu.isEmpty():
            return

        menu.exec(self.tr_queue_download.mapToGlobal(point))

    def on_queue_download_remove_item(
        self, item: QtWidgets.QTreeWidgetItem
    ) -> None:
        """Remove a specific item from the download queue."""
        index = self.tr_queue_download.indexOfTopLevelItem(item)
        if index >= 0:
            self.tr_queue_download.takeTopLevelItem(index)
            logger_gui.info("Removed item from download queue")

    def on_copy_url_share(
        self,
        tree_target: QtWidgets.QTreeWidget | QtWidgets.QTreeView,
        point: QtCore.QPoint | None = None,
    ) -> None:
        """Copy the share URL of a media item to the clipboard."""
        if point is None:
            return

        media: Any

        if isinstance(tree_target, QtWidgets.QTreeWidget):
            item = tree_target.itemAt(point)
            if item is None:
                return
            media = get_user_list_media_item(item)
        else:
            index: QtCore.QModelIndex = tree_target.indexAt(point)
            if not index.isValid():
                return
            media = get_results_media_item(
                index, self.proxy_tr_results, self.model_tr_results
            )

        clipboard = QtWidgets.QApplication.clipboard()
        url_share = (
            media.share_url
            if hasattr(media, "share_url") and media.share_url
            else ""
        )

        if not url_share:
            self.s_statusbar_message.emit(
                StatusbarMessage(
                    message="No share URL available.", timeout=2000
                )
            )
            return

        clipboard.clear()
        clipboard.setText(url_share)
        self.s_statusbar_message.emit(
            StatusbarMessage(message="Share URL copied.", timeout=1500)
        )

    def thread_download_list_media(self, point: QtCore.QPoint) -> None:
        """Start download of a list media item in a thread."""
        self.thread_it(self.playlist_manager.on_download_list_media, point)

    def thread_download_album_from_track(self, point: QtCore.QPoint) -> None:
        """Starts the download of the full album from a selected track in a new thread."""
        self.thread_it(self.on_download_album_from_track, point)

    def on_download_album_from_track(self, point: QtCore.QPoint) -> None:
        """Adds the album associated with a selected track to the download queue."""
        index: QtCore.QModelIndex = self.tr_results.indexAt(point)
        media_track = get_results_media_item(
            index, self.proxy_tr_results, self.model_tr_results
        )

        if (
            isinstance(media_track, Track)
            and media_track.album
            and media_track.album.id
        ):
            try:
                if not self._ensure_session_valid():
                    return

                full_album_object = self.tidal.session.album(
                    str(media_track.album.id)
                )

                queue_dl_item = (
                    self.queue_manager.media_to_queue_download_model(
                        full_album_object
                    )
                )

                if queue_dl_item:
                    self.queue_manager.queue_download_media(queue_dl_item)
                else:
                    logger_gui.warning(
                        f"Failed to create a queue item for album ID: {full_album_object.id}"
                    )
            except Exception:
                logger_gui.exception(
                    "Could not fetch the full album from TIDAL."
                )
        else:
            logger_gui.warning(
                "Could not retrieve album information from the selected track."
            )

    def on_download_all_albums_from_playlist(
        self, point: QtCore.QPoint
    ) -> None:
        """Download all unique albums from tracks in a playlist."""
        try:
            item = self.tr_lists_user.itemAt(point)
            if item is None:
                logger_gui.error("Please select a playlist or mix.")
                return

            media_list = get_user_list_media_item(item)

            if not isinstance(media_list, Playlist | UserPlaylist | Mix):
                logger_gui.error("Please select a playlist or mix.")
                return

            list_name = str(
                getattr(
                    media_list,
                    "name",
                    getattr(media_list, "title", "Unknown list"),
                )
            )
            logger_gui.info(f"Fetching all tracks from: {list_name}")
            tidal_helper_any = cast(Any, tidal_helper)
            media_items = cast(
                list[Any],
                tidal_helper_any.items_results_all(
                    self.tidal.session,
                    media_list,
                ),
            )

            album_ids = self._extract_album_ids_from_tracks(media_items)

            if not album_ids:
                logger_gui.warning("No albums found in this playlist.")
                return

            logger_gui.info(
                f"Found {len(album_ids)} unique albums. Loading with rate limiting..."
            )

            albums_dict = self._load_albums_with_rate_limiting(album_ids)

            if not albums_dict:
                logger_gui.error("Failed to load any albums from playlist.")
                return

            self._queue_loaded_albums(albums_dict)

            message = f"Added {len(albums_dict)} albums to download queue"
            self.s_statusbar_message.emit(
                StatusbarMessage(message=message, timeout=3000)
            )
            logger_gui.info(message)

        except Exception as e:
            error_msg = f"Error downloading albums from playlist: {e!s}"
            logger_gui.error(error_msg)
            self.s_statusbar_message.emit(
                StatusbarMessage(message=error_msg, timeout=3000)
            )

    def _extract_album_ids_from_tracks(
        self, media_items: list[Any]
    ) -> dict[int, Album]:
        """Extract unique album IDs from a list of media items."""
        album_ids: dict[int, Album] = {}

        for media_item in media_items:
            if not isinstance(media_item, Track | Video):
                continue

            if not hasattr(media_item, "album") or not media_item.album:
                continue

            try:
                album_id = media_item.album.id
                if album_id:
                    album_ids[album_id] = media_item.album
            except Exception as e:
                logger_gui.debug(
                    f"Skipping track with unavailable album: {e!s}"
                )
                continue

        return album_ids

    def _load_albums_with_rate_limiting(
        self, album_ids: dict[int, Album]
    ) -> dict[int, Album]:
        """Load full album objects with rate limiting to prevent API throttling."""
        albums_dict: dict[int, Album] = {}
        batch_size = int(
            getattr(self.settings.data, "api_rate_limit_batch_size", 20)
        )
        delay_sec = float(
            getattr(self.settings.data, "api_rate_limit_delay_sec", 3.0)
        )

        if batch_size <= 0:
            batch_size = 20

        for idx, album_id in enumerate(album_ids.keys(), start=1):
            for attempt in range(1, self._ALBUM_FETCH_MAX_RETRIES + 1):
                try:
                    if idx > 1 and (idx - 1) % batch_size == 0:
                        logger_gui.info(
                            f"⏰ RATE LIMITING: Processed {idx - 1} albums, pausing for {delay_sec} seconds..."
                        )
                        time.sleep(delay_sec)

                    if not self._ensure_session_valid():
                        return albums_dict

                    album = self.tidal.session.album(str(album_id))
                    album_obj_id = getattr(album, "id", None)
                    album_key = (
                        album_obj_id
                        if isinstance(album_obj_id, int)
                        else album_id
                    )
                    albums_dict[album_key] = album
                    logger_gui.debug(
                        f"Loaded album {idx}/{len(album_ids)}: {name_builder_artist(album)} - {album.name}"
                    )
                    break

                except Exception as e:
                    can_continue = self._handle_album_load_error(e, album_id)
                    is_last_attempt = attempt >= self._ALBUM_FETCH_MAX_RETRIES

                    if not can_continue:
                        return albums_dict

                    if is_last_attempt:
                        logger_gui.warning(
                            f"Skipping album {album_id} after {attempt} failed attempt(s)."
                        )
                        break

                    logger_gui.info(
                        f"Retrying album {album_id} "
                        f"(attempt {attempt + 1}/{self._ALBUM_FETCH_MAX_RETRIES})..."
                    )
                    time.sleep(1)

        logger_gui.info(f"Successfully loaded {len(albums_dict)} albums.")
        return albums_dict

    def _handle_album_load_error(
        self, error: Exception, album_id: int
    ) -> bool:
        """Handle errors that occur when loading an album."""
        if self.tidal.is_authentication_error(error) or isinstance(
            error, HTTPError
        ):
            error_msg = str(error)
            logger_gui.error(f"Authentication error: {error_msg}")
            if self._ensure_session_valid():
                logger_gui.info(
                    "Session recovered after authentication error."
                )
                return True

            logger_gui.error(
                "Your session has expired. Please restart the application and login again."
            )
            self.s_statusbar_message.emit(
                StatusbarMessage(
                    message="Session expired - please restart and login",
                    timeout=5000,
                )
            )
            return False

        logger_gui.warning(f"Failed to load album {album_id}: {error!s}")
        logger_gui.info(
            "Note: Some albums may be unavailable due to region restrictions or removal from TIDAL. This is normal."
        )
        return True

    def _queue_loaded_albums(self, albums_dict: dict[int, Album]) -> None:
        """Prepare and add loaded albums to the download queue."""
        logger_gui.info(
            f"Preparing queue items for {len(albums_dict)} albums..."
        )

        queue_items: list[tuple[Any, Album]] = []
        for album in albums_dict.values():
            queue_dl_item = self.queue_manager.media_to_queue_download_model(
                album
            )
            if queue_dl_item:
                queue_items.append((queue_dl_item, album))
                logger_gui.debug(
                    f"Prepared: {name_builder_artist(album)} - {album.name}"
                )

        logger_gui.info(f"Adding {len(queue_items)} albums to queue...")
        for queue_dl_item, album in queue_items:
            self.queue_manager.queue_download_media(queue_dl_item)
            logger_gui.info(
                f"Added: {name_builder_artist(album)} - {album.name}"
            )

    def on_search_in_app(self, search_term: str, search_type: str) -> None:
        """Perform a search within the application, selecting the correct category."""
        self.l_search.setText(search_term)

        search_type_map: dict[str, type[Any]] = {
            "artist": Artist,
            "album": Album,
            "track": Track,
            "video": Video,
            "playlist": Playlist,
        }
        search_category = search_type_map.get(search_type.lower())

        if search_category is None:
            search_category = cast(
                type[Any], self.cb_search_type.currentData()
            )

        for i in range(self.cb_search_type.count()):
            if self.cb_search_type.itemData(i) == search_category:
                self.cb_search_type.setCurrentIndex(i)
                break

        self.search_manager.search_populate_results(
            search_term, search_category
        )

    def on_search_in_browser(self, search_term: str, search_type: str) -> None:
        """Open a search in the default web browser."""
        safe_term = urllib.parse.quote(search_term)
        search_path_map = {
            "artist": "artists",
            "album": "albums",
            "track": "tracks",
            "video": "videos",
            "playlist": "playlists",
        }
        search_path = search_path_map.get(search_type.lower())

        if search_path:
            url = QtCore.QUrl(
                f"https://listen.tidal.com/search/{search_path}?q={safe_term}"
            )
        else:
            url = QtCore.QUrl(f"https://listen.tidal.com/search?q={safe_term}")

        QtGui.QDesktopServices.openUrl(url)
