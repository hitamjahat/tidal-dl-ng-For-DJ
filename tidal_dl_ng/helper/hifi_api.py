"""HiFi-API endpoint helpers for TIDAL API requests.

This module provides async functions for interacting with the TIDAL
API endpoints, using the authentication infrastructure from
``tidal_dl_ng.helper.tidal_auth``.

All functions use the shared HTTP client and token management from
``tidal_auth``, supporting proxy-aware retries and rate limiting.

Merged from hifi-api-main/main.py (lines 303-1242).
"""

from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any

from tidal_dl_ng.helper.tidal_auth import (
    _album_tracks_sem,
    _extract_uuid_from_tidal_url,
    authed_get_json,
    get_tidal_token_for_cred,
    make_request,
)

#: API version string for response payloads.
API_VERSION: str = "2.10"

#: Default country code for TIDAL API requests.
COUNTRY_CODE: str = os.getenv("COUNTRY_CODE", "US")


async def get_track_info(
    track_id: int,
    *,
    quality: str = "HI_RES_LOSSLESS",
    immersive_audio: bool = False,
    token: str | None = None,
    cred: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fetch track playback info from TIDAL.

    Args:
        track_id: The TIDAL track ID.
        quality: Audio quality (e.g. "HI_RES_LOSSLESS").
        immersive_audio: Whether to request immersive audio.
        token: Optional pre-fetched access token.
        cred: Optional pre-fetched credential dict.

    Returns:
        dict[str, Any]: Playback info response payload.
    """
    url = f"https://api.tidal.com/v1/tracks/{track_id}/playbackinfo"
    params = {
        "audioquality": quality,
        "playbackmode": "STREAM",
        "assetpresentation": "FULL",
        "immersiveaudio": immersive_audio,
    }
    return await make_request(url, params=params, token=token, cred=cred)


async def get_track_manifests(
    track_id: str,
    *,
    formats: list[str] | None = None,
    adaptive: str = "true",
    manifest_type: str = "MPEG_DASH",
    uri_scheme: str = "HTTPS",
    usage: str = "PLAYBACK",
    token: str | None = None,
    cred: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fetch track manifests from TIDAL's V2 API.

    Args:
        track_id: The TIDAL track ID.
        formats: List of format strings to request.
        adaptive: Whether to request adaptive streaming.
        manifest_type: Manifest type (e.g. "MPEG_DASH").
        uri_scheme: URI scheme (e.g. "HTTPS").
        usage: Usage context (e.g. "PLAYBACK").
        token: Optional pre-fetched access token.
        cred: Optional pre-fetched credential dict.

    Returns:
        dict[str, Any]: Track manifests response payload.
    """
    if formats is None:
        formats = [
            "HEAACV1",
            "AACLC",
            "FLAC",
            "FLAC_HIRES",
            "EAC3_JOC",
        ]
    url = f"https://openapi.tidal.com/v2/trackManifests/{track_id}"
    params = [
        ("adaptive", adaptive),
        ("manifestType", manifest_type),
        ("uriScheme", uri_scheme),
        ("usage", usage),
    ]
    for f in formats:
        params.append(("formats", f))
    return await make_request(url, params=params, token=token, cred=cred)


async def get_recommendations(
    track_id: int,
    *,
    token: str | None = None,
    cred: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fetch track recommendations from TIDAL.

    Args:
        track_id: The TIDAL track ID.
        token: Optional pre-fetched access token.
        cred: Optional pre-fetched credential dict.

    Returns:
        dict[str, Any]: Recommendations response payload.
    """
    url = f"https://api.tidal.com/v1/tracks/{track_id}/recommendations"
    params = {"limit": "20", "countryCode": COUNTRY_CODE}
    return await make_request(url, params=params, token=token, cred=cred)


async def search(
    query: str | None = None,
    artist: str | None = None,
    album: str | None = None,
    video: str | None = None,
    playlist: str | None = None,
    isrc: str | None = None,
    offset: int = 0,
    limit: int = 25,
    *,
    token: str | None = None,
    cred: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Search TIDAL for tracks, artists, albums, videos, or playlists.

    Args:
        query: Track search query.
        artist: Artist search query.
        album: Album search query.
        video: Video search query.
        playlist: Playlist search query.
        isrc: ISRC query (searches tracks by ISRC).
        offset: Results offset.
        limit: Results limit (1-500).
        token: Optional pre-fetched access token.
        cred: Optional pre-fetched credential dict.

    Returns:
        dict[str, Any]: Search results response payload.

    Raises:
        ValueError: If no search query is provided.
    """
    isrc_query = isrc.strip() if isrc else None
    if isrc_query:
        return await make_request(
            "https://api.tidal.com/v1/tracks",
            params={
                "isrc": isrc_query,
                "limit": limit,
                "offset": offset,
                "countryCode": COUNTRY_CODE,
            },
            token=token,
            cred=cred,
        )

    queries = (
        (
            query,
            "https://api.tidal.com/v1/search/tracks",
            {
                "query": query,
                "limit": limit,
                "offset": offset,
                "countryCode": COUNTRY_CODE,
            },
        ),
        (
            artist,
            "https://api.tidal.com/v1/search/top-hits",
            {
                "query": artist,
                "limit": limit,
                "offset": offset,
                "types": "ARTISTS,TRACKS",
                "countryCode": COUNTRY_CODE,
            },
        ),
        (
            album,
            "https://api.tidal.com/v1/search/top-hits",
            {
                "query": album,
                "limit": limit,
                "offset": offset,
                "types": "ALBUMS",
                "countryCode": COUNTRY_CODE,
            },
        ),
        (
            video,
            "https://api.tidal.com/v1/search/top-hits",
            {
                "query": video,
                "limit": limit,
                "offset": offset,
                "types": "VIDEOS",
                "countryCode": COUNTRY_CODE,
            },
        ),
        (
            playlist,
            "https://api.tidal.com/v1/search/top-hits",
            {
                "query": playlist,
                "limit": limit,
                "offset": offset,
                "types": "PLAYLISTS",
                "countryCode": COUNTRY_CODE,
            },
        ),
    )

    for value, url, params in queries:
        if value:
            return await make_request(
                url, params=params, token=token, cred=cred
            )

    raise ValueError(
        "Provide one of query, artist, album, video, " "playlist, or isrc"
    )


async def get_album(
    album_id: int,
    limit: int = 100,
    offset: int = 0,
    *,
    token: str | None = None,
    cred: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fetch album metadata plus items concurrently.

    Args:
        album_id: The TIDAL album ID.
        limit: Maximum number of items to fetch.
        offset: Items offset.
        token: Optional pre-fetched access token.
        cred: Optional pre-fetched credential dict.

    Returns:
        dict[str, Any]: Album data with items.
    """
    token_val, cred_val = await get_tidal_token_for_cred(cred=cred)
    if token is None:
        token = token_val
    if cred is None:
        cred = cred_val

    album_url = f"https://api.tidal.com/v1/albums/{album_id}"
    items_url = f"https://api.tidal.com/v1/albums/{album_id}/items"

    async def fetch(
        url: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        payload, _, _ = await authed_get_json(
            url, params=params, token=token, cred=cred
        )
        return payload

    tasks = [fetch(album_url, {"countryCode": COUNTRY_CODE})]

    max_chunk = 100
    current_offset = offset
    remaining_limit = limit

    while remaining_limit > 0:
        chunk_size = min(remaining_limit, max_chunk)
        tasks.append(
            fetch(
                items_url,
                {
                    "countryCode": COUNTRY_CODE,
                    "limit": chunk_size,
                    "offset": current_offset,
                },
            )
        )
        current_offset += chunk_size
        remaining_limit -= chunk_size

    results = await asyncio.gather(*tasks)

    album_data = results[0]
    items_pages = results[1:]

    all_items: list[dict[str, Any]] = []
    for page in items_pages:
        page_items = (
            page.get("items", page) if isinstance(page, dict) else page
        )
        if isinstance(page_items, list):
            all_items.extend(page_items)

    album_data["items"] = all_items

    return {
        "version": API_VERSION,
        "data": album_data,
    }


async def get_mix(
    mix_id: str,
    *,
    token: str | None = None,
    cred: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fetch items from a TIDAL mix by its ID.

    Args:
        mix_id: The TIDAL mix ID.
        token: Optional pre-fetched access token.
        cred: Optional pre-fetched credential dict.

    Returns:
        dict[str, Any]: Mix data with header and items.
    """
    token_val, cred_val = await get_tidal_token_for_cred(cred=cred)
    if token is None:
        token = token_val
    if cred is None:
        cred = cred_val

    url = "https://api.tidal.com/v1/pages/mix"
    params = {
        "mixId": mix_id,
        "countryCode": COUNTRY_CODE,
        "deviceType": "BROWSER",
    }

    data, _, _ = await authed_get_json(
        url, params=params, token=token, cred=cred
    )

    header: dict[str, Any] = {}
    items: list[dict[str, Any]] = []

    rows = data.get("rows", [])
    for row in rows:
        modules = row.get("modules", [])
        for module in modules:
            if module.get("type") == "MIX_HEADER":
                header = module.get("mix", {})
            elif module.get("type") == "TRACK_LIST":
                paged_list = module.get("pagedList", {})
                items = paged_list.get("items", [])

    return {
        "version": API_VERSION,
        "mix": header,
        "items": [
            item.get("item", item) if isinstance(item, dict) else item
            for item in items
        ],
    }


async def get_playlist(
    playlist_id: str,
    limit: int = 100,
    offset: int = 0,
    *,
    token: str | None = None,
    cred: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fetch playlist metadata plus items concurrently.

    Args:
        playlist_id: The TIDAL playlist ID (UUID string).
        limit: Maximum number of items to fetch.
        offset: Items offset.
        token: Optional pre-fetched access token.
        cred: Optional pre-fetched credential dict.

    Returns:
        dict[str, Any]: Playlist data with items.
    """
    token_val, cred_val = await get_tidal_token_for_cred(cred=cred)
    if token is None:
        token = token_val
    if cred is None:
        cred = cred_val

    playlist_url = f"https://api.tidal.com/v1/playlists/{playlist_id}"
    items_url = f"https://api.tidal.com/v1/playlists/{playlist_id}/items"

    async def fetch(
        url: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        payload, _, _ = await authed_get_json(
            url, params=params, token=token, cred=cred
        )
        return payload

    playlist_data, items_data = await asyncio.gather(
        fetch(
            playlist_url,
            {"countryCode": COUNTRY_CODE},
        ),
        fetch(
            items_url,
            {
                "countryCode": COUNTRY_CODE,
                "limit": limit,
                "offset": offset,
            },
        ),
    )

    return {
        "version": API_VERSION,
        "playlist": playlist_data,
        "items": (
            items_data.get("items", items_data)
            if isinstance(items_data, dict)
            else items_data
        ),
    }


async def get_similar_artists(
    artist_id: int,
    cursor: int | str | None = None,
    *,
    token: str | None = None,
    cred: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fetch artists similar to another by its ID using V2 API.

    Args:
        artist_id: The TIDAL artist ID.
        cursor: Pagination cursor.
        token: Optional pre-fetched access token.
        cred: Optional pre-fetched credential dict.

    Returns:
        dict[str, Any]: Similar artists response.
    """
    url = (
        f"https://openapi.tidal.com/v2/artists/{artist_id}"
        "/relationships/similarArtists"
    )
    params = {
        "page[cursor]": cursor,
        "countryCode": COUNTRY_CODE,
        "include": "similarArtists,similarArtists.profileArt",
    }

    payload, _, _ = await authed_get_json(
        url, params=params, token=token, cred=cred
    )
    included = payload.get("included", [])
    artists_map = {i["id"]: i for i in included if i["type"] == "artists"}
    artworks_map = {i["id"]: i for i in included if i["type"] == "artworks"}

    def resolve_artist(entry: dict[str, Any]) -> dict[str, Any]:
        aid = entry["id"]
        inc = artists_map.get(aid, {})
        attr = inc.get("attributes", {})

        pic_id: str | None = None
        if (
            art_data := inc.get("relationships", {})
            .get("profileArt", {})
            .get("data")
        ):
            if artwork := artworks_map.get(art_data[0].get("id")):
                if files := artwork.get("attributes", {}).get("files"):
                    pic_id = _extract_uuid_from_tidal_url(files[0].get("href"))

        return {
            **attr,
            "id": int(aid) if str(aid).isdigit() else aid,
            "picture": pic_id or attr.get("selectedAlbumCoverFallback"),
            "url": f"http://www.tidal.com/artist/{aid}",
            "relationType": "SIMILAR_ARTIST",
        }

    return {
        "version": API_VERSION,
        "artists": [resolve_artist(e) for e in payload.get("data", [])],
    }


async def get_similar_albums(
    album_id: int,
    cursor: int | str | None = None,
    *,
    token: str | None = None,
    cred: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fetch albums similar to another by its ID using V2 API.

    Args:
        album_id: The TIDAL album ID.
        cursor: Pagination cursor.
        token: Optional pre-fetched access token.
        cred: Optional pre-fetched credential dict.

    Returns:
        dict[str, Any]: Similar albums response.
    """
    url = (
        f"https://openapi.tidal.com/v2/albums/{album_id}"
        "/relationships/similarAlbums"
    )
    params = {
        "page[cursor]": cursor,
        "countryCode": COUNTRY_CODE,
        "include": (
            "similarAlbums,similarAlbums.coverArt," "similarAlbums.artists"
        ),
    }

    payload, _, _ = await authed_get_json(
        url, params=params, token=token, cred=cred
    )
    included = payload.get("included", [])
    albums_map = {i["id"]: i for i in included if i["type"] == "albums"}
    artworks_map = {i["id"]: i for i in included if i["type"] == "artworks"}
    artists_map = {i["id"]: i for i in included if i["type"] == "artists"}

    def resolve_album(entry: dict[str, Any]) -> dict[str, Any]:
        aid = entry["id"]
        inc = albums_map.get(aid, {})
        attr = inc.get("attributes", {})

        cover_id: str | None = None
        if (
            art_data := inc.get("relationships", {})
            .get("coverArt", {})
            .get("data")
        ):
            if artwork := artworks_map.get(art_data[0].get("id")):
                if files := artwork.get("attributes", {}).get("files"):
                    cover_id = _extract_uuid_from_tidal_url(
                        files[0].get("href")
                    )

        artist_list: list[dict[str, Any]] = []
        if (
            art_data := inc.get("relationships", {})
            .get("artists", {})
            .get("data")
        ):
            for a_entry in art_data:
                if a_obj := artists_map.get(a_entry["id"]):
                    a_id = a_obj["id"]
                    artist_list.append(
                        {
                            "id": int(a_id) if str(a_id).isdigit() else a_id,
                            "name": a_obj["attributes"]["name"],
                        }
                    )

        return {
            **attr,
            "id": int(aid) if str(aid).isdigit() else aid,
            "cover": cover_id,
            "artists": artist_list,
            "url": f"http://www.tidal.com/album/{aid}",
        }

    return {
        "version": API_VERSION,
        "albums": [resolve_album(e) for e in payload.get("data", [])],
    }


async def get_artist(
    artist_id: int | None = None,
    fetch_id: int | None = None,
    skip_tracks: bool = False,
    *,
    token: str | None = None,
    cred: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fetch artist detail or album+track aggregation.

    Args:
        artist_id: Basic artist metadata + cover URLs.
        fetch_id: Fetch artist albums and aggregate tracks.
        skip_tracks: If True, return only albums without tracks.
        token: Optional pre-fetched access token.
        cred: Optional pre-fetched credential dict.

    Returns:
        dict[str, Any]: Artist data response.

    Raises:
        ValueError: If neither artist_id nor fetch_id is provided.
    """
    if artist_id is None and fetch_id is None:
        raise ValueError("Provide artist_id or fetch_id")

    token_val, cred_val = await get_tidal_token_for_cred(cred=cred)
    if token is None:
        token = token_val
    if cred is None:
        cred = cred_val

    if artist_id is not None:
        artist_url = f"https://api.tidal.com/v1/artists/{artist_id}"
        artist_data, token, cred = await authed_get_json(
            artist_url,
            params={"countryCode": COUNTRY_CODE},
            token=token,
            cred=cred,
        )

        picture = artist_data.get("picture")
        fallback = artist_data.get("selectedAlbumCoverFallback")

        if not picture and fallback:
            artist_data["picture"] = fallback
            picture = fallback

        cover: dict[str, Any] | None = None
        if picture:
            slug = picture.replace("-", "/")
            cover = {
                "id": artist_data.get("id"),
                "name": artist_data.get("name"),
                "750": (
                    f"https://resources.tidal.com/images/"
                    f"{slug}/750x750.jpg"
                ),
            }

        return {
            "version": API_VERSION,
            "artist": artist_data,
            "cover": cover,
        }

    # Fetch albums and singles/EPs directly in parallel
    albums_url = f"https://api.tidal.com/v1/artists/{fetch_id}/albums"
    common_params = {
        "countryCode": COUNTRY_CODE,
        "limit": 100,
    }

    tasks = [
        authed_get_json(
            albums_url,
            params=common_params,
            token=token,
            cred=cred,
        ),
        authed_get_json(
            albums_url,
            params={**common_params, "filter": "EPSANDSINGLES"},
            token=token,
            cred=cred,
        ),
    ]

    if skip_tracks:
        tasks.append(
            authed_get_json(
                f"https://api.tidal.com/v1/artists/{fetch_id}/toptracks",
                params={
                    "countryCode": COUNTRY_CODE,
                    "limit": 15,
                },
                token=token,
                cred=cred,
            )
        )

    results = await asyncio.gather(*tasks, return_exceptions=True)

    unique_releases: list[dict[str, Any]] = []
    seen_ids: set[int] = set()

    for res in results[:2]:
        if isinstance(res, tuple) and len(res) > 0:
            data = res[0]
            items = data.get("items", []) if isinstance(data, dict) else data
            if isinstance(items, list):
                for item in items:
                    if (
                        isinstance(item, dict)
                        and item.get("id")
                        and item["id"] not in seen_ids
                    ):
                        unique_releases.append(item)
                        seen_ids.add(item["id"])
        elif isinstance(res, Exception):
            pass

    album_ids: list[int] = [item["id"] for item in unique_releases]
    page_data = {"items": unique_releases}

    if skip_tracks:
        top_tracks: list[dict[str, Any]] = []
        if len(results) > 2:
            res = results[2]
            if isinstance(res, tuple) and len(res) > 0:
                data = res[0]
                top_tracks = (
                    data.get("items", []) if isinstance(data, dict) else data
                )
        return {
            "version": API_VERSION,
            "albums": page_data,
            "tracks": top_tracks,
        }

    if not album_ids:
        return {
            "version": API_VERSION,
            "albums": page_data,
            "tracks": [],
        }

    async def fetch_album_tracks(
        album_id: int,
    ) -> list[dict[str, Any]]:
        async with _album_tracks_sem:
            album_data, _, _ = await authed_get_json(
                "https://api.tidal.com/v1/pages/album",
                params={
                    "albumId": album_id,
                    "countryCode": COUNTRY_CODE,
                    "deviceType": "BROWSER",
                },
                token=token,
                cred=cred,
            )

            rows = album_data.get("rows", [])
            if len(rows) < 2:
                return []
            modules = rows[1].get("modules", [])
            if not modules:
                return []
            paged_list = modules[0].get("pagedList", {})
            items = paged_list.get("items", [])
            tracks = [
                track.get("item", track) if isinstance(track, dict) else track
                for track in items
            ]
            return tracks

    results = await asyncio.gather(
        *(fetch_album_tracks(album_id) for album_id in album_ids),
        return_exceptions=True,
    )

    tracks: list[dict[str, Any]] = []
    for res in results:
        if isinstance(res, Exception):
            continue
        tracks.extend(res)

    return {
        "version": API_VERSION,
        "albums": page_data,
        "tracks": tracks,
    }


async def get_cover(
    track_id: int | None = None,
    query: str | None = None,
    *,
    token: str | None = None,
    cred: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fetch album cover data for a track ID or search query.

    Args:
        track_id: The TIDAL track ID.
        query: Search query for finding tracks.
        token: Optional pre-fetched access token.
        cred: Optional pre-fetched credential dict.

    Returns:
        dict[str, Any]: Cover data response.

    Raises:
        ValueError: If neither track_id nor query is provided.
    """
    if track_id is None and query is None:
        raise ValueError("Provide track_id or query")

    token_val, cred_val = await get_tidal_token_for_cred(cred=cred)
    if token is None:
        token = token_val
    if cred is None:
        cred = cred_val

    def build_cover_entry(
        cover_slug: str,
        name: str | None,
        tid: int | None,
    ) -> dict[str, Any]:
        slug = cover_slug.replace("-", "/")
        return {
            "id": tid,
            "name": name,
            "1280": (
                f"https://resources.tidal.com/images/" f"{slug}/1280x1280.jpg"
            ),
            "640": (
                f"https://resources.tidal.com/images/" f"{slug}/640x640.jpg"
            ),
            "80": f"https://resources.tidal.com/images/" f"{slug}/80x80.jpg",
        }

    if track_id is not None:
        track_data, token, cred = await authed_get_json(
            f"https://api.tidal.com/v1/tracks/{track_id}/",
            params={"countryCode": COUNTRY_CODE},
            token=token,
            cred=cred,
        )

        album = track_data.get("album") or {}
        cover_slug = album.get("cover")
        if not cover_slug:
            raise RuntimeError("Cover not found")

        entry = build_cover_entry(
            cover_slug,
            album.get("title") or track_data.get("title"),
            album.get("id") or track_id,
        )
        return {"version": API_VERSION, "covers": [entry]}

    search_data, token, cred = await authed_get_json(
        "https://api.tidal.com/v1/search/tracks",
        params={
            "countryCode": COUNTRY_CODE,
            "query": query,
            "limit": 10,
        },
        token=token,
        cred=cred,
    )

    items = search_data.get("items", [])[:10]
    if not items:
        raise RuntimeError("Cover not found")

    covers: list[dict[str, Any]] = []
    for track in items:
        album = track.get("album") or {}
        cover_slug = album.get("cover")
        if not cover_slug:
            continue
        covers.append(
            build_cover_entry(
                cover_slug,
                track.get("title"),
                track.get("id"),
            )
        )

    if not covers:
        raise RuntimeError("Cover not found")

    return {"version": API_VERSION, "covers": covers}


async def get_lyrics(
    track_id: int,
    *,
    token: str | None = None,
    cred: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fetch lyrics for a track from TIDAL.

    Args:
        track_id: The TIDAL track ID.
        token: Optional pre-fetched access token.
        cred: Optional pre-fetched credential dict.

    Returns:
        dict[str, Any]: Lyrics response.

    Raises:
        RuntimeError: If lyrics are not found.
    """
    url = f"https://api.tidal.com/v1/tracks/{track_id}/lyrics"
    data, token, cred = await authed_get_json(
        url,
        params={
            "countryCode": COUNTRY_CODE,
            "locale": "en_US",
            "deviceType": "BROWSER",
        },
        token=token,
        cred=cred,
    )

    if not data:
        raise RuntimeError("Lyrics not found")

    return {"version": API_VERSION, "lyrics": data}


async def get_top_videos(
    country_code: str = "US",
    locale: str = "en_US",
    device_type: str = "BROWSER",
    limit: int = 25,
    offset: int = 0,
    *,
    token: str | None = None,
    cred: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fetch recommended videos from TIDAL.

    Args:
        country_code: Country code for the request.
        locale: Locale string.
        device_type: Device type string.
        limit: Maximum number of videos.
        offset: Videos offset.
        token: Optional pre-fetched access token.
        cred: Optional pre-fetched credential dict.

    Returns:
        dict[str, Any]: Top videos response.
    """
    token_val, cred_val = await get_tidal_token_for_cred(cred=cred)
    if token is None:
        token = token_val
    if cred is None:
        cred = cred_val

    url = "https://api.tidal.com/v1/pages/mymusic_recommended_videos"
    params = {
        "countryCode": country_code,
        "locale": locale,
        "deviceType": device_type,
    }

    data, token, cred = await authed_get_json(
        url, params=params, token=token, cred=cred
    )

    rows = data.get("rows", [])
    all_videos: list[dict[str, Any]] = []
    for row in rows:
        modules = row.get("modules", [])
        for module in modules:
            module_type = module.get("type")
            if module_type in (
                "VIDEO_PLAYLIST",
                "VIDEO_ROW",
                "PAGED_LIST",
            ):
                paged_list = module.get("pagedList", {})
                if paged_list:
                    items = paged_list.get("items", [])
                    for item in items:
                        video = (
                            item.get("item", item)
                            if isinstance(item, dict)
                            else item
                        )
                        all_videos.append(video)
            elif module_type == "VIDEO" or (
                module_type and "video" in module_type.lower()
            ):
                item = module.get("item", module)
                if isinstance(item, dict):
                    all_videos.append(item)

    paginated = all_videos[offset : offset + limit]

    return {
        "version": API_VERSION,
        "videos": paginated,
        "total": len(all_videos),
    }


async def get_video(
    video_id: int,
    quality: str = "HIGH",
    mode: str = "STREAM",
    presentation: str = "FULL",
    *,
    token: str | None = None,
    cred: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fetch video playback info from TIDAL.

    Args:
        video_id: The TIDAL video ID.
        quality: Video quality (HIGH, MEDIUM, LOW).
        mode: Playback mode (STREAM, OFFLINE).
        presentation: Asset presentation (FULL, PREVIEW).
        token: Optional pre-fetched access token.
        cred: Optional pre-fetched credential dict.

    Returns:
        dict[str, Any]: Video playback info response.
    """
    token_val, cred_val = await get_tidal_token_for_cred(cred=cred)
    if token is None:
        token = token_val
    if cred is None:
        cred = cred_val

    url = f"https://api.tidal.com/v1/videos/{video_id}/playbackinfo"
    params = {
        "videoquality": quality,
        "playbackmode": mode,
        "assetpresentation": presentation,
    }

    data, token, cred = await authed_get_json(
        url, params=params, token=token, cred=cred
    )

    return {"version": API_VERSION, "video": data}
