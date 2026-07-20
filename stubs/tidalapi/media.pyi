"""Stub for tidalapi.media with resolved forward references."""

from enum import Enum
from typing import Dict, List, Optional

from tidalapi.album import Album
from tidalapi.artist import Artist

class Quality:
    """Audio quality enumeration."""

    low_320k: "Quality" = "low"
    high_lossless: "Quality" = "high"
    hi_res_lossless: "Quality" = "hi_res"

class MediaMetadataTags:
    """Media metadata tags enumeration."""

    lossless: str = "lossless"
    hi_res_lossless: str = "hi_res_lossless"

class AudioExtensions(str, Enum):
    """Audio file extensions enumeration."""

    FLAC: str = ".flac"
    M4A: str = ".m4a"
    MP4: str = ".mp4"
    MP3: str = ".mp3"
    WAV: str = ".wav"
    ALAC: str = ".alac"

class Media:
    """Base class for TIDAL media items."""

    id: object
    name: str
    full_name: str
    title: str
    artists: Optional[List[Artist]]
    duration: int
    available: bool

class Track(Media):
    """A TIDAL track."""

    album: Optional[Album]
    audio_quality: Optional[str]
    media_metadata_tags: object
    bpm: object
    isrc: Optional[str]
    track_num: int
    volume_num: int
    copyright: Optional[str]
    explicit: bool

class Video(Media):
    """A TIDAL video."""

    album: Optional[Album]
    duration: int
    volume_num: int
    track_num: int
    explicit: bool
    video_quality: Optional[str]
    explicit: bool
