"""Logging configuration and setup for the application."""

import logging
import sys
from typing import TYPE_CHECKING, ClassVar, TextIO, cast

import coloredlogs
from PySide6 import QtCore

from tidal_dl_ng.runtime_trace import setup_runtime_file_logging

if TYPE_CHECKING:
    from io import TextIOWrapper

#: Module-level format string for log messages.
LOG_FMT: str = "> %(message)s"


class LoggerState:
    """Stores the global verbosity state for the logger."""

    verbose_debug: bool = False

    @staticmethod
    def enable(*, enabled: bool = True) -> None:
        """Enable/disable showing DEBUG and WARNING records globally.

        Args:
            enabled: When True, DEBUG and WARNING messages are shown.
                     INFO/ERROR/CRITICAL are unaffected and always shown.
        """
        LoggerState.verbose_debug = bool(enabled)

    @staticmethod
    def get_verbose() -> bool:
        """Return the current verbose debug state.

        Returns:
            True if verbose debug mode is active.
        """
        return LoggerState.verbose_debug


class DebugWarningFilter(logging.Filter):
    """Dynamically suppresses DEBUG and WARNING log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Determine if the specified record is to be logged.

        Args:
            record: The log record to evaluate.

        Returns:
            True if the record should be logged, False otherwise.
        """
        return LoggerState.verbose_debug or record.levelno not in (
            logging.DEBUG,
            logging.WARNING,
        )

    def is_enabled(self) -> bool:
        """Return whether verbose debug mode is enabled.

        Returns:
            True if verbose debug mode is active.
        """
        return LoggerState.verbose_debug


class XStream(QtCore.QObject):
    """A thread-safe stream redirecting stdout/stderr to a Qt signal."""

    _stdout: ClassVar["XStream | None"] = None
    _stderr: ClassVar["XStream | None"] = None

    message_written: QtCore.Signal = QtCore.Signal(str)

    def __init__(self, *, is_stderr: bool = False) -> None:
        """Initialize the XStream.

        Args:
            is_stderr: True if this is the stderr stream.
        """
        super().__init__()
        self.is_stderr = is_stderr

    def flush(self) -> None:
        """Flush the stream (no-op for signal-based streams)."""

    def fileno(self) -> int:
        """Return an invalid file descriptor indicating non-file stream.

        Returns:
            Always -1 to signal that this is not a real file.
        """
        return -1

    def write(self, msg: str) -> int:
        """Write the message to the Qt signal and original console stream.

        Args:
            msg: The message to write.

        Returns:
            The number of characters written.
        """
        if self.is_stderr:
            if sys.__stderr__ is not None:
                sys.__stderr__.write(msg)
        elif sys.__stdout__ is not None:
            sys.__stdout__.write(msg)

        if not self.signalsBlocked():
            self.message_written.emit(msg)
        return len(msg)

    @classmethod
    def stdout(cls) -> "XStream":
        """Get or create the singleton stdout XStream.

        Returns:
            The singleton XStream for stdout.
        """
        if not cls._stdout:
            cls._stdout = cls(is_stderr=False)
            sys.stdout = cast("TextIOWrapper", cls._stdout)
        return cls._stdout

    @classmethod
    def stderr(cls) -> "XStream":
        """Get or create the singleton stderr XStream.

        Returns:
            The singleton XStream for stderr.
        """
        if not cls._stderr:
            cls._stderr = cls(is_stderr=True)
            sys.stderr = cast("TextIOWrapper", cls._stderr)
        return cls._stderr


class QtHandler(logging.Handler):
    """A logging handler that writes formatted records to XStream."""

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a record to the XStream signal.

        Args:
            record: The log record to emit.
        """
        if formatted_record := self.format(record):
            XStream.stdout().write(f"{formatted_record}\n")


def enable_debug_and_warnings(*, enabled: bool = True) -> None:
    """Enable/disable DEBUG and WARNING log records globally.

    Args:
        enabled: When True, DEBUG and WARNING messages are shown.
    """
    LoggerState.enable(enabled=enabled)


def _build_formatter() -> coloredlogs.ColoredFormatter:
    """Build a ColoredFormatter with custom info color.

    Returns:
        A configured ColoredFormatter instance.
    """
    styles: dict[str, dict[str, str | bool]] = (
        coloredlogs.DEFAULT_LEVEL_STYLES.copy()
    )
    styles["info"] = {"color": "green"}
    return coloredlogs.ColoredFormatter(fmt=LOG_FMT, level_styles=styles)


def _make_gui_logger() -> logging.Logger:
    """Create and configure the GUI logger.

    Returns:
        A configured Logger instance for the GUI.
    """
    log: logging.Logger = logging.getLogger(f"{__name__}.gui")
    handler: QtHandler = QtHandler()
    handler.setFormatter(_build_formatter())
    handler.addFilter(DebugWarningFilter())
    log.addHandler(handler)
    log.setLevel(logging.DEBUG)
    return log


def _make_cli_logger() -> logging.Logger:
    """Create and configure the CLI logger.

    Returns:
        A configured Logger instance for the CLI.
    """
    log: logging.Logger = logging.getLogger(f"{__name__}.cli")
    handler: logging.StreamHandler[TextIO] = logging.StreamHandler()
    handler.setFormatter(_build_formatter())
    handler.addFilter(DebugWarningFilter())
    log.addHandler(handler)
    log.setLevel(logging.DEBUG)
    return log


logger_gui: logging.Logger = _make_gui_logger()
logger_cli: logging.Logger = _make_cli_logger()

# Ensure runtime file logs are always available.
setup_runtime_file_logging()
