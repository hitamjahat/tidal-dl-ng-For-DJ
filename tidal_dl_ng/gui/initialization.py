"""Initialize responsive components for the main application window.

This mixin owns lightweight GUI setup and dependency wiring. Generated UI
classes remain responsible for layout construction, while long-running work
is delegated to the application's thread pool and event-driven managers.
"""

from __future__ import annotations

import inspect
from collections.abc import Iterable
from enum import Enum
from typing import TYPE_CHECKING, Protocol, TypedDict, cast

from ansi2html import Ansi2HTMLConverter
from PySide6 import QtCore, QtGui, QtWidgets
from rich.progress import Progress

from tidal_dl_ng.config import HandlingApp
from tidal_dl_ng.download import Download
from tidal_dl_ng.helper.gui import FilterHeader, HumanProxyModel
from tidal_dl_ng.helper.hover_manager import HoverManager
from tidal_dl_ng.helper.path import resource_path
from tidal_dl_ng.logger import logger_gui
from tidal_dl_ng.model.downloader import DownloadContext
from tidal_dl_ng.model.gui_data import ProgressBars

if TYPE_CHECKING:
    from collections.abc import Callable

    from tidal_dl_ng.config import Settings, Tidal
    from tidal_dl_ng.gui.playlist import GuiPlaylistManager
    from tidal_dl_ng.history import HistoryService
    from tidal_dl_ng.model.cfg import Settings as ModelSettings
    from tidal_dl_ng.ui.spinner import QtWaitingSpinner

type QueueView = QtWidgets.QTreeWidget | QtWidgets.QTableWidget


class _InitializationSignals(Protocol):
    """Describe progress signals supplied by the concrete main window."""

    @property
    def s_item_advance(self) -> QtCore.SignalInstance:
        """Return the item-progress signal."""
        raise NotImplementedError

    @property
    def s_item_name(self) -> QtCore.SignalInstance:
        """Return the item-name signal."""
        raise NotImplementedError

    @property
    def s_list_advance(self) -> QtCore.SignalInstance:
        """Return the list-progress signal."""
        raise NotImplementedError

    @property
    def s_list_name(self) -> QtCore.SignalInstance:
        """Return the list-name signal."""
        raise NotImplementedError


class _InitializationCallbacks(Protocol):
    """Describe handlers supplied by the main-window mixin assembly."""

    @property
    def handle_filter_activated(self) -> Callable[[], None]:
        """Return the results-filter handler."""
        raise NotImplementedError

    @property
    def menu_context_tree_results(
        self,
    ) -> Callable[[QtCore.QPoint], None]:
        """Return the results context-menu handler."""
        raise NotImplementedError

    @property
    def menu_context_queue_download(
        self,
    ) -> Callable[[QtCore.QPoint], None]:
        """Return the queue context-menu handler."""
        raise NotImplementedError

    @property
    def on_track_hover_confirmed(self) -> Callable[[object], None]:
        """Return the confirmed-hover handler."""
        raise NotImplementedError

    @property
    def on_track_hover_left(self) -> Callable[[], None]:
        """Return the hover-left handler."""
        raise NotImplementedError

    @property
    def on_view_history(self) -> Callable[[], None]:
        """Return the view-history handler."""
        raise NotImplementedError

    @property
    def on_toggle_duplicate_prevention(
        self,
    ) -> Callable[[bool], None]:
        """Return the duplicate-prevention handler."""
        raise NotImplementedError


class _ProgressSignalArguments(TypedDict):
    """Keyword arguments used to construct GUI progress handles."""

    item: QtCore.SignalInstance
    item_name: QtCore.SignalInstance
    list_item: QtCore.SignalInstance
    list_name: QtCore.SignalInstance


RESULT_COLUMN_LABELS: tuple[str, ...] = (
    "#",
    "obj",
    "Artist",
    "Title",
    "Album",
    "Duration",
    "Quality",
    "Date",
    "Downloaded?",
    "Playlists",
)

WINDOW_MINIMUM_WIDTH: int = 640
WINDOW_MINIMUM_HEIGHT: int = 480
WINDOW_DEFAULT_WIDTH_RATIO: float = 0.6
WINDOW_DEFAULT_HEIGHT_RATIO: float = 0.65
FALLBACK_SCREEN_RECT: QtCore.QRect = QtCore.QRect(0, 0, 1280, 720)

PROGRESS_MINIMUM: int = 0
PROGRESS_MAXIMUM: int = 100
HOVER_DEBOUNCE_MS: int = 150
DEFAULT_SEARCH_TYPE_INDEX: int = 2

