from concurrent.futures import Future

from tidalapi.album import Album
from tidalapi.artist import Artist
from tidalapi.media import Track, Video
from tidalapi.mix import Mix
from tidalapi.page import Page
from tidalapi.playlist import Playlist
from tidalapi.request import Requests
from tidalapi.user import FetchedUser, LoggedInUser, PlaylistCreator

type SearchTypes = Artist | Album | Track | Video | Playlist | None

class LinkLogin:
    expires_in: float
    user_code: str
    verification_uri: str
    verification_uri_complete: str
    interval: float
    device_code: str

class Session:
    user: LoggedInUser | FetchedUser | PlaylistCreator | None
    request: Requests | None

    def __init__(self, *args: object, **kwargs: object) -> None: ...
    def search(
        self,
        query: str,
        limit: int = 50,
        offset: int = 0,
        models: object = None,
    ) -> dict[str, list[object]]: ...
    def track(self, track_id: str, with_album: bool = True) -> Track: ...
    def video(self, video_id: str) -> Video: ...
    def album(self, album_id: str) -> Album: ...
    def playlist(self, playlist_id: str) -> Playlist: ...
    def mix(self, mix_id: str) -> Mix: ...
    def artist(self, artist_id: str) -> Artist: ...
    def mixes(self) -> Page: ...
    def check_login(self) -> bool: ...
    def login_oauth(
        self,
    ) -> tuple[LinkLogin, Future[object]]: ...
