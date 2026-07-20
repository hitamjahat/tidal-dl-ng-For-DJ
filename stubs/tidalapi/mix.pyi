"""Stub for tidalapi.mix with resolved forward references."""

from typing import List

from tidalapi.media import Track, Video

class Mix:
    """A TIDAL mix."""

    id: object
    name: str
    title: str
    sub_title: str
    description: str
    duration: int
    num_tracks: int

    def items(self) -> List[Track | Video]: ...
