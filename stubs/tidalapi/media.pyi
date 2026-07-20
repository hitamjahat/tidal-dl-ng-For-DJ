"""Stub for tidalapi.media with resolved forward references."""

from enum import Enum
from typing import Dict, List, Optional

from tidalapi.album import Album
from tidalapi.artist import Artist

class Stream:
    """A TIDAL audio/video stream."""

    album_peak_amplitude: Optional[float]
    album_replay_gain: Optional[float]
    asset_presentation: Optional[str]
    audio_mode: Optional[str]
    audio_quality: Optional[str]
    bit_depth: Optional[int]
    is_bts: bool
    is_mpd: bool
    manifest: Optional[str]
    manifest_hash: Optional[str]
    manifest_mime_type: Optional[str]
    sample_rate: Optional[int]
    track_id: Optional[str]
    track_peak_amplitude: Optional[float]
    track_replay_gain: Optional[float]

class Quality:
    """Audio quality enumeration."""

    low_320k: "Quality" = "low"
    high_lossless: "Quality" = "high"
    hi_res_lossless: "Quality" = "hi_res"

    def __init__(self, value: int | str) -> None: ...

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

class AudioMode(str, Enum):
    """Audio playback mode enumeration."""

    stereo = "STEREO"
    sony_360 = "SONY_360RA"
    dolby_atmos = "DOLBY_ATMOS"
    dolby_atmos_360 = "DOLBY_ATMOS_360RA"

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
    artist: Optional[Artist]
    audio_quality: Optional[str]
    media_metadata_tags: object
    bpm: object
    isrc: Optional[str]
    track_num: int
    volume_num: int
    copyright: Optional[str]
    explicit: bool
    lyrics: object
    share_url: Optional[str]
    version: Optional[str]

class Video(Media):
    """A TIDAL video."""

    album: Optional[Album]
    artist: Optional[Artist]
    duration: int
    volume_num: int
    track_num: int
    explicit: bool
    video_quality: Optional[str]
    share_url: Optional[str]
