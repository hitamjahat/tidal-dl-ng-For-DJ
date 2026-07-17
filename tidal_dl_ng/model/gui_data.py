from dataclasses import dataclass
from typing import TYPE_CHECKING

from tidalapi.media import Quality

from tidal_dl_ng.constants import QualityVideo

if TYPE_CHECKING:
    from PySide6 import QtCore

    @dataclass
    class ProgressBars:
        """Signal instances used to report progress to the GUI."""

        item: QtCore.SignalInstance
        item_name: QtCore.SignalInstance
        list_item: QtCore.SignalInstance
        list_name: QtCore.SignalInstance

else:
    try:
        from PySide6 import QtCore

        @dataclass
        class ProgressBars:
            """Signal instances used to report progress to the GUI."""

            item: QtCore.SignalInstance
            item_name: QtCore.SignalInstance
            list_item: QtCore.SignalInstance
            list_name: QtCore.SignalInstance

    except ModuleNotFoundError:

        class ProgressBars:
            """Fallback placeholder when PySide6 is unavailable."""

            pass


@dataclass
class ResultItem:
    position: int
    artist: str
    title: str
    album: str
    duration_sec: int
    obj: object
    quality: str
    explicit: bool
    date_user_added: str
    date_release: str


@dataclass
class StatusbarMessage:
    message: str
    timeout: int = 0


@dataclass
class QueueDownloadItem:
    status: str
    name: str
    type_media: str
    quality_audio: Quality
    quality_video: QualityVideo
    obj: object