TOOLS_MENU_TITLE: str = "Tools"
VIEW_HISTORY_ACTION_NAME: str = "action_view_download_history"
DUPLICATE_ACTION_NAME: str = "action_prevent_duplicate_downloads"


def _validated_int(value: object, fallback: int) -> int:
    """Return an integer setting or a safe fallback.

    Args:
        value (object): Untrusted persisted setting value.
        fallback (int): Value used for non-integer settings.

    Returns:
        int: Validated integer value.
    """
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return fallback


def _resolve_window_geometry(
    settings_data: ModelSettings,
    available: QtCore.QRect,
) -> QtCore.QRect:
    """Resolve saved window geometry within the available screen.

    Args:
        settings_data (ModelSettings): Persisted application settings.
        available (QRect): Available desktop area for the active screen.

    Returns:
        QRect: A positive, visible, screen-bounded window rectangle.
    """
    screen_rect = (
        QtCore.QRect(available)
        if available.width() > 0 and available.height() > 0
        else QtCore.QRect(FALLBACK_SCREEN_RECT)
    )
    screen_width = screen_rect.width()
    screen_height = screen_rect.height()

    default_width = min(
        screen_width,
        max(
            WINDOW_MINIMUM_WIDTH,
            round(screen_width * WINDOW_DEFAULT_WIDTH_RATIO),
        ),
    )
    default_height = min(
        screen_height,
        max(
            WINDOW_MINIMUM_HEIGHT,
            round(screen_height * WINDOW_DEFAULT_HEIGHT_RATIO),
        ),
    )

    saved_width = _validated_int(settings_data.window_w, default_width)
    saved_height = _validated_int(settings_data.window_h, default_height)
    width = (
        min(saved_width, screen_width) if saved_width > 0 else default_width
    )
    height = (
        min(saved_height, screen_height)
        if saved_height > 0
        else default_height
    )

    centered_x = screen_rect.x() + (screen_width - width) // 2
    centered_y = screen_rect.y() + (screen_height - height) // 2
    saved_x = _validated_int(settings_data.window_x, centered_x)
    saved_y = _validated_int(settings_data.window_y, centered_y)

    maximum_x = screen_rect.x() + screen_width - width
    maximum_y = screen_rect.y() + screen_height - height
    x_position = min(max(saved_x, screen_rect.x()), maximum_x)
    y_position = min(max(saved_y, screen_rect.y()), maximum_y)
    return QtCore.QRect(x_position, y_position, width, height)


