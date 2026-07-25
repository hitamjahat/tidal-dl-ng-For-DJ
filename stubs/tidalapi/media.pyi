from datetime import datetime, timedelta
from enum import StrEnum

from tidalapi.album import Album
from tidalapi.artist import Artist
from tidalapi.mix import Mix
from tidalapi.session import Session
from tidalapi.types import JsonObj

class Quality(StrEnum):
    low_96k = "LOW"
    low_320k = "HIGH"
    high_lossless = "LOSSLESS"
    hi_res_lossless = "HI_RES_LOSSLESS"
    default = ...

class VideoQuality(StrEnum):
    high = "HIGH"
    medium = "MEDIUM"
    low = "LOW"
    audio_only = "AUDIO_ONLY"
    default = ...

class AudioMode(StrEnum):
    stereo = "STEREO"
    dolby_atmos = "DOLBY_ATMOS"

class MediaMetadataTags(StrEnum):
    hi_res_lossless = "HIRES_LOSSLESS"
    lossless = "LOSSLESS"
    dolby_atmos = "DOLBY_ATMOS"

class AudioExtensions(StrEnum):
    FLAC = ".flac"
    M4A = ".m4a"
    MP4 = ".mp4"

class VideoExtensions(StrEnum):
    TS = ".ts"

class ManifestMimeType(StrEnum):
    MPD = "application/dash+xml"
    BTS = "application/vnd.tidal.bts"
    VIDEO = "video/mp2t"

class Codec(StrEnum):
    MP3 = "MP3"
    AAC = "AAC"
    MP4A = "MP4A"
    FLAC = "FLAC"
    Atmos = "EAC3"
    AC4 = "AC4"
    LowResCodecs = ...
    PremiumCodecs = ...
    HQCodecs = ...

class MimeType(StrEnum):
    audio_mpeg = "audio/mpeg"
    audio_mp3 = "audio/mp3"
    audio_mp4 = "audio/mp4"
    audio_m4a = "audio/m4a"
    audio_flac = "audio/flac"
    audio_xflac = "audio/x-flac"
    audio_eac3 = "audio/eac3"
    audio_ac4 = "audio/mp4"
    audio_m3u8 = "audio/mpegurl"
    video_mp4 = "video/mp4"
    video_m3u8 = "video/mpegurl"
    audio_map = ...

    @staticmethod
    def from_audio_codec(codec: Codec) -> MimeType: ...
    @staticmethod
    def is_flac(mime_type: MimeType) -> bool: ...

class Media:
    id: int
    title: str
    name: str
    duration: int
    explicit: bool
    popularity: int
    allow_streaming: bool
    available: bool
    stream_ready: bool
    stem_ready: bool
    dj_ready: bool
    ad_supported_stream_ready: bool
    stream_start_date: datetime | None
    tidal_release_date: datetime | None
    date_added: datetime | None
    user_date_added: datetime | None
    track_num: int
    volume_num: int
    artist: Artist | None
    artist_roles: object | None
    artists: list[Artist] | None
    album: Album | None
    type: str | None
    listen_url: str
    share_url: str
    session: Session
    requests: object

    def __init__(
        self, session: Session, media_id: str | None = None
    ) -> None: ...
    def _get(self, media_id: str) -> Media: ...
    def parse(self, json_obj: JsonObj, album: Album | None = None) -> None: ...
    def parse_media(
        self, json_obj: JsonObj, album: Album | None = None
    ) -> Track | Video: ...

class Track(Media):
    access_type: str
    spotlighted: bool
    pay_to_stream: bool
    premium_streaming_only: bool
    editable: bool
    upload: bool
    audio_quality: str | None
    audio_modes: list[str] | None
    media_metadata_tags: object | None
    index: int | None
    item_uuid: str | None
    isrc: str | None
    description: str | None
    version: str | None
    copyright: str
    url: str
    bpm: int
    key: str | None
    key_scale: str | None
    peak: float
    replay_gain: float
    mixes: dict[str, object] | None
    full_name: str

    def parse_track(
        self, json_obj: JsonObj, album: Album | None = None
    ) -> Track: ...
    def _get(self, media_id: str) -> Track: ...
    def get_url(self) -> str: ...
    def lyrics(self) -> Lyrics: ...
    def get_track_radio(self, limit: int = 100) -> list[Track]: ...
    def get_radio_mix(self) -> Mix: ...
    def get_stream(self) -> Stream: ...
    @property
    def is_hi_res_lossless(self) -> bool: ...
    @property
    def is_lossless(self) -> bool: ...
    @property
    def is_dolby_atmos(self) -> bool: ...

class Video(Media):
    album: Album | None
    artist: Artist | None
    duration: int
    volume_num: int
    track_num: int
    explicit: bool
    video_quality: str | None
    share_url: str

    def parse_video(
        self, json_obj: JsonObj, album: Album | None = None
    ) -> Video: ...
    def _get(self, media_id: str) -> Video: ...
    def get_url(self) -> str: ...
    def get_stream(self) -> Stream: ...

class Stream:
    track_id: int
    audio_mode: str
    audio_quality: str
    manifest_mime_type: str
    manifest_hash: str
    manifest: str
    asset_presentation: str
    album_replay_gain: float
    album_peak_amplitude: float
    track_replay_gain: float
    track_peak_amplitude: float
    bit_depth: int
    sample_rate: int

    def parse(self, json_obj: JsonObj) -> Stream: ...
    def get_audio_resolution(self) -> tuple[int, int]: ...
    def get_stream_manifest(self) -> StreamManifest: ...
    def get_manifest_data(self) -> str: ...
    @property
    def is_mpd(self) -> bool: ...
    @property
    def is_bts(self) -> bool: ...

class StreamManifest:
    manifest: str | None
    manifest_mime_type: str | None
    manifest_parsed: str | None
    codecs: str
    encryption_key: object | None
    encryption_type: str | None
    sample_rate: int
    urls: list[str]
    mime_type: MimeType
    file_extension: str | None
    dash_info: DashInfo | None

    def __init__(self, stream: Stream) -> None: ...
    def get_urls(self) -> list[str]: ...
    def get_hls(self) -> str: ...
    def get_codecs(self) -> str: ...
    def get_sampling_rate(self) -> int: ...
    @staticmethod
    def get_mimetype(
        stream_codec: Codec | None, stream_url: str | None = None
    ) -> MimeType: ...
    @staticmethod
    def get_file_extension(
        stream_url: str, stream_codec: str | None = None
    ) -> str: ...
    @property
    def is_encrypted(self) -> bool: ...
    @property
    def is_mpd(self) -> bool: ...
    @property
    def is_bts(self) -> bool: ...

class DashInfo:
    duration: timedelta
    content_type: str
    mime_type: MimeType
    codecs: str
    first_url: str
    media_url: str
    timescale: int
    audio_sampling_rate: int
    chunk_size: int
    last_chunk_size: int
    urls: list[str]

    @staticmethod
    def from_stream(stream: Stream) -> DashInfo: ...
    @staticmethod
    def from_mpd(mpd_manifest: str) -> DashInfo: ...
    def __init__(self, mpd_xml: str) -> None: ...
    @staticmethod
    def get_urls(mpd: object) -> list[str]: ...
    def get_hls(self) -> str: ...

class Lyrics:
    track_id: int
    provider: str
    provider_track_id: int
    provider_lyrics_id: int
    text: str
    subtitles: str
    right_to_left: bool

    def parse(self, json_obj: JsonObj) -> Lyrics: ...
