import logging
from collections.abc import Mapping

DEFAULT_LEVEL_STYLES: dict[str, dict[str, str | bool]]

class ColoredFormatter(logging.Formatter):
    def __init__(
        self,
        fmt: str,
        level_styles: Mapping[str, Mapping[str, str | bool]],
    ) -> None: ...
