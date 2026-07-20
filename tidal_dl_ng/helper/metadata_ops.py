"""Metadata writing operations for TIDAL media downloads.

This module provides the `MetadataWriterMixin` class, which groups the
metadata, lyrics, cover, and contributor extraction logic used by the
main `Download` class. It is implemented as a mixin so that the methods
can keep accessing `self.settings`, `self.params`, `self.session`, and
the file-writing helpers defined on `Download`.
"""

import contextlib
import pathlib
from typing import Any, cast

from requests.exceptions import RequestException
from tidalapi.exceptions import TooManyRequests
from tidalapi.media import Stream, Track

from tidal_dl_ng.constants import (
    METADATA_EXPLICIT,
    METADATA_LOOKUP_UPC,
    CoverDimensions,
    MetadataTargetUPC,
)
from tidal_dl_ng.helper.download_protocol import DownloadProtocol
from tidal_dl_ng.helper.tidal import (
    extract_contributor_names,
    fetch_raw_track_and_album,
    name_builder_album_artist,
    name_builder_artist,
    name_builder_title,
    parse_track_and_album_extras,
)
from tidal_dl_ng.metadata import Metadata
from tidal_dl_ng.model.downloader import (
    TrackAssets,
    TrackExtrasData,
    TrackReleaseInfo,
)


