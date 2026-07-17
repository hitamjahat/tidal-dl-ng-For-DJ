import urllib.parse
import time
from typing import TYPE_CHECKING, Any

from PySide6 import QtCore
from tidalapi import Album, Artist, Mix, Playlist, Track, Video
from tidalapi.media import AudioMode
from tidalapi.playlist import Folder, UserPlaylist
from tidalapi.session import SearchTypes

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
from tidal_dl_ng.runtime_trace import RuntimeWatchdog, new_operation_id, trace_event

if TYPE_CHECKING:
    from tidal_dl_ng.gui.main_window import MainWindow


class SearchSignals(QtCore.QObject):
    """Signals for thread-safe UI updates during search."""
    results_ready = QtCore.Signal(list)
    search_started = QtCore.Signal()
    search_finished = QtCore.Signal()


class GuiSearchManager:
    """Manages the search GUI and logic."""

    def __init__(self, main_window: "MainWindow") -> None:
        """Initialize the search manager."""
        self.main_window: "MainWindow" = main_window

        # Initialize thread-safe signals
        self.signals = SearchSignals()
        self.signals.results_ready.connect(self.main_window.populate_tree_results)
        self.signals.search_started.connect(self._on_search_started)
        self.signals.search_finished.connect(self._on_search_finished)

    def _on_search_started(self) -> None:
        """Handler to start spinner on UI thread."""
        self.main_window.s_spinner_start.emit(self.main_window.tr_results)

    def _on_search_finished(self) -> None:
        """Handler to stop spinner on UI thread."""
        self.main_window.s_spinner_stop.emit()

    def search_populate_results(self, query: str, type_media: Any) -> None:
        """Populate the results tree with search results asynchronously to prevent freezing."""
        self.main_window.thread_it(self._search_worker, query, type_media)

    def _search_worker(self, query: str, type_media: Any) -> None:
        """Background worker to perform search and update the GUI."""
        op_id = new_operation_id("search")
        started_at = time.monotonic()
        watchdog = RuntimeWatchdog(
            operation="search",
            op_id=op_id,
            timeout_sec=30.0,
            check_interval_sec=10.0,
            context={"media_type": getattr(type_media, "__name__", str(type_media))},
        )
        watchdog.start()
        trace_event(
            "search",
            "start",
            expected="ui spinner start -> tidal lookup -> map results -> update ui",
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
        except Exception as e:
            logger_gui.error(f"Search failed: {e}", exc_info=True)
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

    def search(self, query: str, types_media: list[Any], op_id: str | None = None) -> list[ResultItem]:
        """Perform a search and return a list of ResultItems.

        Args:
            query (str): The search query.
            types_media (list[Any]): The types of media to search for.

        Returns:
            list[ResultItem]: The search results.
        """
        query_clean: str = query.strip()
        result_search: dict[str, list[SearchTypes]] = {}

        trace_event(
            "search",
            "resolve_input",
            expected="detect direct link or API query",
            actual=f"is_direct_link={'http' in query_clean}",
            op_id=op_id,
            context={"types_media": [getattr(t, "__name__", str(t)) for t in types_media]},
        )

        # If a direct link was searched for, skip search and create the object from the link directly.
        if "http" in query_clean:
            query_clean = url_ending_clean(query_clean)
            media_type = get_tidal_media_type(query_clean)
            item_id = get_tidal_media_id(query_clean)

            try:
                media = instantiate_media(self.main_window.tidal.session, media_type, item_id)
                if media:
                    result_search = {"direct": [media]}
                    trace_event(
                        "search",
                        "direct_link_resolved",
                        expected="single direct object returned",
                        actual=f"media_type={media_type}",
                        op_id=op_id,
                    )
            except Exception as e:
                logger_gui.error(f"Media not found (ID: {item_id}). Maybe it is not available anymore. Error: {e}")
                trace_event(
                    "search",
                    "direct_link_failed",
                    expected="direct object instantiation succeeds",
                    actual=f"error={e}",
                    op_id=op_id,
                )
        else:
            try:
                result_search = search_results_all(
                    session=self.main_window.tidal.session, needle=query_clean, types_media=types_media
                )
                trace_event(
                    "search",
                    "api_search_done",
                    expected="tidal search endpoint responds",
                    actual=f"buckets={len(result_search)}",
                    op_id=op_id,
                )
            except Exception as e:
                logger_gui.error(f"API Search failed: {e}")
                trace_event(
                    "search",
                    "api_search_failed",
                    expected="tidal search endpoint responds",
                    actual=f"error={e}",
                    op_id=op_id,
                )

        result: list[ResultItem] = []

        for _media_type, l_media in result_search.items():
            if isinstance(l_media, list):
                result.extend(self.search_result_to_model(l_media))

        trace_event(
            "search",
            "map_results_done",
            expected="search results mapped into ResultItem list",
            actual=f"mapped_count={len(result)}",
            op_id=op_id,
        )

        return result

    def search_result_to_model(self, items: list[SearchTypes]) -> list[ResultItem]:
        """Convert search results to ResultItem models.

        Args:
            items (list[SearchTypes]): List of search result items.

        Returns:
            list[ResultItem]: List of ResultItem models.
        """
        result: list[ResultItem] = []

        for idx, item in enumerate(items):
            result_item = self._to_result_item(idx, item)
            if result_item is not None:
                result.append(result_item)

        return result

    def _to_result_item(self, idx: int, item: Any) -> ResultItem | None:
        """Helper to convert a single item to ResultItem, or None if not valid."""
        if not item or (hasattr(item, "available") and item.available is False):
            return None

        # Prepare common data
        explicit = " 🅴" if isinstance(item, (Track, Video, Album)) and getattr(item, "explicit", False) else ""
        date_user_added = (
            item.user_date_added.strftime("%Y-%m-%d_%H:%M") if getattr(item, "user_date_added", None) else ""
        )
        date_release = self._get_date_release(item)

        # Utilize Python 3.10+ Pattern Matching
        match item:
            case Track():
                return self._result_item_from_track(idx, item, explicit, date_user_added, date_release)
            case Video():
                return self._result_item_from_video(idx, item, explicit, date_user_added, date_release)
            case Playlist() | UserPlaylist():
                return self._result_item_from_playlist(idx, item, date_user_added, date_release)
            case Album():
                return self._result_item_from_album(idx, item, explicit, date_user_added, date_release)
            case Mix():
                return self._result_item_from_mix(idx, item, date_user_added, date_release)
            case Artist():
                return self._result_item_from_artist(idx, item, date_user_added, date_release)
            case Folder():
                return self._result_item_from_folder(idx, item, date_user_added)
            case _:
                return None

    def _get_date_release(self, item: Any) -> str:
        """Get the release date string for an item.

        Args:
            item: The item to extract the release date from.

        Returns:
            str: The formatted release date or empty string.
        """
        if hasattr(item, "album") and getattr(item, "album", None) and getattr(item.album, "release_date", None):
            return item.album.release_date.strftime("%Y-%m-%d_%H:%M")

        if hasattr(item, "release_date") and getattr(item, "release_date", None):
            return item.release_date.strftime("%Y-%m-%d_%H:%M")

        return ""

    def _result_item_from_track(
        self, idx: int, item: Track, explicit: str, date_user_added: str, date_release: str
    ) -> ResultItem:
        """Create a ResultItem from a Track."""
        final_quality = str(quality_audio_highest(item))
        audio_modes = getattr(item, "audio_modes", [])

        if audio_modes:
            dolby_value = getattr(AudioMode, "dolby_atmos", "DOLBY_ATMOS")
            dolby_value_str = getattr(dolby_value, "value", str(dolby_value))
            if dolby_value_str in audio_modes or "DOLBY_ATMOS" in audio_modes:
                final_quality = f"{final_quality} / Dolby Atmos"

        return ResultItem(
            position=idx,
            artist=name_builder_artist(item),
            title=f"{name_builder_title(item)}{explicit}",
            album=item.album.name if getattr(item, "album", None) else "",
            duration_sec=getattr(item, "duration", -1),
            obj=item,
            quality=final_quality,
            explicit=getattr(item, "explicit", False),
            date_user_added=date_user_added,
            date_release=date_release,
        )

    def _result_item_from_video(
        self, idx: int, item: Video, explicit: str, date_user_added: str, date_release: str
    ) -> ResultItem:
        """Create a ResultItem from a Video."""
        return ResultItem(
            position=idx,
            artist=name_builder_artist(item),
            title=f"{name_builder_title(item)}{explicit}",
            album=item.album.name if getattr(item, "album", None) else "",
            duration_sec=getattr(item, "duration", -1),
            obj=item,
            quality=str(getattr(item, "video_quality", "")),
            explicit=getattr(item, "explicit", False),
            date_user_added=date_user_added,
            date_release=date_release,
        )

    def _result_item_from_playlist(
        self, idx: int, item: Playlist | UserPlaylist, date_user_added: str, date_release: str
    ) -> ResultItem:
        """Create a ResultItem from a Playlist."""
        promoted_artists = getattr(item, "promoted_artists", None)
        artist_str = ", ".join(artist.name for artist in promoted_artists) if promoted_artists else ""

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
        self, idx: int, item: Album, explicit: str, date_user_added: str, date_release: str
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
        self, idx: int, item: Mix, date_user_added: str, date_release: str
    ) -> ResultItem:
        """Create a ResultItem from a Mix."""
        return ResultItem(
            position=idx,
            artist=getattr(item, "sub_title", ""),
            title=getattr(item, "title", ""),
            album="",
            duration_sec=-1,  # Calculate total duration could be added later
            obj=item,
            quality="",
            explicit=False,
            date_user_added=date_user_added,
            date_release=date_release,
        )

    def _result_item_from_artist(
        self, idx: int, item: Artist, date_user_added: str, date_release: str
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
        self, idx: int, item: Folder, date_user_added: str
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
