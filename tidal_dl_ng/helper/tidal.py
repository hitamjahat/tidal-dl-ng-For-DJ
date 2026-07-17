"""Tidal helper utilities.

Provides functions for building media names, searching, pagination,
session interaction, and raw JSON metadata extraction from the TIDAL API.
"""

import contextlib
import os
from collections.abc import Callable
from typing import Any, cast

import requests
from tidalapi.album import Album
from tidalapi.artist import Artist, Role
from tidalapi.media import MediaMetadataTags, Quality, Track, Video
from tidalapi.mix import Mix
from tidalapi.playlist import Playlist
from tidalapi.session import Session
from tidalapi.user import LoggedInUser

from tidal_dl_ng.constants import FAVORITES, MediaType
from tidal_dl_ng.helper.exceptions import MediaUnknown


def name_builder_artist(media: Track | Video | Album, delimiter: str = ", ") -> str:
    """Builds a string of artist names for a track, video, or album.

    Returns a delimited string of all artist names associated with the given media.

    Args:
        media (Track | Video | Album): The media object to extract artist names from.
        delimiter (str, optional): The delimiter to use between artist names. Defaults to ", ".

    Returns:
        str: A delimited string of artist names.
    """
    artists = getattr(media, "artists", None) or []
    return delimiter.join(str(artist.name) for artist in artists)


def name_builder_album_artist(media: Track | Album, first_only: bool = False, delimiter: str = ", ") -> str:
    """Builds a string of main album artist names for a track or album.

    Returns a delimited string of main artist names from the album, optionally including only the first main artist.

    Args:
        media (Track | Album): The media object to extract artist names from.
        first_only (bool, optional): If True, only the first main artist is included. Defaults to False.
        delimiter (str, optional): The delimiter to use between artist names. Defaults to ", ".

    Returns:
        str: A delimited string of main album artist names.
    """
    artists_tmp: list[str] = []

    if isinstance(media, Track) and media.album is not None:
        artists: list[Any] = getattr(media.album, "artists", None) or []
    else:
        artists = getattr(media, "artists", None) or []

    for artist in artists:
        roles = getattr(artist, "roles", None) or []
        if Role.main in roles:
            name = getattr(artist, "name", None)
            if name:
                artists_tmp.append(str(name))

            if first_only:
                break

    return delimiter.join(artists_tmp)


def name_builder_title(media: Track | Video | Mix | Playlist | Album) -> str:
    """Build a display title for any media type.

    Args:
        media (Track | Video | Mix | Playlist | Album): The media object.

    Returns:
        str: The display title string.
    """
    if isinstance(media, Mix):
        return str(media.title)
    if hasattr(media, "full_name"):
        return str(media.full_name)
    return str(getattr(media, "name", ""))


def name_builder_item(media: Track | Video) -> str:
    """Build a display string 'Artist - Title' for a track or video.

    Args:
        media (Track | Video): The media object.

    Returns:
        str: Formatted 'Artist - Title' string.
    """
    return f"{name_builder_artist(media)} - {name_builder_title(media)}"


def get_tidal_media_id(url_or_id_media: str) -> str:
    """Extract the media ID from a TIDAL URL or return the ID directly.

    Args:
        url_or_id_media (str): A TIDAL URL or raw media ID.

    Returns:
        str: The extracted media ID.
    """
    id_dirty = url_or_id_media.rsplit("/", 1)[-1]
    id_media = id_dirty.rsplit("?", 1)[0]

    return id_media


def get_tidal_media_type(url_media: str) -> MediaType | bool:
    """Determine the media type from a TIDAL URL.

    Args:
        url_media (str): The TIDAL URL to parse.

    Returns:
        MediaType | bool: The detected MediaType, or False if unrecognized.
    """
    result: MediaType | bool = False
    url_split = url_media.split("/")[-2]

    if len(url_split) > 1:
        media_name = url_media.split("/")[-2]

        match media_name:
            case "track":
                result = MediaType.TRACK
            case "video":
                result = MediaType.VIDEO
            case "album":
                result = MediaType.ALBUM
            case "playlist":
                result = MediaType.PLAYLIST
            case "mix":
                result = MediaType.MIX
            case "artist":
                result = MediaType.ARTIST

    return result


def url_ending_clean(url: str) -> str:
    """Checks if a link ends with "/u" or "?u" and removes that part.

    Args:
        url (str): The URL to clean.

    Returns:
        str: The cleaned URL.
    """
    return url[:-2] if url.endswith("/u") or url.endswith("?u") else url


