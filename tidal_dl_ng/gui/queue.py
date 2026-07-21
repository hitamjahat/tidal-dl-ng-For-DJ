"""Download queue management for the TIDAL DL NG application.

This module provides the GuiQueueManager class which handles:
- Managing the download queue UI
- Processing download items
- Handling queue operations like add, remove, clear
- Managing download status and progress
"""

import threading
from typing import TYPE_CHECKING, Optional

from PySide6 import QtCore, QtGui, QtWidgets
from tidalapi import Album, Artist, Mix, Playlist, Quality, Track, Video

from tidal_dl_ng.config import HandlingApp
from tidal_dl_ng.constants import QualityVideo, QueueDownloadStatus
from tidal_dl_ng.download import Download
from tidal_dl_ng.helper.gui import (
    get_queue_download_media,
    get_queue_download_quality_audio,
    get_queue_download_quality_video,
    set_queue_download_media,
)
from tidal_dl_ng.helper.path import get_format_template
from tidal_dl_ng.helper.tidal import (
    items_results_all,
    name_builder_artist,
    name_builder_title,
    quality_audio_highest,
)
from tidal_dl_ng.logger import logger_gui
from tidal_dl_ng.model.downloader import ItemRequest
from tidal_dl_ng.model.gui_data import QueueDownloadItem, StatusbarMessage

if TYPE_CHECKING:
    from tidal_dl_ng.gui.main_window import MainWindow


