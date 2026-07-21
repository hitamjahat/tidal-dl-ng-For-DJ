from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Self

from tidalapi.media import Track, Video
from tidalapi.request import Requests
from tidalapi.session import Session

class MixType(Enum):
    welcome_mix = "WELCOME_MIX"
    video_daily = "VIDEO_DAILY_MIX"
    daily = "DAILY_MIX"
    discovery = "DISCOVERY_MIX"
    new_release = "NEW_RELEASE_MIX"
    track = "TRACK_MIX"
    artist = "ARTIST_MIX"
    songwriter = "SONGWRITER_MIX"
    producter = "PRODUCER_MIX"
    history_alltime = "HISTORY_ALLTIME_MIX"
    history_monthly = "HISTORY_MONTHLY_MIX"
    history_yearly = "HISTORY_YEARLY_MIX"

@dataclass
class ImageResponse:
    small: str
    medium: str
    large: str

class Mix:
    id: str
    title: str
    sub_title: str
    sharing_images: Mapping[str, object] | None
    mix_type: MixType | None
    content_behaviour: str
    short_subtitle: str
    images: ImageResponse | None
    session: Session
    request: Requests
    _retrieved: bool
    _items: list[Video | Track] | None

    def __init__(
        self,
        session: Session,
        mix_id: str | None,
    ) -> None: ...
    def get(self, mix_id: str | None = None) -> Self: ...
    def parse(self, json_obj: Mapping[str, object]) -> Self: ...
    def items(self) -> list[Video | Track]: ...
    def image(self, dimensions: int = 320) -> str: ...

@dataclass
class TextInfo:
    text: str
    color: str

class MixV2:
    mix_type: MixType | None
    country_code: str | None
    date_added: datetime | None
    id: str | None
    artifact_id_type: str | None
    content_behavior: str | None
    images: ImageResponse | None
    detail_images: ImageResponse | None
    master: bool
    is_stable_id: bool
    title: str | None
    sub_title: str | None
    short_subtitle: str | None
    title_text_info: TextInfo | None
    sub_title_text_info: TextInfo | None
    short_subtitle_text_info: TextInfo | None
    updated: datetime | None
    session: Session
    request: Requests
    _retrieved: bool
    _items: list[Video | Track] | None

    def __init__(self, session: Session, mix_id: str) -> None: ...
    def get(self, mix_id: str | None = None) -> Self: ...
    def parse(self, json_obj: Mapping[str, object]) -> Self: ...
    def image(self, dimensions: int = 320) -> str: ...
