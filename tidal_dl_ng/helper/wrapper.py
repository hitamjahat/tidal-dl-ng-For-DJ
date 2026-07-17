from collections.abc import Callable
import logging

from tidal_dl_ng.runtime_trace import setup_runtime_file_logging


class LoggerWrapped:
    fn_print: Callable = None
    logger: logging.Logger

    def __init__(self, fn_print: Callable):
        setup_runtime_file_logging()
        self.fn_print = fn_print
        self.logger = logging.getLogger("tidal_dl_ng.cli")

    def _emit(self, level: int, value: object) -> None:
        text = str(value)
        self.fn_print(text)
        self.logger.log(level, text)

    def debug(self, value: object) -> None:
        self._emit(logging.DEBUG, value)

    def warning(self, value: object) -> None:
        self._emit(logging.WARNING, value)

    def info(self, value: object) -> None:
        self._emit(logging.INFO, value)

    def error(self, value: object) -> None:
        self._emit(logging.ERROR, value)

    def critical(self, value: object) -> None:
        self._emit(logging.CRITICAL, value)

    def exception(self, value: object) -> None:
        self._emit(logging.ERROR, value)
