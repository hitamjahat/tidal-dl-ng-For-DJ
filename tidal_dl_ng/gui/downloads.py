"""Downloads mixin for MainWindow.

Handles download queue and download operations.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, cast

from PySide6 import QtCore, QtWidgets
from tidalapi.album import Album
from tidalapi.artist import Artist
from tidalapi.media import Quality, Track, Video
from tidalapi.mix import Mix
from tidalapi.playlist import Playlist, UserPlaylist

from tidal_dl_ng.config import HandlingApp
from tidal_dl_ng.constants import QualityVideo, QueueDownloadStatus
from tidal_dl_ng.download import Download
from tidal_dl_ng.helper import path as path_helper
from tidal_dl_ng.helper import tidal as tidal_helper
from tidal_dl_ng.helper.gui import (
    get_queue_download_media,
    get_queue_download_quality_audio,
    get_queue_download_quality_video,
    get_results_media_item,
    set_queue_download_media,
)
from tidal_dl_ng.logger import logger_gui
from tidal_dl_ng.model.gui_data import QueueDownloadItem, StatusbarMessage

if TYPE_CHECKING:
    from tidal_dl_ng.config import Settings, Tidal


class DownloadsMixin:
    """Mixin containing download-related methods."""

    # Attributes provided by MainWindow runtime composition.
    tr_results: QtWidgets.QTreeView
    tr_queue_download: QtWidgets.QTreeWidget
    proxy_tr_results: Any
    model_tr_results: Any
    search_manager: Any
    tidal: Tidal
    settings: Settings
    dl: Download
    s_queue_download_item_downloading: Any
    s_queue_download_item_finished: Any
    s_queue_download_item_failed: Any
    s_queue_download_item_skipped: Any
    s_pb_reset: Any
    s_statusbar_message: Any

    @staticmethod
    def _ensure_tidal_session(tidal: Tidal) -> bool:
        """Ensure TIDAL session is authenticated before API operations."""
        try:
            if tidal.session.check_login():
                return True
        except Exception:
            logger_gui.warning(
                "TIDAL session check failed. Attempting token recovery..."
            )

        with_error = False
        try:
            if tidal.login_token():
                logger_gui.info("TIDAL session recovered via stored token.")
                return True
        except Exception:
            with_error = True

        if with_error:
            logger_gui.exception("Failed to recover TIDAL session via token.")

        return False

    def _get_settings_flags(self) -> tuple[bool, bool]:
        """Safely resolve download-related settings flags."""
        settings_data = cast(Any, self.settings.data)
        video_download = bool(getattr(settings_data, "video_download", True))
        download_delay = bool(getattr(settings_data, "download_delay", False))
        return video_download, download_delay

    @staticmethod
    def _resolve_source_info(
        media: Track | Album | Playlist | UserPlaylist | Video | Mix,
    ) -> tuple[str, str | None, str | None]:
        """Resolve source metadata used for history and tracking."""
        source_type = "manual"
        source_id: str | None = None
        source_name: str | None = None

        if isinstance(media, Album):
            source_type = "album"
            source_id = str(media.id)
            source_name = media.name
        elif isinstance(media, Playlist | UserPlaylist):
            source_type = "playlist"
            source_id = str(media.id) if hasattr(media, "id") else None
            source_name = media.name if hasattr(media, "name") else None
        elif isinstance(media, Mix):
            source_type = "mix"
            source_id = str(media.id)
            source_name = media.title
        elif isinstance(media, Track):
            if hasattr(media, "album") and media.album:
                source_type = "album"
                source_id = str(media.album.id)
                source_name = media.album.name
            else:
                source_type = "track"
                source_id = str(media.id)
                source_name = media.name

        return source_type, source_id, source_name

    def on_download_results(self) -> None:
        """Download the selected results in the results tree."""
        items = self.tr_results.selectionModel().selectedRows()

        if len(items) == 0:
            logger_gui.error("Please select a row first.")
        else:
            for item in items:
                media = get_results_media_item(
                    item, self.proxy_tr_results, self.model_tr_results
                )
                queue_dl_item = (
                    self.search_manager.media_to_queue_download_model(media)
                )

                if queue_dl_item:
                    self.queue_download_media(queue_dl_item)

    def queue_download_media(self, queue_dl_item: QueueDownloadItem) -> None:
        """Add a media item to the download queue."""
        child: QtWidgets.QTreeWidgetItem = QtWidgets.QTreeWidgetItem()

        child.setText(0, queue_dl_item.status)
        set_queue_download_media(
            child,
            cast(
                Track | Album | Playlist | UserPlaylist | Video | Mix | Artist,
                queue_dl_item.obj,
            ),
        )
        child.setText(2, queue_dl_item.name)
        child.setText(3, queue_dl_item.type_media)
        child.setText(4, str(queue_dl_item.quality_audio))
        child.setText(5, str(queue_dl_item.quality_video))
        self.tr_queue_download.addTopLevelItem(child)

    def watcher_queue_download(self) -> None:
        """Monitor the download queue and process items as they become available."""
        handling_app = cast(Any, HandlingApp)()

        while not handling_app.event_abort.is_set():
            items = self.tr_queue_download.findItems(
                QueueDownloadStatus.Waiting,
                QtCore.Qt.MatchFlag.MatchExactly,
                column=0,
            )

            if len(items) > 0:
                item: QtWidgets.QTreeWidgetItem = items[0]
                media = get_queue_download_media(item)
                quality_audio: Quality = get_queue_download_quality_audio(item)
                quality_video: QualityVideo = get_queue_download_quality_video(
                    item
                )

                try:
                    if not self._ensure_tidal_session(self.tidal):
                        self.s_statusbar_message.emit(
                            StatusbarMessage(
                                message="Session expired - please login again.",
                                timeout=5000,
                            )
                        )
                        self.s_queue_download_item_failed.emit(item)
                        continue

                    self.s_queue_download_item_downloading.emit(item)
                    result = self.on_queue_download(
                        media,
                        quality_audio=quality_audio,
                        quality_video=quality_video,
                    )

                    if result == QueueDownloadStatus.Finished:
                        self.s_queue_download_item_finished.emit(item)
                    elif result == QueueDownloadStatus.Skipped:
                        self.s_queue_download_item_skipped.emit(item)
                except Exception as e:
                    logger_gui.error(e)
                    self.s_queue_download_item_failed.emit(item)
            else:
                time.sleep(2)

    def on_queue_download_item_downloading(
        self, item: QtWidgets.QTreeWidgetItem
    ) -> None:
        """Update the status of a queue download item to 'Downloading'."""
        self.queue_download_item_status(item, QueueDownloadStatus.Downloading)

    def on_queue_download_item_finished(
        self, item: QtWidgets.QTreeWidgetItem
    ) -> None:
        """Update the status of a queue download item to 'Finished'."""
        self.queue_download_item_status(item, QueueDownloadStatus.Finished)

    def on_queue_download_item_failed(
        self, item: QtWidgets.QTreeWidgetItem
    ) -> None:
        """Update the status of a queue download item to 'Failed'."""
        self.queue_download_item_status(item, QueueDownloadStatus.Failed)

    def on_queue_download_item_skipped(
        self, item: QtWidgets.QTreeWidgetItem
    ) -> None:
        """Update the status of a queue download item to 'Skipped'."""
        self.queue_download_item_status(item, QueueDownloadStatus.Skipped)

    def queue_download_item_status(
        self, item: QtWidgets.QTreeWidgetItem, status: str
    ) -> None:
        """Set the status text of a queue download item."""
        item.setText(0, status)

    def on_queue_download(
        self,
        media: Track | Album | Playlist | Video | Mix | Artist,
        quality_audio: Quality | None = None,
        quality_video: QualityVideo | None = None,
    ) -> QueueDownloadStatus:
        """Download the specified media item(s) and return the result status."""
        result: QueueDownloadStatus = QueueDownloadStatus.Skipped

        helper_any = cast(Any, tidal_helper)
        items_media: list[Track | Album | Playlist | Video | Mix | Artist]
        if isinstance(media, Artist):
            items_media = cast(
                list[Track | Album | Playlist | Video | Mix | Artist],
                helper_any.items_results_all(self.tidal.session, media),
            )
        else:
            items_media = [media]

        if not items_media:
            return QueueDownloadStatus.Skipped

        _video_download, download_delay_setting = self._get_settings_flags()
        download_delay: bool = bool(
            isinstance(media, Track | Video) and download_delay_setting
        )

        for item_media in items_media:
            result = self.download(
                item_media,
                self.dl,
                delay_track=download_delay,
                quality_audio=quality_audio,
                quality_video=quality_video,
            )

        return result

    def download(
        self,
        media: Track | Album | Playlist | UserPlaylist | Video | Mix | Artist,
        dl: Download,
        delay_track: bool = False,
        quality_audio: Quality | None = None,
        quality_video: QualityVideo | None = None,
    ) -> QueueDownloadStatus:
        """Download a media item and return the result status."""
        result_dl: bool = False
        path_file: str | Any = ""
        result: QueueDownloadStatus
        self.s_pb_reset.emit()
        self.s_statusbar_message.emit(
            StatusbarMessage(message="Download started...")
        )

        if isinstance(media, Artist):
            logger_gui.warning(
                "Artist should be resolved to concrete media items before calling download()."
            )
            return QueueDownloadStatus.Skipped

        path_helper_any = cast(Any, path_helper)
        file_template = path_helper_any.get_format_template(
            media, self.settings
        )
        if not isinstance(file_template, str) or not file_template:
            logger_gui.error(
                "Could not determine file template for selected media."
            )
            self.s_statusbar_message.emit(
                StatusbarMessage(
                    message="Download failed: invalid file template",
                    timeout=3000,
                )
            )
            return QueueDownloadStatus.Failed

        source_type, source_id, source_name = self._resolve_source_info(media)
        video_download_setting, download_delay_setting = (
            self._get_settings_flags()
        )

        if isinstance(media, Track | Video):
            result_dl, path_file = dl.item(
                media=media,
                file_template=file_template,
                download_delay=delay_track,
                quality_audio=quality_audio,
                quality_video=quality_video,
                source_type=source_type,
                source_id=source_id,
                source_name=source_name,
            )
        else:
            dl.items(
                media=media,
                file_template=file_template,
                video_download=video_download_setting,
                download_delay=download_delay_setting,
                quality_audio=quality_audio,
                quality_video=quality_video,
                source_type=source_type,
                source_id=source_id,
                source_name=source_name,
            )

            result_dl = True
            path_file = "dummy"

        self.s_statusbar_message.emit(
            StatusbarMessage(message="Download finished.", timeout=2000)
        )

        if result_dl and path_file:
            result = QueueDownloadStatus.Finished
        elif not result_dl and path_file:
            result = QueueDownloadStatus.Skipped
        else:
            result = QueueDownloadStatus.Failed

        return result
