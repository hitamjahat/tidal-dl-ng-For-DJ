# tidal_dl_ng/gui/playlist.py

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

from PySide6 import QtCore, QtWidgets
from tidalapi.album import Album
from tidalapi.artist import Artist
from tidalapi.media import Track
from tidalapi.mix import Mix
from tidalapi.playlist import Folder, Playlist, UserPlaylist
from tidalapi.session import Session

from tidal_dl_ng.constants import FAVORITES, TidalLists
from tidal_dl_ng.helper.gui import (
    get_user_list_media_item,
    set_user_list_media,
)
from tidal_dl_ng.helper.tidal import (
    favorite_function_factory,
    items_results_all,
    user_media_lists,
)
from tidal_dl_ng.logger import logger_gui
from tidal_dl_ng.model.gui_data import (
    QueueDownloadItem,
    ResultItem,
    StatusbarMessage,
)

if TYPE_CHECKING:
    from tidal_dl_ng.gui import MainWindow


FavoriteFunction = Callable[[], list[Any]]
FavoriteFactory = Callable[[Any, str], FavoriteFunction]
ItemsResultsFetcher = Callable[[Session, Any, bool], list[Any]]
UserMediaListsFetcher = Callable[[Session], dict[str, list[Any]]]

FAVORITE_FUNCTION_FACTORY = cast(FavoriteFactory, favorite_function_factory)
ITEMS_RESULTS_ALL = cast(ItemsResultsFetcher, items_results_all)
USER_MEDIA_LISTS = cast(UserMediaListsFetcher, user_media_lists)


