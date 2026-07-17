"""download.py

Implements the Download class and helpers for downloading media from
TIDAL, including segment merging, file moving, metadata writing, and
playlist creation.

Classes:
    RequestsClient: Simple HTTP client for downloading text content.
    Download: Main class for managing downloads, segment merging, file
        operations, and metadata.
"""

import logging
import os
import pathlib
import random
import shutil
import tempfile
import time
from concurrent import futures
from typing import Any, cast
from uuid import uuid4

import m3u8
import requests
from ffmpeg import FFmpeg
from requests.adapters import HTTPAdapter
from requests.exceptions import HTTPError, RequestException
from rich.progress import TaskID
from tidalapi.album import Album
from tidalapi.exceptions import TooManyRequests
from tidalapi.media import (
    AudioExtensions,
    AudioMode,
    Codec,
    Quality,
    Stream,
    StreamManifest,
    Track,
    Video,
    VideoExtensions,
)
from tidalapi.mix import Mix
from tidalapi.playlist import Playlist, UserPlaylist
from tidalapi.session import Session
from urllib3.util.retry import Retry

from tidal_dl_ng.config import Settings, Tidal
from tidal_dl_ng.constants import (
    CHUNK_SIZE,
    COVER_NAME,
    EXTENSION_LYRICS,
    REQUESTS_TIMEOUT_SEC,
    MediaType,
    QualityVideo,
)
from tidal_dl_ng.helper.decryption import decrypt_file, decrypt_security_token
from tidal_dl_ng.helper.exceptions import MediaMissing
from tidal_dl_ng.helper.collection_download import CollectionDownloadMixin
from tidal_dl_ng.helper.metadata_ops import MetadataWriterMixin
from tidal_dl_ng.helper.requests_client import RequestsClient
from tidal_dl_ng.helper.path import (
    check_file_exists,
    format_path_media,
    path_file_sanitize,
    url_to_filename,
)
from tidal_dl_ng.helper.tidal import (
    instantiate_media,
    name_builder_item,
    name_builder_title,
)
from tidal_dl_ng.history import HistoryService
from tidal_dl_ng.model.downloader import (
    DownloadContext,
    DownloadParams,
    DownloadRuntime,
    DownloadSegmentResult,
    ItemRequest,
    ItemFinalizeRequest,
    ItemPrepared,
    ItemPrepareRequest,
    QualityState,
    SegmentDownloadRequest,
    SegmentMeta,
    TrackStreamInfo,
)
from tidal_dl_ng.runtime_trace import (
    RuntimeWatchdog,
    new_operation_id,
    trace_event,
)

SEGMENT_HTTP_RETRY_TOTAL: int = 5
STREAM_INFO_RETRY_TOTAL: int = 3


