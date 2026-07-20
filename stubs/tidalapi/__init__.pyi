"""Stub for tidalapi package initialization."""

from tidalapi.album import Album
from tidalapi.artist import Artist
from tidalapi.media import (
    AudioExtensions,
    Media,
    MediaMetadataTags,
    Quality,
    Stream,
    Track,
    Video,
)
from tidalapi.mix import Mix
from tidalapi.playlist import Playlist, UserPlaylist

__all__ = [
    "Album",
    "Artist",
    "AudioExtensions",
    "Media",
    "MediaMetadataTags",
    "Mix",
    "Playlist",
    "Quality",
    "Stream",
    "Track",
    "UserPlaylist",
    "Video",
]
