"""Stub for tidalapi.playlist with resolved forward references."""

from typing import List

from tidalapi.media import Track, Video

class Playlist:
    """A TIDAL playlist."""

    id: object
    name: str
    title: str
    description: str
    duration: int
    num_tracks: int
    num_videos: int

    def items(self) -> List[Track | Video]: ...
    def tracks(self) -> List[Track]: ...

class UserPlaylist(Playlist):
    """A playlist owned by the current user."""

    def items(
        self,
        offset: int = ...,
        limit: int = ...,
    ) -> List[Track | Video]: ...
    def add(self, media_ids: List[object]) -> None: ...
    def remove_by_index(self, index: int) -> None: ...
    def remove_by_id(self, item_id: str) -> bool: ...
