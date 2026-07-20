"""Logger wrapper that emits to both a print function and a file logger."""

import logging
from collections.abc import Callable

from tidal_dl_ng.runtime_trace import setup_runtime_file_logging


class LoggerWrapped(logging.Logger):
    """Logger wrapper that emits to both a print function and a file logger.

    Inherits from logging.Logger to satisfy type checkers expecting a
    standard logger interface while adding console output via fn_print.
    """

    fn_print: Callable[[str], None]

    def __init__(self, fn_print: Callable[[str], None]) -> None:
        """Initialize the wrapped logger with a print sink.

        Args:
            fn_print: Callable used for console output of log messages.
        """
        super().__init__("tidal_dl_ng.cli")
        setup_runtime_file_logging()
        self.fn_print = fn_print

    def _emit(self, level: int, msg: object, *args: object) -> None:
        """Emit a log record to both the print sink and the file logger.

        Args:
            level: Logging level (e.g., logging.INFO).
            msg: The message or format string to log.
            *args: Format arguments applied to the message string.
        """
        text = str(msg)
        if args:
            text = text % args
        self.fn_print(text)
        self.log(level, text)

    def debug(self, msg: object, *args: object, **_kwargs: object) -> None:
        """Log a debug message to both sinks.

        Args:
            msg: The message or format string to log.
            *args: Format arguments applied to the message string.
            **kwargs: Additional keyword arguments (unused, for
                compatibility with logging.Logger signature).
        """
        self._emit(logging.DEBUG, msg, *args)

    def warning(self, msg: object, *args: object, **_kwargs: object) -> None:
        """Log a warning message to both sinks.

        Args:
            msg: The message or format string to log.
            *args: Format arguments applied to the message string.
            **kwargs: Additional keyword arguments (unused, for
                compatibility with logging.Logger signature).
        """
        self._emit(logging.WARNING, msg, *args)

    def info(self, msg: object, *args: object, **_kwargs: object) -> None:
        """Log an info message to both sinks.

        Args:
            msg: The message or format string to log.
            *args: Format arguments applied to the message string.
            **kwargs: Additional keyword arguments (unused, for
                compatibility with logging.Logger signature).
        """
        self._emit(logging.INFO, msg, *args)

    def error(self, msg: object, *args: object, **_kwargs: object) -> None:
        """Log an error message to both sinks.

        Args:
            msg: The message or format string to log.
            *args: Format arguments applied to the message string.
            **kwargs: Additional keyword arguments (unused, for
                compatibility with logging.Logger signature).
        """
        self._emit(logging.ERROR, msg, *args)

    def critical(self, msg: object, *args: object, **_kwargs: object) -> None:
        """Log a critical message to both sinks.

        Args:
            msg: The message or format string to log.
            *args: Format arguments applied to the message string.
            **kwargs: Additional keyword arguments (unused, for
                compatibility with logging.Logger signature).
        """
        self._emit(logging.CRITICAL, msg, *args)

    def exception(self, msg: object, *args: object, **_kwargs: object) -> None:
        """Log an exception message to both sinks.

        Args:
            msg: The message or format string to log.
            *args: Format arguments applied to the message string.
            **kwargs: Additional keyword arguments (unused, for
                compatibility with logging.Logger signature).
        """
        self._emit(logging.ERROR, msg, *args)
