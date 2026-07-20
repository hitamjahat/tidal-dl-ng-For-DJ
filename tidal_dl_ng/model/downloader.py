"""Download-related data models for tidal-dl-ng.

These dataclasses group the many parameters, runtime handles and
intermediate results used while downloading tracks, videos, albums,
playlists and mixes from TIDAL.
"""

import pathlib
from dataclasses import dataclass, field
from threading import Event

from requests import HTTPError
from rich.progress import Progress, TaskID
from tidalapi.album import Album
from tidalapi.media import Quality, Stream, StreamManifest, Track, Video
from tidalapi.mix import Mix
from tidalapi.playlist import Playlist, UserPlaylist

from tidal_dl_ng.constants import MediaType, QualityVideo
from tidal_dl_ng.model.gui_data import ProgressBars


def _empty_extras() -> dict[str, object]:
    """Return a fresh, empty extras mapping."""
    return {}


def _empty_urls() -> list[str]:
    """Return a fresh, empty list of segment URLs."""
    return []


def _zero_task_id() -> TaskID:
    """Return a fresh, zero-initialised rich progress task id."""
    return TaskID(0)


@dataclass
class DownloadRuntime:
    """Groups runtime control and progress handles for a download.

    Attributes:
        progress_gui: GUI progress bars, if any.
        progress: Active rich progress bar, if any.
        progress_overall: Overall rich progress bar, if any.
        event_abort: Event used to signal an abort request.
        event_run: Event used to pause/resume the download loop.
    """

    progress_gui: ProgressBars | None = None
    progress: Progress | None = None
    progress_overall: Progress | None = None
    event_abort: Event | None = None
    event_run: Event | None = None


@dataclass
class DownloadParams:
    """Groups static download parameters for a Download instance.

    Attributes:
        path_base: Base path for downloads.
        skip_existing: Whether to skip files that already exist.
    """

    path_base: str
    skip_existing: bool = False


@dataclass
class DownloadSegmentResult:
    """Outcome of downloading a single stream segment."""

    result: bool
    """Whether the segment downloaded successfully."""

    url: str
    """Source URL the segment was fetched from."""

    path_segment: pathlib.Path
    """Local path the segment was written to."""

    id_segment: int
    """Numeric segment identifier used for tracing."""

    error: HTTPError | None = None
    """Captured HTTP error, if the download failed."""


@dataclass
class TrackStreamInfo:
    """Container for track stream information."""

    stream_manifest: StreamManifest | None
    file_extension: str
    requires_flac_extraction: bool
    media_stream: Stream | None


@dataclass
class DownloadContext:
    """Groups optional progress and control handles for a Download.

    Attributes:
        progress_gui: GUI progress bars used to emit item-name signals.
        progress: Rich progress bar for the current operation.
        progress_overall: Rich progress bar for the overall run.
        event_abort: Threading event signalling an abort request.
        event_run: Threading event signalling the run is active.
    """

    progress_gui: ProgressBars | None = None
    progress: Progress | None = None
    progress_overall: Progress | None = None
    event_abort: Event | None = None
    event_run: Event | None = None


@dataclass
class QualityState:
    """Groups quality settings used during a download.

    Attributes:
        quality_audio: Requested audio quality for this item.
        quality_video: Requested video quality for this item.
        quality_audio_old: Previously active audio quality to restore.
        quality_video_old: Previously active video quality to restore.
    """

    quality_audio: Quality | None = None
    quality_video: QualityVideo | None = None
    quality_audio_old: Quality | None = None
    quality_video_old: QualityVideo | None = None


@dataclass
class SourceInfo:
    """Groups provenance metadata for a downloaded item.

    Attributes:
        source_type: Origin kind (playlist, album, manual, mix, track).
        source_id: UUID of the originating collection, if any.
        source_name: Display name of the originating collection.
    """

    source_type: str = "manual"
    source_id: str | None = None
    source_name: str | None = None


@dataclass
class ListPosition:
    """Groups ordering metadata for an item inside a collection.

    Attributes:
        is_parent_album: Whether the item belongs to a parent album.
        list_position: Zero-based index of the item in the list.
        list_total: Total number of items in the list.
    """

    is_parent_album: bool = False
    list_position: int = 0
    list_total: int = 0


@dataclass
class ItemRequest:
    """Groups all parameters required to download a single media item.

    Attributes:
        file_template: Template used to build the destination path.
        media_id: Identifier of the media item, if fetched by id.
        media_type: Type of the media item, if fetched by id.
        media: Pre-resolved media object, if already available.
        video_download: Whether video downloads are permitted.
        download_delay: Whether to delay before the next download.
        quality_audio: Requested audio quality for this item.
        quality_video: Requested video quality for this item.
        is_parent_album: Whether the item belongs to a parent album.
        list_position: Zero-based index of the item in the list.
        list_total: Total number of items in the list.
        source_type: Origin kind (playlist, album, manual, mix, track).
        source_id: UUID of the originating collection, if any.
        source_name: Display name of the originating collection.
    """

    file_template: str = ""
    media_id: str | None = None
    media_type: MediaType | None = None
    media: Track | Video | Album | Playlist | UserPlaylist | Mix | None = None
    video_download: bool = True
    download_delay: bool = False
    quality_audio: Quality | None = None
    quality_video: QualityVideo | None = None
    is_parent_album: bool = False
    list_position: int = 0
    list_total: int = 0
    source_type: str = "manual"
    source_id: str | None = None
    source_name: str | None = None


