"""GUI data models for tidal-dl-ng.

These dataclasses carry data between the worker threads and the Qt GUI
layer: progress signal handles, search/result rows, status bar messages
and queued download items.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6 import QtCore
    from tidalapi.album import Album
    from tidalapi.artist import Artist
    from tidalapi.media import Quality, Track, Video
    from tidalapi.mix import Mix
    from tidalapi.playlist import Folder, Playlist

    from tidal_dl_ng.constants import QualityVideo

    MediaObject = Track | Video | Mix | Playlist | Folder | Album | Artist
else:
    MediaObject = object


@dataclass
class ProgressBars:
    """Signal instances used to report progress to the GUI.

    When PySide6 is available the fields are ``SignalInstance`` handles;
    otherwise they fall back to ``None`` placeholders so the module can
    be imported in headless environments.
    """

    if TYPE_CHECKING:
        item: QtCore.SignalInstance
        item_name: QtCore.SignalInstance
        list_item: QtCore.SignalInstance
        list_name: QtCore.SignalInstance
    else:
        item: object = None
        item_name: object = None
        list_item: object = None
        list_name: object = None


@dataclass
class ResultItem:
    """A single row in a search or listing results tree."""

    position: int
    """Zero-based position of the item in the result list."""

    artist: str
    """Display name of the artist (or collection owner)."""

    title: str
    """Title of the media item."""

    album: str
    """Name of the album the item belongs to (empty if none)."""

    duration_sec: int
    """Duration of the item in seconds."""

    obj: MediaObject
    """Underlying tidalapi media object for this row."""

    quality: str
    """Highest available audio/video quality label."""

    explicit: bool
    """Whether the item is flagged as explicit content."""

    date_user_added: str
    """ISO date the item was added to a user list (empty if none)."""

    date_release: str
    """ISO release date of the item."""


@dataclass
class StatusbarMessage:
    """A transient message shown in the application status bar."""

    message: str
    """Text to display in the status bar."""

    timeout: int = 0
    """Auto-hide timeout in milliseconds (0 = no timeout)."""


@dataclass
class QueueDownloadItem:
    """An entry in the download queue."""

    status: str
    """Current queue status (see ``QueueDownloadStatus``)."""

    name: str
    """Human-readable name of the queued item."""

    type_media: str
    """Media type discriminator (track, album, playlist, ...)."""

    quality_audio: Quality
    """Requested audio quality for the download."""

    quality_video: QualityVideo
    """Requested video quality for the download."""

    obj: MediaObject
    """Underlying tidalapi media object to download."""
