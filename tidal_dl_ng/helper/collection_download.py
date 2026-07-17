"""Collection (album/playlist/mix) download orchestration for TIDAL.

This module provides the `CollectionDownloadMixin` class, which groups
the logic for downloading all items in a collection, scheduling worker
futures, and populating playlist (m3u) files. It is implemented as a
mixin so the methods keep accessing `self.settings`, `self.runtime`,
`self.tidal`, `self.item`, and the other helpers defined on `Download`.
"""

import logging
import os
import pathlib
from concurrent import futures
from typing import Any, cast

from rich.progress import Progress, TaskID
from tidalapi.album import Album
from tidalapi.media import Track, Video
from tidalapi.mix import Mix
from tidalapi.playlist import Playlist, UserPlaylist

from tidal_dl_ng.constants import (
    AudioExtensionsValid,
    PLAYLIST_EXTENSION,
    PLAYLIST_PREFIX,
)
from tidal_dl_ng.helper.path import (
    format_path_media,
    path_file_sanitize,
    sanitize_filename,
)
from tidal_dl_ng.helper.tidal import items_results_all, name_builder_title
from tidal_dl_ng.model.downloader import (
    CollectionDownloadRequest,
    ItemRequest,
    ProgressHandles,
)
from tidal_dl_ng.helper.download_protocol import DownloadProtocol
from tidal_dl_ng.runtime_trace import new_operation_id, trace_event


