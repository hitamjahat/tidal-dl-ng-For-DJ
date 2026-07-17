"""Track extras mixin for MainWindow.

Handles track extras caching and retrieval.
"""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

from PySide6 import QtCore

from tidal_dl_ng.helper.tidal import (
    extract_contributor_names,
    fetch_raw_track_and_album,
    parse_track_and_album_extras,
)
from tidal_dl_ng.logger import logger_gui
from tidal_dl_ng.worker import Worker

if TYPE_CHECKING:
    from tidal_dl_ng.gui.main_window import MainWindow


class TrackExtrasMixin:
    """Mixin containing track extras management methods."""

    # Attributes provided by MainWindow at runtime.
    tidal: Any
    threadpool: Any
    track_extras_cache: Any
    _pending_extras_workers: dict[str, Worker]
    _track_extras_callbacks: dict[str, Callable[[str, dict[str, Any] | None], None]]
    cover_manager: Any

    # Signals from MainWindow
    s_track_extras_ready: Any
    s_invoke_callback: Any

    def get_track_extras(
        self, track_id: str, callback: Callable[[str, dict[str, Any] | None], None] | None = None
    ) -> dict[str, Any] | None:
        """Return cached extras for a track or start async fetch."""
        cached = self.track_extras_cache.get(track_id)
        if cached is not None:
            return cast(dict[str, Any], cached)

        # Chain callbacks if multiple components request extras for the same track simultaneously
        if callback:
            existing_callback = self._track_extras_callbacks.get(track_id)
            if existing_callback:

                def chained_callback(
                    t_id: str, ext: dict[str, Any] | None, cb_old: Any = existing_callback, cb_new: Any = callback
                ) -> None:
                    cb_old(t_id, ext)
                    cb_new(t_id, ext)

                self._track_extras_callbacks[track_id] = chained_callback
            else:
                self._track_extras_callbacks[track_id] = callback

        # If a worker is already busy fetching this track, don't spawn another one
        if track_id in self._pending_extras_workers:
            return None

        def worker() -> None:
            extras: dict[str, Any] | None = None
            try:
                track_json, album_json = fetch_raw_track_and_album(self.tidal.session, track_id)
                extras = parse_track_and_album_extras(track_json, album_json)
                extras = self._decorate_extras(extras)
                self.track_extras_cache.set(track_id, extras)
            except Exception as e:
                logger_gui.error(f"Failed to fetch track extras for {track_id}: {e}", exc_info=True)
                extras = None
            finally:
                self._pending_extras_workers.pop(track_id, None)
                self.s_track_extras_ready.emit(track_id, extras)
                self.s_invoke_callback.emit(track_id, extras)

        worker_obj = Worker(worker)
        self._pending_extras_workers[track_id] = worker_obj
        self.threadpool.start(worker_obj)
        return None

    @QtCore.Slot(str, object)
    def _on_invoke_callback(self, track_id: str, extras: dict[str, Any] | None) -> None:
        """Invoke the stored callback for a track in the main thread."""
        callback = self._track_extras_callbacks.pop(track_id, None)
        if callback:
            try:
                callback(track_id, extras)
            except Exception as e:
                logger_gui.error(f"Error in track extras callback for {track_id}: {e}", exc_info=True)

    def _decorate_extras(self, extras: dict[str, Any] | None) -> dict[str, Any]:
        """Add formatted string fields to extras dict."""
        if not extras:
            return {}

        result = dict(extras)
        result["genres_text"] = ", ".join(result.get("genres", []))

        for role, key in [
            ("producer", "producers_text"),
            ("composer", "composers_text"),
            ("lyricist", "lyricists_text"),
        ]:
            result[key] = extract_contributor_names(result.get("contributors_by_role"), role)

        return result

    def preload_covers_for_playlist(self, items: list[Any]) -> None:
        """Preload cover pixmaps for a list of tracks in background."""
        if self.cover_manager:
            self.cover_manager.preload_covers_for_playlist(items)
