"""GUI activation and entry point for TIDAL Downloader Next Generation.

Handles Qt application bootstrap, dark theme setup, window icon
configuration, and platform-specific Windows taskbar integration.
"""

import importlib
import logging
import signal
import sys
from pathlib import Path
from types import TracebackType

from tidal_dl_ng import __name_display__, __version__
from tidal_dl_ng.config import Tidal
from tidal_dl_ng.helper.path import resource_path

logger = logging.getLogger(__name__)

# Icon sizes to load for the application window (multi-resolution support).
_ICON_SIZES: tuple[tuple[str, int, int], ...] = (
    ("icon16.png", 16, 16),
    ("icon32.png", 32, 32),
    ("icon48.png", 48, 48),
    ("icon64.png", 64, 64),
    ("icon256.png", 256, 256),
    ("icon512.png", 512, 512),
)

try:
    qdarktheme = importlib.import_module("qdarktheme")
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:
    logger.exception(
        "Qt dependencies missing. Please install the 'gui' extras: pip install tidal-dl-ng-for-dj[gui]"
    )
    sys.exit(1)


def _setup_application_metadata(app: QtWidgets.QApplication) -> None:
    """Set Qt application metadata for proper desktop integration.

    Args:
        app: The QApplication instance to configure.
    """
    app.setApplicationName(__name_display__)
    app.setApplicationDisplayName(__name_display__)
    app.setApplicationVersion(__version__)
    app.setOrganizationName("exislow")
    app.setOrganizationDomain("exislow.tidal.dl-ng")


def _create_app_icon() -> QtGui.QIcon:
    """Create the application icon with multiple resolutions.

    Uses resource_path() to locate icon files correctly in both
    development and frozen (Nuitka/PyInstaller) environments.

    Returns:
        A QIcon with multiple resolution variants.
    """
    icon: QtGui.QIcon = QtGui.QIcon()

    for filename, width, height in _ICON_SIZES:
        icon_path: str = resource_path(f"tidal_dl_ng/ui/{filename}")
        if Path(icon_path).exists():
            icon.addFile(icon_path, QtCore.QSize(width, height))
        else:
            logger.warning("Icon file not found: %s", icon_path)

    return icon


def _setup_windows_app_id() -> None:
    """Set the Windows AppUserModelID for proper taskbar icon grouping.

    This ensures the taskbar icon works correctly on Windows and that
    PyInstaller/Nuitka builds are properly grouped with their shortcuts.
    """
    if not sys.platform.startswith("win"):
        return

    import ctypes

    # Only set custom AppUserModelID when NOT running as a frozen .exe,
    # since Nuitka/PyInstaller set their own ID for frozen builds.
    if not sys.argv[0].endswith(".exe"):
        my_app_id: str = f"exislow.tidal.dl-ng.{__version__}"
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            my_app_id
        )
        logger.debug("Set Windows AppUserModelID: %s", my_app_id)


def _setup_exception_hook() -> None:
    """Install a global exception hook for unhandled Qt exceptions.

    Ensures unhandled exceptions in Qt slots/signals are logged
    rather than silently swallowed.
    """

    def _exception_hook(
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_tb: TracebackType | None,
    ) -> None:
        logger.critical(
            "Unhandled exception:", exc_info=(exc_type, exc_value, exc_tb)
        )
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = _exception_hook


def _setup_signal_handlers(app: QtWidgets.QApplication) -> None:
    """Install OS signal handlers for graceful GUI shutdown.

    Args:
        app: The QApplication instance used by the GUI.
    """

    def _handle_interrupt(_sig: int, _frame: object) -> None:
        logger.info("Shutdown signal received. Quitting application...")
        app.quit()

    try:
        signal.signal(signal.SIGINT, _handle_interrupt)
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, _handle_interrupt)
    except ValueError:
        # Raised when signal handlers are set from a non-main thread.
        logger.debug(
            "Signal handlers can only be installed from the main thread."
        )


def _ensure_tidal_session(tidal: Tidal | None) -> Tidal | None:
    """Validate or recover a provided Tidal session before GUI startup.

    If a caller injects a stale session object, this function attempts token
    re-login first. If validation still fails, it returns None so MainWindow
    can run the normal interactive login flow.

    Args:
        tidal: Optional pre-existing Tidal object.

    Returns:
        A verified Tidal object, or None to trigger normal login flow.
    """
    if tidal is None:
        return None

    try:
        if tidal.session.check_login():
            return tidal
    except Exception:
        logger.warning(
            "Injected Tidal session check failed; attempting token login."
        )

    try:
        if tidal.login_token():
            logger.info("Recovered injected Tidal session via stored token.")
            return tidal
    except Exception:
        logger.exception("Injected Tidal session recovery failed.")

    logger.info(
        "Injected Tidal session is invalid. Falling back to interactive login flow."
    )
    return None


def gui_activate(tidal: Tidal | None = None) -> None:
    """Activate the GUI application.

    Bootstraps the Qt application, applies the dark theme, configures
    the window icon, and launches the main window.

    Args:
        tidal: Optional pre-existing Tidal session. If None, the
            MainWindow will initiate its own login flow.
    """
    from tidal_dl_ng.gui.main_window import MainWindow

    # Enable HiDPI support (sets rounding policy for Qt6, no-op otherwise).
    qdarktheme.enable_hi_dpi()

    # Create the Qt application instance, or reuse an existing one.
    app_instance = QtWidgets.QApplication.instance()
    app = (
        app_instance
        if isinstance(app_instance, QtWidgets.QApplication)
        else QtWidgets.QApplication(sys.argv)
    )

    app.setQuitOnLastWindowClosed(True)

    # Set application metadata for desktop integration.
    _setup_application_metadata(app)

    # Apply dark theme with Windows tooltip fix.
    # https://github.com/5yutan5/PyQtDarkTheme/issues/239
    qdarktheme.setup_theme(additional_qss="QToolTip { border: 0px; }")

    # Configure application icon.
    app.setWindowIcon(_create_app_icon())

    # Windows taskbar icon integration.
    _setup_windows_app_id()

    # Install global exception hook for unhandled Qt errors.
    _setup_exception_hook()

    # Install process signal handlers for graceful shutdown.
    _setup_signal_handlers(app)

    logger.info("Starting GUI %s on %s", __version__, sys.platform)

    verified_tidal = _ensure_tidal_session(tidal)

    # Create and show the main window.
    window = MainWindow(tidal=verified_tidal)
    window.show()

    exit_code: int = app.exec()
    sys.exit(exit_code)


if __name__ == "__main__":
    gui_activate()