class CollectionDownloadMixin(DownloadProtocol):
    """Mixin providing collection download orchestration helpers."""

    def items(
        self,
        request: ItemRequest,
    ) -> None:
        """Download all items in an album, playlist, or mix.

        Args:
            request (ItemRequest): All parameters for this collection.
        """
        media: Track | Video | Album | Playlist | UserPlaylist | Mix | None = (
            request.media
        )

        # Validate and prepare media collection
        validated_media = self._validate_and_prepare_media(
            media,
            request.media_id,
            request.media_type,
            request.video_download,
        )
        if validated_media is None or not isinstance(
            validated_media, Album | Playlist | UserPlaylist | Mix
        ):
            return

        media = validated_media

        # Set up download context
        download_context = self._setup_collection_download_context(
            media, request.file_template, request.video_download
        )
        (
            file_name_relative,
            list_media_name,
            list_media_name_short,
            items,
            progress_stdout,
        ) = download_context

        # Set up progress tracking
        progress: Progress | None = (
            self.runtime.progress_overall or self.runtime.progress
        )
        assert progress is not None
        progress_task: TaskID = progress.add_task(
            f"[green]List '{list_media_name_short}'",
            total=len(items),
            visible=progress_stdout,
        )

        # Download configuration
        is_album: bool = isinstance(media, Album)

        # Execute downloads
        result_dirs: list[pathlib.Path] = self._execute_collection_downloads(
            items,
            CollectionDownloadRequest(
                file_name_relative=file_name_relative,
                quality_audio=request.quality_audio,
                quality_video=request.quality_video,
                download_delay=request.download_delay,
                is_album=is_album,
                list_total=len(items),
                source_type=request.source_type,
                source_id=request.source_id,
                source_name=request.source_name,
            ),
            ProgressHandles(
                progress=progress,
                progress_task=progress_task,
                progress_stdout=progress_stdout,
            ),
        )

        # Create playlist file if requested
        if self.settings.data.playlist_create:
            self.playlist_populate(
                set(result_dirs),
                list_media_name,
                is_album,
                bool(
                    "album_track_num" in file_name_relative
                    or "list_pos" in file_name_relative
                ),
            )

        self.fn_logger.info(f"Finished list '{list_media_name}'.")

    def _setup_collection_download_context(
        self,
        media: Album | Playlist | UserPlaylist | Mix,
        file_template: str,
        video_download: bool,
    ) -> tuple[str, str, str, list[Any], bool]:
        """Set up download context for media collection.

        Args:
            media (Album | Playlist | UserPlaylist | Mix): Media
                collection.
            file_template (str): Template for file naming.
            video_download (bool): Whether to allow video downloads.

        Returns:
            tuple[str, str, str, list[Any], bool]: (
                file_name_relative, list_media_name,
                list_media_name_short, items, progress_stdout
            )
        """
        # Create file name and path
        file_name_relative: str = format_path_media(
            file_template,
            media,
            delimiter_artist=(self.settings.data.filename_delimiter_artist),
            delimiter_album_artist=(
                self.settings.data.filename_delimiter_album_artist
            ),
            use_primary_album_artist=(
                self.settings.data.use_primary_album_artist
            ),
        )

        # Get the name of the list and check, if videos should be included.
        list_media_name: str = name_builder_title(media)
        list_media_name_short: str = list_media_name[:30]

        # Get all items of the list.
        items = items_results_all(
            self.tidal.session, media, videos_include=video_download
        )

        # Determine where to redirect the progress information.
        progress_stdout: bool = True
        if self.runtime.progress_gui is not None:
            progress_stdout = False

            cast("Any", self.runtime.progress_gui.list_name).emit(
                list_media_name_short
            )

        return (
            file_name_relative,
            list_media_name,
            list_media_name_short,
            items,
            progress_stdout,
        )

    def _execute_collection_downloads(
        self,
        items: list[Any],
        request: CollectionDownloadRequest,
        progress_handles: ProgressHandles,
    ) -> list[pathlib.Path]:
        """Execute downloads for all items in the collection.

        Args:
            items (list[Any]): List of media items to download.
            request (CollectionDownloadRequest): Download parameters.
            progress_handles (ProgressHandles): Progress bar handles.

        Returns:
            list[pathlib.Path]: List of result directories.
        """
        progress: Progress = progress_handles.progress
        progress_task: TaskID = progress_handles.progress_task
        progress_stdout: bool = progress_handles.progress_stdout

        result_dirs: list[pathlib.Path] = []
        op_id = new_operation_id("collection")
        trace_event(
            "collection_download",
            "start",
            expected="schedule item workers and consume their futures",
            actual=(
                f"items={len(items)}, "
                f"max_workers="
                f"{self.settings.data.downloads_concurrent_max}"
            ),
            op_id=op_id,
        )

        # Check if items list is empty
        if not items:
            # Mark progress as complete for empty lists
            progress.update(
                progress_task, completed=progress.tasks[progress_task].total
            )

            if not progress_stdout and self.runtime.progress_gui is not None:
                cast("Any", self.runtime.progress_gui.list_item).emit(100.0)

            trace_event(
                "collection_download",
                "empty_collection",
                expected="at least one item to download",
                actual="items=0",
                op_id=op_id,
            )

            return result_dirs

        # Iterate through list items
        while not progress.finished:
            with futures.ThreadPoolExecutor(
                max_workers=self.settings.data.downloads_concurrent_max
            ) as executor:
                # Dispatch all download tasks to worker threads
                download_futures: list[futures.Future[Any]] = [
                    executor.submit(
                        self.item,
                        ItemRequest(
                            media=item_media,
                            file_template=request.file_name_relative,
                            quality_audio=request.quality_audio,
                            quality_video=request.quality_video,
                            download_delay=request.download_delay,
                            is_parent_album=request.is_album,
                            list_position=count + 1,
                            list_total=request.list_total,
                            source_type=request.source_type,
                            source_id=request.source_id,
                            source_name=request.source_name,
                        ),
                    )
                    for count, item_media in enumerate(items)
                ]

                # Process download results
                result_dirs = self._process_download_futures(
                    download_futures, progress, progress_task, progress_stdout
                )
                trace_event(
                    "collection_download",
                    "futures_processed",
                    expected="all scheduled futures complete",
                    actual=f"completed_dirs={len(result_dirs)}",
                    op_id=op_id,
                    level=logging.DEBUG,
                )

                # Check for abort signal
                if self.runtime.event_abort is not None and (
                    self.runtime.event_abort.is_set()
                ):
                    trace_event(
                        "collection_download",
                        "aborted",
                        expected="collection completes normally",
                        actual="event_abort set",
                        op_id=op_id,
                    )
                    return result_dirs

        trace_event(
            "collection_download",
            "end",
            expected="collection loop exits after completion",
            actual=f"result_dirs={len(result_dirs)}",
            op_id=op_id,
        )
        return result_dirs

    def _create_download_futures(
        self,
        items: list[Any],
        request: CollectionDownloadRequest,
    ) -> list[futures.Future[Any]]:
        """Create download futures for all items in the collection.

        Args:
            items (list[Any]): List of media items to download.
            request (CollectionDownloadRequest): Download parameters.

        Returns:
            list[futures.Future[Any]]: List of download futures.
        """
        with futures.ThreadPoolExecutor(
            max_workers=self.settings.data.downloads_concurrent_max
        ) as executor:
            return [
                executor.submit(
                    self.item,
                    ItemRequest(
                        media=item_media,
                        file_template=request.file_name_relative,
                        quality_audio=request.quality_audio,
                        quality_video=request.quality_video,
                        download_delay=request.download_delay,
                        is_parent_album=request.is_album,
                        list_position=count + 1,
                        list_total=request.list_total,
                    ),
                )
                for count, item_media in enumerate(items)
            ]

    def _process_download_futures(
        self,
        futures_list: list[futures.Future[Any]],
        progress: Progress,
        progress_task: TaskID,
        progress_stdout: bool,
    ) -> list[pathlib.Path]:
        """Process download futures and collect results.

        Args:
            futures_list (list[futures.Future[Any]]): List of download
                futures.
            progress (Progress): Progress bar instance.
            progress_task (TaskID): Progress task ID.
            progress_stdout (bool): Whether to show progress in stdout.

        Returns:
            list[pathlib.Path]: List of result directories.
        """
        result_dirs: list[pathlib.Path] = []

        # Report results as they become available
        for future in futures.as_completed(futures_list):
            # Retrieve result
            _status, result_path_file = future.result()

            if result_path_file:
                result_dirs.append(result_path_file.parent)

            # Advance progress bar.
            progress.advance(progress_task)

            if not progress_stdout and self.runtime.progress_gui is not None:
                cast("Any", self.runtime.progress_gui.list_item).emit(
                    progress.tasks[progress_task].percentage
                )

            # If app is terminated (CTRL+C)
            if self.runtime.event_abort is not None and (
                self.runtime.event_abort.is_set()
            ):
                # Cancel all not yet started tasks
                for f in futures_list:
                    f.cancel()

                break

        return result_dirs

    def playlist_populate(
        self,
        dirs_scoped: set[pathlib.Path],
        name_list: str,
        is_album: bool,
        sort_alphabetically: bool,
    ) -> list[pathlib.Path]:
        """Create playlist files (m3u) for downloaded tracks.

        Args:
            dirs_scoped (set[pathlib.Path]): Set of directories with tracks.
            name_list (str): Name of the playlist.
            is_album (bool): Whether this is an album.
            sort_alphabetically (bool): Sort tracks alphabetically.

        Returns:
            list[pathlib.Path]: List of created playlist file paths.
        """
        result: list[pathlib.Path] = []

        # For each dir, which contains tracks
        for dir_scoped in dirs_scoped:
            # Sanitize final playlist name to fit into OS boundaries.
            path_playlist = dir_scoped / sanitize_filename(
                PLAYLIST_PREFIX + name_list + PLAYLIST_EXTENSION
            )
            path_playlist = pathlib.Path(
                path_file_sanitize(path_playlist, adapt=True)
            )

            self.fn_logger.debug(f"Playlist: Creating {path_playlist}")

            # Get all tracks in the directory
            path_tracks: list[pathlib.Path] = []

            for extension_audio in AudioExtensionsValid:
                path_tracks = path_tracks + list(
                    dir_scoped.glob(f"*{extension_audio!s}")
                )

            # Sort alphabetically, e.g. if items are prefixed with numbers
            if sort_alphabetically:
                path_tracks.sort()
            elif not is_album:
                # If it is not an album sort by creation time
                path_tracks.sort(
                    key=lambda x: (
                        getattr(x.stat(), "st_birthtime", None)
                        or getattr(x.stat(), "st_ctime")
                    )
                )

            # Write data to m3u file
            with path_playlist.open(mode="w", encoding="utf-8") as f:
                for path_track in path_tracks:
                    # If it's a symlink write the relative file path
                    # to the actual track into the playlist file
                    if path_track.is_symlink():
                        media_file_target = path_track.resolve().relative_to(
                            path_track.parent, walk_up=True
                        )
                    else:
                        media_file_target = pathlib.Path(path_track.name)

                    f.write(str(media_file_target) + os.linesep)

            result.append(path_playlist)

        return result
