"""Tidal helper utilities.

Provides functions for building media names, searching, pagination,
session interaction, and raw JSON metadata extraction from the TIDAL API.
"""

import contextlib
import os
from collections.abc import Callable
from typing import cast

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


def name_builder_artist(
    media: Track | Video | Album,
    delimiter: str = ", ",
) -> str:
    """Build a delimited string of artist names for a media object.

    Args:
        media: The track, video, or album to extract artist names from.
        delimiter: The delimiter placed between artist names.

    Returns:
        A delimited string of artist names.
    """
    artists = media.artists or []
    return delimiter.join(str(artist.name) for artist in artists)


def name_builder_album_artist(
    media: Track | Album,
    *,
    first_only: bool = False,
    delimiter: str = ", ",
) -> str:
    """Build a delimited string of main album artist names.

    Args:
        media: The track or album to extract artist names from.
        first_only: When True, only the first main artist is included.
        delimiter: The delimiter placed between artist names.

    Returns:
        A delimited string of main album artist names.
    """
    artists_tmp: list[str] = []

    if isinstance(media, Track) and media.album is not None:
        artists = media.album.artists or []
    else:
        artists = media.artists or []

    for artist in artists:
        roles = artist.roles or []
        if Role.main in roles:
            if name := artist.name:
                artists_tmp.append(str(name))

            if first_only:
                break

    return delimiter.join(artists_tmp)


def name_builder_title(
    media: Track | Video | Mix | Playlist | Album,
) -> str:
    """Build a display title for any supported media type.

    Args:
        media: The media object to build a title for.

    Returns:
        The display title string.
    """
    if isinstance(media, Mix):
        return str(media.title)

    if full_name := getattr(media, "full_name", None):
        return str(full_name)

    return str(getattr(media, "name", ""))


def name_builder_item(media: Track | Video) -> str:
    """Build a display string 'Artist - Title' for a track or video.

    Args:
        media: The track or video object.

    Returns:
        A formatted 'Artist - Title' string.
    """
    return f"{name_builder_artist(media)} - {name_builder_title(media)}"


def get_tidal_media_id(url_or_id_media: str) -> str:
    """Extract the media ID from a TIDAL URL or return the ID directly.

    Args:
        url_or_id_media: A TIDAL URL or raw media ID.

    Returns:
        The extracted media ID.
    """
    id_dirty = url_or_id_media.rsplit("/", 1)[-1]
    return id_dirty.rsplit("?", 1)[0]


def get_tidal_media_type(url_media: str) -> MediaType | bool:
    """Determine the media type from a TIDAL URL.

    Args:
        url_media: The TIDAL URL to parse.

    Returns:
        The detected MediaType, or False when unrecognized.
    """
    result: MediaType | bool = False
    url_split = url_media.split("/")[-2]

    if len(url_split) > 1:
        media_name = url_media.split("/")[-2]

        if media_name == "track":
            result = MediaType.TRACK
        elif media_name == "video":
            result = MediaType.VIDEO
        elif media_name == "album":
            result = MediaType.ALBUM
        elif media_name == "playlist":
            result = MediaType.PLAYLIST
        elif media_name == "mix":
            result = MediaType.MIX
        elif media_name == "artist":
            result = MediaType.ARTIST
        else:
            result = False

    return result


def url_ending_clean(url: str) -> str:
    """Remove a trailing '/u' or '?u' suffix from a URL.

    Args:
        url: The URL to clean.

    Returns:
        The cleaned URL.
    """
    suffixes = ("/u", "?u")
    return url[:-2] if url.endswith(suffixes) else url


def _normalize_search_bucket(value: object) -> list[object]:
    """Normalize tidalapi search bucket values to a list of items."""
    if value is None:
        return []
    if isinstance(value, list):
        return cast("list[object]", value)
    if isinstance(value, tuple | set):
        typed_value = cast("tuple[object, ...] | set[object]", value)
        return list(typed_value)
    items_attr = getattr(value, "items", None)
    if isinstance(items_attr, list):
        return cast("list[object]", items_attr)

    if callable(items_attr):
        with contextlib.suppress(Exception):
            items_from_method = items_attr()
            if isinstance(items_from_method, list):
                return cast("list[object]", items_from_method)

    return [value]