def search_results_all(
    session: Session, needle: str, types_media: Any = None
) -> dict[str, list[Any]]:
    """Fetch all search results across all pages from TIDAL.

    Args:
        session (Session): The TIDAL session.
        needle (str): The search query string.
        types_media: Optional media types to filter (SearchTypes).

    Returns:
        dict[str, list[Any]]: Aggregated search results keyed by media type.
    """
    def _normalize_bucket(value: Any) -> list[Any]:
        """Normalize tidalapi search bucket values to a list of items."""
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, tuple | set):
            return list(value)

        # Some tidalapi versions return page-like wrappers.
        items_attr = getattr(value, "items", None)
        if isinstance(items_attr, list):
            return cast(list[Any], items_attr)

        if callable(items_attr):
            with contextlib.suppress(Exception):
                items_from_method = items_attr()
                if isinstance(items_from_method, list):
                    return cast(list[Any], items_from_method)

        # Fallback for singular results.
        return [value]

    def _item_identity(item: Any) -> str:
        """Build a stable identity key to deduplicate paginated results."""
        item_id = getattr(item, "id", None)
        if item_id is not None:
            return f"{type(item).__name__}:{item_id}"
        return f"{type(item).__name__}:{repr(item)}"

    limit: int = 300
    offset: int = 0
    done: bool = False
    result: dict[str, list[Any]] = {}
    seen: dict[str, set[str]] = {}

    while not done:
        raw_result = session.search(query=needle, models=types_media, limit=limit, offset=offset)
        tmp_result = cast(dict[Any, Any], raw_result)
        added_any: bool = False

        for key, value in tmp_result.items():
            key_name = str(key)
            values_list = _normalize_bucket(value)

            if key_name not in result:
                result[key_name] = []
                seen[key_name] = set()

            for item in values_list:
                identity = _item_identity(item)
                if identity not in seen[key_name]:
                    seen[key_name].add(identity)
                    result[key_name].append(item)
                    added_any = True

        # If no new result was added, assume we reached the end or API ignores offsets.
        done = not added_any
        offset += limit

    return result


def items_results_all(
    session: Session, media_list: Mix | Playlist | Album | Artist | Any, videos_include: bool = True
) -> list[Any]:
    """Fetch all items from a media list (album, playlist, mix, or artist).

    Args:
        session (Session): The TIDAL session.
        media_list (Mix | Playlist | Album | Artist | Any): The media container to fetch items from.
        videos_include (bool): Whether to include videos (for playlists/albums).

    Returns:
        list[Any]: All items from the media list.
    """
    result: list[Any] = []

    if isinstance(media_list, Mix):
        result = media_list.items()
    else:
        func_get_items_media: list[Callable[..., Any]] = []

        if isinstance(media_list, Playlist | Album):
            if videos_include:
                func_get_items_media.append(media_list.items)
            else:
                func_get_items_media.append(media_list.tracks)
        elif isinstance(media_list, Artist):
            func_get_items_media.append(media_list.get_albums)
            func_get_items_media.append(media_list.get_ep_singles)

        result = paginate_results(func_get_items_media)

    return result


def all_artist_album_ids(media_artist: Artist) -> list[int]:
    """Get all album IDs for an artist.

    Args:
        media_artist (Artist): The artist to query.

    Returns:
        list[int]: A list of album IDs.
    """
    result: list[int] = []
    func_get_items_media: list[Callable[..., Any]] = [media_artist.get_albums, media_artist.get_ep_singles]
    albums: list[Any] = paginate_results(func_get_items_media)

    for album in albums:
        album_id = getattr(album, "id", None)
        if album_id is not None:
            result.append(album_id)

    return result


def paginate_results(
    func_get_items_media: list[Callable[..., Any]],
) -> list[Any]:
    """Paginate through TIDAL API results for the given fetcher functions.

    Args:
        func_get_items_media (list[Callable[..., Any]]): List of bound methods that accept limit/offset.

    Returns:
        list[Any]: All collected results.
    """
    result: list[Any] = []

    for func_media in func_get_items_media:
        limit: int = 100
        offset: int = 0
        done: bool = False

        # Use a smaller page size for the user playlist endpoint
        func_ref = getattr(func_media, "__func__", None)
        if func_ref == LoggedInUser.playlist_and_favorite_playlists:
            limit = 50

        while not done:
            tmp_result: list[Any] = func_media(limit=limit, offset=offset)

            if bool(tmp_result):
                result += tmp_result
                # Get the next page in the next iteration.
                offset += limit
            else:
                done = True

    return result


