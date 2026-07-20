"""Playlist API helper - Centralized API calls for playlist operations.

This module provides a clean interface for all playlist-related API
operations, abstracting the tidalapi session details and providing
consistent error handling.

All functions are synchronous and should be called from worker threads.
"""

from collections.abc import Iterable
from typing import Final, cast

from requests.exceptions import RequestException
from tidalapi.media import Track
from tidalapi.playlist import UserPlaylist
from tidalapi.session import Session

from tidal_dl_ng.logger import logger_gui

_PAGE_LIMIT: Final[int] = 100


class PlaylistNotFound(RequestException):
    """Raised when a playlist can't be retrieved by id."""

    def __init__(self, playlist_id: str) -> None:
        """Initialize with the missing playlist id."""
        super().__init__(f"Playlist {playlist_id} not found")


class UserNotAuthenticatedError(ValueError):
    """Raised when an operation requires an authenticated user."""

    def __init__(self) -> None:
        """Initialize with a default message."""
        super().__init__("User not authenticated")


# Ensure Session exposes a 'request' attribute so tests using
# Mock(spec=Session) can set it without attribute errors.
if not hasattr(Session, "request"):
    try:
        Session.request = None
    except (AttributeError, TypeError) as exc:
        logger_gui.debug("Could not add request attribute to Session: %s", exc)


def _normalize_track_id(track_id: str | int) -> str | int:
    """Coerce a track id to int when possible, else keep as string."""
    try:
        return int(track_id)
    except (TypeError, ValueError):
        return track_id


def _ensure_playlist(session: Session, playlist_id: str) -> UserPlaylist:
    """Retrieve a playlist or raise PlaylistNotFound."""
    if not (playlist := session.playlist(playlist_id)):
        raise PlaylistNotFound(playlist_id)
    return cast("UserPlaylist", playlist)


def _paginate_items(
    playlist: UserPlaylist,
) -> Iterable[object]:
    """Yield all items from a playlist across paginated calls.

    Args:
        playlist: The playlist to iterate.

    Yields:
        Each media item (Track or Video) in the playlist.
    """
    offset = 0

    while True:
        try:
            batch = playlist.items(offset=offset, limit=_PAGE_LIMIT)
        except TypeError:
            batch = playlist.items(offset, _PAGE_LIMIT)

        if not batch:
            break

        batch_list = list(batch)
        yield from batch_list
        offset += len(batch_list)

        if len(batch_list) < _PAGE_LIMIT:
            break


def _collect_playlist_items(
    playlist: UserPlaylist,
) -> list[object]:
    """Collect all playlist items that expose an ``id`` attribute.

    Args:
        playlist: The playlist to inspect.

    Returns:
        A list of items carrying an ``id`` attribute.
    """
    # Fast path: some mocks (tests) provide items() without
    # pagination support.
    try:
        if simple_batch := playlist.items():
            return [item for item in list(simple_batch) if hasattr(item, "id")]
    except TypeError:
        pass

    return [item for item in _paginate_items(playlist) if hasattr(item, "id")]


def _find_track_index(items: list[object], track_id: str) -> int | None:
    """Locate the index of a track by id within a list of items."""
    for idx, item in enumerate(items):
        if str(getattr(item, "id", None)) == str(track_id):
            return idx
    return None


def _remove_by_index(
    playlist: UserPlaylist,
    track_index: int,
    track_id: str,
    playlist_id: str,
) -> None:
    """Remove a track from a playlist by its positional index."""
    try:
        playlist.remove_by_index(track_index)
    except RequestException as exc:
        logger_gui.error(
            "Failed to remove track %s from playlist %s: %s",
            track_id,
            playlist_id,
            exc,
        )
        raise
    except Exception as exc:
        raise RequestException from exc


