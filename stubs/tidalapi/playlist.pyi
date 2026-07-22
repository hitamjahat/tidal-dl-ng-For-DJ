from collections.abc import Sequence
from datetime import datetime

from tidalapi.artist import Artist
from tidalapi.media import Track, Video
from tidalapi.request import Requests
from tidalapi.session import Session
from tidalapi.types import JsonObj
from tidalapi.user import User

def list_validate(items: str | Sequence[str]) -> list[str]: ...

class Playlist:
    id: str | None
    trn: str | None
    name: str | None
    num_tracks: int
    num_videos: int
    creator: Artist | User | None
    description: str | None
    duration: int
    last_updated: datetime | None
    created: datetime | None
    type: str | None
    public: bool | None
    popularity: int | None
    promoted_artists: list[Artist] | None
    last_item_added_at: datetime | None
    picture: str | None
    square_picture: str | None
    user_date_added: datetime | None
    session: Session
    request: Requests
    listen_url: str
    share_url: str
    _etag: str | None
    _base_url: str

    def __init__(
        self,
        session: Session,
        playlist_id: str | None,
    ) -> None: ...
    def parse(self, obj: JsonObj) -> Playlist: ...
    def factory(self) -> Playlist | UserPlaylist: ...
    def parse_factory(self, json_obj: JsonObj) -> Playlist: ...
    def get_tracks_count(self) -> int: ...
    def get_items_count(self) -> int: ...
    def tracks(
        self,
        limit: int | None = None,
        offset: int = 0,
        order: str | None = None,
        order_direction: str | None = None,
    ) -> list[Track]: ...
    def tracks_paginated(
        self,
        order: str | None = None,
        order_direction: str | None = None,
    ) -> list[Playlist]: ...
    def items(
        self,
        limit: int = 100,
        offset: int = 0,
        order: str | None = None,
        order_direction: str | None = None,
    ) -> list[Track | Video]: ...
    def image(
        self,
        dimensions: int = 480,
        wide_fallback: bool = True,
    ) -> str: ...
    def wide_image(
        self,
        width: int = 1080,
        height: int = 720,
    ) -> str: ...

class Folder:
    trn: str | None
    id: str | None
    parent_folder_id: str | None
    name: str | None
    parent: str | None
    added: datetime | None
    created: datetime | None
    last_modified: datetime | None
    total_number_of_items: int
    session: Session
    request: Requests
    playlist: Playlist
    listen_url: str
    _endpoint: str

    def __init__(
        self,
        session: Session,
        folder_id: str | None,
        parent_folder_id: str = "root",
    ) -> None: ...
    def _reparse(self) -> None: ...
    def parse(self, json_obj: JsonObj) -> Folder: ...
    def rename(self, name: str) -> bool: ...
    def remove(self) -> bool: ...
    def items(
        self,
        offset: int = 0,
        limit: int = 50,
    ) -> list[Playlist | UserPlaylist]: ...
    def add_items(self, trns: Sequence[str]) -> None: ...
    def move_items_to_root(self, trns: Sequence[str]) -> None: ...
    def move_items_to_folder(
        self,
        trns: Sequence[str],
        folder: str | None = None,
    ) -> bool: ...

class UserPlaylist(Playlist):
    def _reparse(self) -> None: ...
    def edit(
        self,
        title: str | None = None,
        description: str | None = None,
    ) -> bool: ...
    def delete_by_id(self, media_ids: list[str]) -> bool: ...
    def add(
        self,
        media_ids: list[str],
        allow_duplicates: bool = False,
        position: int = -1,
        limit: int = 100,
    ) -> list[int]: ...
    def merge(
        self,
        playlist: str,
        allow_duplicates: bool = False,
        allow_missing: bool = True,
    ) -> list[int]: ...
    def add_by_isrc(
        self,
        isrc: str,
        allow_duplicates: bool = False,
        position: int = -1,
    ) -> bool: ...
    def move_by_id(self, media_id: str, position: int) -> bool: ...
    def move_by_index(self, index: int, position: int) -> bool: ...
    def move_by_indices(
        self,
        indices: Sequence[int],
        position: int,
    ) -> bool: ...
    def remove_by_id(self, media_id: str) -> bool: ...
    def remove_by_index(self, index: int) -> bool: ...
    def remove_by_indices(self, indices: Sequence[int]) -> bool: ...
    def clear(self, chunk_size: int = 50) -> bool: ...
    def set_playlist_public(self) -> bool: ...
    def set_playlist_private(self) -> bool: ...
    def delete(self) -> bool: ...