def _search_item_identity(item: object) -> str:
    """Build a stable identity key to deduplicate search results."""
    if (item_id := getattr(item, "id", None)) is not None:
        return f"{type(item).__name__}:{item_id}"
    return f"{type(item).__name__}:{item!r}"


def search_results_all(
    session: Session,
    needle: str,
    types_media: object = None,
) -> dict[str, list[object]]:
    """Fetch all search results across every page from TIDAL.

    Args:
        session: The TIDAL session.
        needle: The search query string.
        types_media: Optional media types to filter the search.

    Returns:
        Aggregated search results keyed by media type.
    """
    limit = 300
    offset = 0
    done = False
    result: dict[str, list[object]] = {}
    seen: dict[str, set[str]] = {}

    while not done:
        raw_result = session.search(
            query=needle,
            models=types_media,
            limit=limit,
            offset=offset,
        )
        added_any = _merge_search_page(raw_result, result, seen)

        done = not added_any
        offset += limit

    return result


def _merge_search_page(
    raw_result: dict[str, object],
    result: dict[str, list[object]],
    seen: dict[str, set[str]],
) -> bool:
    """Merge one search result page into the aggregated result.

    Args:
        raw_result: The raw search response page.
        result: The aggregated results keyed by media type.
        seen: Tracking set of already-seen item identities.

    Returns:
        True when at least one new item was added.
    """
    added_any = False

    for key, value in raw_result.items():
        key_name = str(key)
        values_list = _normalize_search_bucket(value)

        if key_name not in result:
            result[key_name] = []
            seen[key_name] = set()

        for item in values_list:
            if (identity := _search_item_identity(item)) not in seen[key_name]:
                seen[key_name].add(identity)
                result[key_name].append(item)
                added_any = True

    return added_any


def items_results_all(
    _session: Session,
    media_list: Mix | Playlist | Album | Artist,
    *,
    videos_include: bool = True,
) -> list[object]:
    """Fetch all items from a media list container.

    Args:
        _session: The TIDAL session (reserved for API symmetry).
        media_list: The album, playlist, mix, or artist to fetch from.
        videos_include: Whether to include videos for playlists/albums.

    Returns:
        All items contained in the media list.
    """
    if isinstance(media_list, Mix):
        return cast("list[object]", media_list.items())

    func_get_items_media: list[Callable[..., object]] = []

    if isinstance(media_list, Playlist | Album):
        if videos_include:
            func_get_items_media.append(media_list.items)
        else:
            func_get_items_media.append(media_list.tracks)
    else:
        func_get_items_media.append(media_list.get_albums)
        func_get_items_media.append(media_list.get_ep_singles)

    return paginate_results(func_get_items_media)


def all_artist_album_ids(media_artist: Artist) -> list[int]:
    """Get all album IDs for an artist.

    Args:
        media_artist: The artist to query.

    Returns:
        A list of album IDs.
    """
    fetchers: list[Callable[..., object]] = [
        media_artist.get_albums,
        media_artist.get_ep_singles,
    ]
    albums = paginate_results(fetchers)

    return [
        int(album_id)
        for album in albums
        if (album_id := getattr(album, "id", None)) is not None
    ]


def paginate_results(
    func_get_items_media: list[Callable[..., object]],
) -> list[object]:
    """Paginate through TIDAL API results for the given fetcher functions.

    Args:
        func_get_items_media: Bound methods accepting limit/offset.

    Returns:
        All collected results across every page.
    """
    result: list[object] = []

    for func_media in func_get_items_media:
        limit = 100
        offset = 0
        done = False

        func_ref = getattr(func_media, "__func__", None)
        if func_ref == LoggedInUser.playlist_and_favorite_playlists:
            limit = 50

        while not done:
            tmp_result = cast(
                "list[object]", func_media(limit=limit, offset=offset)
            )

            if bool(tmp_result):
                result += tmp_result
                offset += limit
            else:
                done = True

    return result


