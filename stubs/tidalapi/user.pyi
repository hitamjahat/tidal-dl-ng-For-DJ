# Type stubs for tidalapi.user module with dynamically-set attributes.
# Shadow the real implementations for type-checking purposes.

from tidalapi.playlist import UserPlaylist

class Favorites:
    def playlists_paginated(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> list[object]: ...
    def playlist_folders(
        self,
        limit: int = 50,
        offset: int = 0,
        parent_folder_id: str | None = None,
    ) -> list[object]: ...

class User:
    favorites: Favorites

    def __init__(self, *args: object, **kwargs: object) -> None: ...

class FetchedUser(User):
    def playlists(self) -> list[UserPlaylist]: ...

class LoggedInUser(FetchedUser):
    def playlists(self) -> list[UserPlaylist]: ...
    def playlist_folders(
        self,
        limit: int = 50,
        offset: int = 0,
        parent_folder_id: str | None = None,
    ) -> list[object]: ...
    @staticmethod
    def playlist_and_favorite_playlists(
        limit: int = 50,
        offset: int = 0,
    ) -> list[object]: ...

class PlaylistCreator(User):
    def playlists(self) -> list[UserPlaylist]: ...