class MetadataWriterMixin(DownloadProtocol):
    """Mixin providing metadata, lyrics, and cover writing helpers."""

    def _gather_track_assets(
        self,
        track: Track,
        is_parent_album: bool,
    ) -> TrackAssets:
        """Collect lyrics, cover, and extras for a track.

        Args:
            track: The track to gather assets for.
            is_parent_album: Whether this is a parent album.

        Returns:
            TrackAssets with all collected metadata assets.
        """
        _, lyrics_synced, lyrics_unsynced, path_lyrics = self._collect_lyrics(
            track
        )
        cover_data, path_cover = self._collect_cover(track, is_parent_album)
        extras = self._fetch_extras(track)
        return TrackAssets(
            lyrics_synced=lyrics_synced,
            lyrics_unsynced=lyrics_unsynced,
            path_lyrics=path_lyrics,
            cover_data=cover_data,
            path_cover=path_cover,
            extras=extras,
        )

    def metadata_write(
        self,
        track: Track,
        path_media: pathlib.Path,
        is_parent_album: bool,
        media_stream: Stream,
    ) -> tuple[bool, pathlib.Path | None, pathlib.Path | None]:
        """Write metadata, lyrics, and cover to a media file.

        Args:
            track (Track): Track object.
            path_media (pathlib.Path): Path to media file.
            is_parent_album (bool): Whether this is a parent album.
            media_stream (Stream): Stream object.

        Returns:
            tuple[bool, pathlib.Path | None, pathlib.Path | None]: (
                Success, path to lyrics, path to cover
            )
        """
        release_date = self._release_date_str(track)
        copy_right: str = (
            track.copyright
            if hasattr(track, "copyright") and track.copyright
            else ""
        )
        isrc: str = track.isrc if hasattr(track, "isrc") and track.isrc else ""
        assets = self._gather_track_assets(track, is_parent_album)
        m = self._build_metadata(
            path_media,
            track,
            media_stream,
            TrackReleaseInfo(
                release_date=release_date,
                copy_right=copy_right,
                isrc=isrc,
            ),
            TrackExtrasData(
                cover_data=assets.cover_data,
                lyrics_synced=assets.lyrics_synced,
                lyrics_unsynced=assets.lyrics_unsynced,
                extras=assets.extras,
            ),
        )
        m.save()
        return True, assets.path_lyrics, assets.path_cover

    def _release_date_str(self, track: Track) -> str:
        album = track.album
        date = None
        if album is not None:
            date = album.available_release_date or album.release_date
        return date.strftime("%Y-%m-%d") if date else ""

    def _collect_lyrics(
        self, track: Track
    ) -> tuple[str, str, str, pathlib.Path | None]:
        lyrics = ""
        lyrics_synced = ""
        lyrics_unsynced = ""
        path_lyrics: pathlib.Path | None = None
        if not (
            self.settings.data.lyrics_embed or self.settings.data.lyrics_file
        ):
            return lyrics, lyrics_synced, lyrics_unsynced, None
        try:
            lyrics_obj = track.lyrics()
            if text := getattr(lyrics_obj, "text", None):
                lyrics_unsynced = text or ""
                lyrics = lyrics_unsynced
            if subtitles := getattr(lyrics_obj, "subtitles", None):
                lyrics_synced = subtitles or ""
                lyrics = lyrics_synced
        except (RequestException, TooManyRequests, ValueError):
            lyrics = ""
        if lyrics and self.settings.data.lyrics_file:
            path_lyrics_str = self.lyrics_to_file(
                pathlib.Path(self.params.path_base), lyrics
            )
            if path_lyrics_str:
                path_lyrics = pathlib.Path(path_lyrics_str)
        return lyrics, lyrics_synced, lyrics_unsynced, path_lyrics

    def _collect_cover(
        self, track: Track, is_parent_album: bool
    ) -> tuple[bytes | None, pathlib.Path | None]:
        cover_data: bytes | None = None
        path_cover: pathlib.Path | None = None
        if not (
            self.settings.data.metadata_cover_embed
            or (self.settings.data.cover_album_file and is_parent_album)
        ):
            return None, None
        cover_dimension = self.settings.data.metadata_cover_dimension
        dim = (
            int(cover_dimension)
            if cover_dimension != CoverDimensions.PxORIGIN
            else int(CoverDimensions.Px1280)
        )
        album = track.album
        url_cover: str | None = None
        if album is not None:
            url_cover = album.image(dim)
        cover_data_tmp = self.cover_data(url=url_cover) if url_cover else None
        cover_data = (
            cover_data_tmp if isinstance(cover_data_tmp, bytes) else None
        )
        if (
            cover_data
            and self.settings.data.cover_album_file
            and is_parent_album
        ):
            url_cover_album_file: str | None = None
            if (
                cover_dimension == CoverDimensions.PxORIGIN
                and album is not None
            ):
                url_cover_album_file = album.image(CoverDimensions.PxORIGIN)
                cover_data_album_file = self.cover_data(
                    url=url_cover_album_file
                )
            else:
                cover_data_album_file = cover_data
            path_cover_str = self.cover_to_file(
                pathlib.Path(self.params.path_base),
                cast("bytes", cover_data_album_file),
            )
            if path_cover_str:
                path_cover = pathlib.Path(path_cover_str)
        return cover_data, path_cover

    def _fetch_extras(self, track: Track) -> dict[str, Any]:
        extras: dict[str, Any] = {
            "bpm": None,
            "label": "",
            "genres": [],
            "contributors_by_role": {},
        }
        # Use suppress to avoid bare try/except pass
        with contextlib.suppress(Exception):
            track_json, album_json = fetch_raw_track_and_album(
                self.session,
                str(track.id),
                extra_params={"include": "contributors,genres"},
            )
            parsed = parse_track_and_album_extras(track_json, album_json)
            if parsed:
                extras.update(parsed)
        return extras

    def _extract_contributor_fields(
        self,
        extras: dict[str, Any],
    ) -> tuple[str, str, str, int | None]:
        """Extract producer, composer, lyricist, and BPM from extras.

        Args:
            extras: Parsed metadata extras for the track.

        Returns:
            Tuple of producers, composers, lyricists, and BPM value.
        """
        contributors_by_role: dict[str, list[str]] = cast(
            "dict[str, list[str]]",
            extras.get("contributors_by_role") or {},
        )
        delimiter = self.settings.data.metadata_delimiter_artist
        producers = extract_contributor_names(
            contributors_by_role, "producer", delimiter=delimiter
        )
        composers_detailed = extract_contributor_names(
            contributors_by_role, "composer", delimiter=delimiter
        ) or extract_contributor_names(
            contributors_by_role, "composers", delimiter=delimiter
        )
        lyricists = extract_contributor_names(
            contributors_by_role, "lyricist", delimiter=delimiter
        ) or extract_contributor_names(
            contributors_by_role, "lyricists", delimiter=delimiter
        )
        bpm_val = extras.get("bpm")
        bpm: int | None = (
            int(bpm_val) if isinstance(bpm_val, (int | float)) else None
        )
        return producers, composers_detailed, lyricists, bpm

    def _compute_genre_display(
        self,
        extras: dict[str, Any],
    ) -> str:
        """Build a delimiter-joined genre string from track extras.

        Args:
            extras: Parsed metadata extras for the track.

        Returns:
            Genre string joined with the configured artist delimiter.
        """
        genres: list[str] = cast("list[str]", extras.get("genres") or [])
        genres_clean = [g for g in genres if g]
        return self.settings.data.metadata_delimiter_artist.join(genres_clean)

    def _build_metadata(
        self,
        path: pathlib.Path,
        track: Track,
        media_stream: Stream,
        release: TrackReleaseInfo,
        extras_data: TrackExtrasData,
    ) -> Metadata:
        explicit: bool = (
            track.explicit if hasattr(track, "explicit") else False
        )
        title = name_builder_title(track)
        if explicit and self.settings.data.mark_explicit:
            title += METADATA_EXPLICIT
        extras: dict[str, Any] = extras_data.extras
        genre_display = self._compute_genre_display(extras)
        producers, composers_detailed, lyricists, bpm = (
            self._extract_contributor_fields(extras)
        )
        return Metadata(
            path_file=path,
            target_upc=METADATA_LOOKUP_UPC[
                MetadataTargetUPC(self.settings.data.metadata_target_upc)
            ],
            lyrics=extras_data.lyrics_synced,
            lyrics_unsynced=extras_data.lyrics_unsynced,
            copy_right=release.copy_right,
            title=title,
            artists=name_builder_artist(
                track,
                delimiter=self.settings.data.metadata_delimiter_artist,
            ),
            album=(
                track.album.name
                if hasattr(track, "album") and track.album and track.album.name
                else ""
            ),
            tracknumber=track.track_num,
            date=release.release_date,
            isrc=release.isrc,
            albumartist=name_builder_album_artist(
                track,
                delimiter=self.settings.data.metadata_delimiter_album_artist,
            ),
            totaltrack=(
                track.album.num_tracks
                if track.album and track.album.num_tracks
                else 1
            ),
            totaldisc=(
                track.album.num_volumes
                if track.album and track.album.num_volumes
                else 1
            ),
            discnumber=track.volume_num or 1,
            cover_data=(
                extras_data.cover_data
                if self.settings.data.metadata_cover_embed
                and extras_data.cover_data
                else b""
            ),
            album_replay_gain=media_stream.album_replay_gain or 1.0,
            album_peak_amplitude=media_stream.album_peak_amplitude or 1.0,
            track_replay_gain=media_stream.track_replay_gain or 1.0,
            track_peak_amplitude=media_stream.track_peak_amplitude or 1.0,
            url_share=(
                track.share_url
                if track.share_url and self.settings.data.metadata_write_url
                else ""
            ),
            replay_gain_write=self.settings.data.metadata_replay_gain,
            upc=track.album.upc if track.album and track.album.upc else "",
            explicit=explicit,
            genre=genre_display,
            label=extras.get("label") or "",
            bpm=bpm,
            producers=producers,
            composers_detailed=composers_detailed,
            lyricists=lyricists,
        )
