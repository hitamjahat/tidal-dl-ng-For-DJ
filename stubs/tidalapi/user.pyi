# Stub for tidalapi.user with dynamically-set attributes.
# Re-declares classes to expose dynamically-set attributes and
# methods used by the project. These shadow the real
# implementations for type-checking purposes only.

from __future__ import annotations

from typing import Any

from tidalapi.playlist import UserPlaylist

class Favorites:
    # Favorites container with paginated accessors.

    def playlists_paginated(
        self,
        limit: int = ...,
        offset: int = ...,
    ) -> list[Any]: ...
    def playlist_folders(
        self,
        limit: int = ...,
        offset: int = ...,
        parent_folder_id: str = ...,
    ) -> list[Any]: ...

class User:
    # Base user class.

    favorites: Favorites

    def __init__(self, *args: object, **kwargs: object) -> None: ...

class FetchedUser(User):
    # User fetched from the TIDAL API.

    def playlists(self) -> list[UserPlaylist]: ...

class LoggedInUser(FetchedUser):
    # Currently authenticated user.

    def playlists(self) -> list[UserPlaylist]: ...
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
    # User that can create playlists.

    def playlists(self) -> list[UserPlaylist]: ...