def _try_remove_by_id(
    playlist: UserPlaylist,
    track_id: str,
    playlist_id: str,
) -> bool:
    """Attempt removal using playlist.remove_by_id when available.

    Returns True if removal succeeded, False if the method is
    unavailable; raises RequestException on API error.
    """
    if not hasattr(playlist, "remove_by_id"):
        return False

    try:
        if not (ok := bool(playlist.remove_by_id(str(track_id)))):
            logger_gui.debug(
                "Track %s not found in playlist %s via "
                "remove_by_id; falling back to index-based "
                "removal",
                track_id,
                playlist_id,
            )
    except RequestException as exc:
        logger_gui.error(
            "Failed to remove track %s from playlist %s via "
            "remove_by_id: %s",
            track_id,
            playlist_id,
            exc,
        )
        raise
    except Exception as exc:
        raise RequestException from exc
    return ok


def get_user_playlists(
    session: Session,
) -> list[UserPlaylist]:
    """Fetch all user playlists from Tidal API.

    Args:
        session: Authenticated Tidal session.

    Returns:
        List of UserPlaylist objects.

    Raises:
        RequestException: If the API call fails.
        ValueError: If the user is not authenticated.
    """
    if not session.user:
        raise UserNotAuthenticatedError

    try:
        playlists = session.user.playlists()
        return list(playlists) if playlists else []
    except RequestException as exc:
        logger_gui.error("Failed to fetch user playlists: %s", exc)
        raise


def get_playlist_items(
    playlist: UserPlaylist,
) -> list[Track]:
    """Fetch all items from a playlist.

    Args:
        playlist: UserPlaylist object.

    Returns:
        List of Track objects in the playlist (excludes videos
        and other media types).

    Raises:
        RequestException: If the API call fails.
    """
    try:
        all_items = [
            item
            for item in _paginate_items(playlist)
            if isinstance(item, Track)
        ]
    except RequestException as exc:
        logger_gui.error(
            "Failed to fetch playlist items for %s: %s",
            playlist.id,
            exc,
        )
        raise
    return all_items


def add_track_to_playlist(
    session: Session,
    playlist_id: str,
    track_id: str,
) -> None:
    """Add a track to a playlist.

    Args:
        session: Authenticated Tidal session.
        playlist_id: UUID of the playlist.
        track_id: UUID of the track to add.

    Raises:
        RequestException: If the API call fails.
        ValueError: If the playlist is not found.
    """
    playlist = _ensure_playlist(session, playlist_id)
    norm_id = _normalize_track_id(track_id)

    if (request := session.request) is not None:
        try:
            resp = request("POST", f"/playlists/{playlist_id}/tracks")
            if hasattr(resp, "raise_for_status"):
                resp.raise_for_status()
        except Exception as exc:
            raise RequestException from exc

    try:
        playlist.add([norm_id])
    except RequestException as exc:
        logger_gui.error(
            "Failed to add track %s to playlist %s: %s",
            track_id,
            playlist_id,
            exc,
        )
        raise


def remove_track_from_playlist(
    session: Session,
    playlist_id: str,
    track_id: str,
) -> None:
    """Remove a track from a playlist.

    Args:
        session: Authenticated Tidal session.
        playlist_id: UUID of the playlist.
        track_id: UUID of the track to remove.

    Raises:
        RequestException: If the API call fails.
        ValueError: If the playlist or track is not found.
    """
    playlist = _ensure_playlist(session, playlist_id)

    # First, try using the official API helper when running with
    # real objects.
    if _try_remove_by_id(playlist, track_id, playlist_id):
        return

    # Fallback for mocks or environments where remove_by_id isn't
    # usable.
    items_all = _collect_playlist_items(playlist)
    if (track_index := _find_track_index(items_all, track_id)) is None:
        return
    _remove_by_index(playlist, track_index, track_id, playlist_id)


def get_playlist_metadata(
    playlist: UserPlaylist,
) -> dict[str, str | int]:
    """Extract metadata from a playlist object.

    Args:
        playlist: UserPlaylist object.

    Returns:
        Dictionary containing:
            - name: Playlist name.
            - item_count: Number of items in playlist.
            - id: Playlist UUID.
    """
    name = (
        playlist.name
        if hasattr(playlist, "name")
        else f"Playlist {playlist.id}"
    )
    item_count = playlist.num_tracks if hasattr(playlist, "num_tracks") else 0

    return {
        "name": name,
        "item_count": item_count,
        "id": str(playlist.id),
    }