class InitializationMixin:
    """Initialize typed, responsive main-window components."""

    settings: Settings
    tidal: Tidal
    history_service: HistoryService
    playlist_manager: GuiPlaylistManager
    statusbar: QtWidgets.QStatusBar
    l_pm_cover: QtWidgets.QLabel
    cb_search_type: QtWidgets.QComboBox
    dl: Download
    threadpool: QtCore.QThreadPool
    proxy_tr_results: HumanProxyModel
    hover_manager: HoverManager
    pb_list: QtWidgets.QProgressBar
    pb_item: QtWidgets.QProgressBar
    a_view_history: QtGui.QAction
    a_toggle_duplicate_prevention: QtGui.QAction

    def initialize_gui(self) -> None:
        """Initialize geometry and lightweight GUI helper state.

        Returns:
            None: Window state and helper objects are initialized in place.
        """
        self._apply_window_geometry(self.settings.data)
        self.spinners: dict[QtWidgets.QWidget, QtWaitingSpinner] = {}
        self.converter_ansi_html = Ansi2HTMLConverter()

    def _init_gui(self) -> None:
        """Retain the legacy private entry point for GUI initialization.

        Returns:
            None: Initialization is delegated to :meth:`initialize_gui`.
        """
        self.initialize_gui()

    def _apply_window_geometry(self, settings_data: ModelSettings) -> None:
        """Apply validated geometry that keeps window controls visible.

        Args:
            settings_data (ModelSettings): Persisted window geometry values.

        Returns:
            None: Geometry and minimum size are applied to the main window.
        """
        window = self._window()
        screen_geometry = window.screen().availableGeometry()
        geometry = _resolve_window_geometry(settings_data, screen_geometry)

        window.setWindowFlags(
            QtCore.Qt.WindowType.Window
            | QtCore.Qt.WindowType.WindowMinimizeButtonHint
            | QtCore.Qt.WindowType.WindowMaximizeButtonHint
            | QtCore.Qt.WindowType.WindowCloseButtonHint,
        )
        window.setMinimumSize(
            min(WINDOW_MINIMUM_WIDTH, screen_geometry.width()),
            min(WINDOW_MINIMUM_HEIGHT, screen_geometry.height()),
        )
        window.setGeometry(geometry)

    def _init_threads(self) -> None:
        """Create the application-owned pool for background operations.

        The queue manager is event-driven, so no blocking watcher is started.

        Returns:
            None: A parent-owned thread pool is available to other managers.
        """
        self.threadpool = QtCore.QThreadPool(self._qobject())

    def _init_dl(self) -> None:
        """Build the download service with progress and control handles.

        Returns:
            None: The configured download service replaces ``self.dl``.
        """
        signals = self._signals()
        progress_signal_arguments = _ProgressSignalArguments(
            item=signals.s_item_advance,
            item_name=signals.s_item_name,
            list_item=signals.s_list_advance,
            list_name=signals.s_list_name,
        )
        progress_bars = ProgressBars(**progress_signal_arguments)
        handling_app = HandlingApp()
        self.dl = Download(
            tidal_obj=self.tidal,
            skip_existing=self.settings.data.skip_existing,
            path_base=self.settings.data.download_base_path,
            fn_logger=logger_gui,
            context=DownloadContext(
                progress_gui=progress_bars,
                progress=Progress(),
                event_abort=handling_app.event_abort,
                event_run=handling_app.event_run,
            ),
        )

    def _init_progressbar(self) -> None:
        """Create status-bar progress indicators using the status layout.

        Returns:
            None: Item and list progress bars are added permanently.
        """
        self.pb_list = self._create_progress_bar(
            "listDownloadProgress",
            "Overall list download progress",
        )
        self.pb_item = self._create_progress_bar(
            "itemDownloadProgress",
            "Current item download progress",
        )
        self.statusbar.addPermanentWidget(self.pb_list, stretch=1)
        self.statusbar.addPermanentWidget(self.pb_item, stretch=1)

    def _create_progress_bar(
        self,
        object_name: str,
        accessible_name: str,
    ) -> QtWidgets.QProgressBar:
        """Create one accessible progress bar owned by the status bar.

        Args:
            object_name (str): Stable Qt object name.
            accessible_name (str): Screen-reader description.

        Returns:
            QProgressBar: Configured progress bar widget.
        """
        progress_bar = QtWidgets.QProgressBar(self.statusbar)
        progress_bar.setObjectName(object_name)
        progress_bar.setAccessibleName(accessible_name)
        progress_bar.setRange(PROGRESS_MINIMUM, PROGRESS_MAXIMUM)
        progress_bar.setTextVisible(True)
        return progress_bar

    def _init_info(self) -> None:
        """Load the default cover with accessible fallback presentation.

        Returns:
            None: The cover label is updated in place.
        """
        image_path = resource_path(
            "tidal_dl_ng/ui/default_album_image.png",
        )
        pixmap = QtGui.QPixmap(image_path)
        if pixmap.isNull():
            logger_gui.warning(
                "Default album image could not be loaded: %s",
                image_path,
            )

        self.l_pm_cover.setPixmap(pixmap)
        self.l_pm_cover.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.l_pm_cover.setAccessibleName("Album cover artwork")

    def _init_tree_results(
        self,
        tree: QtWidgets.QTreeView,
        model: QtGui.QStandardItemModel,
    ) -> None:
        """Configure the responsive, filterable results model and view.

        Args:
            tree (QTreeView): Results view from the generated main UI.
            model (QStandardItemModel): Source results model.

        Returns:
            None: Proxy, header, hover, and context-menu wiring is installed.
        """
        callbacks = self._callbacks()
        header = FilterHeader(tree)
        self.proxy_tr_results = HumanProxyModel(self._qobject())
        self.proxy_tr_results.setSourceModel(model)

        tree.setHeader(header)
        tree.setModel(self.proxy_tr_results)
        tree.setSortingEnabled(True)
        tree.setUniformRowHeights(True)
        tree.setAlternatingRowColors(True)
        tree.setAccessibleName("Search and collection results")
        tree.hideColumn(1)
        tree.sortByColumn(0, QtCore.Qt.SortOrder.AscendingOrder)

        header.setStretchLastSection(False)
        header.setMinimumSectionSize(60)
        header.setSectionResizeMode(
            0,
            QtWidgets.QHeaderView.ResizeMode.ResizeToContents,
        )
        for column in (2, 3, 4):
            header.setSectionResizeMode(
                column,
                QtWidgets.QHeaderView.ResizeMode.Stretch,
            )
        for column in (5, 6, 7, 8, 9):
            header.setSectionResizeMode(
                column,
                QtWidgets.QHeaderView.ResizeMode.ResizeToContents,
            )

        header.set_filter_boxes(model.columnCount())
        header.filter_activated.connect(
            callbacks.handle_filter_activated,
        )
        tree.setContextMenuPolicy(
            QtCore.Qt.ContextMenuPolicy.CustomContextMenu,
        )
        tree.customContextMenuRequested.connect(
            callbacks.menu_context_tree_results,
        )

        self.hover_manager = HoverManager(
            tree_view=tree,
            proxy_model=self.proxy_tr_results,
            source_model=model,
            debounce_delay_ms=HOVER_DEBOUNCE_MS,
            parent=self._qobject(),
        )
        self.hover_manager.s_hover_confirmed.connect(
            callbacks.on_track_hover_confirmed,
        )
        self.hover_manager.s_hover_left.connect(
            callbacks.on_track_hover_left,
        )

    def _init_tree_results_model(
        self,
        model: QtGui.QStandardItemModel,
    ) -> None:
        """Initialize the source model's stable column schema.

        Args:
            model (QStandardItemModel): Results model to reset.

        Returns:
            None: Rows are cleared and headers are assigned.
        """
        model.clear()
        model.setColumnCount(len(RESULT_COLUMN_LABELS))
        model.setHorizontalHeaderLabels(list(RESULT_COLUMN_LABELS))

    def _init_tree_queue(self, tree: QueueView) -> None:
        """Configure a responsive queue view and its context menu.

        Args:
            tree (QueueView): Tree- or table-based queue widget.

        Returns:
            None: Header behavior and context-menu wiring are installed.
        """
        tree.hideColumn(1)
        header = (
            tree.header()
            if isinstance(tree, QtWidgets.QTreeWidget)
            else tree.horizontalHeader()
        )
        header.setMinimumSectionSize(60)
        header.setSectionResizeMode(
            0,
            QtWidgets.QHeaderView.ResizeMode.ResizeToContents,
        )
        header.setSectionResizeMode(
            2,
            QtWidgets.QHeaderView.ResizeMode.Stretch,
        )
        tree.setContextMenuPolicy(
            QtCore.Qt.ContextMenuPolicy.CustomContextMenu,
        )
        tree.customContextMenuRequested.connect(
            self._callbacks().menu_context_queue_download,
        )

    def _init_tree_lists(self, tree: QtWidgets.QTreeWidget) -> None:
        """Configure the responsive user-lists tree.

        Args:
            tree (QTreeWidget): User playlists, mixes, and favorites tree.

        Returns:
            None: Header behavior and context-menu wiring are installed.
        """
        tree.hideColumn(1)
        tree.setUniformRowHeights(True)
        tree.setAlternatingRowColors(True)
        tree.setAccessibleName("Playlists, mixes, and favorites")
        header = tree.header()
        header.setMinimumSectionSize(80)
        header.setSectionResizeMode(
            0,
            QtWidgets.QHeaderView.ResizeMode.Stretch,
        )
        header.setSectionResizeMode(
            2,
            QtWidgets.QHeaderView.ResizeMode.ResizeToContents,
        )
        tree.expandAll()
        tree.setContextMenuPolicy(
            QtCore.Qt.ContextMenuPolicy.CustomContextMenu,
        )
        tree.customContextMenuRequested.connect(
            self.playlist_manager.menu_context_tree_lists,
        )

    def initialize_menu_actions(self) -> None:
        """Create accessible history actions in the Tools menu.

        Returns:
            None: Main-window actions are created and connected.
        """
        window = self._window()
        tools_menu = self._find_or_create_tools_menu(window.menuBar())
        callbacks = self._callbacks()

        self.a_view_history = QtGui.QAction(
            "View Download History\N{HORIZONTAL ELLIPSIS}",
            window,
        )
        self.a_view_history.setObjectName(VIEW_HISTORY_ACTION_NAME)
        self.a_view_history.setStatusTip(
            "View, import, export, or clear download history",
        )
        self.a_view_history.setShortcut(QtGui.QKeySequence("Ctrl+Shift+H"))
        self.a_view_history.triggered.connect(callbacks.on_view_history)
        tools_menu.addAction(self.a_view_history)
        tools_menu.addSeparator()

        self.a_toggle_duplicate_prevention = QtGui.QAction(
            "Prevent Duplicate Downloads",
            window,
        )
        self.a_toggle_duplicate_prevention.setObjectName(
            DUPLICATE_ACTION_NAME,
        )
        self.a_toggle_duplicate_prevention.setStatusTip(
            "Skip tracks that are already recorded in download history",
        )
        self.a_toggle_duplicate_prevention.setCheckable(True)
        history_settings = self.history_service.get_settings()
        self.a_toggle_duplicate_prevention.setChecked(
            history_settings.get("preventDuplicates", True),
        )
        self.a_toggle_duplicate_prevention.triggered.connect(
            callbacks.on_toggle_duplicate_prevention,
        )
        tools_menu.addAction(self.a_toggle_duplicate_prevention)

    def _init_menu_actions(self) -> None:
        """Retain the legacy private menu-initialization entry point.

        Returns:
            None: Initialization delegates to
                :meth:`initialize_menu_actions`.
        """
        self.initialize_menu_actions()

    @staticmethod
    def _find_or_create_tools_menu(
        menubar: QtWidgets.QMenuBar,
    ) -> QtWidgets.QMenu:
        """Return the existing Tools menu or create it.

        Args:
            menubar (QMenuBar): Main-window menu bar.

        Returns:
            QMenu: Existing or newly created Tools menu.
        """
        for action in menubar.actions():
            menu = action.menu()
            if isinstance(menu, QtWidgets.QMenu) and action.text().replace(
                "&",
                "",
            ) == (TOOLS_MENU_TITLE):
                return menu
        return menubar.addMenu(TOOLS_MENU_TITLE)

    def _populate_quality(
        self,
        ui_target: QtWidgets.QComboBox,
        options: object,
    ) -> None:
        """Populate a combo box from an enum class or enum iterable.

        Args:
            ui_target (QComboBox): Combo box to replace with quality choices.
            options (object): Runtime iterable of enum members.

        Raises:
            TypeError: If ``options`` is not iterable or contains non-enums.

        Returns:
            None: Existing items are replaced with the supplied choices.
        """
        ui_target.clear()
        for option in self._iter_options(options):
            if not isinstance(option, Enum):
                message = "Quality options must contain enum members."
                raise TypeError(message)
            ui_target.addItem(option.name, option)

    def _populate_search_types(
        self,
        ui_target: QtWidgets.QComboBox,
        options: object,
    ) -> None:
        """Populate a combo box with supported TIDAL search model classes.

        Args:
            ui_target (QComboBox): Combo box to replace with media types.
            options (object): Iterable of media classes and optional ``None``.

        Raises:
            TypeError: If a non-class search option is supplied.

        Returns:
            None: Valid classes are inserted and the track default selected.
        """
        ui_target.clear()
        for media_type in self._iter_options(options):
            if media_type is None:
                continue
            if not inspect.isclass(media_type):
                message = "Search options must contain classes or None."
                raise TypeError(message)
            ui_target.addItem(media_type.__name__, media_type)

        if ui_target.count() > 0:
            default_index = min(
                DEFAULT_SEARCH_TYPE_INDEX,
                ui_target.count() - 1,
            )
            ui_target.setCurrentIndex(default_index)

    @staticmethod
    def _iter_options(options: object) -> Iterable[object]:
        """Validate and return a runtime options iterable.

        Args:
            options (object): Candidate combo-box options collection.

        Raises:
            TypeError: If the supplied object is not iterable.

        Returns:
            Iterable[object]: Validated options iterable.
        """
        if isinstance(options, Iterable):
            return cast("Iterable[object]", options)
        message = "Combo-box options must be iterable."
        raise TypeError(message)

    def _window(self) -> QtWidgets.QMainWindow:
        """Return the concrete main window used by this mixin.

        Raises:
            TypeError: If the mixin is attached to a non-window object.

        Returns:
            QMainWindow: Concrete Qt main window.
        """
        if isinstance(self, QtWidgets.QMainWindow):
            return self
        message = "InitializationMixin requires a QMainWindow host."
        raise TypeError(message)

    def _qobject(self) -> QtCore.QObject:
        """Return the concrete QObject used for Qt ownership.

        Raises:
            TypeError: If the mixin is attached to a non-QObject host.

        Returns:
            QObject: Concrete Qt object.
        """
        if isinstance(self, QtCore.QObject):
            return self
        message = "InitializationMixin requires a QObject host."
        raise TypeError(message)

    def _signals(self) -> _InitializationSignals:
        """Return a structural view of concrete progress signals.

        Returns:
            _InitializationSignals: Typed progress-signal interface.
        """
        return cast("_InitializationSignals", self)

    def _callbacks(self) -> _InitializationCallbacks:
        """Return a structural view of concrete event handlers.

        Returns:
            _InitializationCallbacks: Typed callback interface.
        """
        return cast("_InitializationCallbacks", self)
