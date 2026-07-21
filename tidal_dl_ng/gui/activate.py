"""Bootstrap the graphical TIDAL Downloader application.

This module owns process-level Qt configuration: high-DPI behavior,
application metadata, global theming, desktop integration, exception
reporting, and graceful shutdown.  Screen layout and application logic remain
in their dedicated GUI modules.
"""

from __future__ import annotations

import ctypes
import importlib
import logging
import signal
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Never, cast

from PySide6 import QtCore, QtGui, QtWidgets
from tidalapi.exceptions import TidalAPIError

from tidal_dl_ng import __name_display__, __version__

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import FrameType, ModuleType, TracebackType

    from tidal_dl_ng.config import Tidal
    from tidal_dl_ng.gui.main_window import MainWindow

qdarktheme: ModuleType = importlib.import_module("qdarktheme")

logger: logging.Logger = logging.getLogger(__name__)

ORGANIZATION_NAME: str = "exislow"
ORGANIZATION_DOMAIN: str = "exislow.tidal.dl-ng"
SIGNAL_POLL_INTERVAL_MS: int = 250
TOOLTIP_STYLE: str = "QToolTip { border: 0; }"

ICON_RESOURCES: tuple[tuple[str, int], ...] = (
    ("icon16.png", 16),
    ("icon32.png", 32),
    ("icon48.png", 48),
    ("icon64.png", 64),
    ("icon256.png", 256),
    ("icon512.png", 512),
)

SESSION_RECOVERY_ERRORS: tuple[type[Exception], ...] = (
    AttributeError,
    OSError,
    TidalAPIError,
    TypeError,
    ValueError,
)


def _configure_high_dpi() -> None:
    """Configure Qt 6 high-DPI rounding before application creation.

    Returns:
        None: This function configures Qt's process-wide policy in place.
    """
    QtWidgets.QApplication.setHighDpiScaleFactorRoundingPolicy(
        QtCore.Qt.HighDpiScaleFactorRoundingPolicy.PassThrough,
    )


def _get_application() -> QtWidgets.QApplication:
    """Return the process QApplication, creating it when necessary.

    Returns:
        QtWidgets.QApplication: The process-wide GUI application.

    Raises:
        RuntimeError: If a non-GUI QCoreApplication already exists.
    """
    if (application := QtWidgets.QApplication.instance()) is None:
        _configure_high_dpi()
        return QtWidgets.QApplication(sys.argv)
    if isinstance(application, QtWidgets.QApplication):
        return application

    message = (
        "A QCoreApplication already exists; the GUI requires a QApplication."
    )
    raise RuntimeError(message)


def _setup_application_metadata(
    application: QtWidgets.QApplication,
) -> None:
    """Set metadata used by desktop environments and window managers.

    Args:
        application (QtWidgets.QApplication): Application to configure.

    Returns:
        None: The application is configured in place.
    """
    application.setApplicationName(__name_display__)
    application.setApplicationDisplayName(__name_display__)
    application.setApplicationVersion(__version__)
    application.setOrganizationName(ORGANIZATION_NAME)
    application.setOrganizationDomain(ORGANIZATION_DOMAIN)


def _resolve_resource_path(relative_path: str) -> Path:
    """Resolve a packaged resource without extending the import cycle.

    Args:
        relative_path (str): Resource path relative to the project root.

    Returns:
        Path: Absolute resource location for source or frozen builds.
    """
    path_module = importlib.import_module("tidal_dl_ng.helper.path")
    resource_locator = cast(
        "Callable[[str], str]",
        path_module.resource_path,
    )
    return Path(resource_locator(relative_path)).resolve()


def _create_application_icon() -> QtGui.QIcon:
    """Build a multi-resolution icon for source and frozen installations.

    Returns:
        QtGui.QIcon: Icon containing every available resolution.
    """
    application_icon = QtGui.QIcon()

    for filename, size in ICON_RESOURCES:
        try:
            icon_path = _resolve_resource_path(
                f"tidal_dl_ng/ui/{filename}",
            )
            if icon_path.is_file():
                application_icon.addFile(
                    str(icon_path),
                    QtCore.QSize(size, size),
                )
            else:
                logger.warning("Icon file not found: %s", icon_path)
        except OSError:
            logger.exception("Unable to read icon resource: %s", filename)

    return application_icon


def _is_frozen_application() -> bool:
    """Report whether a supported freezer built the current process.

    Returns:
        bool: ``True`` for PyInstaller or Nuitka executables.
    """
    current_module = sys.modules.get(__name__)
    return hasattr(sys, "frozen") or (
        current_module is not None and hasattr(current_module, "__compiled__")
    )


def _setup_windows_app_id() -> None:
    """Set the source build's Windows taskbar grouping identifier.

    Frozen builds provide their own AppUserModelID, so only source-based
    Windows launches need this process-level setting.

    Returns:
        None: Non-Windows and frozen processes are left unchanged.
    """
    if sys.platform != "win32" or _is_frozen_application():
        return

    app_user_model_id = f"{ORGANIZATION_NAME}.tidal.dl-ng.{__version__}"
    try:
        set_app_user_model_id = cast(
            "Callable[[str], int]",
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID,
        )
        result = set_app_user_model_id(app_user_model_id)
    except (AttributeError, OSError):
        logger.exception(
            "Unable to set Windows AppUserModelID: %s",
            app_user_model_id,
        )
        return

    if result:
        logger.warning(
            "Windows rejected AppUserModelID %s with HRESULT %s.",
            app_user_model_id,
            result,
        )
    else:
        logger.debug(
            "Set Windows AppUserModelID: %s",
            app_user_model_id,
        )


