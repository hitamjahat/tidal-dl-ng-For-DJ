"""Type stubs for the coloredlogs package.

Provides type information for coloredlogs so Pyright/Mypy can
type-check imports in tidal_dl_ng/logger.py.
"""

import logging
from collections.abc import Mapping

DEFAULT_LEVEL_STYLES: dict[str, dict[str, str | bool]]

class ColoredFormatter(logging.Formatter):
    def __init__(
        self,
        fmt: str,
        level_styles: Mapping[str, Mapping[str, str | bool]],
    ) -> None: ...
