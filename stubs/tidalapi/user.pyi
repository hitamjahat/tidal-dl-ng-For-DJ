"""Stub for tidalapi.user to expose dynamically-set attributes."""

from typing import Any, List

from tidalapi.playlist import UserPlaylist

# Re-declare the classes to add dynamically-set attributes and the methods
# used by the project. These shadow the real implementations for type checking.
class Favorites:
    """Favorites container with paginated accessors."""

    def playlists_paginated(
        self, limit: int = ..., offset: int = ...
    ) -> list[Any]: ...
    def playlist_folders(
        self,
        limit: int = ...,
        offset: int = ...,
        parent_folder_id: str = ...,
    ) -> list[Any]: ...

class User:
    """Base user class."""

    favorites: Favorites

    def __init__(self, *args: object, **kwargs: object) -> None: ...

class FetchedUser(User):
    """User fetched from the API."""

    def playlists(self) -> List[UserPlaylist]: ...

class LoggedInUser(FetchedUser):
    """Currently authenticated user."""

    def playlists(self) -> List[UserPlaylist]: ...
    def playlist_folders(
        self,
        limit: int = ...,
        offset: int = ...,
        parent_folder_id: str = ...,
    ) -> list[Any]: ...
    @staticmethod
    def playlist_and_favorite_playlists(
        limit: int = ...,
        offset: int = ...,
    ) -> list[Any]: ...

class PlaylistCreator(User):
    """User that can create playlists."""

    def playlists(self) -> List[UserPlaylist]: ...

class Favorites:
    """Favorites container with paginated accessors."""

    def playlists_paginated(
        self, limit: int = ..., offset: int = ...
    ) -> list[Any]: ...
    def playlist_folders(
        self,
        limit: int = ...,
        offset: int = ...,
        parent_folder_id: str = ...,
    ) -> list[Any]: ...
