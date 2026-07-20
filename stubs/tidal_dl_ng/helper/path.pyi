"""Stub for tidal_dl_ng.helper.path."""

from tidal_dl_ng.config import Settings
from tidal_dl_ng.constants import MediaType
from tidalapi.album import Album
from tidalapi.media import Track, Video
from tidalapi.mix import Mix
from tidalapi.playlist import Playlist, UserPlaylist

def get_format_template(
    media: Track | Album | Playlist | UserPlaylist | Video | Mix | MediaType,
    settings: Settings,
) -> str | bool: ...
def path_file_settings() -> str: ...
