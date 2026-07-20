"""Signals mixin for MainWindow.

Handles all Qt signal definitions and connections.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any, cast

from PySide6 import QtCore, QtGui, QtWidgets
from tidalapi import Quality

from tidal_dl_ng.constants import QualityVideo
from tidal_dl_ng.helper.gui import get_results_media_item

if TYPE_CHECKING:
    from tidalapi import Album, Artist, Mix, Playlist, Track, Video

    from tidal_dl_ng.config import Settings, Tidal
    from tidal_dl_ng.gui.covers import CoverManager
    from tidal_dl_ng.gui.playlist import GuiPlaylistManager
    from tidal_dl_ng.gui.queue import GuiQueueManager
    from tidal_dl_ng.gui.search import GuiSearchManager
    from tidal_dl_ng.ui.info_tab_widget import InfoTabWidget

    # Media types returned when resolving a results-tree row.
    ResultMedia = Track | Video | Album | Artist | Playlist | Mix

    # Quality values stored in the combo-box item data.
    QualityValue = Quality | QualityVideo | int | str | None


class SignalsMixin:
    """Mixin containing Qt signal definitions and signal connection methods."""

    # Attributes provided by MainWindow at runtime.
    settings: Settings
    tidal: Tidal
    thread_it: Any

    pb_download: QtWidgets.QPushButton
    pb_download_list: QtWidgets.QPushButton
    pb_search: QtWidgets.QPushButton
    l_search: QtWidgets.QLineEdit
    cb_search_type: QtWidgets.QComboBox
    cb_quality_audio: QtWidgets.QComboBox
    cb_quality_video: QtWidgets.QComboBox
    tr_results: QtWidgets.QTreeView
    a_exit: QtGui.QAction
    a_version: QtGui.QAction
    a_preferences: QtGui.QAction
    a_logout: QtGui.QAction
    a_updates_check: QtGui.QAction

    proxy_tr_results: QtCore.QSortFilterProxyModel
    model_tr_results: QtGui.QStandardItemModel
    search_manager: GuiSearchManager
    queue_manager: GuiQueueManager
    playlist_manager: GuiPlaylistManager
    info_tab_widget: InfoTabWidget
    cover_manager: CoverManager
    close: Any

    # Signals emitted by other mixins.
    s_spinner_start: Any
    s_spinner_stop: Any
    s_item_advance: Any
    s_item_name: Any
    s_list_name: Any
    s_list_advance: Any
    s_pb_reset: Any
    s_statusbar_message: Any
    s_tr_results_add_top_level_item: Any
    s_settings_save: Any
    s_pb_reload_status: Any
    s_update_check: Any
    s_update_show: Any

    # Slots defined in sibling mixins.
    on_spinner_start: Any
    on_spinner_stop: Any
    on_progress_item: Any
    on_progress_item_name: Any
    on_progress_list_name: Any
    on_progress_list: Any
    on_progress_reset: Any
    on_statusbar_message: Any
    on_tr_results_add_top_level_item: Any
    on_settings_save: Any
    button_reload_status: Any
    on_version: Any
    on_preferences: Any
    on_logout: Any
    on_tr_results_expanded: Any
    on_search_in_app: Any
    on_search_in_browser: Any
    on_download_results: Any
    on_update_check: Any

    def _init_signals(self) -> None:
        """Connect signals to their respective slots."""
        self.pb_download.clicked.connect(self._on_download_results_triggered)
        self.pb_download_list.clicked.connect(self._on_download_list_triggered)
        self.l_search.returnPressed.connect(self._on_search_triggered)
        self.pb_search.clicked.connect(self._on_search_triggered)
        self.cb_quality_audio.currentIndexChanged.connect(
            self.on_quality_set_audio
        )
        self.cb_quality_video.currentIndexChanged.connect(
            self.on_quality_set_video
        )
        self.s_spinner_start[QtWidgets.QWidget].connect(self.on_spinner_start)
        self.s_spinner_stop.connect(self.on_spinner_stop)
        self.s_item_advance.connect(self.on_progress_item)
        self.s_item_name.connect(self.on_progress_item_name)
        self.s_list_name.connect(self.on_progress_list_name)
        self.s_list_advance.connect(self.on_progress_list)
        self.s_pb_reset.connect(self.on_progress_reset)
        self.s_statusbar_message.connect(self.on_statusbar_message)
        self.s_tr_results_add_top_level_item.connect(
            self.on_tr_results_add_top_level_item
        )
        self.s_settings_save.connect(self.on_settings_save)
        self.s_pb_reload_status.connect(self.button_reload_status)
        self.s_update_check.connect(self._on_update_check_triggered)
        self.s_update_show.connect(self.on_version)

        # Menubar
        self.a_exit.triggered.connect(self.close)
        self.a_version.triggered.connect(self._on_version_triggered)
        self.a_preferences.triggered.connect(self.on_preferences)
        self.a_logout.triggered.connect(self.on_logout)
        self.a_updates_check.triggered.connect(self._on_update_check_manual)

        # Results
        self.tr_results.expanded.connect(self.on_tr_results_expanded)
        self.tr_results.clicked.connect(self.on_result_item_clicked)
        self.tr_results.doubleClicked.connect(
            self._on_download_results_triggered
        )

        # Managers
        self.queue_manager.connect_signals()
        self.playlist_manager.connect_signals()
        self.info_tab_widget.s_search_in_app.connect(self.on_search_in_app)
        self.info_tab_widget.s_search_in_browser.connect(
            self.on_search_in_browser
        )

    def _on_search_triggered(self, *_args: Any) -> None:
        """Run a search using the current query and selected type."""
        self.search_manager.search_populate_results(
            self.l_search.text(),
            self.cb_search_type.currentData(),
        )

    def _on_download_results_triggered(self, *_args: Any) -> None:
        """Trigger a download of the current results in a worker thread."""
        self.thread_it(self.on_download_results)

    def _on_download_list_triggered(self, *_args: Any) -> None:
        """Trigger a download of the selected list in a worker thread."""
        self.thread_it(self.playlist_manager.on_download_list_media)

    def _on_update_check_triggered(self, *_args: Any) -> None:
        """Trigger an update check in a worker thread."""
        self.thread_it(self.on_update_check)

    def _on_version_triggered(self, *_args: Any) -> None:
        """Show the version dialog without receiving a QAction state."""
        self.on_version()

    def _on_update_check_manual(self, *_args: Any) -> None:
        """Run an update check without the startup-only behavior."""
        self.on_update_check(on_startup=False)

    def on_result_item_clicked(self, index: QtCore.QModelIndex) -> None:
        """Handle the event when a result item is clicked."""
        media: ResultMedia | None = cast(
            "ResultMedia | None",
            get_results_media_item(
                index, self.proxy_tr_results, self.model_tr_results
            ),
        )

        if media is not None:
            self.info_tab_widget.update_on_selection(media)
            self.thread_it(self.cover_manager.load_cover, media)

    def on_quality_set_audio(self, index: int) -> None:
        """Set the audio quality for downloads."""
        quality_data: QualityValue = cast(
            "QualityValue",
            self.cb_quality_audio.itemData(index),
        )

        if isinstance(quality_data, Quality):
            self.settings.data.quality_audio = quality_data
        elif isinstance(quality_data, (int, str)):
            with contextlib.suppress(ValueError):
                self.settings.data.quality_audio = Quality(quality_data)

        self.settings.save()
        if self.tidal:
            self.tidal.settings_apply()

    def on_quality_set_video(self, index: int) -> None:
        """Set the video quality for downloads."""
        quality_data: QualityValue = cast(
            "QualityValue",
            self.cb_quality_video.itemData(index),
        )

        if isinstance(quality_data, QualityVideo):
            self.settings.data.quality_video = quality_data
        elif isinstance(quality_data, (int, str)):
            with contextlib.suppress(ValueError):
                self.settings.data.quality_video = QualityVideo(quality_data)

        self.settings.save()
        if self.tidal:
            self.tidal.settings_apply()
