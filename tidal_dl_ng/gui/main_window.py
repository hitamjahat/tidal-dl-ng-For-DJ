"""Main window for TIDAL Downloader Next Generation.

This module combines all GUI functionality through mixins to create
the main application window.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from PySide6 import QtCore, QtGui, QtWidgets
from tidalapi.media import Quality

from tidal_dl_ng.cache import TrackExtrasCache
from tidal_dl_ng.config import HandlingApp, Settings, Tidal
from tidal_dl_ng.constants import QualityVideo
from tidal_dl_ng.download import Download
from tidal_dl_ng.gui.context_menus import ContextMenusMixin
from tidal_dl_ng.gui.covers import CoverManager
from tidal_dl_ng.gui.downloads import DownloadsMixin
from tidal_dl_ng.gui.history import HistoryMixin
from tidal_dl_ng.gui.initialization import InitializationMixin
from tidal_dl_ng.gui.playlist import GuiPlaylistManager
from tidal_dl_ng.gui.playlist_membership_mixin import PlaylistMembershipMixin
from tidal_dl_ng.gui.progress import ProgressMixin
from tidal_dl_ng.gui.queue import GuiQueueManager
from tidal_dl_ng.gui.search import GuiSearchManager
from tidal_dl_ng.gui.signals import SignalsMixin
from tidal_dl_ng.gui.tidal_session import TidalSessionMixin
from tidal_dl_ng.gui.track_extras import TrackExtrasMixin
from tidal_dl_ng.gui.trees_results import TreesResultsMixin
from tidal_dl_ng.gui.ui_helpers import UIHelpersMixin
from tidal_dl_ng.gui.updates import UpdatesMixin
from tidal_dl_ng.helper.gui import HumanProxyModel
from tidal_dl_ng.helper.hover_manager import HoverManager
from tidal_dl_ng.history import HistoryService
from tidal_dl_ng.logger import XStream, logger_gui
from tidal_dl_ng.ui.info_tab_widget import InfoTabWidget
from tidal_dl_ng.ui.main import Ui_MainWindow
from tidal_dl_ng.worker import Worker


# TODO: Make more use of Exceptions
class MainWindow(
    QtWidgets.QMainWindow,
    Ui_MainWindow,
    InitializationMixin,
    TidalSessionMixin,
    SignalsMixin,
    ProgressMixin,
    UIHelpersMixin,
    TrackExtrasMixin,
    UpdatesMixin,
    DownloadsMixin,
    TreesResultsMixin,
    ContextMenusMixin,
    HistoryMixin,
    PlaylistMembershipMixin,
):
    """Main application window for TIDAL Downloader Next Generation.

    Handles GUI setup, user interactions, and download logic through
    a combination of mixins for better code organization.
    """

    # Type hints for class attributes
    settings: Settings
    tidal: Tidal
    dl: Download
    history_service: HistoryService
    threadpool: QtCore.QThreadPool
    tray: QtWidgets.QSystemTrayIcon
    spinners: dict[QtWidgets.QWidget, Any]
    cover_url_current: str = ""
    shutdown: bool = False
    model_tr_results: QtGui.QStandardItemModel = QtGui.QStandardItemModel()
    proxy_tr_results: HumanProxyModel
    info_tab_widget: InfoTabWidget
    hover_manager: HoverManager
    queue_manager: GuiQueueManager
    playlist_manager: GuiPlaylistManager
    search_manager: GuiSearchManager
    cover_manager: CoverManager
    track_extras_cache: TrackExtrasCache
    _pending_extras_workers: dict[str, Worker]
    _track_extras_callbacks: dict[str, Callable[..., Any]]

    # Qt Signals
    s_spinner_start: QtCore.Signal = QtCore.Signal(QtWidgets.QWidget)
    s_spinner_stop: QtCore.Signal = QtCore.Signal()
    s_track_extras_ready: QtCore.Signal = QtCore.Signal(str, object)
    s_invoke_callback: QtCore.Signal = QtCore.Signal(str, object)
    pb_item: QtWidgets.QProgressBar
    s_item_advance: QtCore.Signal = QtCore.Signal(float)
    s_item_name: QtCore.Signal = QtCore.Signal(str)
    s_list_name: QtCore.Signal = QtCore.Signal(str)
    pb_list: QtWidgets.QProgressBar
    s_list_advance: QtCore.Signal = QtCore.Signal(float)
    s_pb_reset: QtCore.Signal = QtCore.Signal()
    s_populate_tree_lists: QtCore.Signal = QtCore.Signal(dict)
    s_populate_folder_children: QtCore.Signal = QtCore.Signal(
        object, list, list
    )
    s_statusbar_message: QtCore.Signal = QtCore.Signal(object)
    s_tr_results_add_top_level_item: QtCore.Signal = QtCore.Signal(object)
    s_settings_save: QtCore.Signal = QtCore.Signal()
    s_pb_reload_status: QtCore.Signal = QtCore.Signal(bool)
    s_update_check: QtCore.Signal = QtCore.Signal(bool)
    s_update_show: QtCore.Signal = QtCore.Signal(bool, bool, object)
    s_queue_download_item_downloading: QtCore.Signal = QtCore.Signal(object)
    s_queue_download_item_finished: QtCore.Signal = QtCore.Signal(object)
    s_queue_download_item_failed: QtCore.Signal = QtCore.Signal(object)
    s_queue_download_item_skipped: QtCore.Signal = QtCore.Signal(object)

    def __init__(self, tidal: Tidal | None = None) -> None:
        """Initialize the main window and all components.

        Args:
            tidal (Tidal | None): Optional Tidal session object.
        """
        super().__init__()
        cast(Any, self).setupUi(self)
        self.setWindowTitle("TIDAL Downloader Next Generation!")

        # Initialize settings first
        self.settings = cast(Any, Settings)()

        # Initialize managers that depend on settings
        self.queue_manager = GuiQueueManager(self)
        self.playlist_manager = GuiPlaylistManager(self)
        self.search_manager = GuiSearchManager(self)
        self.info_tab_widget = InfoTabWidget(self, self.tabWidget)

        # Logging redirect
        cast(Any, XStream).stdout().messageWritten.connect(self._log_output)

        self.history_service = cast(Any, HistoryService)()

        # Core components
        self._init_threads()
        self._init_gui()
        self.track_extras_cache = TrackExtrasCache()
        self._pending_extras_workers: dict[str, Worker] = {}
        self._track_extras_callbacks: dict[str, Callable[..., Any]] = {}

        # Managers that have dependencies
        self.cover_manager = CoverManager(
            cast(Any, self),
            self.threadpool,
            self.info_tab_widget,
        )

        # Initialize the rest of the UI
        info_tab_widget_any = cast(Any, self.info_tab_widget)
        set_extras_provider = info_tab_widget_any.set_track_extras_provider
        self_any = cast(Any, self)
        track_extras_provider = self_any.get_track_extras
        set_extras_provider(track_extras_provider)
        self._init_tree_results_model(self.model_tr_results)
        self._init_tree_results(self.tr_results, self.model_tr_results)
        cast(Any, self.playlist_manager).init_ui()
        cast(Any, self.queue_manager).init_ui()
        self._init_tree_lists(self.tr_lists_user)
        cast(Any, self)._init_tree_queue(self.tr_queue_download)
        self._init_info()
        self._init_progressbar()
        self._populate_quality(self.cb_quality_audio, Quality)
        self._populate_quality(self.cb_quality_video, QualityVideo)

        from tidalapi.session import SearchTypes

        self._populate_search_types(self.cb_search_type, SearchTypes)

        self.apply_settings(self.settings)
        self._init_menu_actions()
        self._init_signals()

        # Connect signal for invoking track extras callbacks
        invoke_callback_handler = self_any._on_invoke_callback
        cast(Any, self.s_invoke_callback).connect(invoke_callback_handler)

        # Connect playlist manager signals
        populate_tree_lists_handler = self_any.on_populate_tree_lists
        cast(Any, self.s_populate_tree_lists).connect(
            populate_tree_lists_handler
        )

        self.init_tidal(tidal)

        logger_gui.info("All setup.")

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        """Handle the close event of the main window.

        Args:
            event (QtGui.QCloseEvent): The close event.
        """
        logger_gui.warning("⚠️ CLOSE EVENT TRIGGERED!")
        import traceback

        logger_gui.debug("Close event traceback:")
        for line in traceback.format_stack():
            logger_gui.debug(line.strip())
        # Save the main window size and position
        settings_data = cast(Any, self.settings.data)
        settings_data.window_x = self.x()
        settings_data.window_y = self.y()
        settings_data.window_w = self.width()
        settings_data.window_h = self.height()
        self.settings.save()

        self.shutdown = True

        handling_app = cast(Any, HandlingApp)()
        handling_app.event_abort.set()

        event.accept()

    def apply_settings(self, settings: Settings) -> None:
        """Apply user settings to the GUI.

        Args:
            settings (Settings): The settings object.
        """
        settings_data = getattr(settings, "data", None)
        quality_audio = getattr(settings_data, "quality_audio", 1)
        quality_video = getattr(settings_data, "quality_video", 0)
        elements: list[tuple[QtWidgets.QComboBox, Any, int]] = [
            (self.cb_quality_audio, quality_audio, 1),
            (self.cb_quality_video, quality_video, 0),
        ]

        for element, setting_value, default_id in elements:
            idx = element.findData(setting_value)

            if idx > -1:
                element.setCurrentIndex(idx)
            else:
                element.setCurrentIndex(default_id)

    def thread_it(
        self,
        fn: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """Run a function in a separate thread.

        Args:
            fn (Callable): The function to run.
            *args: Positional arguments for the function.
            **kwargs: Keyword arguments for the function.
        """
        worker = cast(Any, Worker)(fn, *args, **kwargs)
        self.threadpool.start(worker)
