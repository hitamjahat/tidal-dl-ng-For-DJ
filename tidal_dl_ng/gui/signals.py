"""Signals mixin for MainWindow.

Handles all Qt signal definitions and connections.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, cast

from tidalapi import Quality

from tidal_dl_ng.constants import QualityVideo
from tidal_dl_ng.helper.gui import HumanProxyModel, get_results_media_item

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from typing import ParamSpec, Protocol, TypeVar

    from PySide6 import QtCore, QtGui, QtWidgets
    from tidalapi import Album, Artist, Mix, Playlist, Track, Video

    from tidal_dl_ng.config import Settings, Tidal
    from tidal_dl_ng.gui.covers import CoverManager
    from tidal_dl_ng.gui.playlist import GuiPlaylistManager
    from tidal_dl_ng.gui.queue import GuiQueueManager
    from tidal_dl_ng.gui.search import GuiSearchManager, SearchMediaType
    from tidal_dl_ng.model.gui_data import StatusbarMessage
    from tidal_dl_ng.model.meta import ReleaseLatest
    from tidal_dl_ng.ui.info_tab_widget import InfoTabWidget

    _P = ParamSpec("_P")
    _R = TypeVar("_R")

    # Media types returned when resolving a results-tree row.
    type ResultMedia = Track | Video | Album | Artist | Playlist | Mix

    # Quality values stored in the combo-box item data.
    type QualityValue = Quality | QualityVideo | int | str | None

    class _UpdateCheckSlot(Protocol):
        """Callable type for startup and manual update checks."""

        def __call__(self, on_startup: bool = True) -> None: ...

    class _VersionSlot(Protocol):
        """Callable type for ``on_version`` with all-optional args."""

        def __call__(
            self,
            update_check: bool = False,
            is_available: bool = False,
            update_info: ReleaseLatest | None = None,
        ) -> None: ...


class SignalsMixin:
    """Mixin containing Qt signal definitions and signal connection methods."""

    # Attributes provided by MainWindow at runtime.
    settings: Settings
    tidal: Tidal

    if TYPE_CHECKING:

        def thread_it(
            self,
            function: Callable[_P, _R],
            *args: _P.args,
            **kwargs: _P.kwargs,
        ) -> None:
            """Dispatch a callable through the owning window's pool."""

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

    proxy_tr_results: HumanProxyModel
    model_tr_results: QtGui.QStandardItemModel
    search_manager: GuiSearchManager
    queue_manager: GuiQueueManager
    playlist_manager: GuiPlaylistManager
    info_tab_widget: InfoTabWidget
    cover_manager: CoverManager
    close: Callable[[], bool]

    # Signals emitted by other mixins.
    s_spinner_start: QtCore.SignalInstance
    s_spinner_stop: QtCore.SignalInstance
    s_item_advance: QtCore.SignalInstance
    s_item_name: QtCore.SignalInstance
    s_list_name: QtCore.SignalInstance
    s_list_advance: QtCore.SignalInstance
    s_pb_reset: QtCore.SignalInstance
    s_statusbar_message: QtCore.SignalInstance
    s_tr_results_add_top_level_item: QtCore.SignalInstance
    s_settings_save: QtCore.SignalInstance
    s_pb_reload_status: QtCore.SignalInstance
    s_update_check: QtCore.SignalInstance
    s_update_show: QtCore.SignalInstance

    # Slots defined in sibling mixins.
    on_spinner_start: Callable[[QtWidgets.QWidget], None]
    on_spinner_stop: Callable[[], None]
    on_progress_item: Callable[[float], None]
    on_progress_item_name: Callable[[str], None]
    on_progress_list_name: Callable[[str], None]
    on_progress_list: Callable[[float], None]
    on_progress_reset: Callable[[], None]
    on_statusbar_message: Callable[[StatusbarMessage], None]
    on_tr_results_add_top_level_item: Callable[
        [Sequence[QtGui.QStandardItem]], None
    ]
    on_settings_save: Callable[[], None]
    button_reload_status: Callable[[bool], None]
    on_version: _VersionSlot
    on_preferences: Callable[[], None]
    on_logout: Callable[[], None]
    on_tr_results_expanded: Callable[[QtCore.QModelIndex], None]
    on_search_in_app: Callable[[str, str], None]
    on_search_in_browser: Callable[[str, str], None]
    on_download_results: Callable[[], None]
    on_update_check: _UpdateCheckSlot

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
        self.s_spinner_start.connect(self.on_spinner_start)
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

    def _on_search_triggered(self, *_args: object) -> None:
        """Run a search using the current query and selected type."""
        self.search_manager.search_populate_results(
            self.l_search.text(),
            cast("SearchMediaType | None", self.cb_search_type.currentData()),
        )

    def _on_download_results_triggered(self, *_args: object) -> None:
        """Trigger a download of the current results in a worker thread."""
        self.thread_it(self.on_download_results)

    def _on_download_list_triggered(self, *_args: object) -> None:
        """Trigger a download of the selected list in a worker thread."""
        self.thread_it(self.playlist_manager.on_download_list_media)

    def _on_update_check_triggered(self, *_args: object) -> None:
        """Trigger an update check in a worker thread."""
        self.thread_it(self.on_update_check)

    def _on_version_triggered(self, *_args: object) -> None:
        """Show the version dialog without receiving a QAction state."""
        self.on_version()

    def _on_update_check_manual(self, *_args: object) -> None:
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
                self.settings.data.quality_video = QualityVideo(
                    str(quality_data)
                )

        self.settings.save()
        if self.tidal:
            self.tidal.settings_apply()
