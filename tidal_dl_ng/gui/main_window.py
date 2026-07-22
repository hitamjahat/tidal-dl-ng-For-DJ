"""Compose and coordinate the main TIDAL Downloader application window.

The concrete window combines focused GUI mixins, owns application services,
and wires their Qt signals. Generated widgets remain in ``ui.main`` while
network and download work is dispatched through ``QThreadPool`` workers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ParamSpec, TypeVar, cast, override

from PySide6 import QtCore, QtGui, QtWidgets
from tidalapi.media import Quality
from tidalapi.session import SearchTypes

from tidal_dl_ng.cache import TrackExtrasCache
from tidal_dl_ng.config import HandlingApp, Settings, Tidal
from tidal_dl_ng.constants import QualityVideo
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
from tidal_dl_ng.history import HistoryService
from tidal_dl_ng.logger import XStream, logger_gui
from tidal_dl_ng.ui.info_tab_widget import InfoTabWidget
from tidal_dl_ng.ui.main import Ui_MainWindow
from tidal_dl_ng.worker import Worker

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from tidal_dl_ng.download import Download
    from tidal_dl_ng.helper.gui import HumanProxyModel
    from tidal_dl_ng.helper.hover_manager import HoverManager
    from tidal_dl_ng.ui.spinner import QtWaitingSpinner


_P = ParamSpec("_P")
_R = TypeVar("_R")

SETTINGS_WRITE_ERRORS: tuple[type[Exception], ...] = (
    OSError,
    TypeError,
    ValueError,
)


def _qt_signal(
    *argument_types: type[object],
) -> QtCore.SignalInstance:
    """Create a Qt signal with its bound-instance type exposed to checkers.

    Args:
        *argument_types (type[object]): Runtime types carried by the signal.

    Returns:
        SignalInstance: Signal descriptor installed by Qt's class metatype.
    """
    return cast("QtCore.SignalInstance", QtCore.Signal(*argument_types))


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
    """Coordinate the application's generated UI, services, and managers."""

    settings: Settings
    tidal: Tidal
    dl: Download
    history_service: HistoryService
    threadpool: QtCore.QThreadPool
    tray: QtWidgets.QSystemTrayIcon
    spinners: dict[QtWidgets.QWidget, QtWaitingSpinner]
    cover_url_current: str
    shutdown: bool
    model_tr_results: QtGui.QStandardItemModel
    proxy_tr_results: HumanProxyModel
    info_tab_widget: InfoTabWidget
    hover_manager: HoverManager
    queue_manager: GuiQueueManager
    playlist_manager: GuiPlaylistManager
    search_manager: GuiSearchManager
    cover_manager: CoverManager
    track_extras_cache: TrackExtrasCache
    _pending_extras_workers: dict[str, Worker]
    _track_extras_callbacks: dict[
        str,
        Callable[[str, Mapping[str, object] | None], None],
    ]

    s_spinner_start = _qt_signal(QtWidgets.QWidget)
    s_spinner_stop = _qt_signal()
    s_track_extras_ready = _qt_signal(str, object)
    s_invoke_callback = _qt_signal(str, object)
    s_item_advance = _qt_signal(float)
    s_item_name = _qt_signal(str)
    s_list_name = _qt_signal(str)
    s_list_advance = _qt_signal(float)
    s_pb_reset = _qt_signal()
    s_populate_tree_lists = _qt_signal(dict)
    s_populate_folder_children = _qt_signal(object, list, list)
    s_statusbar_message = _qt_signal(object)
    s_tr_results_add_top_level_item = _qt_signal(object)
    s_settings_save = _qt_signal()
    s_pb_reload_status = _qt_signal(bool)
    s_update_check = _qt_signal(bool)
    s_update_show = _qt_signal(bool, bool, object)
    s_queue_download_item_downloading = _qt_signal(object)
    s_queue_download_item_finished = _qt_signal(object)
    s_queue_download_item_failed = _qt_signal(object)
    s_queue_download_item_skipped = _qt_signal(object)

    def __init__(self, tidal: Tidal | None = None) -> None:
        """Initialize the main window and all coordinated components.

        Args:
            tidal (Tidal | None): Optional authenticated TIDAL configuration.

        Returns:
            None: A fully initialized application window is created.
        """
        super().__init__()
        setup_ui = cast(
            "Callable[[Ui_MainWindow, QtWidgets.QMainWindow], None]",
            Ui_MainWindow.setupUi,
        )
        setup_ui(self, self)
        self.setWindowTitle("TIDAL Downloader Next Generation")

        self._initialize_state()
        self._initialize_managers()
        self._initialize_views()
        self._connect_runtime_signals()
        self.init_tidal(tidal)

        logger_gui.info("Main window setup completed.")

    def _initialize_state(self) -> None:
        """Create settings, services, models, and other owned state.

        Returns:
            None: Core application state is initialized in dependency order.
        """
        self.shutdown = False
        self.cover_url_current = ""
        self.settings = Settings()
        self.history_service = HistoryService()
        self.model_tr_results = QtGui.QStandardItemModel(self)
        self.track_extras_cache = TrackExtrasCache()
        self._pending_extras_workers = {}
        self._track_extras_callbacks = {}

        self._init_threads()
        self.initialize_gui()

    def _initialize_managers(self) -> None:
        """Create controllers after their settings dependencies exist.

        Returns:
            None: All GUI managers are owned by this window or its widgets.
        """
        self.queue_manager = GuiQueueManager(self)
        self.playlist_manager = GuiPlaylistManager(self)
        self.search_manager = GuiSearchManager(self)
        self.info_tab_widget = InfoTabWidget(self, self.tabWidget)
        self.cover_manager = CoverManager(
            self,
            self.threadpool,
            self.info_tab_widget,
        )
        self.info_tab_widget.set_track_extras_provider(self.get_track_extras)

    def _initialize_views(self) -> None:
        """Configure models, responsive views, actions, and Qt connections.

        Returns:
            None: Generated widgets are ready for user interaction.
        """
        self._init_tree_results_model(self.model_tr_results)
        self._init_tree_results(self.tr_results, self.model_tr_results)

        self._init_tree_lists(self.tr_lists_user)
        self._init_tree_queue(self.tr_queue_download)
        self.queue_manager.pb_queue_download_run()

        self._init_info()
        self._init_progressbar()
        self._populate_quality(self.cb_quality_audio, Quality)
        self._populate_quality(self.cb_quality_video, QualityVideo)
        self._populate_search_types(self.cb_search_type, SearchTypes)

        self.apply_settings(self.settings)
        self.initialize_menu_actions()
        self._init_signals()

    def _connect_runtime_signals(self) -> None:
        """Connect cross-thread callback and playlist result signals.

        Returns:
            None: Queued results are delivered on the GUI thread.
        """
        self.s_invoke_callback.connect(self._on_invoke_callback)
        XStream.stdout().message_written.connect(self._log_output)

    @override
    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        """Persist geometry and stop pending application work before closing.

        Args:
            event (QCloseEvent): Qt close request.

        Returns:
            None: The event is accepted after cleanup is requested.
        """
        if self.shutdown:
            event.accept()
            return

        logger_gui.info("Closing the main window.")
        self.shutdown = True
        self._save_window_geometry()

        handling_app = HandlingApp()
        handling_app.event_abort.set()
        self.threadpool.clear()
        self.hover_manager.stop()
        self.on_spinner_stop()
        event.accept()

    def _save_window_geometry(self) -> None:
        """Persist normal window geometry for the next application launch.

        Returns:
            None: Save errors are logged without preventing application exit.
        """
        geometry = (
            self.normalGeometry()
            if self.isMaximized() or self.isFullScreen()
            else self.geometry()
        )
        settings_data = self.settings.data
        settings_data.window_x = geometry.x()
        settings_data.window_y = geometry.y()
        settings_data.window_w = geometry.width()
        settings_data.window_h = geometry.height()

        try:
            self.settings.save()
        except SETTINGS_WRITE_ERRORS:
            logger_gui.exception("Failed to save window geometry on exit.")

    def apply_settings(self, settings: Settings) -> None:
        """Apply typed user settings to their corresponding controls.

        Args:
            settings (Settings): Application settings to apply.

        Returns:
            None: Matching combo-box options are selected in place.
        """
        self._select_combo_value(
            self.cb_quality_audio,
            settings.data.quality_audio,
            fallback_index=1,
        )
        self._select_combo_value(
            self.cb_quality_video,
            settings.data.quality_video,
            fallback_index=0,
        )

    @staticmethod
    def _select_combo_value(
        combo_box: QtWidgets.QComboBox,
        value: object,
        *,
        fallback_index: int,
    ) -> None:
        """Select combo data or a bounded fallback index.

        Args:
            combo_box (QComboBox): Target settings control.
            value (object): Item data value to locate.
            fallback_index (int): Preferred index when no value matches.

        Returns:
            None: Selection is updated when the combo contains items.
        """
        if combo_box.count() == 0:
            return

        if (matching_index := combo_box.findData(value)) >= 0:
            combo_box.setCurrentIndex(matching_index)
            return

        bounded_index = min(max(fallback_index, 0), combo_box.count() - 1)
        combo_box.setCurrentIndex(bounded_index)

    def thread_it(
        self,
        function: Callable[_P, _R],
        *args: _P.args,
        **kwargs: _P.kwargs,
    ) -> None:
        """Dispatch a callable to the application thread pool.

        Args:
            function (Callable[_P, _R]): Work to execute off the GUI thread.
            *args (_P.args): Positional arguments forwarded to ``function``.
            **kwargs (_P.kwargs): Keyword arguments forwarded to ``function``.

        Returns:
            None: The pool owns and schedules the created worker.
        """
        self.threadpool.start(Worker(function, *args, **kwargs))