class GuiPlaylistManager:
    """Manages the playlist, mixes, and favorites GUI and logic."""

    def __init__(self, main_window: MainWindow) -> None:
        """Initialize the playlist manager.

        Args:
            main_window: Reference to the main application window.
        """
        self.main_window: MainWindow = main_window
        self.settings = main_window.settings

    def _ensure_session_valid(self) -> bool:
        """Ensure TIDAL session is valid before making API calls.

        Returns:
            bool: True if session is valid, False otherwise.
        """
        if (
            not hasattr(self.main_window, "tidal")
            or not self.main_window.tidal
        ):
            logger_gui.error("Tidal session not available")
            return False

        session: Session | None = getattr(
            self.main_window.tidal, "session", None
        )
        if not session:
            logger_gui.error("Tidal session object not available")
            return False

        # Check if session has valid credentials
        if not getattr(session, "access_token", None):
            logger_gui.error("Tidal session missing access token")
            return False

        return True

    def _safe_tidal_call(
        self, func: Callable[..., Any], *args: Any, **kwargs: Any
    ) -> Any:
        """Safely execute a TIDAL API call with error handling.

        Args:
            func: The function to call.
            *args: Positional arguments for the function.
            **kwargs: Keyword arguments for the function.

        Returns:
            The function result or None if failed.
        """
        if not self._ensure_session_valid():
            return None

        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger_gui.exception(f"TIDAL API call failed: {e}")
            return None

    def _extract_album_ids_from_tracks(
        self, media_items: list[Any]
    ) -> list[str]:
        """Extract album IDs via main window helper with safe fallback."""
        extractor = getattr(
            self.main_window,
            "_extract_album_ids_from_tracks",
            None,
        )
        if not callable(extractor):
            logger_gui.error("Album ID extractor helper not available")
            return []

        try:
            album_ids_any = extractor(media_items)
        except Exception as e:
            logger_gui.exception(f"Failed to extract album IDs: {e}")
            return []

        if not isinstance(album_ids_any, list):
            return []

        return [str(album_id) for album_id in album_ids_any]

    def _load_albums_with_rate_limiting(
        self, album_ids: list[str]
    ) -> dict[str, Album]:
        """Load albums via main window helper with safe fallback."""
        loader = getattr(
            self.main_window,
            "_load_albums_with_rate_limiting",
            None,
        )
        if not callable(loader):
            logger_gui.error("Album loader helper not available")
            return {}

        try:
            albums_any = loader(album_ids)
        except Exception as e:
            logger_gui.exception(f"Failed to load albums: {e}")
            return {}

        if not isinstance(albums_any, dict):
            return {}

        albums_dict: dict[str, Album] = {}
        for album_id, album in albums_any.items():
            if isinstance(album, Album):
                albums_dict[str(album_id)] = album

        return albums_dict

    def _queue_loaded_albums(self, albums_dict: dict[str, Album]) -> None:
        """Queue albums via main window helper if available."""
        queue_loader = getattr(self.main_window, "_queue_loaded_albums", None)
        if not callable(queue_loader):
            logger_gui.error("Album queue helper not available")
            return

        try:
            queue_loader(albums_dict)
        except Exception as e:
            logger_gui.exception(f"Failed to queue loaded albums: {e}")

    def init_ui(self) -> None:
        """Initialize UI elements related to playlists."""
        self._init_tree_lists(self.main_window.tr_lists_user)

    def connect_signals(self) -> None:
        """Connect signals for playlist-related widgets."""
        self.main_window.pb_reload_user_lists.clicked.connect(
            lambda: self.main_window.thread_it(self.tidal_user_lists)
        )
        self.main_window.tr_lists_user.itemClicked.connect(
            self.on_list_items_show
        )
        self.main_window.tr_lists_user.itemExpanded.connect(
            self.on_tr_lists_user_expanded
        )
        self.main_window.tr_lists_user.customContextMenuRequested.connect(
            self.menu_context_tree_lists
        )
        self.main_window.s_populate_tree_lists.connect(
            self.on_populate_tree_lists
        )
        self.main_window.s_populate_folder_children.connect(
            self.on_populate_folder_children
        )

    def _init_tree_lists(self, tree: QtWidgets.QTreeWidget) -> None:
        """Initialize the user lists tree widget.

        Args:
            tree: The QTreeWidget to initialize.
        """
        tree.setColumnWidth(0, 200)
        tree.setColumnHidden(1, True)
        tree.setColumnWidth(2, 300)
        tree.expandAll()
        tree.setContextMenuPolicy(
            QtCore.Qt.ContextMenuPolicy.CustomContextMenu
        )

    def tidal_user_lists(self) -> None:
        """Fetch and emit user playlists, mixes, and favorites from Tidal."""
        self.main_window.s_spinner_start.emit(self.main_window.tr_lists_user)
        self.main_window.s_pb_reload_status.emit(False)

        def _fetch_user_lists() -> dict[str, list[Any]] | None:
            return USER_MEDIA_LISTS(self.main_window.tidal.session)

        user_all = self._safe_tidal_call(_fetch_user_lists)

        if user_all is not None:
            self.main_window.s_populate_tree_lists.emit(user_all)
        else:
            self.main_window.s_spinner_stop.emit()
            self.main_window.s_pb_reload_status.emit(True)

    def on_populate_tree_lists(self, user_lists: dict[str, list[Any]]) -> None:
        """Populate the user lists tree with playlists, mixes, and favorites.

        Args:
            user_lists: Dictionary containing 'playlists' and 'mixes' lists.
        """
        twi_playlists = self.main_window.tr_lists_user.findItems(
            TidalLists.Playlists, QtCore.Qt.MatchFlag.MatchExactly, 0
        )[0]
        twi_mixes = self.main_window.tr_lists_user.findItems(
            TidalLists.Mixes, QtCore.Qt.MatchFlag.MatchExactly, 0
        )[0]
        twi_favorites = self.main_window.tr_lists_user.findItems(
            TidalLists.Favorites, QtCore.Qt.MatchFlag.MatchExactly, 0
        )[0]

        for twi in [twi_playlists, twi_mixes, twi_favorites]:
            for i in reversed(range(twi.childCount())):
                twi.removeChild(twi.child(i))

        for item in user_lists.get("playlists", []):
            if isinstance(item, Folder):
                twi_child = QtWidgets.QTreeWidgetItem(twi_playlists)
                twi_child.setText(0, f"📁 {item.name}")
                set_user_list_media(twi_child, item)
                info = (
                    f"({item.total_number_of_items} items)"
                    if item.total_number_of_items
                    else ""
                )
                twi_child.setText(2, info)
                dummy_child = QtWidgets.QTreeWidgetItem(twi_child)
                dummy_child.setDisabled(True)
            elif isinstance(item, (UserPlaylist, Playlist)):
                twi_child = QtWidgets.QTreeWidgetItem(twi_playlists)
                name = item.name or ""
                description = (
                    f" {item.description}" if item.description else ""
                )
                info = f"({item.num_tracks + item.num_videos} Tracks){description}"
                twi_child.setText(0, name)
                set_user_list_media(twi_child, item)
                twi_child.setText(2, info)

        for item in user_lists.get("mixes", []):
            if isinstance(item, Mix):
                twi_child = QtWidgets.QTreeWidgetItem(twi_mixes)
                twi_child.setText(0, item.title)
                set_user_list_media(twi_child, item)
                twi_child.setText(2, item.sub_title)

        for key, favorite in FAVORITES.items():
            twi_child = QtWidgets.QTreeWidgetItem(twi_favorites)
            twi_child.setText(0, favorite["name"])
            set_user_list_media(twi_child, key)

        self.main_window.s_spinner_stop.emit()
        self.main_window.s_pb_reload_status.emit(True)

    def menu_context_tree_lists(self, point: QtCore.QPoint) -> None:
        """Show context menu for user lists tree.

        Args:
            point (QPoint): The point where the menu is requested.
        """
        # Infos about the node selected.
        index = self.main_window.tr_lists_user.indexAt(point)

        # Do not open menu if something went wrong or a parent node is clicked.
        if not index.isValid() or not index.parent().data():
            return

        # Get the media item to determine type
        item = self.main_window.tr_lists_user.itemAt(point)
        if item is None:
            return
        media = get_user_list_media_item(item)

        # We build the menu.
        menu = QtWidgets.QMenu()

        if isinstance(media, Folder):
            # Folder-specific menu items
            menu.addAction(
                "Download All Playlists in Folder",
                lambda: self.main_window.thread_it(
                    self.on_download_folder_playlists, point
                ),
            )
            menu.addAction(
                "Download All Albums from Folder",
                lambda: self.main_window.thread_it(
                    self.on_download_folder_albums, point
                ),
            )
        elif isinstance(media, str):
            # Favorites items (stored as string keys like "fav_tracks", "fav_albums")
            menu.addAction(
                "Download All Items",
                lambda: self.main_window.thread_it(
                    self.on_download_favorites, point
                ),
            )
            menu.addAction(
                "Download All Albums from Items",
                lambda: self.main_window.thread_it(
                    self.on_download_albums_from_favorites, point
                ),
            )
        else:
            # Playlist/Mix menu items (existing)
            menu.addAction(
                "Download Playlist",
                lambda: self.main_window.thread_download_list_media(point),
            )
            menu.addAction(
                "Download All Albums in Playlist",
                lambda: self.main_window.thread_it(
                    self.on_download_all_albums_from_playlist, point
                ),
            )
            menu.addAction(
                "Copy Share URL",
                lambda: self.main_window.on_copy_url_share(
                    self.main_window.tr_lists_user, point
                ),
            )

        menu.exec(self.main_window.tr_lists_user.mapToGlobal(point))

    def on_download_list_media(
        self, point: QtCore.QPoint | None = None
    ) -> None:
        """Download all media items in a selected list.

        Args:
            point (QPoint | None, optional): The point in the tree. Defaults to None.
        """
        items: list[QtWidgets.QTreeWidgetItem] = []

        if point:
            item_at_point = self.main_window.tr_lists_user.itemAt(point)
            if item_at_point is None:
                logger_gui.error("Please select a mix or playlist first.")
                return
            items = [item_at_point]
        else:
            items = self.main_window.tr_lists_user.selectedItems()

            if len(items) == 0:
                logger_gui.error("Please select a mix or playlist first.")

        for item in items:
            media = get_user_list_media_item(item)
            if not isinstance(media, (Artist, Track, Album, Playlist, Mix)):
                continue
            queue_dl_item = (
                self.main_window.search_manager.media_to_queue_download_model(
                    media
                )
            )

            if isinstance(queue_dl_item, QueueDownloadItem):
                self.main_window.queue_download_media(queue_dl_item)

    def on_download_folder_playlists(self, point: QtCore.QPoint) -> None:
        """Download all playlists in a folder.

        Args:
            point (QPoint): The point in the tree where the folder was right-clicked.
        """
        try:
            # Get and validate the folder
            item = self.main_window.tr_lists_user.itemAt(point)
            if item is None:
                logger_gui.error("Please select a folder.")
                return
            media = get_user_list_media_item(item)

            if not isinstance(media, Folder):
                logger_gui.error("Please select a folder.")
                return

            # Fetch all playlists in the folder
            logger_gui.info(f"Fetching playlists from folder: {media.name}")
            playlists = self._get_folder_playlists(media)

            if not playlists:
                logger_gui.info(f"No playlists found in folder: {media.name}")
                return

            # Queue each playlist for download
            logger_gui.info(
                f"Queueing {len(playlists)} playlists from folder: {media.name}"
            )

            for playlist in playlists:
                queue_dl_item = self.main_window.search_manager.media_to_queue_download_model(
                    playlist
                )

                if isinstance(queue_dl_item, QueueDownloadItem):
                    self.main_window.queue_download_media(queue_dl_item)

            logger_gui.info(
                f"✅ Successfully queued {len(playlists)} playlists from folder: {media.name}"
            )

        except Exception as e:
            logger_gui.exception(
                f"Error downloading playlists from folder: {e}"
            )
            logger_gui.error(
                "Failed to download playlists from folder. See log for details."
            )

    def on_download_folder_albums(self, point: QtCore.QPoint) -> None:
        """Download all unique albums from all playlists in a folder.

        Args:
            point (QPoint): The point in the tree where the folder was right-clicked.
        """
        try:
            # Get and validate the folder
            item = self.main_window.tr_lists_user.itemAt(point)
            if item is None:
                logger_gui.error("Please select a folder.")
                return
            media = get_user_list_media_item(item)

            if not isinstance(media, Folder):
                logger_gui.error("Please select a folder.")
                return

            # Fetch all playlists in the folder
            logger_gui.info(f"Fetching playlists from folder: {media.name}")
            playlists = self._get_folder_playlists(media)

            if not playlists:
                logger_gui.info(f"No playlists found in folder: {media.name}")
                return

            logger_gui.info(
                f"Found {len(playlists)} playlists in folder: {media.name}"
            )

            # Collect all tracks from all playlists
            all_tracks: list[Track] = []

            for playlist in playlists:
                try:
                    tracks = self._get_playlist_tracks(playlist)
                    all_tracks.extend(tracks)
                    logger_gui.debug(
                        f"Collected {len(tracks)} tracks from playlist: {playlist.name}"
                    )
                except Exception as e:
                    logger_gui.error(
                        f"Error getting tracks from playlist '{playlist.name}': {e}"
                    )
                    continue

            if not all_tracks:
                logger_gui.info(
                    f"No tracks found in folder playlists: {media.name}"
                )
                return

            logger_gui.info(
                f"Collected {len(all_tracks)} total tracks from all playlists"
            )

            # Extract unique album IDs
            album_ids = self._extract_album_ids_from_tracks(all_tracks)
            logger_gui.info(
                f"Found {len(album_ids)} unique albums across all playlists in folder: {media.name}"
            )

            if not album_ids:
                logger_gui.info("No albums found to download.")
                return

            # Load full album objects with rate limiting
            albums_dict = self._load_albums_with_rate_limiting(album_ids)

            if not albums_dict:
                logger_gui.error("Failed to load any albums.")
                return

            # Queue the albums for download
            self._queue_loaded_albums(albums_dict)

            logger_gui.info(
                f"✅ Successfully queued {len(albums_dict)} unique albums from folder: {media.name}"
            )

        except Exception as e:
            logger_gui.exception(f"Error downloading albums from folder: {e}")
            logger_gui.error(
                "Failed to download albums from folder. See log for details."
            )

    def on_download_favorites(self, point: QtCore.QPoint) -> None:
        """Download all items from a Favorites category.

        Args:
            point (QPoint): The point in the tree where the favorites item was right-clicked.
        """
        try:
            # Get and validate the favorites item
            item = self.main_window.tr_lists_user.itemAt(point)
            if item is None:
                logger_gui.error("Please select a favorites category.")
                return
            media = get_user_list_media_item(item)

            if not isinstance(media, str):
                logger_gui.error("Please select a favorites category.")
                return

            # Get the favorites category name for logging
            favorite_name = FAVORITES.get(media, {}).get("name", media)
            logger_gui.info(
                f"Fetching all items from favorites: {favorite_name}"
            )

            # Use the factory to get the appropriate favorites function
            favorite_function: FavoriteFunction = FAVORITE_FUNCTION_FACTORY(
                self.main_window.tidal, media
            )

            # Fetch all items from this favorites category
            media_items = self._safe_tidal_call(favorite_function)

            if not media_items:
                logger_gui.info(
                    f"No items found in favorites: {favorite_name}"
                )
                return

            logger_gui.info(
                f"Found {len(media_items)} items in favorites: {favorite_name}"
            )

            # Queue each item for download
            queued_count = 0

            for media_item in media_items:
                queue_dl_item = self.main_window.search_manager.media_to_queue_download_model(
                    media_item
                )

                if isinstance(queue_dl_item, QueueDownloadItem):
                    self.main_window.queue_download_media(queue_dl_item)
                    queued_count += 1

            logger_gui.info(
                f"✅ Successfully queued {queued_count} items from favorites: {favorite_name}"
            )

        except Exception as e:
            logger_gui.exception(f"Error downloading favorites: {e}")
            logger_gui.error(
                "Failed to download favorites. See log for details."
            )

    def _download_albums_from_fav_artists(
        self, media_items: list[Any]
    ) -> None:
        """Download all albums from favorite artists."""
        all_albums: dict[str, Album] = {}
        for artist in media_items:
            try:
                artist_albums = self._safe_tidal_call(
                    ITEMS_RESULTS_ALL,
                    self.main_window.tidal.session,
                    artist,
                )
                if artist_albums:
                    for album in artist_albums:
                        if isinstance(album, Album) and album.id:
                            all_albums[str(album.id)] = album
            except Exception as e:
                logger_gui.error(
                    f"Error getting albums from artist '{artist.name}': {e}"
                )
        if all_albums:
            self._queue_loaded_albums(all_albums)

    def _download_albums_from_fav_tracks(self, media_items: list[Any]) -> None:
        """Download all albums from favorite tracks."""
        album_ids = self._extract_album_ids_from_tracks(media_items)
        if album_ids:
            albums_dict = self._load_albums_with_rate_limiting(album_ids)
            if albums_dict:
                self._queue_loaded_albums(albums_dict)

    def on_download_albums_from_favorites(self, point: QtCore.QPoint) -> None:
        """Download all unique albums from items in a Favorites category.

        Args:
            point (QPoint): The point in the tree where the favorites item was right-clicked.
        """
        try:
            # Get and validate the favorites item
            item = self.main_window.tr_lists_user.itemAt(point)
            if item is None:
                logger_gui.error("Please select a favorites category.")
                return
            media = get_user_list_media_item(item)

            if not isinstance(media, str):
                logger_gui.error("Please select a favorites category.")
                return

            # Get the favorites category name for logging
            favorite_name = FAVORITES.get(media, {}).get("name", media)
            logger_gui.info(
                f"Fetching all items from favorites: {favorite_name}"
            )

            # Use the factory to get the appropriate favorites function
            favorite_function: FavoriteFunction = FAVORITE_FUNCTION_FACTORY(
                self.main_window.tidal, media
            )

            # Fetch all items from this favorites category
            media_items = self._safe_tidal_call(favorite_function)

            if not media_items:
                logger_gui.info(
                    f"No items found in favorites: {favorite_name}"
                )
                return

            logger_gui.info(
                f"Found {len(media_items)} items in favorites: {favorite_name}"
            )

            # Delegate to appropriate handler based on favorites type
            if media == "fav_albums":
                self._download_albums_from_favorites_albums(
                    media_items, favorite_name
                )
            elif media == "fav_artists":
                self._download_albums_from_favorites_artists(
                    media_items, favorite_name
                )
            else:
                self._download_albums_from_favorites_tracks(
                    media_items, favorite_name
                )

        except Exception as e:
            logger_gui.exception(
                f"Error downloading albums from favorites: {e}"
            )
            logger_gui.error(
                "Failed to download albums from favorites. See log for details."
            )

    def on_download_all_albums_from_playlist(
        self, point: QtCore.QPoint
    ) -> None:
        """Download all unique albums from tracks in a playlist."""
        item = self.main_window.tr_lists_user.itemAt(point)
        if item is None:
            logger_gui.error("Please select a playlist or mix.")
            return
        media_list = get_user_list_media_item(item)
        if not isinstance(media_list, (Playlist, UserPlaylist, Mix)):
            logger_gui.error("Please select a playlist or mix.")
            return
        media_items = self._safe_tidal_call(
            ITEMS_RESULTS_ALL,
            self.main_window.tidal.session,
            media_list,
        )
        if media_items is None:
            logger_gui.error("Failed to fetch playlist items.")
            return
        album_ids = self._extract_album_ids_from_tracks(media_items)
        if not album_ids:
            logger_gui.warning("No albums found in this playlist.")
            return
        albums_dict = self._load_albums_with_rate_limiting(album_ids)
        if not albums_dict:
            logger_gui.error("Failed to load any albums from playlist.")
            return
        self._queue_loaded_albums(albums_dict)
        message = f"Added {len(albums_dict)} albums to download queue"
        self.main_window.s_statusbar_message.emit(
            StatusbarMessage(message=message, timeout=3000)
        )

    def on_tr_lists_user_expanded(
        self, item: QtWidgets.QTreeWidgetItem
    ) -> None:
        """Handle expansion of folders in the user lists tree.

        Args:
            item (QTreeWidgetItem): The expanded tree item.
        """
        # Check if it's a first-time expansion (has disabled dummy child)
        if item.childCount() > 0 and item.child(0).isDisabled():
            # Run in thread to avoid blocking UI
            self.main_window.thread_it(
                self.tr_lists_user_load_folder_children, item
            )

    def tr_lists_user_load_folder_children(
        self, parent_item: QtWidgets.QTreeWidgetItem
    ) -> None:
        """Load and display children of a folder in the user lists tree.

        Args:
            parent_item (QTreeWidgetItem): The parent folder item.
        """
        folder_media = get_user_list_media_item(parent_item)

        if not isinstance(folder_media, Folder):
            return
        folder = folder_media

        # Show spinner while loading
        self.main_window.s_spinner_start.emit(self.main_window.tr_lists_user)

        try:
            # Fetch folder contents
            folders, playlists = self._fetch_folder_contents(folder)

            # Emit signal to populate in main thread
            self.main_window.s_populate_folder_children.emit(
                parent_item, folders, playlists
            )

        finally:
            self.main_window.s_spinner_stop.emit()

    def on_populate_folder_children(
        self,
        parent_item: QtWidgets.QTreeWidgetItem,
        folders: list[Folder],
        playlists: list[Playlist],
    ) -> None:
        """Populate folder children in the main thread (signal handler).

        Args:
            parent_item (QTreeWidgetItem): The parent folder item.
            folders (list[Folder]): List of sub-folders.
            playlists (list[Playlist]): List of playlists.
        """
        # Remove dummy child
        parent_item.takeChild(0)

        # Add sub-folders as children
        for sub_folder in folders:
            twi_child = QtWidgets.QTreeWidgetItem(parent_item)
            twi_child.setText(0, f"📁 {sub_folder.name}")
            set_user_list_media(twi_child, sub_folder)
            info = (
                f"({sub_folder.total_number_of_items} items)"
                if sub_folder.total_number_of_items
                else ""
            )
            twi_child.setText(2, info)

            # Add dummy child for potential sub-folders
            dummy = QtWidgets.QTreeWidgetItem(twi_child)
            dummy.setDisabled(True)

        # Add playlists as children
        for playlist in playlists:
            twi_child = QtWidgets.QTreeWidgetItem(parent_item)
            name = playlist.name if playlist.name else ""
            twi_child.setText(0, name)
            set_user_list_media(twi_child, playlist)
            info = f"({playlist.num_tracks + playlist.num_videos} Tracks)"
            if playlist.description:
                info += f" {playlist.description}"
            twi_child.setText(2, info)

    def _fetch_folder_contents(
        self, folder: Folder
    ) -> tuple[list[Folder], list[Playlist]]:
        """Fetch contents (sub-folders and playlists) of a folder.

        Args:
            folder (Folder): The folder to fetch contents for.

        Returns:
            tuple[list[Folder], list[Playlist]]: Sub-folders and playlists within the folder.
        """
        folder_id = folder.id if folder.id else "root"

        # Fetch sub-folders with manual pagination
        offset = 0
        limit = 50
        folders: list[Folder] = []

        while True:
            user = getattr(self.main_window.tidal.session, "user", None)
            favorites = getattr(user, "favorites", None)
            playlist_folders_fn = getattr(favorites, "playlist_folders", None)
            if not callable(playlist_folders_fn):
                break

            batch = self._safe_tidal_call(
                cast(Callable[..., list[Folder]], playlist_folders_fn),
                limit=limit,
                offset=offset,
                parent_folder_id=folder_id,
            )
            if not batch:
                break
            folders.extend(batch)
            if len(batch) < limit:
                break
            offset += limit

        # Fetch playlists in this folder using folder.items() method
        offset = 0
        playlists: list[Playlist] = []

        while True:
            batch = self._safe_tidal_call(
                folder.items, offset=offset, limit=limit
            )
            if not batch:
                break
            playlists.extend(batch)
            if len(batch) < limit:
                break
            offset += limit

        return folders, playlists

    def _get_folder_playlists(self, folder: Folder) -> list[Playlist]:
        """Fetch all playlists from a folder.

        Args:
            folder (Folder): The folder to fetch playlists from.

        Returns:
            list[Playlist]: List of playlists in the folder.
        """
        # Use existing method to fetch folder contents
        # Since folders can't contain folders, we ignore the folders return value
        _, playlists = self._fetch_folder_contents(folder)

        logger_gui.debug(
            f"Found {len(playlists)} playlists in folder: {folder.name}"
        )

        return playlists

    def _get_playlist_tracks(
        self, playlist: Playlist | UserPlaylist | Mix
    ) -> list[Track]:
        """Fetch all tracks from a playlist.

        Args:
            playlist (Playlist | UserPlaylist | Mix): The playlist to fetch tracks from.

        Returns:
            list[Track]: List of tracks in the playlist.
        """
        playlist_name = getattr(playlist, "name", "unknown")
        logger_gui.debug(f"Fetching tracks from playlist: {playlist_name}")
        media_items = self._safe_tidal_call(
            ITEMS_RESULTS_ALL,
            self.main_window.tidal.session,
            playlist,
        )
        if media_items is None:
            logger_gui.error(
                f"Failed to fetch tracks from playlist: {playlist_name}"
            )
            return []

        # Filter for Track objects only (items_results_all may return Videos too)
        tracks = [item for item in media_items if isinstance(item, Track)]

        logger_gui.debug(
            f"Found {len(tracks)} tracks in playlist: {playlist_name}"
        )

        return tracks

    def on_list_items_show(self, item: QtWidgets.QTreeWidgetItem) -> None:
        """Show the items in the selected playlist or mix.

        Args:
            item (QtWidgets.QTreeWidgetItem): The selected tree widget item.
        """
        self.main_window.thread_it(self.list_items_show, item)

    def list_items_show(self, item: QtWidgets.QTreeWidgetItem) -> None:
        """Fetch and display the items in a playlist, mix, or folder.

        Args:
            item (QtWidgets.QTreeWidgetItem): The tree widget item representing a playlist, mix, or folder.
        """
        media_list: Mix | Playlist | Folder | str = get_user_list_media_item(
            item
        )

        # Only if clicked item is not a top level item.
        if media_list:
            # Show spinner while loading list
            self.main_window.s_spinner_start.emit(self.main_window.tr_results)
            try:
                if isinstance(media_list, Folder):
                    # Show folder contents
                    self._show_folder_contents(media_list)
                elif isinstance(media_list, str) and media_list.startswith(
                    "fav_"
                ):
                    function_list: FavoriteFunction = (
                        FAVORITE_FUNCTION_FACTORY(
                            self.main_window.tidal, media_list
                        )
                    )
                    self.main_window.list_items_show_result(
                        favorite_function=function_list
                    )
                elif isinstance(media_list, (Playlist, Mix)):
                    self.main_window.list_items_show_result(media_list)
                    # Load cover asynchronously to avoid blocking the GUI
                    if hasattr(self.main_window, "cover_manager"):
                        self.main_window.cover_manager.load_cover(media_list)
            finally:
                self.main_window.s_spinner_stop.emit()

    def _show_folder_contents(self, folder: Folder) -> None:
        """Display folder contents (nested playlists/folders) in results pane.

        Args:
            folder (Folder): The folder to display contents for.
        """
        # Fetch folder contents using the shared helper method
        folders, playlists = self._fetch_folder_contents(folder)

        # Combine folders and playlists
        items = folders + playlists

        # Convert to ResultItems and display
        result = self.main_window.search_manager.search_result_to_model(items)
        self.main_window.populate_tree_results(result)

    def _download_albums_from_favorites_albums(
        self, media_items: list[Any], favorite_name: str
    ) -> None:
        """Download albums from favorite albums list.

        Args:
            media_items (list): List of favorite albums.
            favorite_name (str): Name of the favorites category for logging.
        """
        logger_gui.info(
            f"Queueing {len(media_items)} albums from favorites: {favorite_name}"
        )
        albums_dict: dict[str, Album] = {
            str(album.id): album
            for album in media_items
            if isinstance(album, Album) and album.id
        }
        self._queue_loaded_albums(albums_dict)
        logger_gui.info(
            f"✅ Successfully queued {len(albums_dict)} albums from favorites: {favorite_name}"
        )

    def _download_albums_from_favorites_artists(
        self, media_items: list[Any], favorite_name: str
    ) -> None:
        """Download albums from favorite artists list.

        Args:
            media_items (list): List of favorite artists.
            favorite_name (str): Name of the favorites category for logging.
        """
        logger_gui.info(f"Fetching albums from {len(media_items)} artists...")
        all_albums: dict[str, Album] = {}

        for artist in media_items:
            if isinstance(artist, Artist):
                try:
                    artist_albums = self._safe_tidal_call(
                        ITEMS_RESULTS_ALL,
                        self.main_window.tidal.session,
                        artist,
                    )
                    if artist_albums is None:
                        logger_gui.error(
                            f"Failed to fetch albums from artist: {artist.name}"
                        )
                        continue
                    for album in artist_albums:
                        if isinstance(album, Album) and album.id:
                            all_albums[str(album.id)] = album
                    logger_gui.debug(
                        f"Found {len(artist_albums)} albums from artist: {artist.name}"
                    )
                except Exception as e:
                    logger_gui.error(
                        f"Error getting albums from artist '{artist.name}': {e}"
                    )
                    continue

        if not all_albums:
            logger_gui.info("No albums found from favorite artists.")
            return

        logger_gui.info(
            f"Found {len(all_albums)} unique albums from favorite artists"
        )
        self._queue_loaded_albums(all_albums)
        logger_gui.info(
            f"✅ Successfully queued {len(all_albums)} albums from favorites: {favorite_name}"
        )

    def _download_albums_from_favorites_tracks(
        self, media_items: list[Any], favorite_name: str
    ) -> None:
        """Download albums from favorite tracks/videos/mixes list.

        Args:
            media_items (list): List of favorite tracks/videos/mixes.
            favorite_name (str): Name of the favorites category for logging.
        """
        logger_gui.info("Extracting albums from tracks...")
        album_ids = self._extract_album_ids_from_tracks(media_items)

        if not album_ids:
            logger_gui.info(f"No albums found in favorites: {favorite_name}")
            return

        logger_gui.info(
            f"Found {len(album_ids)} unique albums. Loading with rate limiting..."
        )

        # Load full album objects with rate limiting
        albums_dict = self._load_albums_with_rate_limiting(album_ids)

        if not albums_dict:
            logger_gui.error("Failed to load any albums from favorites.")
            return

        # Queue the albums for download
        self._queue_loaded_albums(albums_dict)
        logger_gui.info(
            f"✅ Successfully queued {len(albums_dict)} unique albums from favorites: {favorite_name}"
        )

    def search_populate_results(self, query: str, type_media: Any) -> None:
        """Populate the results tree with search results.

        Args:
            query (str): The search query.
            type_media (SearchTypes): The type of media to search for.
        """
        results: list[ResultItem] = self.main_window.search_manager.search(
            query, [type_media]
        )

        self.main_window.populate_tree_results(results)
