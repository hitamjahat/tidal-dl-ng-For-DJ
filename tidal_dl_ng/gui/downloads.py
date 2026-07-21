"""Download orchestration shared by the main application window.

The queue manager owns queue state and widget updates.  This mixin converts
selected result rows into queue entries and provides the worker-safe service
methods that translate GUI download requests into downloader request models.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeGuard

from PySide6 import QtCore, QtGui, QtWidgets
from tidalapi.album import Album
from tidalapi.artist import Artist
from tidalapi.exceptions import TidalAPIError
from tidalapi.media import Quality, Track, Video
from tidalapi.mix import Mix
from tidalapi.playlist import Playlist, UserPlaylist

from tidal_dl_ng.config import HandlingApp
from tidal_dl_ng.constants import QualityVideo, QueueDownloadStatus
from tidal_dl_ng.helper.gui import get_results_media_item
from tidal_dl_ng.helper.path import get_format_template
from tidal_dl_ng.helper.tidal import items_results_all
from tidal_dl_ng.logger import logger_gui
from tidal_dl_ng.model.downloader import ItemRequest
from tidal_dl_ng.model.gui_data import QueueDownloadItem, StatusbarMessage

if TYPE_CHECKING:
    from tidal_dl_ng.config import Settings, Tidal
    from tidal_dl_ng.download import Download
    from tidal_dl_ng.gui.queue import GuiQueueManager


type DownloadableMedia = Track | Video | Album | Playlist | UserPlaylist | Mix
type QueueableMedia = DownloadableMedia | Artist

SESSION_ERRORS = (
    TidalAPIError,
    AttributeError,
    OSError,
    RuntimeError,
    TypeError,
    ValueError,
)

DOWNLOAD_ERRORS = SESSION_ERRORS


def _is_downloadable(media: object) -> TypeGuard[DownloadableMedia]:
    """Return whether an object is accepted by the downloader.

    Args:
        media (object): Candidate object returned by TIDAL.

    Returns:
        TypeGuard[DownloadableMedia]: Whether the object is downloadable.
    """
    return isinstance(media, (Track, Video, Album, Playlist, Mix))


def _is_queueable(media: object) -> TypeGuard[QueueableMedia]:
    """Return whether an object can be added to the GUI queue.

    Args:
        media (object): Candidate object from a results model.

    Returns:
        TypeGuard[QueueableMedia]: Whether the object is queueable.
    """
    return _is_downloadable(media) or isinstance(media, Artist)


class DownloadsMixin:
    """Provide result-to-queue and download services to ``MainWindow``."""

    tr_results: QtWidgets.QTreeView
    proxy_tr_results: QtCore.QSortFilterProxyModel
    model_tr_results: QtGui.QStandardItemModel
    queue_manager: GuiQueueManager
    tidal: Tidal
    settings: Settings
    dl: Download
    s_queue_download_item_downloading: QtCore.SignalInstance
    s_queue_download_item_finished: QtCore.SignalInstance
    s_queue_download_item_failed: QtCore.SignalInstance
    s_queue_download_item_skipped: QtCore.SignalInstance
    s_pb_reset: QtCore.SignalInstance
    s_statusbar_message: QtCore.SignalInstance

    @staticmethod
    def _ensure_tidal_session(tidal: Tidal) -> bool:
        """Ensure that the TIDAL session is authenticated.

        Args:
            tidal (Tidal): Application TIDAL configuration and session.

        Returns:
            bool: ``True`` when the existing or recovered session is valid.
        """
        try:
            if tidal.session.check_login():
                return True
        except SESSION_ERRORS:
            logger_gui.warning(
                "TIDAL session check failed; attempting token recovery.",
                exc_info=True,
            )

        try:
            recovered: bool = tidal.login_token()
        except SESSION_ERRORS:
            logger_gui.exception(
                "Failed to recover the TIDAL session from the stored token."
            )
            return False

        if recovered:
            logger_gui.info("Recovered the TIDAL session from its token.")
        return recovered

    @staticmethod
    def _resolve_source_info(
        media: DownloadableMedia,
    ) -> tuple[str, str | None, str | None]:
        """Build history provenance for a media object.

        Args:
            media (DownloadableMedia): Media being downloaded.

        Returns:
            tuple[str, str | None, str | None]: Source type, identifier,
                and display name.
        """
        if isinstance(media, Album):
            return "album", str(media.id), media.name

        if isinstance(media, Playlist):
            return "playlist", str(media.id), media.name

        if isinstance(media, Mix):
            return "mix", str(media.id), media.title

        if isinstance(media, Track):
            if (album := media.album) is not None:
                return "album", str(album.id), album.name
            return "track", str(media.id), media.name

        return "video", str(media.id), media.name

    def on_download_results(self) -> None:
        """Add every selected results row to the download queue.

        This slot may still be called through the legacy worker helper.  When
        that happens, it reschedules itself on the results view's GUI thread
        before reading selection or model data.
        """
        if QtCore.QThread.currentThread() != self.tr_results.thread():
            QtCore.QTimer.singleShot(
                0,
                self.tr_results,
                self.on_download_results,
            )
            return

        selected_rows: list[QtCore.QModelIndex] = (
            self.tr_results.selectionModel().selectedRows()
        )
        if not selected_rows:
            logger_gui.error("Please select at least one result first.")
            self.s_statusbar_message.emit(
                StatusbarMessage(
                    message="Select at least one result to download.",
                    timeout=3000,
                )
            )
            return

        queued_count: int = 0
        for index in selected_rows:
            media = get_results_media_item(
                index,
                self.proxy_tr_results,
                self.model_tr_results,
            )
            if not _is_queueable(media):
                log_message: str = (
                    f"Cannot queue unsupported result type "
                    f"'{type(media).__name__}'."
                )
                logger_gui.warning(log_message)
                continue

            queue_item: QueueDownloadItem | None = (
                self.queue_manager.media_to_queue_download_model(media)
            )
            if queue_item is None:
                log_message = (
                    f"Result '{type(media).__name__}' is unavailable and "
                    "was not queued."
                )
                logger_gui.warning(log_message)
                continue

            self.queue_download_media(queue_item)
            queued_count += 1

        self._report_queued_results(queued_count)

    def _report_queued_results(self, queued_count: int) -> None:
        """Report how many selected rows entered the queue.

        Args:
            queued_count (int): Number of newly queued rows.
        """
        if queued_count == 0:
            message: str = "No downloadable results were added to the queue."
        elif queued_count == 1:
            message = "Added one result to the download queue."
        else:
            message = f"Added {queued_count} results to the download queue."

        self.s_statusbar_message.emit(
            StatusbarMessage(message=message, timeout=3000)
        )

    def queue_download_media(self, queue_item: QueueDownloadItem) -> None:
        """Add a prepared item through the central queue manager.

        Args:
            queue_item (QueueDownloadItem): Prepared queue entry.
        """
        self.queue_manager.queue_download_media(queue_item)

    def watcher_queue_download(self) -> None:
        """Start the queue manager's compatibility watcher entry point.

        The queue manager now processes work from queue events.  Delegating
        keeps old startup integrations valid without introducing polling.
        """
        self.queue_manager.watcher_queue_download()

    def on_queue_download_item_downloading(
        self,
        item: QtWidgets.QTreeWidgetItem,
    ) -> None:
        """Mark a queue item as downloading on the GUI thread.

        Args:
            item (QTreeWidgetItem): Queue row to update.
        """
        self.queue_manager.on_queue_download_item_downloading(item)

    def on_queue_download_item_finished(
        self,
        item: QtWidgets.QTreeWidgetItem,
    ) -> None:
        """Mark a queue item as finished on the GUI thread.

        Args:
            item (QTreeWidgetItem): Queue row to update.
        """
        self.queue_manager.on_queue_download_item_finished(item)

    def on_queue_download_item_failed(
        self,
        item: QtWidgets.QTreeWidgetItem,
    ) -> None:
        """Mark a queue item as failed on the GUI thread.

        Args:
            item (QTreeWidgetItem): Queue row to update.
        """
        self.queue_manager.on_queue_download_item_failed(item)

    def on_queue_download_item_skipped(
        self,
        item: QtWidgets.QTreeWidgetItem,
    ) -> None:
        """Mark a queue item as skipped on the GUI thread.

        Args:
            item (QTreeWidgetItem): Queue row to update.
        """
        self.queue_manager.on_queue_download_item_skipped(item)

    def queue_download_item_status(
        self,
        item: QtWidgets.QTreeWidgetItem,
        status: str,
    ) -> None:
        """Set a queue item's status through the queue manager.

        Args:
            item (QTreeWidgetItem): Queue row to update.
            status (str): New queue status label.
        """
        self.queue_manager.queue_download_item_status(item, status)

    def on_queue_download(
        self,
        media: QueueableMedia,
        quality_audio: Quality | None = None,
        quality_video: QualityVideo | None = None,
    ) -> QueueDownloadStatus:
        """Download queued media and return its aggregate status.

        Args:
            media (QueueableMedia): Media or artist queued for download.
            quality_audio (Quality | None): Requested audio quality.
            quality_video (QualityVideo | None): Requested video quality.

        Returns:
            QueueDownloadStatus: Aggregate result for all resolved media.
        """
        if not self._ensure_tidal_session(self.tidal):
            self.s_statusbar_message.emit(
                StatusbarMessage(
                    message="Session expired; please sign in again.",
                    timeout=5000,
                )
            )
            return QueueDownloadStatus.Failed

        resolved_items: list[object]
        if isinstance(media, Artist):
            resolved_items = items_results_all(self.tidal.session, media)
        else:
            resolved_items = [media]

        handling_app = HandlingApp()
        results: list[QueueDownloadStatus] = []
        for resolved_item in resolved_items:
            if handling_app.event_abort.is_set():
                logger_gui.info("Download queue processing was cancelled.")
                break

            if not _is_downloadable(resolved_item):
                log_message = (
                    f"Ignoring unsupported artist result "
                    f"'{type(resolved_item).__name__}'."
                )
                logger_gui.warning(log_message)
                continue

            delay_track: bool = bool(
                isinstance(resolved_item, Track | Video)
                and self.settings.data.download_delay
            )
            result: QueueDownloadStatus = self.download(
                resolved_item,
                self.dl,
                delay_track=delay_track,
                quality_audio=quality_audio,
                quality_video=quality_video,
            )
            results.append(result)

        return self._aggregate_download_results(results)

    @staticmethod
    def _aggregate_download_results(
        results: list[QueueDownloadStatus],
    ) -> QueueDownloadStatus:
        """Combine item results into one queue status.

        Args:
            results (list[QueueDownloadStatus]): Individual item results.

        Returns:
            QueueDownloadStatus: Failed if any item failed, finished if at
                least one completed, otherwise skipped.
        """
        if QueueDownloadStatus.Failed in results:
            return QueueDownloadStatus.Failed
        if QueueDownloadStatus.Finished in results:
            return QueueDownloadStatus.Finished
        return QueueDownloadStatus.Skipped

    def download(
        self,
        media: DownloadableMedia,
        downloader: Download,
        delay_track: bool = False,
        quality_audio: Quality | None = None,
        quality_video: QualityVideo | None = None,
    ) -> QueueDownloadStatus:
        """Download one item or collection through the request-object API.

        Args:
            media (DownloadableMedia): Item or collection to download.
            downloader (Download): Configured downloader service.
            delay_track (bool): Whether to apply the configured track delay.
            quality_audio (Quality | None): Requested audio quality.
            quality_video (QualityVideo | None): Requested video quality.

        Returns:
            QueueDownloadStatus: Finished, skipped, or failed.
        """
        self.s_pb_reset.emit()
        self.s_statusbar_message.emit(
            StatusbarMessage(message="Download started...")
        )

        file_template = get_format_template(media, self.settings)
        if not isinstance(file_template, str) or not file_template:
            log_message = (
                f"No file template is configured for '{type(media).__name__}'."
            )
            logger_gui.error(log_message)
            self._report_download_failure("invalid file template")
            return QueueDownloadStatus.Failed

        source_type, source_id, source_name = self._resolve_source_info(media)
        request = ItemRequest(
            file_template=file_template,
            media=media,
            video_download=self.settings.data.video_download,
            download_delay=delay_track,
            quality_audio=quality_audio,
            quality_video=quality_video,
            source_type=source_type,
            source_id=source_id,
            source_name=source_name,
        )

        try:
            if isinstance(media, Track | Video):
                downloaded, path_file = downloader.item(request)
            else:
                downloader.items(request)
                downloaded = True
                path_file = "collection"
        except DOWNLOAD_ERRORS:
            log_message = (
                f"Download failed for {type(media).__name__} "
                f"'{source_id or source_name or 'unknown'}'."
            )
            logger_gui.exception(log_message)
            self._report_download_failure("download service error")
            return QueueDownloadStatus.Failed

        self.s_statusbar_message.emit(
            StatusbarMessage(message="Download finished.", timeout=2000)
        )
        if downloaded and path_file:
            return QueueDownloadStatus.Finished
        if path_file:
            return QueueDownloadStatus.Skipped
        self._report_download_failure("no output was produced")
        return QueueDownloadStatus.Failed

    def _report_download_failure(self, reason: str) -> None:
        """Publish a contextual download failure to the status bar.

        Args:
            reason (str): Short user-facing reason for the failure.
        """
        self.s_statusbar_message.emit(
            StatusbarMessage(
                message=f"Download failed: {reason}.",
                timeout=5000,
            )
        )
