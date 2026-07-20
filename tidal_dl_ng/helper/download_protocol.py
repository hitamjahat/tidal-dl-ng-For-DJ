"""Protocol describing the shared surface used by Download mixins.

The `Download` class is split across several mixins
(`MetadataWriterMixin`, `CollectionDownloadMixin`). Those mixins access
attributes and methods that are only defined on the concrete `Download`
class. To give pyright (Pylance) a precise type for ``self`` inside the
mixins without resorting to ``# type: ignore`` comments, this protocol
declares the common surface that every mixin relies on.
"""

import logging
import pathlib
from typing import Protocol

from tidalapi.album import Album
from tidalapi.media import Stream, Track, Video
from tidalapi.mix import Mix
from tidalapi.playlist import Playlist, UserPlaylist
from tidalapi.session import Session

from tidal_dl_ng.config import Settings, Tidal
from tidal_dl_ng.constants import MediaType
from tidal_dl_ng.history import HistoryService
from tidal_dl_ng.model.downloader import (
    DownloadParams,
    DownloadRuntime,
    ItemRequest,
)

# Media types that can be downloaded or prepared by the Download class.
DownloadMedia = Track | Video | Album | Playlist | UserPlaylist | Mix


class DownloadProtocol(Protocol):
    """Structural type for the shared Download surface."""

    settings: Settings
    tidal: Tidal
    session: Session
    fn_logger: logging.Logger
    params: DownloadParams
    runtime: DownloadRuntime
    history_service: HistoryService

    def _validate_and_prepare_media(
        self,
        media: DownloadMedia | None,
        media_id: str | None,
        media_type: MediaType | None,
        video_download: bool = True,
    ) -> DownloadMedia | None:
        """Validate and prepare a media instance for download."""
        raise NotImplementedError

    def item(self, request: ItemRequest) -> tuple[bool, pathlib.Path | str]:
        """Download a single media item."""
        raise NotImplementedError

    def metadata_write(
        self,
        track: Track,
        path_media: pathlib.Path,
        is_parent_album: bool,
        media_stream: Stream,
    ) -> tuple[bool, pathlib.Path | None, pathlib.Path | None]:
        """Write metadata, lyrics, and cover to a media file."""
        raise NotImplementedError

    def lyrics_to_file(
        self, dir_destination: pathlib.Path, lyrics: str
    ) -> str:
        """Write lyrics to a temporary file."""
        raise NotImplementedError

    @staticmethod
    def cover_data(
        url: str | None = None, path_file: str | None = None
    ) -> str | bytes:
        """Retrieve cover image data from a URL or file."""
        raise NotImplementedError

    def cover_to_file(
        self, dir_destination: pathlib.Path, image: bytes
    ) -> str:
        """Write cover image to a temporary file."""
        raise NotImplementedError