def user_media_lists(session: Session) -> dict[str, list[Any]]:
    """Fetch user media lists using tidalapi's built-in pagination where available.

    Returns a dictionary with 'playlists' and 'mixes' keys containing lists of media items.
    For playlists, includes both Folder and Playlist objects at the root level.

    Args:
        session (Session): TIDAL session object.

    Returns:
        dict[str, list[Any]]: Dictionary with 'playlists' (includes Folder and Playlist) and 'mixes' lists.
    """
    # session.user is typed as FetchedUser | PlaylistCreator | None by tidalapi,
    # but when logged in it is always a LoggedInUser with .favorites
    user = cast(Any, session.user)

    # Use built-in pagination for playlists (root level only)
    playlists: list[Any] = user.favorites.playlists_paginated()

    # Fetch root-level folders manually (no paginated version available)
    folders: list[Any] = []
    offset = 0
    limit = 50

    while True:
        batch = user.favorites.playlist_folders(limit=limit, offset=offset, parent_folder_id="root")
        if not batch:
            break
        folders.extend(batch)
        if len(batch) < limit:
            break
        offset += limit

    # Combine folders and playlists
    all_playlists = folders + playlists

    # Get mixes
    mixes_page = session.mixes()
    categories = getattr(mixes_page, "categories", None) or []
    user_mixes: list[Any] = getattr(categories[0], "items", []) if categories else []

    return {"playlists": all_playlists, "mixes": user_mixes}


def instantiate_media(
    session: Session,
    media_type: MediaType,
    id_media: str,
) -> Track | Video | Album | Playlist | Mix | Artist:
    """Instantiate a TIDAL media object from its type and ID.

    Args:
        session (Session): The TIDAL session.
        media_type (MediaType): The type of media to instantiate.
        id_media (str): The media ID.

    Returns:
        Track | Video | Album | Playlist | Mix | Artist: The instantiated media object.

    Raises:
        MediaUnknown: If the media_type is not recognized.
    """
    match media_type:
        case MediaType.TRACK:
            return session.track(id_media, with_album=True)
        case MediaType.VIDEO:
            return session.video(id_media)
        case MediaType.ALBUM:
            return session.album(id_media)
        case MediaType.PLAYLIST:
            return session.playlist(id_media)
        case MediaType.MIX:
            return session.mix(id_media)
        case MediaType.ARTIST:
            return session.artist(id_media)
        case _:
            raise MediaUnknown


def quality_audio_highest(media: Track | Album) -> Quality:
    """Determine the highest available audio quality for a track or album.

    Args:
        media (Track | Album): The media object to check.

    Returns:
        Quality: The highest available quality tier.
    """
    # media_metadata_tags may be missing (Mock objects) or None; use safe getter
    tags = getattr(media, "media_metadata_tags", None)
    try:
        iterable_tags = set(tags) if tags is not None else set()
    except Exception:
        # If tags is a Mock or non-iterable, fall back to empty set
        iterable_tags = set()

    if MediaMetadataTags.hi_res_lossless in iterable_tags:
        quality = Quality.hi_res_lossless
    elif MediaMetadataTags.lossless in iterable_tags:
        quality = Quality.high_lossless
    else:
        quality = getattr(media, "audio_quality", Quality.low_320k)

    return quality


def favorite_function_factory(tidal: Any, favorite_item: str) -> Callable[..., Any]:
    """Create a callable that fetches items for a specific TIDAL favorite category.

    Args:
        tidal: The Tidal configuration/session wrapper.
        favorite_item (str): The key into the FAVORITES dictionary.

    Returns:
        Callable[..., Any]: A bound method from session.user.favorites.
    """
    function_name: str = FAVORITES[favorite_item]["function_name"]
    function_list: Callable[..., Any] = getattr(tidal.session.user.favorites, function_name)

    return function_list


