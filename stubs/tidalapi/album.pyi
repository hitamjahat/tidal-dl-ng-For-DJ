"""Stub for tidalapi.album with resolved forward references."""

from typing import List, Optional

from tidalapi.artist import Artist
from tidalapi.media import Track, Video

class Album:
    """A TIDAL album."""

    id: object
    name: str
    title: str
    artists: Optional[List[Artist]]
    media_metadata_tags: object
    duration: int
    available: bool
    num_tracks: int
    num_videos: int
    copyright: Optional[str]
    explicit: bool
    year: int
    release_date: Optional[object]
    artist: Optional[Artist]
    type: str
    num_volumes: int

    def items(self) -> List[Track | Video]: ...
    def tracks(self) -> List[Track]: ...