def user_media_lists(session: Session) -> dict[str, list[object]]:
    """Fetch user media lists using tidalapi pagination where available.

    Returns a dictionary with 'playlists' and 'mixes' keys. For playlists,
    both Folder and Playlist objects at the root level are included.

    Args:
        session: The TIDAL session object.

    Returns:
        A mapping with 'playlists' and 'mixes' lists.
    """
    user = cast("LoggedInUser", session.user)

    playlists: list[object] = user.favorites.playlists_paginated()

    folders: list[object] = []
    offset = 0
    limit = 50

    while True:
        batch = user.favorites.playlist_folders(
            limit=limit,
            offset=offset,
            parent_folder_id="root",
        )
        if not batch:
            break
        folders.extend(batch)
        if len(batch) < limit:
            break
        offset += limit

    all_playlists = folders + playlists

    mixes_page = cast("object", session.mixes())
    categories_attr = getattr(mixes_page, "categories", None)
    categories = (
        cast("list[object]", categories_attr)
        if isinstance(categories_attr, list)
        else []
    )
    user_mixes: list[object] = (
        getattr(categories[0], "items", []) if categories else []
    )

    return {"playlists": all_playlists, "mixes": user_mixes}


def instantiate_media(
    session: Session,
    media_type: MediaType,
    id_media: str,
) -> Track | Video | Album | Playlist | Mix | Artist:
    """Instantiate a TIDAL media object from its type and ID.

    Args:
        session: The TIDAL session.
        media_type: The type of media to instantiate.
        id_media: The media ID.

    Returns:
        The instantiated media object.

    Raises:
        MediaUnknown: If the media_type is not recognized.
    """
    if media_type == MediaType.TRACK:
        return session.track(id_media, with_album=True)
    if media_type == MediaType.VIDEO:
        return session.video(id_media)
    if media_type == MediaType.ALBUM:
        return session.album(id_media)
    if media_type == MediaType.PLAYLIST:
        return session.playlist(id_media)
    if media_type == MediaType.MIX:
        return session.mix(id_media)
    if media_type == MediaType.ARTIST:
        return session.artist(id_media)

    raise MediaUnknown


def quality_audio_highest(media: Track | Album) -> Quality:
    """Determine the highest available audio quality for a media object.

    Args:
        media: The track or album to inspect.

    Returns:
        The highest available quality tier.
    """
    tags = getattr(media, "media_metadata_tags", None)
    iterable_tags: set[str] = set()
    if isinstance(tags, dict):
        tags_dict = cast("dict[str, object]", tags)
        iterable_tags = {str(k) for k in tags_dict}

    if MediaMetadataTags.hi_res_lossless in iterable_tags:
        return Quality.hi_res_lossless
    if MediaMetadataTags.lossless in iterable_tags:
        return Quality.high_lossless

    audio_quality = getattr(media, "audio_quality", None)
    if isinstance(audio_quality, Quality):
        return audio_quality

    return Quality.low_320k


def favorite_function_factory(
    tidal: object,
    favorite_item: str,
) -> Callable[..., object]:
    """Create a callable fetching a TIDAL favorite category.

    Args:
        tidal: The Tidal configuration/session wrapper.
        favorite_item: The key into the FAVORITES dictionary.

    Returns:
        A bound method from session.user.favorites.
    """
    function_name = FAVORITES[favorite_item]["function_name"]
    favorites = getattr(tidal, "session", None)
    user = getattr(favorites, "user", None)
    user_favorites = getattr(user, "favorites", None)
    function_list: Callable[..., object] = getattr(
        user_favorites,
        function_name,
    )

    return function_list


def fetch_raw_media_json(
    session: Session,
    media_type: str,
    media_id: str,
    country_code: str | None = None,
    extra_params: dict[str, str | int | None] | None = None,
) -> dict[str, object] | None:
    """Fetch raw JSON for a media resource via tidalapi's session.

    Args:
        session: The tidalapi Session.
        media_type: 'tracks' or 'albums'.
        media_id: The id of the media.
        country_code: Optional countryCode query parameter.
        extra_params: Additional query parameters.

    Returns:
        Parsed JSON, or None when the fetch fails.
    """
    try:
        params: dict[str, str | int | None] = {}
        if cc := country_code or os.environ.get("TIDAL_COUNTRY"):
            params["countryCode"] = cc

        if extra_params:
            params.update(extra_params)

        resp = session.request.request(
            "GET",
            f"{media_type}/{media_id}",
            params=params,
        )
        resp.raise_for_status()
        return cast("dict[str, object]", resp.json())
    except requests.exceptions.HTTPError:
        return None
    except (requests.exceptions.RequestException, ValueError):
        return None


