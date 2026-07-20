"""Search manager for the MainWindow GUI.

Handles TIDAL search queries, direct-link resolution, and conversion of
raw API results into :class:`ResultItem` rows for the results tree.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, cast

from PySide6 import QtCore
from requests.exceptions import RequestException
from tidalapi import Album, Artist, Mix, Playlist, Track, Video
from tidalapi.exceptions import TidalAPIError
from tidalapi.media import AudioMode
from tidalapi.playlist import Folder, UserPlaylist

from tidal_dl_ng.helper.tidal import (
    get_tidal_media_id,
    get_tidal_media_type,
    instantiate_media,
    name_builder_artist,
    name_builder_title,
    quality_audio_highest,
    search_results_all,
    url_ending_clean,
)
from tidal_dl_ng.logger import logger_gui
from tidal_dl_ng.model.gui_data import ResultItem
from tidal_dl_ng.runtime_trace import (
    RuntimeWatchdog,
    new_operation_id,
    trace_event,
)

if TYPE_CHECKING:
    from datetime import datetime

    from tidal_dl_ng.gui.main_window import MainWindow

    # Media type classes selectable in the search combo-box.
    SearchMediaType = type[Track | Video | Album | Artist | Playlist | Mix]

    # Concrete media objects returned by a search or direct link.
    SearchResultItem = (
        Track | Video | Album | Artist | Playlist | UserPlaylist | Mix | Folder
    )

# Exceptions that may surface during a search or direct-link resolution.
SearchError = (
    RequestException,
    TidalAPIError,
    ValueError,
    AttributeError,
    TypeError,
)


class SearchSignals(QtCore.QObject):
    """Signals for thread-safe UI updates during search."""

    results_ready = QtCore.Signal(list)
    search_started = QtCore.Signal()
    search_finished = QtCore.Signal()


class GuiSearchManager:
    """Manages the search GUI and logic."""

    # Attributes provided by the host window at runtime.
    main_window: MainWindow

    def __init__(self, main_window: MainWindow) -> None:
        """Initialize the search manager."""
        self.main_window: MainWindow = main_window

        # Initialize thread-safe signals.
        self.signals = SearchSignals()
        self.signals.results_ready.connect(
            self.main_window.populate_tree_results
        )
        self.signals.search_started.connect(self._on_search_started)
        self.signals.search_finished.connect(self._on_search_finished)

    def _on_search_started(self) -> None:
        """Handler to start spinner on UI thread."""
        self.main_window.s_spinner_start.emit(self.main_window.tr_results)

    def _on_search_finished(self) -> None:
        """Handler to stop spinner on UI thread."""
        self.main_window.s_spinner_stop.emit()

    def search_populate_results(
        self, query: str, type_media: SearchMediaType | None
    ) -> None:
        """Populate the results tree asynchronously to avoid freezing.

        Args:
            query: The raw search query or direct TIDAL link.
            type_media: The media type class selected in the UI.
        """
        self.main_window.thread_it(self._search_worker, query, type_media)

    def _search_worker(
        self, query: str, type_media: SearchMediaType | None
    ) -> None:
        """Background worker performing the search and updating the GUI."""
        op_id = new_operation_id("search")
        started_at = time.monotonic()
        watchdog = RuntimeWatchdog(
            operation="search",
            op_id=op_id,
            timeout_sec=30.0,
            check_interval_sec=10.0,
            context={
                "media_type": getattr(type_media, "__name__", str(type_media))
            },
        )
        watchdog.start()
        trace_event(
            "search",
            "start",
            expected=(
                "ui spinner start -> tidal lookup -> map results -> update ui"
            ),
            actual=f"query={query.strip()[:120]}",
            op_id=op_id,
        )

        self.signals.search_started.emit()
        try:
            watchdog.ping("search_api_begin")
            results = self.search(query, [type_media], op_id=op_id)
            watchdog.ping("search_api_done")

            trace_event(
                "search",
                "results_ready",
                expected="results emitted to GUI",
                actual=f"count={len(results)}",
                op_id=op_id,
            )
            self.signals.results_ready.emit(results)
        except SearchError as e:
            logger_gui.error("Search failed: %s", e, exc_info=True)
            trace_event(
                "search",
                "failed",
                expected="search returns results",
                actual=f"error={e}",
                op_id=op_id,
            )
        finally:
            self.signals.search_finished.emit()
            watchdog.stop("search_finished")
            elapsed = time.monotonic() - started_at
            trace_event(
                "search",
                "end",
                expected="spinner stopped and worker exits",
                actual=f"elapsed_sec={elapsed:.3f}",
                op_id=op_id,
            )

    def search(
        self,
        query: str,
        types_media: list[SearchMediaType | None],
        op_id: str | None = None,
    ) -> list[ResultItem]:
        """Perform a search and return a list of ResultItems.

        Args:
            query: The search query or direct TIDAL link.
            types_media: The media type classes to search for.
            op_id: Optional tracing operation identifier.

        Returns:
            The mapped search results.
        """
        query_clean: str = query.strip()
        result_search: dict[str, list[SearchResultItem]] = {}

        trace_event(
            "search",
            "resolve_input",
            expected="detect direct link or API query",
            actual=f"is_direct_link={'http' in query_clean}",
            op_id=op_id,
            context={
                "types_media": [
                    getattr(t, "__name__", str(t)) for t in types_media
                ]
            },
        )

        # A direct link skips the search API and builds the object
        # directly from the URL.
        if "http" in query_clean:
            query_clean = url_ending_clean(query_clean)
            media_type = get_tidal_media_type(query_clean)
            item_id = get_tidal_media_id(query_clean)

            # get_tidal_media_type may return False for unknown links.
            if not isinstance(media_type, bool):
                try:
                    media = instantiate_media(
                        self.main_window.tidal.session,
                        media_type,
                        item_id,
                    )
                    if media:
                        result_search = {"direct": [media]}
                        trace_event(
                            "search",
                            "direct_link_resolved",
                            expected="single direct object returned",
                            actual=f"media_type={media_type}",
                            op_id=op_id,
                        )
                except SearchError as e:
                    logger_gui.error(
                        "Media not found (ID: %s). "
                        "Maybe it is not available anymore. "
                        "Error: %s",
                        item_id,
                        e,
                    )
                    trace_event(
                        "search",
                        "direct_link_failed",
                        expected="direct object instantiation succeeds",
                        actual=f"error={e}",
                        op_id=op_id,
                    )
        else:
            try:
                result_search = cast(
                    "dict[str, list[SearchResultItem]]",
                    search_results_all(
                        session=self.main_window.tidal.session,
                        needle=query_clean,
                        types_media=types_media,
                    ),
                )
                trace_event(
                    "search",
                    "api_search_done",
                    expected="tidal search endpoint responds",
                    actual=f"buckets={len(result_search)}",
                    op_id=op_id,
                )
            except SearchError as e:
                logger_gui.error("API Search failed: %s", e)
                trace_event(
                    "search",
                    "api_search_failed",
                    expected="tidal search endpoint responds",
                    actual=f"error={e}",
                    op_id=op_id,
                )

        result: list[ResultItem] = []

        for l_media in result_search.values():
            result.extend(self.search_result_to_model(l_media))

        trace_event(
            "search",
            "map_results_done",
            expected="search results mapped into ResultItem list",
            actual=f"mapped_count={len(result)}",
            op_id=op_id,
        )

        return result

    def search_result_to_model(
        self, items: list[SearchResultItem]
    ) -> list[ResultItem]:
        """Convert search results to ResultItem models.

        Args:
            items: The raw search result items.

        Returns:
            The converted ResultItem models.
        """
        result: list[ResultItem] = []

        for idx, item in enumerate(items):
            result_item = self._to_result_item(idx, item)
            if result_item is not None:
                result.append(result_item)

        return result

    def _to_result_item(
        self, idx: int, item: SearchResultItem | None
    ) -> ResultItem | None:
        """Convert a single item to a ResultItem, or None if invalid."""
        if not item or getattr(item, "available", None) is False:
            return None

        # Prepare common data shared across media types.
        explicit = (
            " 🅴"
            if isinstance(item, (Track, Video, Album))
            and getattr(item, "explicit", False)
            else ""
        )
        user_date: datetime | None = getattr(item, "user_date_added", None)
        date_user_added = (
            user_date.strftime("%Y-%m-%d_%H:%M") if user_date else ""
        )
        date_release = self._get_date_release(item)

        # Utilize Python 3.10+ structural pattern matching.
        result_item: ResultItem | None = None
        match item:
            case Track():
                result_item = self._result_item_from_track(
                    idx, item, explicit, date_user_added, date_release
                )
            case Video():
                result_item = self._result_item_from_video(
                    idx, item, explicit, date_user_added, date_release
                )
            case Playlist():
                result_item = self._result_item_from_playlist(
                    idx, item, date_user_added, date_release
                )
            case Album():
                result_item = self._result_item_from_album(
                    idx, item, explicit, date_user_added, date_release
                )
            case Mix():
                result_item = self._result_item_from_mix(
                    idx, item, date_user_added, date_release
                )
            case Artist():
                result_item = self._result_item_from_artist(
                    idx, item, date_user_added, date_release
                )
            case Folder():
                result_item = self._result_item_from_folder(
                    idx, item, date_user_added
                )

        return result_item

    def _get_date_release(self, item: SearchResultItem | None) -> str:
        """Return the formatted release date for an item.

        Args:
            item: The media object to inspect.

        Returns:
            The ISO release date string, or empty when unavailable.
        """
        album = getattr(item, "album", None)
        if album and getattr(album, "release_date", None):
            return album.release_date.strftime("%Y-%m-%d_%H:%M")

        release_date = getattr(item, "release_date", None)
        if release_date:
            return release_date.strftime("%Y-%m-%d_%H:%M")

        return ""

    def _result_item_from_track(
        self,
        idx: int,
        item: Track,
        explicit: str,
        date_user_added: str,
        date_release: str,
    ) -> ResultItem:
        """Create a ResultItem from a Track."""
        final_quality = str(quality_audio_highest(item))
        audio_modes = getattr(item, "audio_modes", [])

        if audio_modes and (
            AudioMode.dolby_atmos.value in audio_modes
            or "DOLBY_ATMOS" in audio_modes
        ):
            final_quality = f"{final_quality} / Dolby Atmos"

        album = getattr(item, "album", None)
        return ResultItem(
            position=idx,
            artist=name_builder_artist(item),
            title=f"{name_builder_title(item)}{explicit}",
            album=album.name if album else "",
            duration_sec=getattr(item, "duration", -1),
            obj=item,
            quality=final_quality,
            explicit=getattr(item, "explicit", False),
            date_user_added=date_user_added,
            date_release=date_release,
        )

    def _result_item_from_video(
        self,
        idx: int,
        item: Video,
        explicit: str,
        date_user_added: str,
        date_release: str,
    ) -> ResultItem:
        """Create a ResultItem from a Video."""
        album = getattr(item, "album", None)
        return ResultItem(
            position=idx,
            artist=name_builder_artist(item),
            title=f"{name_builder_title(item)}{explicit}",
            album=album.name if album else "",
            duration_sec=getattr(item, "duration", -1),
            obj=item,
            quality=str(getattr(item, "video_quality", "")),
            explicit=getattr(item, "explicit", False),
            date_user_added=date_user_added,
            date_release=date_release,
        )

    def _result_item_from_playlist(
        self,
        idx: int,
        item: Playlist | UserPlaylist,
        date_user_added: str,
        date_release: str,
    ) -> ResultItem:
        """Create a ResultItem from a Playlist."""
        promoted_artists = getattr(item, "promoted_artists", None)
        artist_str = (
            ", ".join(artist.name for artist in promoted_artists)
            if promoted_artists
            else ""
        )

        return ResultItem(
            position=idx,
            artist=artist_str,
            title=getattr(item, "name", ""),
            album="",
            duration_sec=getattr(item, "duration", -1),
            obj=item,
            quality="",
            explicit=False,
            date_user_added=date_user_added,
            date_release=date_release,
        )

    def _result_item_from_album(
        self,
        idx: int,
        item: Album,
        explicit: str,
        date_user_added: str,
        date_release: str,
    ) -> ResultItem:
        """Create a ResultItem from an Album."""
        return ResultItem(
            position=idx,
            artist=name_builder_artist(item),
            title="",
            album=f"{getattr(item, 'name', '')}{explicit}",
            duration_sec=getattr(item, "duration", -1),
            obj=item,
            quality=str(quality_audio_highest(item)),
            explicit=getattr(item, "explicit", False),
            date_user_added=date_user_added,
            date_release=date_release,
        )

    def _result_item_from_mix(
        self,
        idx: int,
        item: Mix,
        date_user_added: str,
        date_release: str,
    ) -> ResultItem:
        """Create a ResultItem from a Mix."""
        return ResultItem(
            position=idx,
            artist=getattr(item, "sub_title", ""),
            title=getattr(item, "title", ""),
            album="",
            duration_sec=-1,  # Total duration could be summed later.
            obj=item,
            quality="",
            explicit=False,
            date_user_added=date_user_added,
            date_release=date_release,
        )

    def _result_item_from_artist(
        self,
        idx: int,
        item: Artist,
        date_user_added: str,
        date_release: str,
    ) -> ResultItem:
        """Create a ResultItem from an Artist."""
        return ResultItem(
            position=idx,
            artist=getattr(item, "name", ""),
            title="",
            album="",
            duration_sec=-1,
            obj=item,
            quality="",
            explicit=False,
            date_user_added=date_user_added,
            date_release=date_release,
        )

    def _result_item_from_folder(
        self,
        idx: int,
        item: Folder,
        date_user_added: str,
    ) -> ResultItem:
        """Create a ResultItem from a Folder."""
        total_items: int = getattr(item, "total_number_of_items", 0)
        return ResultItem(
            position=idx,
            artist="",
            title=f"📁 {getattr(item, 'name', '')} ({total_items} items)",
            album="",
            duration_sec=-1,
            obj=item,
            quality="",
            explicit=False,
            date_user_added=date_user_added,
            date_release="",
        )