def _setup_exception_hook() -> None:
    """Log uncaught Qt callback exceptions before normal reporting.

    Returns:
        None: The process-wide exception hook is replaced in place.
    """
    default_exception_hook = sys.__excepthook__

    def _exception_hook(
        exception_type: type[BaseException],
        exception: BaseException,
        traceback: TracebackType | None,
    ) -> None:
        """Log and report one uncaught exception.

        Args:
            exception_type (type[BaseException]): Concrete exception type.
            exception (BaseException): Uncaught exception instance.
            traceback (TracebackType | None): Associated traceback.

        Returns:
            None: Reporting is performed through logging and stderr.
        """
        exception_details = (exception_type, exception, traceback)
        logger.critical("Unhandled GUI exception.", exc_info=exception_details)
        default_exception_hook(*exception_details)

    sys.excepthook = _exception_hook


def _setup_signal_handlers(
    application: QtWidgets.QApplication,
) -> None:
    """Install graceful process-shutdown handlers for the Qt event loop.

    A lightweight Qt timer periodically invokes Python so its signal handlers
    continue to run while Qt owns the main event loop.

    Args:
        application (QtWidgets.QApplication): Application to stop.

    Returns:
        None: Handlers and their application-owned timer are installed.
    """

    def _handle_shutdown(
        signal_number: int,
        _frame: FrameType | None,
    ) -> None:
        """Request application shutdown after an operating-system signal.

        Args:
            signal_number (int): Received operating-system signal number.
            _frame (FrameType | None): Interrupted Python stack frame.

        Returns:
            None: Shutdown is requested asynchronously through Qt.
        """
        logger.info(
            "Shutdown signal %s received; quitting application.",
            signal_number,
        )
        application.quit()

    def _allow_python_signal_dispatch() -> None:
        """Allow Python to dispatch pending signals during Qt event loops."""

    try:
        signal.signal(signal.SIGINT, _handle_shutdown)
        signal.signal(signal.SIGTERM, _handle_shutdown)
    except (OSError, ValueError):
        logger.debug(
            "Process signal handlers are unavailable outside the main thread.",
            exc_info=True,
        )

    signal_timer = QtCore.QTimer(application)
    signal_timer.setInterval(SIGNAL_POLL_INTERVAL_MS)
    signal_timer.timeout.connect(_allow_python_signal_dispatch)
    signal_timer.start()


def _ensure_tidal_session(tidal: Tidal | None) -> Tidal | None:
    """Validate or recover an injected TIDAL session before startup.

    Args:
        tidal (Tidal | None): Optional session supplied by the CLI.

    Returns:
        Tidal | None: A verified session, or ``None`` to start the normal
        interactive login flow.
    """
    if tidal is None:
        return None

    try:
        if tidal.session.check_login():
            return tidal
    except SESSION_RECOVERY_ERRORS:
        logger.warning(
            "Injected TIDAL session validation failed; attempting stored "
            "token login.",
            exc_info=True,
        )

    try:
        if tidal.login_token():
            logger.info("Recovered injected TIDAL session from stored token.")
            return tidal
    except SESSION_RECOVERY_ERRORS:
        logger.exception("Injected TIDAL session recovery failed.")

    logger.info(
        "Injected TIDAL session is invalid; using interactive login.",
    )
    return None


def _load_main_window_class() -> type[MainWindow]:
    """Load the main window after bootstrap dependencies are initialized.

    Returns:
        type[MainWindow]: Concrete application window class.
    """
    main_window_module = importlib.import_module(
        "tidal_dl_ng.gui.main_window",
    )
    return cast(
        "type[MainWindow]",
        main_window_module.MainWindow,
    )


def gui_activate(tidal: Tidal | None = None) -> Never:
    """Configure and run the graphical application until process exit.

    Args:
        tidal (Tidal | None): Optional pre-existing TIDAL session. Invalid
            sessions fall back to the main window's login flow.

    Raises:
        SystemExit: After the Qt event loop finishes, using its exit status.
    """
    application = _get_application()
    application.setQuitOnLastWindowClosed(True)

    _setup_application_metadata(application)
    qdarktheme.setup_theme(
        theme="dark",
        corner_shape="rounded",
        additional_qss=TOOLTIP_STYLE,
    )
    application.setWindowIcon(_create_application_icon())
    _setup_windows_app_id()
    _setup_exception_hook()
    _setup_signal_handlers(application)

    logger.info("Starting GUI %s on %s.", __version__, sys.platform)

    main_window_class = _load_main_window_class()
    main_window = main_window_class(tidal=_ensure_tidal_session(tidal))
    main_window.show()

    exit_code = application.exec()
    logger.info("GUI stopped with exit status %s.", exit_code)
    raise SystemExit(exit_code)


if __name__ == "__main__":
    gui_activate()