# Future: Use pathlib.Path everywhere
class Download(MetadataWriterMixin, CollectionDownloadMixin):
    """Main class for managing downloads, segment merging, file
    operations, and metadata for TIDAL media."""

    settings: Settings
    tidal: "Tidal"
    session: Session
    fn_logger: logging.Logger
    params: DownloadParams
    runtime: DownloadRuntime
    history_service: HistoryService

    def __init__(
        self,
        tidal_obj: Tidal,  # Required for Atmos session context manager
        path_base: str,
        fn_logger: logging.Logger,
        skip_existing: bool = False,
        context: DownloadContext | None = None,
    ) -> None:
        """Initialize the Download object and its dependencies.

        Args:
            tidal_obj (Tidal): TIDAL configuration object. Required for:
                - session: Main TIDAL API session
                - switch_to_atmos_session(): Dolby Atmos credential switching
                - restore_normal_session(): Restore original session
                    credentials
            path_base (str): Base path for downloads.
            fn_logger (Callable): Logger function or object.
            skip_existing (bool, optional): Whether to skip existing
                files. Defaults to False.
            context (DownloadContext | None, optional): Grouped progress
                bars and control events. Defaults to None.
        """
        super().__init__()
        self.settings = Settings()
        self.tidal = tidal_obj
        self.session = tidal_obj.session
        self.fn_logger = fn_logger
        self.params = DownloadParams(
            path_base=path_base,
            skip_existing=skip_existing,
        )
        self.history_service = HistoryService()
        self.runtime = DownloadRuntime()
        if context is not None:
            self.runtime = DownloadRuntime(
                progress_gui=context.progress_gui,
                progress=context.progress,
                progress_overall=context.progress_overall,
                event_abort=context.event_abort,
                event_run=context.event_run,
            )

        if not self.settings.data.path_binary_ffmpeg and (
            self.settings.data.video_convert_mp4
            or self.settings.data.extract_flac
        ):
            self.settings.data.video_convert_mp4 = False
            self.settings.data.extract_flac = False

            self.fn_logger.error(
                "FFmpeg path is not set. Videos can be downloaded but "
                "will not be processed. FLAC cannot be "
                "extracted from MP4 containers. Make sure FFmpeg is "
                "installed. The path to the FFmpeg binary must "
                "be set in (`path_binary_ffmpeg`)."
            )

    def _get_media_urls(
        self,
        media: Track | Video,
        stream_manifest: StreamManifest | None,
    ) -> list[str]:
        """Extract URLs for the given media item.

        Args:
            media (Track | Video): The media item to download.
            stream_manifest (StreamManifest | None, optional): Stream
                manifest for tracks. Defaults to None.

        Returns:
            list[str]: List of URLs for the media segments.
        """
        # Get urls for media.
        if isinstance(media, Track):
            if stream_manifest is not None:
                manifest: Any = stream_manifest
                return cast("list[str]", manifest.get_urls())
            return []
        # media is narrowed to Video here.
        quality_video = self.settings.data.quality_video
        m3u8_variant = cast(
            "Any", m3u8.load(media.get_url(), http_client=RequestsClient())
        )
        # Find the desired video resolution or the next best one.
        m3u8_playlist, _ = self._extract_video_stream(
            m3u8_variant, int(quality_video)
        )

        if not isinstance(m3u8_playlist, bool):
            return cast("list[str]", m3u8_playlist.files)
        return []

    def _setup_progress(
        self,
        media_name: str,
        urls: list[str],
        progress_to_stdout: bool,
    ) -> tuple[TaskID, int | float | None, int | None]:
        """Set up the progress bar/task and compute progress total and
        block size.

        Args:
            media_name (str): Name of the media item.
            urls (list[str]): List of segment URLs.
            progress_to_stdout (bool): Whether to show progress in stdout.

        Returns:
            tuple[TaskID, int | float | None, int | None]: (
                TaskID, progress_total, block_size)
        """
        urls_count: int = len(urls)
        progress_total: int | float | None = None
        block_size: int | None = None

        # Compute total iterations for progress
        if urls_count > 1:
            progress_total = urls_count
            block_size = None
        elif urls_count == 1:
            # Get file size and compute progress steps.
            with requests.head(
                urls[0], timeout=REQUESTS_TIMEOUT_SEC, allow_redirects=True
            ) as response:
                total_size_in_bytes: int = int(
                    response.headers.get("content-length", 0)
                )
                block_size = 1048576
                progress_total = (
                    total_size_in_bytes / block_size
                    if total_size_in_bytes > 0
                    else None
                )
        else:
            raise ValueError

        # Create progress Task
        assert self.runtime.progress is not None
        p_task: TaskID = self.runtime.progress.add_task(
            f"[blue]Item '{media_name[:30]}'",
            total=progress_total,
            visible=progress_to_stdout,
        )
        return p_task, progress_total, block_size

    def _download_segments(
        self,
        urls: list[str],
        path_base: pathlib.Path,
        block_size: int | None,
        p_task: TaskID,
        progress_to_stdout: bool,
    ) -> tuple[bool, list[DownloadSegmentResult]]:
        """Download all segments with progress reporting and abort handling.

        Args:
            urls (list[str]): List of segment URLs.
            path_base (pathlib.Path): Base path for segment files.
            block_size (int | None): Block size for streaming.
            p_task (TaskID): Progress bar task ID.
            progress_to_stdout (bool): Whether to show progress in stdout.

        Returns:
            tuple[bool, list[DownloadSegmentResult]]: (
                result_segments, list of segment results)
        """
        result_segments: bool = True
        dl_segment_results: list[DownloadSegmentResult] = []

        assert self.runtime.progress is not None
        # Download segments until progress is finished.
        # Future: Compute download speed
        # (https://github.com/Textualize/rich/blob/master/
        # examples/downloader.py)
        while not self.runtime.progress.tasks[p_task].finished:
            with futures.ThreadPoolExecutor(
                max_workers=(
                    self.settings.data.downloads_simultaneous_per_track_max
                )
            ) as executor:
                # Dispatch all download tasks to worker threads
                l_futures: list[futures.Future[Any]] = [
                    executor.submit(
                        self._download_segment,
                        url,
                        path_base,
                        block_size,
                        p_task,
                        progress_to_stdout,
                    )
                    for url in urls
                ]

                # Report results as they become available
                for future in futures.as_completed(l_futures):
                    # Retrieve result
                    result_dl_segment: DownloadSegmentResult = future.result()

                    dl_segment_results.append(result_dl_segment)

                    # Check for a link that was skipped
                    if not result_dl_segment.result and (
                        result_dl_segment.url is not urls[-1]
                    ):
                        # Sometimes it happens, if a track is very short
                        # (< 8 seconds or so), that the last URL in `urls` is
                        # invalid (HTTP Error 500) and not necessary.
                        # File won't be corrupt.
                        # If this is NOT the case, but any other URL has
                        # resulted in an error,
                        # mark the whole thing as corrupt.
                        result_segments = False

                        self.fn_logger.error(
                            "Something went wrong while downloading. "
                            "File is corrupt!"
                        )

                    # If app is terminated (CTRL+C)
                    if (
                        self.runtime.event_abort is not None
                        and self.runtime.event_abort.is_set()
                    ):
                        # Cancel all not yet started tasks
                        for f in l_futures:
                            f.cancel()

                        return False, dl_segment_results

        return result_segments, dl_segment_results

    def _download_postprocess(
        self,
        result_segments: bool,
        path_file: pathlib.Path,
        dl_segment_results: list[DownloadSegmentResult],
        media: Track | Video,
        stream_manifest: StreamManifest | None = None,
    ) -> tuple[bool, pathlib.Path]:
        """Merge segments, decrypt if needed, and return the final file path.

        Args:
            result_segments (bool): Whether all segments downloaded
                successfully.
            path_file (pathlib.Path): Path to the output file.
            dl_segment_results (list[DownloadSegmentResult]): List of
                segment download results.
            media (Track | Video): The media item.
            stream_manifest (StreamManifest | None, optional): Stream
                manifest for tracks. Defaults to None.

        Returns:
            tuple[bool, pathlib.Path]: (Success, path to downloaded or
                decrypted file)
        """
        tmp_path_file_decrypted: pathlib.Path = path_file
        result_merge: bool = False

        # Only if no error happened while downloading.
        if result_segments:
            # Bring list into right order, so segments can be easily merged.
            dl_segment_results.sort(key=lambda x: x.id_segment)

            result_merge = self._segments_merge(path_file, dl_segment_results)

            if not result_merge:
                self.fn_logger.error(
                    f"Something went wrong while writing to "
                    f"{media.name}. File is corrupt!"
                )
            elif (
                isinstance(media, Track)
                and stream_manifest is not None
                and stream_manifest.is_encrypted
            ):
                key, nonce = decrypt_security_token(
                    cast("str", stream_manifest.encryption_key)
                )
                tmp_path_file_decrypted = path_file.with_suffix(".decrypted")

                decrypt_file(path_file, tmp_path_file_decrypted, key, nonce)

        return result_merge, tmp_path_file_decrypted

    def _resolve_media_urls(
        self,
        media: Track | Video,
        stream_manifest: StreamManifest | None,
        op_id: str,
        media_name: str,
    ) -> list[str] | None:
        """Resolve download URLs for a media item.

        Args:
            media: The media item to resolve URLs for.
            stream_manifest: Stream manifest for tracks, if available.
            op_id: Operation id used for trace events.
            media_name: Human readable media name for tracing.

        Returns:
            The list of segment URLs, or None when resolution fails.
        """
        try:
            return self._get_media_urls(media, stream_manifest)
        except (RequestException, TooManyRequests, ValueError):
            trace_event(
                "stream_download",
                "resolve_urls_failed",
                expected="media urls are available",
                actual=f"media={media_name}",
                op_id=op_id,
            )
            return None

    def _setup_progress_task(
        self,
        media_name: str,
        urls: list[str],
        progress_to_stdout: bool,
        op_id: str,
    ) -> tuple[TaskID, int | float | None, int | None] | None:
        """Create the progress task for the current download.

        Args:
            media_name: Human readable media name.
            urls: Resolved segment URLs.
            progress_to_stdout: Whether progress is shown on stdout.
            op_id: Operation id used for trace events.

        Returns:
            The progress task tuple, or None when setup fails.
        """
        try:
            return self._setup_progress(media_name, urls, progress_to_stdout)
        except (RequestException, ValueError):
            trace_event(
                "stream_download",
                "setup_progress_failed",
                expected="progress task created",
                actual=f"media={media_name}",
                op_id=op_id,
            )
            return None

    def _download(
        self,
        media: Track | Video,
        path_file: pathlib.Path,
        stream_manifest: StreamManifest | None = None,
    ) -> tuple[bool, pathlib.Path]:
        """Download a media item (track or video), handling segments
        and merging.

        Args:
            media (Track | Video): The media item.
            path_file (pathlib.Path): Path to the output file.
            stream_manifest (StreamManifest | None, optional): Stream
                manifest for tracks. Defaults to None.

        Returns:
            tuple[bool, pathlib.Path]: (Success, path to downloaded or
                decrypted file)
        """
        media_name: str = name_builder_item(media)
        op_id = new_operation_id("stream")
        watchdog = RuntimeWatchdog(
            operation="stream_download",
            op_id=op_id,
            timeout_sec=60.0,
            check_interval_sec=20.0,
            context={
                "media_id": getattr(media, "id", ""),
                "media_name": media_name[:120],
            },
        )
        watchdog.start()
        trace_event(
            "stream_download",
            "start",
            expected="resolve urls -> download segments -> merge/decrypt",
            actual=f"media={media_name}",
            op_id=op_id,
        )

        try:
            watchdog.ping("resolve_urls")
            urls: list[str] | None = self._resolve_media_urls(
                media, stream_manifest, op_id, media_name
            )
            if urls is None:
                return False, path_file

            trace_event(
                "stream_download",
                "urls_resolved",
                expected="downloadable urls resolved",
                actual=f"urls_count={len(urls)}",
                op_id=op_id,
            )

            # Set the correct progress output channel.
            if not (progress_to_stdout := self.runtime.progress_gui is None):
                # Send signal to GUI with media name
                gui = self.runtime.progress_gui
                cast("Any", gui.item_name).emit(media_name[:30])

            watchdog.ping("setup_progress")
            progress_setup = self._setup_progress_task(
                media_name, urls, progress_to_stdout, op_id
            )
            if progress_setup is None:
                return False, path_file
            p_task, _progress_total, block_size = progress_setup

            watchdog.ping("download_segments")
            return self._run_download_pipeline(
                media,
                path_file,
                SegmentDownloadRequest(
                    stream_manifest=stream_manifest,
                    urls=urls,
                    progress_to_stdout=progress_to_stdout,
                    p_task=p_task,
                    block_size=block_size,
                ),
                op_id,
            )
        finally:
            watchdog.stop("stream_download_complete")

    def _run_download_pipeline(
        self,
        media: Track | Video,
        path_file: pathlib.Path,
        segment_request: SegmentDownloadRequest,
        op_id: str,
    ) -> tuple[bool, pathlib.Path]:
        """Download segments and post-process the merged file.

        Args:
            media: The media item being downloaded.
            path_file: Path to the output file.
            segment_request: Grouped segment download parameters.
            op_id: Operation id used for trace events.

        Returns:
            tuple[bool, pathlib.Path]: (Success, final temp path).
        """
        result_segments, dl_segment_results = self._download_segments(
            segment_request.urls,
            path_file.parent,
            segment_request.block_size,
            segment_request.p_task,
            segment_request.progress_to_stdout,
        )

        trace_event(
            "stream_download",
            "segments_done",
            expected="all segments downloaded",
            actual=(
                f"ok={result_segments}, " f"segments={len(dl_segment_results)}"
            ),
            op_id=op_id,
        )

        result_merge, tmp_path_file_decrypted = self._download_postprocess(
            result_segments,
            path_file,
            dl_segment_results,
            media,
            segment_request.stream_manifest,
        )

        trace_event(
            "stream_download",
            "end",
            expected="download returns final temp path",
            actual=(
                f"ok={result_merge}, " f"tmp_file={tmp_path_file_decrypted}"
            ),
            op_id=op_id,
        )

        return result_merge, tmp_path_file_decrypted

    def _segments_merge(
        self,
        path_file: pathlib.Path,
        dl_segment_results: list[DownloadSegmentResult],
    ) -> bool:
        """Merge downloaded segments into a single file and clean up
        segment files.

        Args:
            path_file (pathlib.Path): Path to the output file.
            dl_segment_results (list[DownloadSegmentResult]): List of
                segment download results.

        Returns:
            bool: True if merge succeeded, False
                otherwise.
        """
        result: bool = True

        # Copy the content of all segments into one file.
        try:
            with path_file.open("wb") as f_target:
                for dl_segment_result in dl_segment_results:
                    with dl_segment_result.path_segment.open(
                        "rb"
                    ) as f_segment:
                        # Read and write chunks, which gives better HDD
                        # write performance
                        while segment := f_segment.read(CHUNK_SIZE):
                            f_target.write(segment)

                    # Delete segment from HDD
                    dl_segment_result.path_segment.unlink()

        except OSError:
            result = False

        return result

    def _attempt_segment_download(
        self,
        url: str,
        path_segment: pathlib.Path,
        block_size: int | None,
        meta: SegmentMeta,
    ) -> tuple[bool, HTTPError | None]:
        """Download a single segment using a retrying HTTP session.

        Args:
            url: Segment URL to download.
            path_segment: Local file path for the segment.
            block_size: Block size used when streaming the response.
            meta: Grouped progress and tracing identifiers.

        Returns:
            tuple[bool, HTTPError | None]: (Success, HTTP error if any).
        """
        error: HTTPError | None = None
        with requests.Session() as s:
            retries = Retry(
                total=SEGMENT_HTTP_RETRY_TOTAL,
                backoff_factor=1,
                status_forcelist=[429, 500, 502, 503, 504],
            )
            s.mount("https://", HTTPAdapter(max_retries=retries))
            s.mount("http://", HTTPAdapter(max_retries=retries))

            try:
                trace_event(
                    "segment_download",
                    "start",
                    expected="download segment bytes",
                    actual=f"segment_id={meta.id_segment}",
                    op_id=meta.op_id,
                    level=logging.DEBUG,
                )
                with s.get(
                    url,
                    stream=True,
                    timeout=REQUESTS_TIMEOUT_SEC,
                ) as response:
                    response.raise_for_status()
                    with path_segment.open("wb") as f:
                        for data in response.iter_content(
                            chunk_size=block_size
                        ):
                            f.write(data)
                            if self.runtime.progress is not None:
                                self.runtime.progress.advance(meta.p_task)
                return True, error
            except RequestException as e:
                if isinstance(e, HTTPError):
                    error = e
                if self.runtime.progress is not None:
                    self.runtime.progress.advance(meta.p_task)
                trace_event(
                    "segment_download",
                    "failed",
                    expected="segment bytes written to disk",
                    actual=f"segment_id={meta.id_segment}, error={e}",
                    op_id=meta.op_id,
                    level=logging.DEBUG,
                )
                return False, error

    def _download_segment(
        self,
        url: str,
        path_base: pathlib.Path,
        block_size: int | None,
        p_task: TaskID,
        progress_to_stdout: bool,
    ) -> DownloadSegmentResult:
        """Download a single segment of a media file.

        Args:
            url (str): URL of the segment.
            path_base (pathlib.Path): Base path for segment file.
            block_size (int | None): Block size for streaming.
            p_task (TaskID): Progress bar task ID.
            progress_to_stdout (bool): Whether to show progress in stdout.

        Returns:
            DownloadSegmentResult: Result of the segment download.
        """
        result: bool = False
        op_id = new_operation_id("segment")
        path_segment: pathlib.Path = path_base / url_to_filename(url)
        # Calculate the segment ID based on the file name within the URL.
        filename_stem: str = str(path_segment.stem).rsplit("_", maxsplit=1)[-1]
        # CAUTION: This is a workaround, so BTS (LOW quality) track will
        # work. They usually have only ONE link.
        id_segment: int = (
            int(filename_stem) if filename_stem.isdecimal() else 0
        )
        error: HTTPError | None = None

        # If app is terminated (CTRL+C)
        if self.runtime.event_abort is not None and (
            self.runtime.event_abort.is_set()
        ):
            trace_event(
                "segment_download",
                "aborted_before_start",
                expected="segment starts downloading",
                actual=(f"segment_id={id_segment}"),
                op_id=op_id,
                level=logging.DEBUG,
            )
            return DownloadSegmentResult(
                result=False,
                url=url,
                path_segment=path_segment,
                id_segment=id_segment,
                error=error,
            )

        if self.runtime.event_run is not None and (
            not self.runtime.event_run.is_set()
        ):
            self.runtime.event_run.wait()

        # Retry download on failed segments, with an exponential delay
        # between retries
        result, error = self._attempt_segment_download(
            url,
            path_segment,
            block_size,
            SegmentMeta(
                p_task=p_task,
                id_segment=id_segment,
                op_id=op_id,
            ),
        )

        # To send the progress to the GUI, we need to emit the percentage.
        if not progress_to_stdout and self.runtime.progress_gui is not None:
            assert self.runtime.progress is not None
            cast("Any", self.runtime.progress_gui.item).emit(
                self.runtime.progress.tasks[p_task].percentage
            )

        if result:
            segment_size = (
                path_segment.stat().st_size if path_segment.exists() else 0
            )
            trace_event(
                "segment_download",
                "end",
                expected="segment completed",
                actual=(f"segment_id={id_segment}, " f"size={segment_size}"),
                op_id=op_id,
                level=logging.DEBUG,
            )

        return DownloadSegmentResult(
            result=result,
            url=url,
            path_segment=path_segment,
            id_segment=id_segment,
            error=error,
        )

    def extension_guess(
        self, quality_audio: Quality, metadata_tags: list[str], is_video: bool
    ) -> str:
        """Guess the file extension for a media item based on quality and type.

        Args:
            quality_audio (Quality): Audio quality.
            metadata_tags (list[str]): Metadata tags for the media.
            is_video (bool): Whether the media is a video.

        Returns:
            str: Guessed file extension (member of AudioExtensions or
                VideoExtensions).
        """
        result: str

        if is_video:
            result = (
                AudioExtensions.MP4
                if self.settings.data.video_convert_mp4
                else VideoExtensions.TS
            )
        else:
            result = (
                AudioExtensions.FLAC
                if (
                    self.settings.data.extract_flac
                    and quality_audio
                    in (Quality.hi_res_lossless, Quality.high_lossless)
                )
                or (
                    "HIRES_LOSSLESS" not in metadata_tags
                    and quality_audio
                    not in (Quality.low_96k, Quality.low_320k)
                )
                or quality_audio == Quality.high_lossless
                else AudioExtensions.M4A
            )

        return result

    def _should_skip_history_duplicate(
        self,
        media: Track | Video,
        op_id: str,
    ) -> bool:
        """Check persistent history and log a skip when duplicated.

        Args:
            media: The media item being considered.
            op_id: Operation id used for trace events.

        Returns:
            True when the item should be skipped due to history.
        """
        if not isinstance(media, Track):
            return False
        track_id = str(media.id)
        if not self.history_service.should_skip_download(track_id):
            return False
        self.fn_logger.info(
            f"Skipped item '{name_builder_item(media)}' "
            f"(already in history)."
        )
        trace_event(
            "download_item",
            "skipped_history_duplicate",
            expected="track is not in history",
            actual=f"track_id={track_id}",
            op_id=op_id,
        )
        return True

    def _setup_item_operation(
        self,
        media: Track | Video | Album | Playlist | UserPlaylist | Mix | None,
        media_id: str | None,
        source_type: str,
        source_id: str | None,
        source_name: str | None,
    ) -> tuple[str, float, RuntimeWatchdog]:
        """Create operation id, start timestamp, and watchdog for an item.

        Args:
            media: The media item being downloaded.
            media_id: Identifier of the media item.
            source_type: Origin kind of the item.
            source_id: UUID of the originating collection.
            source_name: Display name of the originating collection.

        Returns:
            Tuple of operation id, start timestamp, and watchdog.
        """
        op_id = new_operation_id("item")
        started_at = time.monotonic()
        trace_event(
            "download_item",
            "start",
            expected="validate -> path prep -> stream fetch -> post-process",
            actual=f"media_id={media_id or getattr(media, 'id', '')}",
            op_id=op_id,
            context={
                "source_type": source_type,
                "source_id": source_id or "",
                "source_name": source_name or "",
            },
        )

        watchdog = RuntimeWatchdog(
            operation="download_item",
            op_id=op_id,
            timeout_sec=90.0,
            check_interval_sec=30.0,
            context={"media_id": media_id or getattr(media, "id", "")},
        )
        watchdog.start()
        return op_id, started_at, watchdog

    def _prepare_item_for_download(
        self,
        request: ItemPrepareRequest,
    ) -> ItemPrepared | None:
        """Validate media and resolve destination paths and skip flags.

        Args:
            request: All parameters needed to prepare the item.

        Returns:
            ItemPrepared when valid, otherwise None to signal a skip.
        """
        validated_media = self._validate_and_prepare_media(
            request.media,
            request.media_id,
            request.media_type,
            request.video_download,
        )
        if validated_media is None or not isinstance(
            validated_media, Track | Video
        ):
            trace_event(
                "download_item",
                "skip_invalid_media",
                expected="media is available and downloadable",
                actual="validation returned None",
                op_id=request.op_id,
            )
            return None

        media = validated_media
        trace_event(
            "download_item",
            "media_ready",
            expected="media object resolved",
            actual=f"name={name_builder_item(media)}",
            op_id=request.op_id,
        )

        path_media_dst, file_extension_dummy, skip_file, skip_download = (
            self._prepare_file_paths_and_skip_logic(
                media,
                request.file_template,
                request.quality_audio,
                request.list_position,
                request.list_total,
            )
        )
        trace_event(
            "download_item",
            "paths_prepared",
            expected="destination and skip flags resolved",
            actual=(
                f"dst={path_media_dst}, "
                f"skip_file={skip_file}, "
                f"skip_download={skip_download}"
            ),
            op_id=request.op_id,
        )
        return ItemPrepared(
            media=media,
            path_media_dst=path_media_dst,
            file_extension_dummy=file_extension_dummy,
            skip_file=skip_file,
            skip_download=skip_download,
        )

    def item(
        self,
        request: ItemRequest,
    ) -> tuple[bool, pathlib.Path | str]:
        """Download a single media item, handling file naming,
        skipping, and post-processing.

        Args:
            request (ItemRequest): All parameters for this download.

        Returns:
            tuple[bool, pathlib.Path | str]: (Downloaded, path to file)
        """
        media: Track | Video | Album | Playlist | UserPlaylist | Mix | None = (
            request.media
        )
        op_id, started_at, watchdog = self._setup_item_operation(
            media,
            request.media_id,
            request.source_type,
            request.source_id,
            request.source_name,
        )

        try:
            # Step 1 & 2: Validate media and prepare paths
            watchdog.ping("validate_media")
            prepared = self._prepare_item_for_download(
                ItemPrepareRequest(
                    media=media,
                    file_template=request.file_template,
                    media_id=request.media_id,
                    media_type=request.media_type,
                    video_download=request.video_download,
                    quality_audio=request.quality_audio,
                    list_position=request.list_position,
                    list_total=request.list_total,
                    op_id=op_id,
                )
            )
            if prepared is None:
                return False, ""

            media = prepared.media
            path_media_dst = prepared.path_media_dst
            file_extension_dummy = prepared.file_extension_dummy
            skip_file = prepared.skip_file
            skip_download = prepared.skip_download

            # Step 2b: Duplicate prevention based on persistent history
            if self._should_skip_history_duplicate(media, op_id):
                return False, path_media_dst

            if skip_file:
                self.fn_logger.debug(
                    f"Download skipped, since file exists: '{path_media_dst}'"
                )
                trace_event(
                    "download_item",
                    "skipped_existing_file",
                    expected="target file does not exist",
                    actual=f"dst={path_media_dst}",
                    op_id=op_id,
                )
                return True, path_media_dst

            # Step 3: Handle quality settings
            watchdog.ping("adjust_quality")
            quality_audio_old, quality_video_old = (
                self._adjust_quality_settings(
                    request.quality_audio, request.quality_video
                )
            )

            # Step 4: Download and process media
            watchdog.ping("download_and_process")
            download_success = self._download_and_process_media(
                media,
                path_media_dst,
                skip_download,
                request.is_parent_album,
                file_extension_dummy,
            )
            trace_event(
                "download_item",
                "download_processed",
                expected="media downloaded and transformed if needed",
                actual=f"ok={download_success}",
                op_id=op_id,
            )

            # Step 5 & 6: Post-processing and history update
            watchdog.ping("post_processing")
            self._finalize_item_download(
                ItemFinalizeRequest(
                    media=media,
                    path_media_dst=path_media_dst,
                    quality_audio=request.quality_audio,
                    quality_video=request.quality_video,
                    quality_audio_old=quality_audio_old,
                    quality_video_old=quality_video_old,
                    download_delay=request.download_delay,
                    skip_file=skip_file,
                    download_success=download_success,
                    source_type=request.source_type,
                    source_id=request.source_id,
                    source_name=request.source_name,
                    op_id=op_id,
                )
            )

            elapsed = time.monotonic() - started_at
            trace_event(
                "download_item",
                "end",
                expected="item returns with final status",
                actual=f"ok={download_success}, elapsed_sec={elapsed:.3f}",
                op_id=op_id,
            )
            return download_success, path_media_dst
        finally:
            watchdog.stop("item_done")

    def _finalize_item_download(
        self,
        request: ItemFinalizeRequest,
    ) -> None:
        """Run post-processing and update download history for an item.

        Args:
            request: All parameters needed to finalize the download.
        """
        media: Track | Video = request.media
        path_media_dst: pathlib.Path = request.path_media_dst

        self._perform_post_processing(
            media,
            path_media_dst,
            QualityState(
                quality_audio=request.quality_audio,
                quality_video=request.quality_video,
                quality_audio_old=request.quality_audio_old,
                quality_video_old=request.quality_video_old,
            ),
            request.download_delay,
            request.skip_file,
        )

        # Add to download history if successful (only for Tracks)
        if request.download_success and isinstance(media, Track):
            try:
                self.history_service.add_track_to_history(
                    track_id=str(media.id),
                    source_type=request.source_type,
                    source_id=request.source_id,
                    source_name=request.source_name,
                )
            except (OSError, ValueError) as e:
                # Don't fail the download if history tracking fails
                self.fn_logger.warning(f"Failed to add track to history: {e}")
                trace_event(
                    "download_item",
                    "history_update_failed",
                    expected="download history update succeeds",
                    actual=f"error={e}",
                    op_id=request.op_id,
                )

    def _validate_and_prepare_media(
        self,
        media: Track | Video | Album | Playlist | UserPlaylist | Mix | None,
        media_id: str | None,
        media_type: MediaType | None,
        video_download: bool = True,
    ) -> Track | Video | Album | Playlist | UserPlaylist | Mix | None:
        """Validate and prepare media instance for download.

        Args:
            media (Track | Video | Album | Playlist | UserPlaylist |
                Mix | None): Media instance.
            media_id (str | None): Media ID if creating new instance.
            media_type (MediaType | None): Media type if creating
                new instance.
            video_download (bool, optional): Whether video downloads
                are allowed. Defaults to True.

        Returns:
            Track | Video | Album | Playlist | UserPlaylist | Mix |
                None: Prepared media instance or None if invalid.
        """
        try:
            media = self._resolve_media_instance(media, media_id, media_type)
        except (RequestException, TooManyRequests, ValueError, MediaMissing):
            return None

        # If video download is not allowed and this is a video,
        # return None
        if not video_download and isinstance(media, Video):
            self.fn_logger.info(
                f"Video downloads are deactivated (see settings). "
                f"Skipping video: {name_builder_item(media)}"
            )
            return None

        return media

    def _resolve_media_instance(
        self,
        media: Track | Video | Album | Playlist | UserPlaylist | Mix | None,
        media_id: str | None,
        media_type: MediaType | None,
    ) -> Track | Video | Album | Playlist | UserPlaylist | Mix | None:
        """Resolve the media instance from id or validate availability.

        Args:
            media: Pre-existing media instance, if any.
            media_id: Identifier used to instantiate a new media object.
            media_type: Type used to instantiate a new media object.

        Returns:
            The resolved media instance, or None when unavailable.
        """
        if media_id and media_type:
            # If no media instance is provided, we need to
            # create the media instance.
            # Throws `tidalapi.exceptions.ObjectNotFound` if item
            # is not available anymore.
            return cast(
                "Any",
                instantiate_media(self.session, media_type, media_id),
            )

        resolved: (
            Track | Video | Album | Playlist | UserPlaylist | Mix | (None)
        ) = media
        if isinstance(media, Track | Video):
            # Check if media is available not deactivated /
            # removed from TIDAL.
            if not media.available:
                self.fn_logger.info(
                    f"This item is not available for "
                    f"listening anymore on TIDAL. Skipping: "
                    f"{name_builder_item(media)}"
                )
                return None
            if isinstance(media, Track):
                # Re-create media instance with full album information
                resolved = self.session.track(str(media.id), with_album=True)
        elif isinstance(media, Album):
            # Check if media is available not deactivated /
            # removed from TIDAL.
            if not media.available:
                self.fn_logger.info(
                    f"This item is not available for "
                    f"listening anymore on TIDAL. Skipping: "
                    f"{name_builder_title(media)}"
                )
                return None
        elif not media:
            raise MediaMissing

        return resolved

    def _compute_symlink_track_path(
        self, media: Track | Video, file_extension_dummy: str
    ) -> pathlib.Path:
        """Compute the sanitized track-dir path used for symlink checks.

        Args:
            media: The media item to build the path for.
            file_extension_dummy: Guessed file extension for the media.

        Returns:
            The absolute, sanitized path inside the track directory.
        """
        file_name_track_dir_relative: str = format_path_media(
            self.settings.data.format_track,
            media,
            delimiter_artist=(self.settings.data.filename_delimiter_artist),
            delimiter_album_artist=(
                self.settings.data.filename_delimiter_album_artist
            ),
            use_primary_album_artist=(
                self.settings.data.use_primary_album_artist
            ),
        )
        path_media_track_dir: pathlib.Path = (
            pathlib.Path(self.params.path_base).expanduser()
            / (file_name_track_dir_relative + file_extension_dummy)
        ).absolute()
        return pathlib.Path(
            path_file_sanitize(path_media_track_dir, adapt=True)
        )

    def _prepare_file_paths_and_skip_logic(
        self,
        media: Track | Video,
        file_template: str,
        quality_audio: Quality | None,
        list_position: int,
        list_total: int,
    ) -> tuple[pathlib.Path, str, bool, bool]:
        """Prepare file paths and determine skip logic.

        Args:
            media (Track | Video): Media item.
            file_template (str): Template for file naming.
            quality_audio (Quality | None): Audio quality setting.
            list_position (int): Position in list.
            list_total (int): Total items in list.

        Returns:
            tuple[pathlib.Path, str, bool, bool]: (
                path_media_dst, file_extension_dummy, skip_file,
                skip_download
            )
        """
        # Create file name and path
        metadata_tags: list[str] = (
            []
            if isinstance(media, Video)
            else (media.media_metadata_tags or [])
        )
        quality_for_extension: str = str(Quality.high_lossless)
        if quality_audio is not None:
            quality_for_extension = str(quality_audio)

        file_extension_dummy: str = self.extension_guess(
            cast("Quality", quality_for_extension),
            metadata_tags=metadata_tags,
            is_video=isinstance(media, Video),
        )

        file_name_relative: str = format_path_media(
            file_template,
            media,
            self.settings.data.album_track_num_pad_min,
            list_position,
            list_total,
            delimiter_artist=(self.settings.data.filename_delimiter_artist),
            delimiter_album_artist=(
                self.settings.data.filename_delimiter_album_artist
            ),
            use_primary_album_artist=(
                self.settings.data.use_primary_album_artist
            ),
        )

        path_media_dst: pathlib.Path = (
            pathlib.Path(self.params.path_base).expanduser()
            / (file_name_relative + file_extension_dummy)
        ).absolute()

        # Sanitize final path_file to fit into OS boundaries.
        path_media_dst = pathlib.Path(
            path_file_sanitize(path_media_dst, adapt=True)
        )

        # Compute if and how downloads need to be skipped.
        skip_download: bool = False

        if self.params.skip_existing:
            skip_file: bool = check_file_exists(
                path_media_dst, extension_ignore=False
            )
            skip_download = self._compute_symlink_skip_flags(
                media, file_extension_dummy, path_media_dst, skip_file
            )
        else:
            skip_file = False

        return path_media_dst, file_extension_dummy, skip_file, skip_download

    def _compute_symlink_skip_flags(
        self,
        media: Track | Video,
        file_extension_dummy: str,
        path_media_dst: pathlib.Path,
        skip_file: bool,
    ) -> bool:
        """Determine skip_download using symlink-to-track configuration.

        Args:
            media: The media item being considered.
            file_extension_dummy: Placeholder extension for the file.
            path_media_dst: Destination file path.
            skip_file: Whether the destination file already exists.

        Returns:
            True when the download can be skipped via symlink logic.
        """
        if not self.settings.data.symlink_to_track or isinstance(media, Video):
            return False

        # Compute symlink tracks path, sanitize and check if file exists
        path_media_track_dir = self._compute_symlink_track_path(
            media, file_extension_dummy
        )
        file_exists_track_dir: bool = check_file_exists(
            path_media_track_dir, extension_ignore=False
        )
        file_exists_playlist_dir: bool = (
            not file_exists_track_dir
            and skip_file
            and not path_media_dst.is_symlink()
        )
        skip_download = file_exists_playlist_dir or file_exists_track_dir

        # If file exists in playlist dir but not in track dir,
        # we don't skip the file itself
        if skip_file and file_exists_playlist_dir:
            skip_file = False
        return skip_download

    def _adjust_quality_settings(
        self,
        quality_audio: Quality | None,
        quality_video: QualityVideo | None,
    ) -> tuple[Quality | None, QualityVideo | None]:
        """Adjust quality settings and return previous values.

        Args:
            quality_audio (Quality | None): Audio quality setting.
            quality_video (QualityVideo | None): Video quality setting.

        Returns:
            tuple[Quality | None, QualityVideo | None]: (
                Previous quality settings.
            )
        """
        quality_audio_old: Quality | None = None
        quality_video_old: QualityVideo | None = None

        if quality_audio:
            quality_audio_old = self.adjust_quality_audio(quality_audio)

        if quality_video:
            quality_video_old = self.adjust_quality_video(quality_video)

        return quality_audio_old, quality_video_old

    def _download_and_process_media(
        self,
        media: Track | Video,
        path_media_dst: pathlib.Path,
        skip_download: bool,
        is_parent_album: bool,
        _file_extension_dummy: str,
    ) -> bool:
        """Download and process media file.

        Args:
            media (Track | Video): Media item.
            path_media_dst (pathlib.Path): Destination file path.
            skip_download (bool): Whether to skip download.
            is_parent_album (bool): Whether this is a parent album.
            _file_extension_dummy (str): Unused interface placeholder.

        Returns:
            bool: Whether download was successful.
        """
        if skip_download:
            return True

        # Get stream information and final file extension
        stream_manifest, file_extension, do_flac_extract, media_stream = (
            self._get_stream_info(media)
        )

        if stream_manifest is None and isinstance(media, Track):
            return False

        # Update path if extension changed
        if path_media_dst.suffix != file_extension:
            path_media_dst = path_media_dst.with_suffix(file_extension)
            path_media_dst = pathlib.Path(
                path_file_sanitize(path_media_dst, adapt=True)
            )

        os.makedirs(path_media_dst.parent, exist_ok=True)

        # Perform actual download
        return self._perform_actual_download(
            media,
            path_media_dst,
            TrackStreamInfo(
                stream_manifest=stream_manifest,
                file_extension="",
                requires_flac_extraction=do_flac_extract,
                media_stream=media_stream,
            ),
            is_parent_album,
        )

    def _get_stream_info(
        self, media: Track | Video
    ) -> tuple[StreamManifest | None, str, bool, Stream | None]:
        """Get stream information for media.

        Args:
            media (Track | Video): Media item.

        Returns:
        tuple[StreamManifest | None, str, bool, Stream | None]: Stream info.
        """
        stream_manifest: StreamManifest | None = None
        media_stream: Stream | None = None
        do_flac_extract: bool = False
        file_extension: str = ""
        op_id = new_operation_id("stream_info")
        started_at = time.monotonic()

        trace_event(
            "stream_info",
            "start",
            expected="acquire stream lock and resolve stream manifest",
            actual=f"media_id={getattr(media, 'id', '')}",
            op_id=op_id,
        )

        # CRITICAL: This lock is intentionally broad and serializes all
        # stream-fetching (Phase 1) to prevent a critical race condition.
        # THE PROBLEM:
        # The single, shared session (self.tidal.session) must change its
        # credentials to switch between Atmos and Hi-Res/Normal streams.
        # THE RACE CONDITION IT FIXES:
        # If this lock is released *before* get_stream() is called,
        # another thread could change the session (e.g., back to "Normal")
        # right after this thread switched it to "Atmos". This would
        # cause this thread to call get_stream() with the wrong credentials,
        # resulting in the API returning AAC 320 instead of Atmos.
        # THE TRADEOFF:
        # This creates a "tollbooth" bottleneck, serializing the get_stream()
        # calls. However, the *actual* segment downloads (Phase 2)
        # still run in parallel, governed by `downloads_concurrent_max`.
        # DO NOT "OPTIMIZE" THIS by making the lock more granular.
        # Correctness > Performance.

        with self.tidal.stream_lock:
            try:
                trace_event(
                    "stream_info",
                    "lock_acquired",
                    expected="stream lock protects session context switching",
                    actual=f"media_type={type(media).__name__}",
                    op_id=op_id,
                    level=logging.DEBUG,
                )

                if isinstance(media, Track):
                    track_info = self._get_track_stream_info(media)

                    if track_info.stream_manifest is None:
                        return None, "", False, None

                    stream_manifest = track_info.stream_manifest
                    file_extension = track_info.file_extension
                    do_flac_extract = track_info.requires_flac_extraction
                    media_stream = track_info.media_stream

                else:
                    # media is narrowed to Video here.
                    # Videos always require the normal session
                    if not self.tidal.restore_normal_session():
                        self.fn_logger.error(
                            f"Failed to restore normal session for "
                            f"video: {media.id}"
                        )
                        return None, "", False, None

                    file_extension = (
                        AudioExtensions.MP4
                        if self.settings.data.video_convert_mp4
                        else VideoExtensions.TS
                    )

                    stream_manifest = None
                    media_stream = None
                    do_flac_extract = False

            except TooManyRequests:
                self.fn_logger.exception(
                    f"Too many requests against TIDAL backend. "
                    f"Skipping '{name_builder_item(media)}'. "
                    f"Consider to activate delay between downloads."
                )
                trace_event(
                    "stream_info",
                    "failed_too_many_requests",
                    expected=("TIDAL backend accepts stream request"),
                    actual=f"media_id={getattr(media, 'id', '')}",
                    op_id=op_id,
                )
                return None, "", False, None

            except (RequestException, ValueError):
                self.fn_logger.exception(
                    f"Something went wrong. Skipping "
                    f"'{name_builder_item(media)}'."
                )
                trace_event(
                    "stream_info",
                    "failed_exception",
                    expected="stream info resolution succeeds",
                    actual=f"media_id={getattr(media, 'id', '')}",
                    op_id=op_id,
                )
                return None, "", False, None

        elapsed = time.monotonic() - started_at
        trace_event(
            "stream_info",
            "end",
            expected="stream info resolved and lock released",
            actual=f"elapsed_sec={elapsed:.3f}, extension={file_extension}",
            op_id=op_id,
            level=logging.DEBUG,
        )

        return stream_manifest, file_extension, do_flac_extract, media_stream

    def _get_track_stream_info(self, media: Track) -> TrackStreamInfo:
        """Gets stream info for a Track, handling Atmos/Normal session
        switching.

        Args:
            media: The track to get stream information for.

        Returns:
            TrackStreamInfo: Container with stream manifest, file
                            extension, FLAC extraction flag, and media
                            stream object.
                            Returns TrackStreamInfo with None/empty
                            values if fails.
        """
        # Resolve the user's configured audio quality. Atmos streams are
        # delivered as AAC 320 (E-AC-3 JOC), which is a *lower* bitrate than
        # true lossless.
        # Therefore, when the user explicitly requests a lossless tier
        # (high_lossless / hi_res_lossless), we must NOT switch to the Atmos
        # session — doing so would silently downgrade their choice to AAC 320.
        # Atmos is only honored when the requested quality is a lossy tier
        # (low_96k / low_320k), where the immersive AAC stream is comparable.
        # `self.settings.data.quality_audio` is a `tidalapi.Quality`
        # enum object (dataclasses_json reconstructs the enum on load).
        # Pass its string *value* so the comparison and any quality
        # resolution use the correct tier.
        quality_requested: Quality = Quality(
            self.settings.data.quality_audio.value
        )
        is_lossless_requested = quality_requested in (
            Quality.high_lossless,
            Quality.hi_res_lossless,
        )

        want_atmos = (
            self.settings.data.download_dolby_atmos
            and not is_lossless_requested
            and hasattr(media, "audio_modes")
            and media.audio_modes
            and str(AudioMode.dolby_atmos) in media.audio_modes
        )

        trace_event(
            "track_stream_info",
            "quality_decision",
            expected=("honor user's configured audio quality"),
            actual=(
                f"requested={str(quality_requested)}, "
                f"is_lossless={is_lossless_requested}, "
                f"download_dolby_atmos="
                f"{self.settings.data.download_dolby_atmos}, "
                f"want_atmos={want_atmos}"
            ),
            op_id=new_operation_id("track_stream_info"),
            level=logging.DEBUG,
        )

        if want_atmos:
            if not self.tidal.switch_to_atmos_session():
                self.fn_logger.error(
                    f"Failed to switch to Atmos session for track: {media.id}"
                )
                return TrackStreamInfo(None, "", False, None)
        elif not self.tidal.restore_normal_session():
            self.fn_logger.error(
                f"Failed to restore normal session for track: {media.id}"
            )
            return TrackStreamInfo(None, "", False, None)

        if (media_stream := self._fetch_track_stream(media)) is None:
            return TrackStreamInfo(None, "", False, None)

        stream_manifest: StreamManifest = media_stream.get_stream_manifest()
        file_extension = stream_manifest.file_extension or ""
        requires_flac_extraction = False

        if self.settings.data.extract_flac and (
            str(stream_manifest.codecs).upper() == Codec.FLAC
            and file_extension != AudioExtensions.FLAC
        ):
            file_extension = AudioExtensions.FLAC
            requires_flac_extraction = True

        return TrackStreamInfo(
            stream_manifest=stream_manifest,
            file_extension=file_extension or "",
            requires_flac_extraction=requires_flac_extraction,
            media_stream=media_stream,
        )

    def _fetch_track_stream(self, media: Track) -> Stream | None:
        """Fetch the media stream for a track with retry logic.

        Args:
            media: The track to fetch the stream for.

        Returns:
            The resolved media stream, or None after all retries fail.
        """
        media_stream: Stream | None = None
        last_error: Exception | None = None

        for attempt in range(1, STREAM_INFO_RETRY_TOTAL + 1):
            try:
                # Re-fetch track each attempt to avoid stale state and
                # improve API compatibility.
                track_for_stream = self.session.track(
                    str(media.id), with_album=True
                )

                try:
                    media_stream = cast(
                        "Stream | None", track_for_stream.get_stream()
                    )
                except TypeError:
                    # Compatibility path for tidalapi variants that
                    # require explicit quality.
                    track_any: Any = track_for_stream
                    media_stream = cast(
                        "Stream | None",
                        track_any.get_stream(
                            quality=self.session.audio_quality
                        ),
                    )

                if media_stream is not None:
                    break
            except (RequestException, TooManyRequests) as error:
                last_error = error
                self.fn_logger.warning(
                    f"Stream fetch retry {attempt}/"
                    f"{STREAM_INFO_RETRY_TOTAL} for track "
                    f"{media.id} failed: {error}"
                )
                if attempt < STREAM_INFO_RETRY_TOTAL:
                    time.sleep(float(attempt))

        if media_stream is None:
            self.fn_logger.error(
                f"Failed to fetch stream info for track "
                f"{media.id} after retries: {last_error}"
            )

        return media_stream

    def _perform_actual_download(
        self,
        media: Track | Video,
        path_media_dst: pathlib.Path,
        stream_info: TrackStreamInfo,
        is_parent_album: bool,
    ) -> bool:
        """Perform the actual download and processing.

        Args:
            media (Track | Video): Media item.
            path_media_dst (pathlib.Path): Destination file path.
            stream_info (TrackStreamInfo): Resolved stream details.
            is_parent_album (bool): Whether this is a parent album.

        Returns:
            bool: Whether download was successful.
        """
        # Create a temp directory and file.
        with tempfile.TemporaryDirectory(
            ignore_cleanup_errors=True
        ) as tmp_path_dir:
            tmp_path_file: pathlib.Path = pathlib.Path(tmp_path_dir) / str(
                uuid4()
            )
            tmp_path_file.touch()

            # Download media.
            result_download, tmp_path_file = self._download(
                media=media,
                stream_manifest=stream_info.stream_manifest,
                path_file=tmp_path_file,
            )

            if not result_download:
                return False

            # Convert video from TS to MP4
            if (
                isinstance(media, Video)
                and self.settings.data.video_convert_mp4
            ):
                tmp_path_file = self._video_convert(tmp_path_file)

            # Extract FLAC from MP4 container using ffmpeg
            if (
                isinstance(media, Track)
                and self.settings.data.extract_flac
                and stream_info.requires_flac_extraction
            ):
                tmp_path_file = self._extract_flac(tmp_path_file)

            # Handle metadata, lyrics, and cover
            self._handle_metadata_and_extras(
                media,
                tmp_path_file,
                path_media_dst,
                is_parent_album,
                stream_info.media_stream,
            )

            self.fn_logger.info(
                f"Downloaded item '{name_builder_item(media)}'."
            )

            # Move final file to the configured destination directory.
            shutil.move(tmp_path_file, path_media_dst)

            return True

    def _handle_metadata_and_extras(
        self,
        media: Track | Video,
        tmp_path_file: pathlib.Path,
        path_media_dst: pathlib.Path,
        is_parent_album: bool,
        media_stream: Stream | None,
    ) -> None:
        """Handle metadata, lyrics, and cover processing.

        Args:
            media (Track | Video): Media item.
            tmp_path_file (pathlib.Path): Temporary file path.
            path_media_dst (pathlib.Path): Destination file path.
            is_parent_album (bool): Whether this is a parent album.
            media_stream (Stream | None): Media stream.
        """
        if isinstance(media, Video):
            return

        tmp_path_lyrics: pathlib.Path | None = None
        tmp_path_cover: pathlib.Path | None = None

        # Write metadata to file.
        if media_stream:
            _result_metadata, tmp_path_lyrics, tmp_path_cover = (
                self.metadata_write(
                    media, tmp_path_file, is_parent_album, media_stream
                )
            )

        # Move lyrics file
        if self.settings.data.lyrics_file and tmp_path_lyrics:
            self._move_lyrics(tmp_path_lyrics, path_media_dst)

        # Move cover file
        if self.settings.data.cover_album_file and tmp_path_cover:
            self._move_cover(tmp_path_cover, path_media_dst)

    def _perform_post_processing(
        self,
        media: Track | Video,
        path_media_dst: pathlib.Path,
        quality: QualityState,
        download_delay: bool,
        skip_file: bool,
    ) -> None:
        """Perform post-processing tasks.

        Args:
            media (Track | Video): Media item.
            path_media_dst (pathlib.Path): Destination file path.
            quality (QualityState): Quality settings for this item.
            download_delay (bool): Whether to apply download delay.
            skip_file (bool): Whether file was skipped.
        """
        # If files needs to be symlinked, do postprocessing here.
        if self.settings.data.symlink_to_track and not isinstance(
            media, Video
        ):
            # Determine file extension for symlink
            file_extension = path_media_dst.suffix
            self.media_move_and_symlink(media, path_media_dst, file_extension)

        # Reset quality settings
        if quality.quality_audio_old is not None:
            self.adjust_quality_audio(quality.quality_audio_old)

        if quality.quality_video_old is not None:
            self.adjust_quality_video(quality.quality_video_old)

        # Apply download delay if needed
        if (
            download_delay
            and not skip_file
            and self.runtime.event_abort is not None
            and not self.runtime.event_abort.is_set()
        ):
            time_sleep: float = round(
                random.SystemRandom().uniform(
                    self.settings.data.download_delay_sec_min,
                    self.settings.data.download_delay_sec_max,
                ),
                1,
            )

            self.fn_logger.debug(
                f"Next download will start in {time_sleep} seconds."
            )
            time.sleep(time_sleep)

    def media_move_and_symlink(
        self,
        media: Track | Video,
        path_media_src: pathlib.Path,
        file_extension: str,
    ) -> pathlib.Path:
        """Move a media file and create a symlink if required.

        Args:
            media (Track | Video): Media item.
            path_media_src (pathlib.Path): Source file path.
            file_extension (str): File extension.

        Returns:
            pathlib.Path: Destination path.
        """
        # Compute tracks path, sanitize and ensure path exists
        file_name_relative: str = format_path_media(
            self.settings.data.format_track,
            media,
            delimiter_artist=(self.settings.data.filename_delimiter_artist),
            delimiter_album_artist=(
                self.settings.data.filename_delimiter_album_artist
            ),
            use_primary_album_artist=(
                self.settings.data.use_primary_album_artist
            ),
        )
        path_media_dst: pathlib.Path = (
            pathlib.Path(self.params.path_base).expanduser()
            / (file_name_relative + file_extension)
        ).absolute()
        path_media_dst = pathlib.Path(
            path_file_sanitize(path_media_dst, adapt=True)
        )

        os.makedirs(path_media_dst.parent, exist_ok=True)

        # Move item and symlink it
        if path_media_dst != path_media_src:
            if self.params.skip_existing:
                skip_file: bool = check_file_exists(
                    path_media_dst, extension_ignore=False
                )
                skip_symlink: bool = path_media_src.is_symlink()
            else:
                skip_file = False
                skip_symlink = False

            if not skip_file:
                self.fn_logger.debug(
                    f"Move: {path_media_src} -> {path_media_dst}"
                )
                shutil.move(path_media_src, path_media_dst)

            if not skip_symlink:
                self.fn_logger.debug(
                    f"Symlink: {path_media_src} -> {path_media_dst}"
                )
                path_media_dst_relative: pathlib.Path = (
                    path_media_dst.relative_to(
                        path_media_src.parent, walk_up=True
                    )
                )

                path_media_src.unlink(missing_ok=True)
                path_media_src.symlink_to(path_media_dst_relative)

        return path_media_dst

    def adjust_quality_audio(self, quality: Quality) -> Quality:
        """Temporarily set audio quality and return the previous value.

        Args:
            quality (Quality): New audio quality.

        Returns:
            Quality: Previous audio quality.
        """
        # Save original quality settings
        quality_old = cast("Quality", self.session.audio_quality)
        self.session.audio_quality = quality

        return quality_old

    def adjust_quality_video(self, quality: QualityVideo) -> QualityVideo:
        """Temporarily set video quality and return the previous value.

        Args:
            quality (QualityVideo): New video quality.

        Returns:
            QualityVideo: Previous video quality.
        """
        quality_old: QualityVideo = self.settings.data.quality_video

        self.settings.data.quality_video = quality

        return quality_old

    def _move_file(
        self,
        path_file_source: pathlib.Path,
        path_file_destination: str | pathlib.Path,
    ) -> bool:
        """Move a file from source to destination.

        Args:
            path_file_source (pathlib.Path): Source file path.
            path_file_destination (str | pathlib.Path): Destination file path.

        Returns:
            bool: True if moved, False otherwise.
        """
        result: bool

        # Check if the file was downloaded
        if path_file_source and path_file_source.is_file():
            # Move it.
            shutil.move(path_file_source, path_file_destination)

            result = True
        else:
            result = False

        return result

    def _move_lyrics(
        self, path_lyrics: pathlib.Path, file_media_dst: pathlib.Path
    ) -> bool:
        """Move a lyrics file to the destination.

        Args:
            path_lyrics (pathlib.Path): Source lyrics file.
            file_media_dst (pathlib.Path): Destination media file path.

        Returns:
            bool: True if moved, False otherwise.
        """
        # Build tmp lyrics filename
        path_file_lyrics: pathlib.Path = file_media_dst.with_suffix(
            EXTENSION_LYRICS
        )
        result: bool = self._move_file(path_lyrics, path_file_lyrics)

        return result

    def _move_cover(
        self, path_cover: pathlib.Path, file_media_dst: pathlib.Path
    ) -> bool:
        """Move a cover file to the destination.

        Args:
            path_cover (pathlib.Path): Source cover file.
            file_media_dst (pathlib.Path): Destination media file path.

        Returns:
            bool: True if moved, False otherwise.
        """
        # Build tmp lyrics filename
        path_file_cover: pathlib.Path = file_media_dst.parent / COVER_NAME
        result: bool = self._move_file(path_cover, path_file_cover)

        return result

    def lyrics_to_file(
        self, dir_destination: pathlib.Path, lyrics: str
    ) -> str:
        """Write lyrics to a temporary file.

        Args:
            dir_destination (pathlib.Path): Directory for the temp file.
            lyrics (str): Lyrics content.

        Returns:
            str: Path to the temp file.
        """
        return self.write_to_tmp_file(
            dir_destination, mode="x", content=lyrics
        )

    def cover_to_file(
        self, dir_destination: pathlib.Path, image: bytes
    ) -> str:
        """Write cover image to a temporary file.

        Args:
            dir_destination (pathlib.Path): Directory for the temp file.
            image (bytes): Image data.

        Returns:
            pathlib.Path: Path to the temp file.
        """
        return self.write_to_tmp_file(
            dir_destination, mode="xb", content=image
        )

    def write_to_tmp_file(
        self, dir_destination: pathlib.Path, mode: str, content: str | bytes
    ) -> str:
        """Write content to a temporary file.

        Args:
            dir_destination (pathlib.Path): Directory for the temp file.
            mode (str): File open mode.
            content (str | bytes): Content to write.

        Returns:
            str: Path to the temp file.
        """
        result: pathlib.Path = dir_destination / str(uuid4())
        encoding: str | None = "utf-8" if isinstance(content, str) else None

        try:
            with open(result, mode=mode, encoding=encoding) as f:
                f.write(content)
        except OSError:
            return ""

        return str(result)

    @staticmethod
    def cover_data(
        url: str | None = None,
        path_file: str | None = None,
    ) -> str | bytes:
        """Retrieve cover image data from a URL or file.

        Args:
            url (str | None, optional): URL to download image
                from. Defaults to None.
            path_file (str | None, optional): Path to image
                file. Defaults to None.

        Returns:
            str | bytes: Image data or empty string on failure.
        """
        result: str | bytes = ""

        if url:
            response: requests.Response | None = None
            try:
                response = requests.get(url, timeout=REQUESTS_TIMEOUT_SEC)
                result = response.content
            except RequestException:
                pass
            finally:
                if response is not None:
                    response.close()
        elif path_file:
            try:
                with open(path_file, "rb") as f:
                    result = f.read()
            except OSError:
                pass

        return result

    def _video_convert(self, path_file: pathlib.Path) -> pathlib.Path:
        """Convert a TS video file to MP4 using ffmpeg.

        Args:
            path_file (pathlib.Path): Path to the TS file.

        Returns:
            pathlib.Path: Path to the converted MP4 file.
        """
        path_file_out: pathlib.Path = path_file.with_suffix(
            AudioExtensions.MP4
        )

        self.fn_logger.debug(
            f"Converting video: {path_file.name} -> {path_file_out.name}"
        )

        ffmpeg_cmd: Any = FFmpeg(
            executable=self.settings.data.path_binary_ffmpeg
        )
        ffmpeg_cmd.option("y").option("hide_banner").option("nostdin").input(
            url=path_file
        ).output(url=path_file_out, codec="copy", map=0, loglevel="quiet")

        ffmpeg_cmd.execute()

        self.fn_logger.debug(
            f"Video conversion complete: {path_file_out.name}"
        )

        return path_file_out

    def _extract_flac(self, path_media_src: pathlib.Path) -> pathlib.Path:
        """Extract FLAC audio from a media file using ffmpeg.

        Args:
            path_media_src (pathlib.Path): Path to the source media file.

        Returns:
            pathlib.Path: Path to the extracted FLAC file.
        """
        path_media_out = path_media_src.with_suffix(AudioExtensions.FLAC)

        self.fn_logger.debug(
            f"Extracting FLAC: {path_media_src.name} -> {path_media_out.name}"
        )

        ffmpeg_cmd: Any = FFmpeg(
            executable=self.settings.data.path_binary_ffmpeg
        )
        ffmpeg_cmd.option("hide_banner").option("nostdin").input(
            url=path_media_src
        ).output(
            url=path_media_out,
            map=0,
            movflags="use_metadata_tags",
            acodec="copy",
            map_metadata="0:g",
            loglevel="quiet",
        )

        ffmpeg_cmd.execute()

        self.fn_logger.debug(
            f"FLAC extraction complete: {path_media_out.name}"
        )

        return path_media_out

    def _extract_video_stream(
        self,
        m3u8_variant: Any,
        quality: int,
    ) -> tuple[Any, str]:
        """Extract the best matching video stream from an m3u8 variant
        playlist.

        Args:
            m3u8_variant (m3u8.M3U8): The m3u8 variant playlist.
            quality (int): Desired video quality (vertical resolution).

        Returns:
            tuple[Any, str]: (Selected m3u8 playlist or False, codecs string)
        """
        m3u8_playlist: Any = False
        resolution_best: int = 0
        mime_type: str = ""

        if m3u8_variant.is_variant:
            for playlist in m3u8_variant.playlists:
                if resolution_best < playlist.stream_info.resolution[1]:
                    resolution_best = playlist.stream_info.resolution[1]
                    m3u8_playlist = m3u8.load(playlist.uri)
                    mime_type = playlist.stream_info.codecs

                    if quality == playlist.stream_info.resolution[1]:
                        break

        return m3u8_playlist, mime_type