def fetch_raw_media_json(
    session: Session,
    media_type: str,
    media_id: str,
    country_code: str | None = None,
    extra_params: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Fetch raw JSON for a media resource using tidalapi's session.request.

    Args:
        session (Session): the tidalapi Session
        media_type (str): 'tracks' or 'albums'
        media_id (str): id of media
        country_code (str | None): optional countryCode param
        extra_params (dict[str, Any] | None): additional query parameters

    Returns:
        dict[str, Any] | None: parsed JSON or None if fetch fails
    """
    try:
        params: dict[str, Any] = {}
        # If caller didn't provide a country code, check environment variable
        cc = country_code or os.environ.get("TIDAL_COUNTRY")
        if cc:
            params["countryCode"] = cc
        # merge extra params if provided (do not overwrite existing keys unless provided)
        if extra_params and isinstance(extra_params, dict):
            for k, v in extra_params.items():
                params[k] = v

        # Use session.request.request to call the internal API endpoint
        resp = session.request.request("GET", f"{media_type}/{media_id}", params=params)
        resp.raise_for_status()
        result: dict[str, Any] = resp.json()
    except requests.exceptions.HTTPError:
        return None  # Silently ignore HTTP errors
    except Exception:
        return None  # Silently ignore other errors
    else:
        return result


def fetch_raw_track_and_album(
    session: Session,
    track_id: str,
    country_code: str | None = None,
    extra_params: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Convenience to fetch raw track JSON and its album JSON (if available).

    Returns a tuple (track_json, album_json).

    Uses TIDAL API parameters to fetch extended metadata.
    Note: 'credits' and 'contributors' are NOT available in TIDAL API v2.
    Available include values: albums, artists, genres, lyrics, owners, providers,
    radio, shares, similarTracks, sourceFile, trackStatistics
    """
    # Use valid include parameters according to TIDAL API v2 spec
    # https://tidal-music.github.io/tidal-api-reference/
    default_track_params: dict[str, Any] = {
        "include": "albums,artists,genres",  # Valid parameters per API spec
    }
    merged_track_params = {**default_track_params, **(extra_params or {})}

    track_json = fetch_raw_media_json(
        session,
        "tracks",
        str(track_id),
        country_code=country_code,
        extra_params=merged_track_params,
    )

    album_json: dict[str, Any] | None = None
    try:
        if isinstance(track_json, dict):
            album = track_json.get("album")
            album_id = album.get("id") if isinstance(album, dict) else album
            if album_id:
                # Request extended album metadata
                default_album_params: dict[str, Any] = {
                    "include": "artists,genres",  # Valid parameters for albums
                }
                merged_album_params = {**default_album_params, **(extra_params or {})}

                album_json = fetch_raw_media_json(
                    session,
                    "albums",
                    str(album_id),
                    country_code=country_code,
                    extra_params=merged_album_params,
                )
    except Exception:
        album_json = None

    return track_json, album_json


def _normalize_dict_contributors(raw_contributors: dict[str, Any]) -> dict[str, list[str]]:
    """Process contributors in dict format: role -> list[{name, ...}]."""
    result: dict[str, list[str]] = {}
    for role, people in raw_contributors.items():
        if not isinstance(people, list):
            continue
        names: list[str] = []
        for person in people:
            if isinstance(person, dict):
                name = person.get("name")
                if isinstance(name, str) and name:
                    names.append(name)
        if names:
            result[role] = names
    return result


def _normalize_list_contributors(raw_contributors: list[Any]) -> dict[str, list[str]]:
    """Process contributors in list format: [{name, role, ...}, ...]."""
    result: dict[str, list[str]] = {}
    for person in raw_contributors:
        if not isinstance(person, dict):
            continue
        name = person.get("name")
        role = person.get("role")
        if isinstance(name, str) and name and isinstance(role, str) and role:
            result.setdefault(role, []).append(name)
    return result


def _normalize_contributors(raw_contributors: object) -> dict[str, list[str]]:
    """Normalize various possible contributor JSON shapes into role -> list[str] names.

    The TIDAL API has used at least two shapes historically:
    - dict role -> list[ {"name": str, ...} ]
    - list[ {"name": str, "role": str, ...} ]

    We accept both and ignore malformed entries.
    """
    if isinstance(raw_contributors, dict):
        return _normalize_dict_contributors(raw_contributors)
    if isinstance(raw_contributors, list):
        return _normalize_list_contributors(raw_contributors)
    return {}


def _extract_bpm_from_track(track_json: dict[str, Any]) -> int | None:
    """Extract BPM from track JSON."""
    bpm = track_json.get("bpm")
    if isinstance(bpm, int):
        return bpm
    if isinstance(bpm, float):
        return round(bpm)
    if isinstance(bpm, str):
        with contextlib.suppress(ValueError):
            return round(float(bpm))
    return None


def _process_credits_contributors(credits_list: list[Any]) -> dict[str, list[str]]:
    """Process credits API v2 format and return contributors by role."""
    role_mapping: dict[str, str] = {
        "producer": "producer",
        "producers": "producer",
        "composer": "composer",
        "composers": "composer",
        "lyricist": "lyricist",
        "lyricists": "lyricist",
        "writer": "composer",
        "writers": "composer",
    }
    result: dict[str, list[str]] = {}
    for credit in credits_list:
        if not isinstance(credit, dict):
            continue
        credit_type = credit.get("type", "").lower()
        contributors = credit.get("contributors", [])
        role = role_mapping.get(credit_type, credit_type)
        if isinstance(contributors, list):
            for contributor in contributors:
                if isinstance(contributor, dict):
                    name = contributor.get("name")
                    if name:
                        result.setdefault(role, []).append(name)
    return result


def _extract_track_contributors(track_json: dict[str, Any]) -> dict[str, list[str]]:
    """Extract contributors from track JSON."""
    # Try credits first (API v2)
    track_credits = track_json.get("credits")
    if track_credits and isinstance(track_credits, list):
        contributors = _process_credits_contributors(track_credits)
        if contributors:
            return contributors
    # Fallback to old format
    raw_contributors = track_json.get("contributors")
    if raw_contributors:
        return _normalize_contributors(raw_contributors)
    return {}


def _process_genre_item(g: object) -> str | None:
    """Extract genre name from various formats."""
    if isinstance(g, str) and g:
        return g
    if isinstance(g, dict):
        name = g.get("name")
        if isinstance(name, str) and name:
            return name
    return None


def _deduplicate_genres(genres: list[str]) -> list[str]:
    """Deduplicate genres while preserving order."""
    seen: set[str] = set()
    unique: list[str] = []
    for g in genres:
        if g not in seen:
            seen.add(g)
            unique.append(g)
    return unique


def _extract_album_label_genres(album_json: dict[str, Any]) -> tuple[str, list[str]]:
    """Extract label and genres from album JSON."""
    # Label
    label = album_json.get("label") or album_json.get("recordLabel")
    label_str = label if isinstance(label, str) else ""

    # Genres
    raw_genres = album_json.get("genres") or album_json.get("genre")
    genres: list[str] = []

    if isinstance(raw_genres, list):
        for g in raw_genres:
            genre = _process_genre_item(g)
            if genre:
                genres.append(genre)
    elif isinstance(raw_genres, str) and raw_genres:
        genres.append(raw_genres)
    else:
        genre = _process_genre_item(raw_genres)
        if genre:
            genres.append(genre)

    # Deduplicate while preserving order
    if genres:
        return label_str, _deduplicate_genres(genres)
    return label_str, []


def _extract_album_contributors(album_json: dict[str, Any]) -> dict[str, list[str]]:
    """Extract contributors from album JSON."""
    # Try credits first (API v2)
    album_credits = album_json.get("credits")
    if album_credits and isinstance(album_credits, list):
        contributors = _process_credits_contributors(album_credits)
        if contributors:
            return contributors
    # Fallback to old format
    raw_contributors = album_json.get("contributors")
    if raw_contributors:
        return _normalize_contributors(raw_contributors)
    return {}


def parse_track_and_album_extras(
    track_json: dict[str, Any] | None,
    album_json: dict[str, Any] | None,
) -> dict[str, Any]:
    """Extract extra metadata from raw TIDAL JSON for a track and its album.

    Returned dict keys (all optional, may be missing or empty):
      - bpm: int | None
      - label: str
      - genres: list[str]
      - contributors_by_role: dict[str, list[str]]
    """

    extras: dict[str, Any] = {
        "bpm": None,
        "label": "",
        "genres": [],
        "contributors_by_role": {},
    }

    # Extract from track
    if isinstance(track_json, dict):
        extras["bpm"] = _extract_bpm_from_track(track_json)
        extras["contributors_by_role"] = _extract_track_contributors(track_json)

    # Extract from album
    if isinstance(album_json, dict):
        label, genres = _extract_album_label_genres(album_json)
        extras["label"] = label
        extras["genres"] = genres

        # If we did not get track-level contributors, try album-level
        if not extras["contributors_by_role"]:
            extras["contributors_by_role"] = _extract_album_contributors(album_json)

    return extras


def extract_contributor_names(
    contributors_by_role: dict[str, list[str]] | None,
    role: str,
    delimiter: str = ", ",
) -> str:
    """Return a delimited string of contributor names for a given role.

    If the role is not present or has no names, returns an empty string.
    Role matching is case-insensitive.
    """
    if not contributors_by_role:
        return ""

    # Normalise keys to lowercase for robust lookups.
    role_lc = role.lower()
    for r, names in contributors_by_role.items():
        if r.lower() == role_lc and isinstance(names, list):
            filtered = [n for n in names if isinstance(n, str) and n]
            if filtered:
                return delimiter.join(filtered)

    return ""
