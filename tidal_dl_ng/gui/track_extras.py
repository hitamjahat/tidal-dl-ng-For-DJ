"""Track extras mixin for MainWindow.

Handles track extras caching and retrieval.
"""

from __future__ import annotations

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
    from collections.abc import Callable, Mapping, Sequence

    from tidal_dl_ng.cache import TrackExtrasCache
    from tidal_dl_ng.gui.covers import CoverManager

    # A single track's extra metadata mapping.
    TrackExtras = Mapping[str, object]
    # Callback invoked when extras are ready (or failed) for a track.
    TrackExtrasCallback = Callable[[str, "TrackExtras | None"], None]


class TrackExtrasMixin:
    """Mixin containing track extras management methods."""

    # Attributes provided by MainWindow at runtime.
    tidal: Any
    threadpool: Any
    track_extras_cache: TrackExtrasCache
    _pending_extras_workers: dict[str, Worker]
    _track_extras_callbacks: dict[str, TrackExtrasCallback]
    cover_manager: CoverManager

    # Signals from MainWindow.
    s_track_extras_ready: Any
    s_invoke_callback: Any

    def get_track_extras(
        self,
        track_id: str,
        callback: TrackExtrasCallback | None = None,
    ) -> TrackExtras | None:
        """Return cached extras for a track or start async fetch.

        Args:
            track_id: Identifier of the track to fetch extras for.
            callback: Optional callback invoked on the main thread once
                extras are available (or ``None`` on failure).

        Returns:
            The cached extras when present, otherwise ``None`` while an
            asynchronous fetch is started.
        """
        cached = self.track_extras_cache.get(track_id)
        if cached is not None:
            return cached

        # Chain callbacks when several components request the same track
        # simultaneously so every requester is notified on completion.
        if callback:
            existing_callback = self._track_extras_callbacks.get(track_id)
            if existing_callback:
                old_callback = existing_callback
                new_callback = callback

                def chained_callback(
                    t_id: str,
                    ext: TrackExtras | None,
                ) -> None:
                    old_callback(t_id, ext)
                    new_callback(t_id, ext)

                self._track_extras_callbacks[track_id] = chained_callback
            else:
                self._track_extras_callbacks[track_id] = callback

        # Avoid spawning a second worker for an in-flight track.
        if track_id in self._pending_extras_workers:
            return None

        def worker() -> None:
            extras: TrackExtras | None = None
            try:
                track_json, album_json = fetch_raw_track_and_album(
                    self.tidal.session, track_id
                )
                extras = parse_track_and_album_extras(track_json, album_json)
                extras = self._decorate_extras(extras)
                self.track_extras_cache.set(track_id, extras)
            except (KeyError, TypeError, ValueError, AttributeError) as error:
                logger_gui.error(
                    "Failed to fetch track extras for %s: %s",
                    track_id,
                    error,
                    exc_info=True,
                )
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
    def _on_invoke_callback(
        self,
        track_id: str,
        extras: TrackExtras | None,
    ) -> None:
        """Invoke the stored callback for a track in the main thread."""
        callback = self._track_extras_callbacks.pop(track_id, None)
        if callback:
            try:
                callback(track_id, extras)
            except (KeyError, TypeError, ValueError, AttributeError) as error:
                logger_gui.error(
                    "Error in track extras callback for %s: %s",
                    track_id,
                    error,
                    exc_info=True,
                )

    def _decorate_extras(
        self,
        extras: TrackExtras | None,
    ) -> dict[str, object]:
        """Add formatted string fields to an extras mapping.

        Args:
            extras: The raw extras mapping, or ``None`` when unavailable.

        Returns:
            A new dict with derived display fields added.
        """
        if not extras:
            return {}

        result: dict[str, object] = dict(extras)
        genres = cast("list[str]", result.get("genres", []))
        result["genres_text"] = ", ".join(genres)

        roles: Sequence[tuple[str, str]] = [
            ("producer", "producers_text"),
            ("composer", "composers_text"),
            ("lyricist", "lyricists_text"),
        ]
        contributors = cast(
            "dict[str, list[str]] | None",
            result.get("contributors_by_role"),
        )
        for role, key in roles:
            result[key] = extract_contributor_names(contributors, role)

        return result

    def preload_covers_for_playlist(self, items: list[Any]) -> None:
        """Preload cover pixmaps for a list of tracks in background."""
        if self.cover_manager:
            self.cover_manager.preload_covers_for_playlist(items)