def fetch_raw_track_and_album(
    session: Session,
    track_id: str,
    country_code: str | None = None,
    extra_params: dict[str, str | int | None] | None = None,
) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    """Fetch raw track JSON and its album JSON when available.

    Args:
        session: The tidalapi Session.
        track_id: The track ID to fetch.
        country_code: Optional countryCode query parameter.
        extra_params: Additional query parameters.

    Returns:
        A tuple of (track_json, album_json).
    """
    default_track_params: dict[str, str | int | None] = {
        "include": "albums,artists,genres",
    }
    merged_track_params: dict[str, str | int | None] = {
        **default_track_params,
        **(extra_params or {}),
    }

    track_json = fetch_raw_media_json(
        session,
        "tracks",
        str(track_id),
        country_code=country_code,
        extra_params=merged_track_params,
    )

    album_json: dict[str, object] | None = None
    try:
        if isinstance(track_json, dict):
            album = track_json.get("album")
            if isinstance(album, dict):
                album_dict = cast("dict[str, object]", album)
                album_id = album_dict.get("id")
            else:
                album_id = album
            if album_id:
                default_album_params: dict[str, str | int | None] = {
                    "include": "artists,genres",
                }
                merged_album_params: dict[str, str | int | None] = {
                    **default_album_params,
                    **(extra_params or {}),
                }

                album_json = fetch_raw_media_json(
                    session,
                    "albums",
                    str(album_id),
                    country_code=country_code,
                    extra_params=merged_album_params,
                )
    except (requests.exceptions.RequestException, ValueError):
        album_json = None

    return track_json, album_json


def _normalize_dict_contributors(
    raw_contributors: dict[str, object],
) -> dict[str, list[str]]:
    """Process contributors in dict format: role -> list[{name, ...}]."""
    result: dict[str, list[str]] = {}
    for role, people in raw_contributors.items():
        if not isinstance(people, list):
            continue
        people_list = cast("list[object]", people)
        names: list[str] = []
        for person in people_list:
            if isinstance(person, dict):
                person_dict = cast("dict[str, object]", person)
                name = person_dict.get("name")
                if isinstance(name, str) and name:
                    names.append(name)
        if names:
            result[role] = names
    return result


def _normalize_list_contributors(
    raw_contributors: list[object],
) -> dict[str, list[str]]:
    """Process contributors in list format: [{name, role, ...}, ...]."""
    result: dict[str, list[str]] = {}
    for person in raw_contributors:
        if not isinstance(person, dict):
            continue
        person_dict = cast("dict[str, object]", person)
        name = person_dict.get("name")
        role = person_dict.get("role")
        if isinstance(name, str) and name and isinstance(role, str) and role:
            result.setdefault(role, []).append(name)
    return result


def _normalize_contributors(raw_contributors: object) -> dict[str, list[str]]:
    """Normalize contributor JSON shapes into role -> list[str] names.

    The TIDAL API has used at least two shapes historically:
    - dict role -> list[{"name": str, ...}]
    - list[{"name": str, "role": str, ...}]

    Both are accepted; malformed entries are ignored.
    """
    if isinstance(raw_contributors, dict):
        return _normalize_dict_contributors(
            cast("dict[str, object]", raw_contributors)
        )
    if isinstance(raw_contributors, list):
        return _normalize_list_contributors(
            cast("list[object]", raw_contributors)
        )
    return {}


def _extract_bpm_from_track(track_json: dict[str, object]) -> int | None:
    """Extract the BPM value from a track JSON object."""
    bpm = track_json.get("bpm")
    if isinstance(bpm, int):
        return bpm
    if isinstance(bpm, float):
        return round(bpm)
    if isinstance(bpm, str):
        with contextlib.suppress(ValueError):
            return round(float(bpm))
    return None


def _process_credits_contributors(
    credits_list: list[object],
) -> dict[str, list[str]]:
    """Process credits API v2 format into contributors by role."""
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
        credit_dict = cast("dict[str, object]", credit)
        credit_type = credit_dict.get("type", "")
        credit_type_str = credit_type if isinstance(credit_type, str) else ""
        role = role_mapping.get(credit_type_str, credit_type_str)
        contributors = credit_dict.get("contributors", [])
        if isinstance(contributors, list):
            contributors_list = cast("list[object]", contributors)
            for contributor in contributors_list:
                if isinstance(contributor, dict):
                    contributor_dict = cast("dict[str, object]", contributor)
                    name = contributor_dict.get("name")
                    if isinstance(name, str) and name:
                        result.setdefault(role, []).append(name)
    return result


