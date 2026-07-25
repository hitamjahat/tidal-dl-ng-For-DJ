from typing import NoReturn

from datetime import datetime
from enum import Enum

from tidalapi.album import Album
from tidalapi.media import Track, Video
from tidalapi.mix import Mix
from tidalapi.page import Page
from tidalapi.session import Session

class Artist:
    id: int | None
    name: str | None
    roles: list[Role] | None
    role: Role | None
    picture: str | None
    user_date_added: datetime | None
    bio: str | None
    listen_url: str
    share_url: str

    def __init__(self, session: Session, artist_id: str | None) -> None: ...
    def get_albums(
        self, limit: int | None = None, offset: int = 0
    ) -> list[Album]: ...
    def get_albums_ep_singles(
        self, limit: int | None = None, offset: int = 0
    ) -> list[Album]: ...
    def get_ep_singles(
        self, limit: int | None = None, offset: int = 0
    ) -> list[Album]: ...
    def get_albums_other(
        self, limit: int | None = None, offset: int = 0
    ) -> list[Album]: ...
    def get_other(
        self, limit: int | None = None, offset: int = 0
    ) -> list[Album]: ...
    def get_top_tracks(
        self, limit: int | None = None, offset: int = 0
    ) -> list[Track]: ...
    def get_videos(
        self, limit: int | None = None, offset: int = 0
    ) -> list[Video]: ...
    def get_bio(self) -> str: ...
    def get_similar(self) -> list[Artist]: ...
    def get_radio(self, limit: int = 100) -> list[Track]: ...
    def get_radio_mix(self) -> Mix: ...
    def items(self) -> list[NoReturn]: ...
    def image(self, dimensions: int = 320) -> str: ...
    def page(self) -> Page: ...

class Role(Enum):
    main = "MAIN"
    featured = "FEATURED"
    contributor = "CONTRIBUTOR"
    artist = "ARTIST"