@dataclass
class TrackReleaseInfo:
    """Groups release metadata for a track.

    Attributes:
        release_date: Release date string for the track.
        copy_right: Copyright statement for the track.
        isrc: ISRC identifier for the track.
    """

    release_date: str = ""
    copy_right: str = ""
    isrc: str = ""


@dataclass
class TrackExtrasData:
    """Groups auxiliary track data used when writing metadata.

    Attributes:
        cover_data: Raw cover image bytes, if available.
        lyrics_synced: Synchronized lyrics text, if available.
        lyrics_unsynced: Unsynchronized lyrics text, if available.
        extras: Additional metadata map from the API.
    """

    cover_data: bytes | None = None
    lyrics_synced: str = ""
    lyrics_unsynced: str = ""
    extras: dict[str, object] = field(default_factory=_empty_extras)


@dataclass
class ProgressHandles:
    """Groups Rich progress handles used during a batch download.

    Attributes:
        progress: Rich progress bar for the current operation.
        progress_task: Task id of the active progress bar.
        progress_stdout: Whether progress is rendered to stdout.
    """

    progress: Progress
    progress_task: TaskID
    progress_stdout: bool = False


@dataclass
class CollectionDownloadRequest:
    """Groups parameters for downloading a collection of items.

    Attributes:
        file_name_relative: Relative file name template.
        quality_audio: Requested audio quality for the items.
        quality_video: Requested video quality for the items.
        download_delay: Whether to delay between downloads.
        is_album: Whether the collection is an album.
        list_total: Total number of items in the collection.
        source_type: Origin kind (playlist, album, manual, mix, track).
        source_id: UUID of the originating collection, if any.
        source_name: Display name of the originating collection.
    """

    file_name_relative: str = ""
    quality_audio: Quality | None = None
    quality_video: QualityVideo | None = None
    download_delay: bool = False
    is_album: bool = False
    list_total: int = 0
    source_type: str = "manual"
    source_id: str | None = None
    source_name: str | None = None


@dataclass
class SegmentDownloadRequest:
    """Groups parameters for downloading and merging segments.

    Attributes:
        stream_manifest: Stream manifest for tracks, if available.
        urls: Resolved segment URLs to download.
        progress_to_stdout: Whether progress is shown on stdout.
        p_task: Progress bar task id for segment progress.
        block_size: Block size used when streaming segments.
    """

    stream_manifest: StreamManifest | None = None
    urls: list[str] = field(default_factory=_empty_urls)
    progress_to_stdout: bool = False
    p_task: TaskID = field(default_factory=_zero_task_id)
    block_size: int | None = None


@dataclass
class SegmentMeta:
    """Groups tracing and progress identifiers for one segment.

    Attributes:
        p_task: Progress bar task id for this segment.
        id_segment: Numeric segment identifier for tracing.
        op_id: Operation id used for trace events.
    """

    p_task: TaskID
    id_segment: int
    op_id: str


@dataclass
class TrackAssets:
    """Collected metadata assets for writing to a media file.

    Attributes:
        lyrics_synced: Synchronized lyrics text.
        lyrics_unsynced: Unsynchronized lyrics text.
        path_lyrics: Path to the written lyrics file, if any.
        cover_data: Raw cover image bytes, if any.
        path_cover: Path to the written cover file, if any.
        extras: Additional metadata extras keyed by name.
    """

    lyrics_synced: str
    lyrics_unsynced: str
    path_lyrics: pathlib.Path | None
    cover_data: bytes | None
    path_cover: pathlib.Path | None
    extras: dict[str, object]


@dataclass
class ItemPrepareRequest:
    """Groups parameters needed to prepare a single item for download.

    Attributes:
        media: The media item to prepare.
        file_template: Template used for file naming.
        media_id: Identifier of the media item.
        media_type: Type of the media item.
        video_download: Whether video downloads are allowed.
        quality_audio: Requested audio quality.
        list_position: Position of the item in its collection.
        list_total: Total number of items in the collection.
        op_id: Operation id used for trace events.
    """

    media: Track | Video | Album | Playlist | UserPlaylist | Mix | None
    file_template: str
    media_id: str | None
    media_type: MediaType | None
    video_download: bool
    quality_audio: Quality | None
    list_position: int
    list_total: int
    op_id: str


@dataclass
class ItemPrepared:
    """Result of preparing a single item for download.

    Attributes:
        media: The validated media item ready for download.
        path_media_dst: Destination file path.
        file_extension_dummy: Placeholder extension used during prep.
        skip_file: Whether the destination file already exists.
        skip_download: Whether the download itself should be skipped.
    """

    media: Track | Video
    path_media_dst: pathlib.Path
    file_extension_dummy: str
    skip_file: bool
    skip_download: bool


@dataclass
class ItemFinalizeRequest:
    """Groups all parameters needed to finalize a single item download.

    Attributes:
        media: The downloaded media item.
        path_media_dst: Destination file path.
        quality_audio: Requested audio quality for this item.
        quality_video: Requested video quality for this item.
        quality_audio_old: Previously active audio quality.
        quality_video_old: Previously active video quality.
        download_delay: Whether to delay before the next download.
        skip_file: Whether the file was skipped.
        download_success: Whether the download succeeded.
        source_type: Origin kind of the item.
        source_id: UUID of the originating collection.
        source_name: Display name of the originating collection.
        op_id: Operation id used for trace events.
    """

    media: Track | Video
    path_media_dst: pathlib.Path
    quality_audio: Quality | None
    quality_video: QualityVideo | None
    quality_audio_old: Quality | None
    quality_video_old: QualityVideo | None
    download_delay: bool
    skip_file: bool
    download_success: bool
    source_type: str
    source_id: str | None
    source_name: str | None
    op_id: str