def _extract_track_contributors(
    track_json: dict[str, object],
) -> dict[str, list[str]]:
    """Extract contributors from a track JSON object."""
    if (track_credits := track_json.get("credits")) and isinstance(
        track_credits, list
    ):
        contributors = _process_credits_contributors(
            cast("list[object]", track_credits)
        )
        if contributors:
            return contributors

    if raw_contributors := track_json.get("contributors"):
        return _normalize_contributors(raw_contributors)
    return {}


def _process_genre_item(genre: object) -> str | None:
    """Extract a genre name from various possible formats."""
    if isinstance(genre, str) and genre:
        return genre
    if isinstance(genre, dict):
        genre_dict = cast("dict[str, object]", genre)
        name = genre_dict.get("name")
        if isinstance(name, str) and name:
            return name
    return None


def _deduplicate_genres(genres: list[str]) -> list[str]:
    """Deduplicate genres while preserving order."""
    seen: set[str] = set()
    unique: list[str] = []
    for genre in genres:
        if genre not in seen:
            seen.add(genre)
            unique.append(genre)
    return unique


def _extract_album_label_genres(
    album_json: dict[str, object],
) -> tuple[str, list[str]]:
    """Extract the label and genres from an album JSON object."""
    label = album_json.get("label") or album_json.get("recordLabel")
    label_str = label if isinstance(label, str) else ""

    raw_genres = album_json.get("genres") or album_json.get("genre")
    genres: list[str] = []

    if isinstance(raw_genres, list):
        raw_genres_list = cast("list[object]", raw_genres)
        genres.extend(
            extracted
            for genre in raw_genres_list
            if (extracted := _process_genre_item(genre))
        )
    elif isinstance(raw_genres, str) and raw_genres:
        genres.append(raw_genres)
    elif extracted := _process_genre_item(raw_genres):
        genres.append(extracted)

    if genres:
        return label_str, _deduplicate_genres(genres)
    return label_str, []


def _extract_album_contributors(
    album_json: dict[str, object],
) -> dict[str, list[str]]:
    """Extract contributors from an album JSON object."""
    if (album_credits := album_json.get("credits")) and isinstance(
        album_credits, list
    ):
        contributors = _process_credits_contributors(
            cast("list[object]", album_credits)
        )
        if contributors:
            return contributors

    if raw_contributors := album_json.get("contributors"):
        return _normalize_contributors(raw_contributors)
    return {}


def parse_track_and_album_extras(
    track_json: dict[str, object] | None,
    album_json: dict[str, object] | None,
) -> dict[str, object]:
    """Extract extra metadata from raw TIDAL JSON for a track and album.

    Returned keys (all optional, may be missing or empty):
      - bpm: int | None
      - label: str
      - genres: list[str]
      - contributors_by_role: dict[str, list[str]]
    """
    extras: dict[str, object] = {
        "bpm": None,
        "label": "",
        "genres": [],
        "contributors_by_role": {},
    }

    if isinstance(track_json, dict):
        extras["bpm"] = _extract_bpm_from_track(track_json)
        extras["contributors_by_role"] = _extract_track_contributors(
            track_json,
        )

    if isinstance(album_json, dict):
        label, genres = _extract_album_label_genres(album_json)
        extras["label"] = label
        extras["genres"] = genres

        if not extras["contributors_by_role"]:
            extras["contributors_by_role"] = _extract_album_contributors(
                album_json,
            )

    return extras


def extract_contributor_names(
    contributors_by_role: dict[str, list[str]] | None,
    role: str,
    delimiter: str = ", ",
) -> str:
    """Return a delimited string of contributor names for a given role.

    Role matching is case-insensitive. When the role is absent or has no
    names, an empty string is returned.

    Args:
        contributors_by_role: Mapping of role to contributor names.
        role: The role to look up.
        delimiter: The delimiter between names.

    Returns:
        A delimited string of matching contributor names.
    """
    if not contributors_by_role:
        return ""

    role_lc = role.lower()
    for current_role, names in contributors_by_role.items():
        if current_role.lower() == role_lc and (
            filtered := [n for n in names if n]
        ):
            return delimiter.join(filtered)

    return ""