class GuiQueueManager:
    """Manages the download queue GUI and logic."""

    def __init__(self, main_window: "MainWindow") -> None:
        """Initialize the queue manager.
        
        Args:
            main_window: The main window instance
        """
        self.main_window = main_window
        self.settings = main_window.settings
        self._is_downloading = False
        self._lock = threading.Lock()

    def init_ui(self) -> None:
        """Initialize UI elements related to the queue."""
        self._init_tree_queue(self.main_window.tr_queue_download)
        self.pb_queue_download_run()

    def connect_signals(self) -> None:
        """Connect signals for queue-related widgets."""
        # Connect queue-related widget signals
        self.main_window.pb_queue_download_clear_all.clicked.connect(
            self.on_queue_download_clear_all
        )
        self.main_window.pb_queue_download_clear_finished.clicked.connect(
            self.on_queue_download_clear_finished
        )
        self.main_window.pb_queue_download_remove.clicked.connect(
            self.on_queue_download_remove
        )
        self.main_window.pb_queue_download_toggle.clicked.connect(
            self.on_pb_queue_download_toggle
        )
        self.main_window.tr_queue_download.itemClicked.connect(
            self.on_queue_download_item_clicked
        )
        self.main_window.tr_queue_download.customContextMenuRequested.connect(
            self.menu_context_queue_download
        )

        # Connect queue download signals
        self.main_window.s_queue_download_item_downloading.connect(
            self.on_queue_download_item_downloading
        )
        self.main_window.s_queue_download_item_finished.connect(
            self.on_queue_download_item_finished
        )
        self.main_window.s_queue_download_item_failed.connect(
            self.on_queue_download_item_failed
        )
        self.main_window.s_queue_download_item_skipped.connect(
            self.on_queue_download_item_skipped
        )

    def _init_tree_queue(self, tree: QtWidgets.QTreeWidget) -> None:
        """Initialize the download queue tree widget.
        
        Args:
            tree: The tree widget to initialize
        """
        tree.setColumnHidden(column=1, hide=True)
        tree.setColumnWidth(2, 200)
        
        header = tree.header()
        if hasattr(header, "setSectionResizeMode"):
            header.setSectionResizeMode(
                0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents
            )
        tree.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)

    def menu_context_queue_download(self, point: QtCore.QPoint) -> None:
        """Show context menu for download queue.
        
        Args:
            point: The point where the context menu was requested
        """
        item = self.main_window.tr_queue_download.itemAt(point)
        if not item:
            return
        
        menu = QtWidgets.QMenu()
        status = item.text(0)
        
        if status == QueueDownloadStatus.Waiting:
            menu.addAction(
                "🗑️ Remove from Queue",
                lambda: self.on_queue_download_remove_item(item)
            )
        
        if menu.isEmpty():
            return
        
        menu.exec(self.main_window.tr_queue_download.mapToGlobal(point))

    def on_queue_download_remove_item(
        self, item: QtWidgets.QTreeWidgetItem
    ) -> None:
        """Remove a specific item from the download queue.
        
        Args:
            item: The item to remove
        """
        index = self.main_window.tr_queue_download.indexOfTopLevelItem(item)
        if index >= 0:
            self.main_window.tr_queue_download.takeTopLevelItem(index)
            logger_gui.info("Removed item from download queue")

    def on_queue_download_clear_all(self) -> None:
        """Clear all items from the download queue."""
        self.on_clear_queue_download(
            f"({QueueDownloadStatus.Waiting}|{QueueDownloadStatus.Finished}|"
            f"{QueueDownloadStatus.Failed})"
        )

    def on_queue_download_clear_finished(self) -> None:
        """Clear finished items from the download queue."""
        self.on_clear_queue_download(f"[{QueueDownloadStatus.Finished}]")

    def on_clear_queue_download(self, regex: str) -> None:
        """Clear items from the download queue matching the given regex.
        
        Args:
            regex: Regular expression to match status values
        """
        items = self.main_window.tr_queue_download.findItems(
            regex, QtCore.Qt.MatchFlag.MatchRegularExpression, column=0
        )
        
        for item in items:
            self.main_window.tr_queue_download.takeTopLevelItem(
                self.main_window.tr_queue_download.indexOfTopLevelItem(item)
            )

    def on_queue_download_remove(self) -> None:
        """Remove selected items from the download queue."""
        items = self.main_window.tr_queue_download.selectedItems()
        
        if not items:
            logger_gui.error("Please select an item from the queue first.")
            return
        
        for item in items:
            status = item.text(0)
            if status != QueueDownloadStatus.Downloading:
                self.main_window.tr_queue_download.takeTopLevelItem(
                    self.main_window.tr_queue_download.indexOfTopLevelItem(item)
                )
            else:
                logger_gui.info(
                    "Cannot remove a currently downloading item from queue."
                )

    def on_pb_queue_download_toggle(self) -> None:
        """Toggle download status (pause / resume) accordingly."""
        handling_app = HandlingApp()
        
        if handling_app.event_run.is_set():
            self.pb_queue_download_pause()
        else:
            self.pb_queue_download_run()

    def pb_queue_download_run(self) -> None:
        """Start the download queue and update the button state."""
        handling_app = HandlingApp()
        handling_app.event_run.set()

        icon = QtGui.QIcon(
            QtGui.QIcon.fromTheme(QtGui.QIcon.ThemeIcon.MediaPlaybackPause)
        )
        self.main_window.pb_queue_download_toggle.setIcon(icon)
        self.main_window.pb_queue_download_toggle.setStyleSheet(
            "background-color: #e0a800; color: #212529"
        )
        
        self._process_next_item()

    def pb_queue_download_pause(self) -> None:
        """Pause the download queue and update the button state."""
        handling_app = HandlingApp()
        handling_app.event_run.clear()

        icon = QtGui.QIcon(
            QtGui.QIcon.fromTheme(QtGui.QIcon.ThemeIcon.MediaPlaybackStart)
        )
        self.main_window.pb_queue_download_toggle.setIcon(icon)
        self.main_window.pb_queue_download_toggle.setStyleSheet(
            "background-color: #218838; color: #fff"
        )

    def queue_download_media(self, queue_dl_item: QueueDownloadItem) -> None:
        """Add a media item to the download queue.
        
        Args:
            queue_dl_item: The item to add to the queue
        """
        child = QtWidgets.QTreeWidgetItem()
        child.setText(0, queue_dl_item.status)
        set_queue_download_media(child, queue_dl_item.obj)
        child.setText(2, queue_dl_item.name)
        child.setText(3, queue_dl_item.type_media)
        child.setText(4, str(queue_dl_item.quality_audio))
        child.setText(5, str(queue_dl_item.quality_video))
        self.main_window.tr_queue_download.addTopLevelItem(child)
        
        self._process_next_item()

    def watcher_queue_download(self) -> None:
        """Monitor the download queue and process items as they become available.
        
        Note: The original implementation used a blocking while loop, which is
        unsafe for GUI operations. This method is now a no-op, replaced by
        event-driven processing in `_process_next_item`.
        """
        # No operation needed - replaced by event-driven processing

    def _process_next_item(self) -> None:
        """Safely find and process the next item in the queue from the GUI thread."""
        with self._lock:
            if self._is_downloading:
                return

            handling_app = HandlingApp()
            if (not handling_app.event_run.is_set() or 
                handling_app.event_abort.is_set()):
                return

            items = self.main_window.tr_queue_download.findItems(
                QueueDownloadStatus.Waiting, 
                QtCore.Qt.MatchFlag.MatchExactly, 
                column=0
            )
            
            if not items:
                return
            
            item = items[0]
            self._is_downloading = True
        
        media = get_queue_download_media(item)
        quality_audio = get_queue_download_quality_audio(item)
        quality_video = get_queue_download_quality_video(item)

        if not media:
            logger_gui.error("Media is invalid in queue item")
            self._on_item_processed()
            return
            
        # Filter out unsupported types
        if not isinstance(media, (Track, Album, Playlist, Video, Mix)):
            logger_gui.error("Unsupported media type in queue: %s", type(media))
            self._on_item_processed()
            return
            
        self.main_window.s_queue_download_item_downloading.emit(item)
        self.main_window.thread_it(
            self._download_worker, item, media, quality_audio, quality_video
        )

    def _download_worker(
        self, 
        item: QtWidgets.QTreeWidgetItem, 
        media: Track | Album | Playlist | Video | Mix,
        quality_audio: Quality | None, 
        quality_video: QualityVideo | None
    ) -> None:
        """Background worker method to process a download and emit results.
        
        Args:
            item: The queue item being processed
            media: The media to download
            quality_audio: Audio quality setting
            quality_video: Video quality setting
        """
        try:
            result = self.on_queue_download(
                media, quality_audio=quality_audio, quality_video=quality_video
            )
            
            if result == QueueDownloadStatus.Finished:
                self.main_window.s_queue_download_item_finished.emit(item)
            elif result == QueueDownloadStatus.Skipped:
                self.main_window.s_queue_download_item_skipped.emit(item)
            else:
                self.main_window.s_queue_download_item_failed.emit(item)
        except Exception as e:
            logger_gui.error("Download failed: %s", str(e))
            self.main_window.s_queue_download_item_failed.emit(item)

    def on_queue_download_item_downloading(
        self, item: QtWidgets.QTreeWidgetItem
    ) -> None:
        """Update the status of a queue download item to 'Downloading'.
        
        Args:
            item: The item to update
        """
        self.queue_download_item_status(item, QueueDownloadStatus.Downloading)

    def on_queue_download_item_finished(
        self, item: QtWidgets.QTreeWidgetItem
    ) -> None:
        """Update the status of a queue download item to 'Finished'.
        
        Args:
            item: The item to update
        """
        self.queue_download_item_status(item, QueueDownloadStatus.Finished)
        self._on_item_processed()

    def on_queue_download_item_failed(
        self, item: QtWidgets.QTreeWidgetItem
    ) -> None:
        """Update the status of a queue download item to 'Failed'.
        
        Args:
            item: The item to update
        """
        self.queue_download_item_status(item, QueueDownloadStatus.Failed)
        self._on_item_processed()

    def on_queue_download_item_skipped(
        self, item: QtWidgets.QTreeWidgetItem
    ) -> None:
        """Update the status of a queue download item to 'Skipped'.
        
        Args:
            item: The item to update
        """
        self.queue_download_item_status(item, QueueDownloadStatus.Skipped)
        self._on_item_processed()
        
    def _on_item_processed(self) -> None:
        """Reset downloading state and trigger the next item."""
        with self._lock:
            self._is_downloading = False
        self._process_next_item()

    def queue_download_item_status(
        self, item: QtWidgets.QTreeWidgetItem, status: str
    ) -> None:
        """Set the status text of a queue download item.
        
        Args:
            item: The item to update
            status: The status text to set
        """
        item.setText(0, status)

    def on_queue_download(
        self,
        media: Track | Album | Playlist | Video | Mix | Artist,
        quality_audio: Quality | None = None,
        quality_video: QualityVideo | None = None,
    ) -> QueueDownloadStatus:
        """Download the specified media item(s) and return the result status.
        
        Args:
            media: The media to download
            quality_audio: Audio quality setting
            quality_video: Video quality setting
            
        Returns:
            The download status
        """
        items_media = (
            items_results_all(self.main_window.tidal.session, media)
            if isinstance(media, Artist)
            else [media]
        )
        download_delay = bool(
            isinstance(media, (Track, Video)) 
            and self.settings.data.download_delay
        )
        
        result = QueueDownloadStatus.Failed
        handling_app = HandlingApp()
        
        for item_media in items_media:
            if handling_app.event_abort.is_set():
                break
                
            if isinstance(item_media, Artist):
                continue  # Skip Artist type as it's not supported in download
                
            # Ensure we only pass supported types to download
            if isinstance(item_media, (Track, Album, Playlist, Video, Mix)):
                result = self.download(
                    item_media,
                    self.main_window.dl,
                    delay_track=download_delay,
                    quality_audio=quality_audio,
                    quality_video=quality_video,
                )
                
        return result

    def download(
        self,
        media: Track | Album | Playlist | Video | Mix,
        dl: Download,
        delay_track: bool = False,
        quality_audio: Quality | None = None,
        quality_video: QualityVideo | None = None,
    ) -> QueueDownloadStatus:
        """Download a media item and return the result status.
        
        Args:
            media: The media to download
            dl: The Download instance to use
            delay_track: Whether to delay the download
            quality_audio: Audio quality setting
            quality_video: Video quality setting
            
        Returns:
            The download status
        """
        self.main_window.s_pb_reset.emit()
        self.main_window.s_statusbar_message.emit(
            StatusbarMessage(message="Download started...")
        )
        
        file_template = get_format_template(media, self.settings)
        result_dl = False
        path_file: Optional[str] = None
        
        try:
            # Create request object for download
            request = ItemRequest(
                file_template=str(file_template),  # Ensure file_template is string
                media=media,
                download_delay=delay_track,
                quality_audio=quality_audio,
                quality_video=quality_video,
                video_download=self.settings.data.video_download,
            )
            
            result_dl, path_file = dl.item(request)
        except Exception as e:
            logger_gui.error("Download failed: %s", str(e))
            return QueueDownloadStatus.Failed

        self.main_window.s_statusbar_message.emit(
            StatusbarMessage(message="Download finished.", timeout=2000)
        )
        
        if result_dl and path_file:
            return QueueDownloadStatus.Finished
        if not result_dl and path_file:
            return QueueDownloadStatus.Skipped
            
        return QueueDownloadStatus.Failed

    def on_queue_download_item_clicked(
        self, item: QtWidgets.QTreeWidgetItem
    ) -> None:
        """Handle the event when a queue download item is clicked.
        
        Args:
            item: The clicked item
        """
        media = get_queue_download_media(item)
        if isinstance(media, (Track, Video, Album, Mix, Playlist, Artist)):
            self.main_window.info_tab_widget.update_on_selection(media)
            self.main_window.thread_it(
                self.main_window.cover_manager.load_cover, media
            )

    def media_to_queue_download_model(
        self, media: Artist | Track | Video | Album | Playlist | Mix
    ) -> Optional[QueueDownloadItem]:
        """Convert a media object to a QueueDownloadItem for the download queue.
        
        Args:
            media: The media to convert
            
        Returns:
            The converted QueueDownloadItem or None if conversion failed
        """
        if getattr(media, "available", True) is False:
            return None
            
        explicit = " 🅴" if (
            isinstance(media, (Track, Video, Album)) 
            and getattr(media, "explicit", False)
        ) else ""
        name = ""
        
        if isinstance(media, (Track, Video)):
            name = f"{name_builder_artist(media)} - {name_builder_title(media)}{explicit}"
        elif isinstance(media, (Playlist, Artist)):
            name = media.name or ""  # Handle possible None
        elif isinstance(media, Album):
            name = f"{name_builder_artist(media)} - {media.name}{explicit}"
        elif isinstance(media, Mix):
            name = media.title

        quality_audio = self.settings.data.quality_audio
        
        if isinstance(media, (Track, Album)):
            quality_highest = quality_audio_highest(media)
            if (
                self.settings.data.quality_audio == quality_highest
                or self.settings.data.quality_audio == getattr(Quality, "hi_res_lossless", None)
            ):
                quality_audio = quality_highest

        if name:
            return QueueDownloadItem(
                name=name,
                quality_audio=quality_audio,
                quality_video=self.settings.data.quality_video,
                type_media=type(media).__name__,
                status=QueueDownloadStatus.Waiting,
                obj=media,
            )
            
        return None