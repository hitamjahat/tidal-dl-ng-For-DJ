"""Global constants and configuration settings for the application."""

# pylint: disable=invalid-name,consider-using-namedtuple-or-dataclass

import base64
from enum import StrEnum

from tidalapi.media import Quality

CTX_TIDAL: str = "tidal"
REQUESTS_TIMEOUT_SEC: int = 45
EXTENSION_LYRICS: str = ".lrc"
UNIQUIFY_THRESHOLD: int = 99
FILENAME_SANITIZE_PLACEHOLDER: str = "_"
COVER_NAME: str = "cover.jpg"
BLOCK_SIZE: int = 4096
BLOCKS: int = 1024
CHUNK_SIZE: int = BLOCK_SIZE * BLOCKS
PLAYLIST_EXTENSION: str = ".m3u"
PLAYLIST_PREFIX: str = "_"
FILENAME_LENGTH_MAX: int = 255
FORMAT_TEMPLATE_EXPLICIT: str = " (Explicit)"
METADATA_EXPLICIT: str = " 🅴"

# Dolby Atmos API credentials (obfuscated)
ATMOS_ID_B64 = "N203QX" + "AwSkM5aj" + "FjT00zbg=="
ATMOS_SECRET_B64 = (
    "dlJBZEExMDh0bHZrSnBUc0daUzhyR1o3eFRsYkowcWFaMks5c2FFenNnWT0="  # noqa: S105
)

ATMOS_CLIENT_ID = base64.b64decode(ATMOS_ID_B64).decode("utf-8")
ATMOS_CLIENT_SECRET = base64.b64decode(ATMOS_SECRET_B64).decode("utf-8")
ATMOS_REQUEST_QUALITY = Quality.low_320k


class QualityVideo(StrEnum):
    """Available video quality options."""

    P360 = "360"
    P480 = "480"
    P720 = "720"
    P1080 = "1080"


class MediaType(StrEnum):
    """Available media types for processing."""

    TRACK = "track"
    VIDEO = "video"
    PLAYLIST = "playlist"
    ALBUM = "album"
    MIX = "mix"
    ARTIST = "artist"


class CoverDimensions(StrEnum):
    """Available cover art dimensions."""

    Px80 = "80"
    Px160 = "160"
    Px320 = "320"
    Px640 = "640"
    Px1280 = "1280"
    PxORIGIN = "origin"


class TidalLists(StrEnum):
    """Types of lists available in Tidal."""

    Playlists = "Playlists"
    Favorites = "Favorites"
    Mixes = "Mixes"


class QueueDownloadStatus(StrEnum):
    """Status icons for the download queue."""

    Waiting = "⏳️"
    Downloading = "▶️"
    Finished = "✅"
    Failed = "❌"
    Skipped = "↪️"


FAVORITES: dict[str, dict[str, str]] = {
    "fav_videos": {"name": "Videos", "function_name": "videos"},
    "fav_tracks": {"name": "Tracks", "function_name": "tracks_paginated"},
    "fav_mixes": {"name": "Mixes & Radio", "function_name": "mixes"},
    "fav_artists": {"name": "Artists", "function_name": "artists_paginated"},
    "fav_albums": {"name": "Albums", "function_name": "albums_paginated"},
}


class AudioExtensionsValid(StrEnum):
    """Valid audio file extensions."""

    FLAC = ".flac"
    M4A = ".m4a"
    MP4 = ".mp4"
    MP3 = ".mp3"
    OGG = ".ogg"
    ALAC = ".alac"


class MetadataTargetUPC(StrEnum):
    """Target tags for UPC/Barcode metadata."""

    UPC = "UPC"
    BARCODE = "BARCODE"
    EAN = "EAN"


METADATA_LOOKUP_UPC: dict[str, dict[str, str]] = {
    "UPC": {"MP3": "UPC", "MP4": "UPC", "FLAC": "UPC"},
    "BARCODE": {"MP3": "BARCODE", "MP4": "BARCODE", "FLAC": "BARCODE"},
    "EAN": {"MP3": "EAN", "MP4": "EAN", "FLAC": "EAN"},
}
