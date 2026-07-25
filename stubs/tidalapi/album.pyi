from datetime import datetime

from tidalapi.artist import Artist
from tidalapi.media import Track, Video
from tidalapi.page import Page

class Album:
    id: int | None
    name: str | None
    cover: str | None
    video_cover: str | None
    type: str | None
    duration: int | None
    available: bool | None
    ad_supported_ready: bool | None
    dj_ready: bool | None
    allow_streaming: bool | None
    premium_streaming_only: bool | None
    num_tracks: int | None
    num_videos: int | None
    num_volumes: int | None
    tidal_release_date: datetime | None
    release_date: datetime | None
    copyright: str | None
    upc: str | None
    version: str | None
    explicit: bool | None
    universal_product_number: int | None
    popularity: int | None
    user_date_added: datetime | None
    audio_quality: str | None
    audio_modes: list[str] | None
    media_metadata_tags: list[str] | None
    artist: Artist | None
    artists: list[Artist] | None
    listen_url: str
    share_url: str

    @property
    def year(self) -> int | None: ...
    @property
    def available_release_date(self) -> datetime | None: ...
    def image(
        self, dimensions: int | str = 320, default: str = ...
    ) -> str: ...
    def tracks(
        self,
        limit: int | None = None,
        offset: int = 0,
        sparse_album: bool = False,
    ) -> list[Track]: ...
    def items(
        self, limit: int = 100, offset: int = 0, sparse_album: bool = False
    ) -> list[Track | Video]: ...
    def video(self, dimensions: int | str = 320) -> str: ...
    def page(self) -> Page: ...
    def similar(self) -> list[Album]: ...
    def review(self) -> str: ...
    def get_audio_resolution(
        self, individual_tracks: bool = False
    ) -> list[list[int]]: ...
