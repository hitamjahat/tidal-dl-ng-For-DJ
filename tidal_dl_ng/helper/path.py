"""Path and filename utilities for media downloads.

Provides helpers for resolving configuration paths, building sanitized
media file paths from format templates, and ensuring filename uniqueness
across the local filesystem.
"""

from __future__ import annotations

import logging
import math
import os
import pathlib
import posixpath
import re
import sys
from copy import deepcopy
from typing import TYPE_CHECKING, Any
from urllib.parse import unquote, urlsplit

from pathvalidate import sanitize_filename, sanitize_filepath
from pathvalidate.error import ValidationError
from tidalapi import Album, Mix, Playlist, Track, UserPlaylist, Video
from tidalapi.media import AudioExtensions

from tidal_dl_ng import __name_display__
from tidal_dl_ng.constants import (
    FILENAME_LENGTH_MAX,
    FILENAME_SANITIZE_PLACEHOLDER,
    FORMAT_TEMPLATE_EXPLICIT,
    UNIQUIFY_THRESHOLD,
    MediaType,
)
from tidal_dl_ng.helper.tidal import (
    name_builder_album_artist,
    name_builder_artist,
    name_builder_title,
)

if TYPE_CHECKING:
    from tidal_dl_ng.config import Settings

logger = logging.getLogger(__name__)

MediaTypeUnion = Track | Album | Playlist | UserPlaylist | Video | Mix


def path_home() -> str:
    """Get the home directory path.

    Returns:
        str: The home directory path.
    """
    if "XDG_CONFIG_HOME" in os.environ:
        return os.environ["XDG_CONFIG_HOME"]
    if "HOME" in os.environ:
        return os.environ["HOME"]
    if "HOMEDRIVE" in os.environ and "HOMEPATH" in os.environ:
        return str(
            pathlib.Path(os.environ["HOMEDRIVE"]) / os.environ["HOMEPATH"]
        )
    return str(pathlib.Path.cwd())


def path_config_base() -> str:
    """Get the base configuration path.

    Returns:
        str: The base configuration path.
    """
    # https://wiki.archlinux.org/title/XDG_Base_Directory
    # X11 workaround: If user specified config path is set, do not
    # point to "~/.config"
    path_user_custom: str = os.environ.get("XDG_CONFIG_HOME", "")
    path_config: str = ".config" if not path_user_custom else ""
    path_base = pathlib.Path(path_home())
    if path_config:
        path_base = path_base / path_config
    path_base = path_base / __name_display__

    return str(path_base)


def path_file_log() -> str:
    """Get the path to the log file.

    Returns:
        str: The log file path.
    """
    return str(pathlib.Path(path_config_base()) / "app.log")


def path_file_token() -> str:
    """Get the path to the token file.

    Returns:
        str: The token file path.
    """
    return str(pathlib.Path(path_config_base()) / "token.json")


def path_file_settings() -> str:
    """Get the path to the settings file.

    Returns:
        str: The settings file path.
    """
    return str(pathlib.Path(path_config_base()) / "settings.json")


def format_path_media(
    fmt_template: str,
    media: MediaTypeUnion,
    album_track_num_pad_min: int = 0,
    list_pos: int = 0,
    list_total: int = 0,
    delimiter_artist: str = ", ",
    delimiter_album_artist: str = ", ",
    *,
    use_primary_album_artist: bool = False,
) -> str:
    """Format a media path string from a template and media attributes.

    Replaces placeholders in the format template with sanitized media
    attribute values to generate a valid file path.

    Args:
        fmt_template: The format template string with placeholders.
        media: The media object to extract values from.
        album_track_num_pad_min: Minimum padding for track numbers.
        list_pos: Position in a list.
        list_total: Total items in a list.
        delimiter_artist: Delimiter for artist names.
        delimiter_album_artist: Delimiter for album artist names.
        use_primary_album_artist: Use first album artist for folders.

    Returns:
        str: The formatted and sanitized media path string.
    """
    result = fmt_template

    # Search track format template for placeholder.
    regex = r"\{(.+?)\}"
    matches = re.finditer(regex, fmt_template, re.MULTILINE)

    for _match_num, match in enumerate(matches, start=1):
        template_str = match.group()
        result_fmt = format_str_media(
            match.group(1),
            media,
            album_track_num_pad_min,
            list_pos,
            list_total,
            delimiter_artist=delimiter_artist,
            delimiter_album_artist=delimiter_album_artist,
            use_primary_album_artist=use_primary_album_artist,
        )

        if result_fmt != match.group(1):
            # Sanitize here, in case the filename has slashes or
            # something that would be recognized later as a directory
            # separator. Do not sanitize if value is the
            # FORMAT_TEMPLATE_EXPLICIT placeholder, since it has a
            # leading whitespace which otherwise gets removed.
            value = (
                sanitize_filename(result_fmt)
                if result_fmt != FORMAT_TEMPLATE_EXPLICIT
                else FORMAT_TEMPLATE_EXPLICIT
            )
            result = result.replace(template_str, value)

    return result


def format_str_media(
    name: str,
    media: MediaTypeUnion,
    album_track_num_pad_min: int = 0,
    list_pos: int = 0,
    list_total: int = 0,
    delimiter_artist: str = ", ",
    delimiter_album_artist: str = ", ",
    *,
    use_primary_album_artist: bool = False,
) -> str:
    """Format a string for media attributes by name.

    Attempts to format the given name using a sequence of formatter
    functions, returning the first successful result.

    Args:
        name: The format string name to process.
        media: The media object to extract values from.
        album_track_num_pad_min: Minimum padding for track numbers.
        list_pos: Position in a list.
        list_total: Total items in a list.
        delimiter_artist: Delimiter for artist names.
        delimiter_album_artist: Delimiter for album artist names.
        use_primary_album_artist: Use first album artist for folders.

    Returns:
        str: The formatted string, or the original name if no
            formatter matches.
    """
    try:
        # Try each formatter function in sequence
        result = _format_names(
            name,
            media,
            delimiter_artist,
            delimiter_album_artist,
            use_primary_album_artist=use_primary_album_artist,
        )
        if result is not None:
            return result

        for formatter in (
            _format_numbers,
            _format_ids,
            _format_durations,
            _format_dates,
            _format_metadata,
            _format_volumes,
        ):
            result = formatter(
                name,
                media,
                album_track_num_pad_min,
                list_pos,
                list_total,
            )
            if result is not None:
                return result
    except Exception:
        # TODO(copilot): Implement better exception logging.
        logger.exception("Failed to format media string: %s", name)

    return name


def _format_artist_names(
    name: str,
    media: MediaTypeUnion,
    delimiter_artist: str = ", ",
    delimiter_album_artist: str = ", ",
    *_args: Any,
    use_primary_album_artist: bool = False,
    **kwargs: Any,
) -> str | None:
    """Handle artist name-related format strings.

    Args:
        name: The format string name to check.
        media: The media object to extract artist information from.
        delimiter_artist: Delimiter for artist names.
        delimiter_album_artist: Delimiter for album artist names.
        use_primary_album_artist: Use only the primary album artist.
        *args: Additional positional arguments (unused).
        **kwargs: Additional keyword arguments (unused).

    Returns:
        str | None: The formatted artist name or None if not
            artist-related.
    """
    if name == "artist_name" and isinstance(media, Track | Video):
        # For folder paths, use album artist if setting is enabled
        if (
            use_primary_album_artist
            and hasattr(media, "album")
            and media.album
            and media.album.artists
        ):
            return media.album.artists[0].name
        # Otherwise use track artists as before
        if hasattr(media, "artists"):
            return name_builder_artist(media, delimiter=delimiter_artist)
        if hasattr(media, "artist") and media.artist is not None:
            return media.artist.name
    if name == "album_artist" and isinstance(media, Track | Album):
        return name_builder_album_artist(media, first_only=True)
    if name == "album_artists" and isinstance(media, Track | Album):
        return name_builder_album_artist(
            media, delimiter=delimiter_album_artist
        )
    return None


def _format_titles(
    name: str,
    media: MediaTypeUnion,
    *_args: Any,
    **kwargs: Any,
) -> str | None:
    """Handle title-related format strings.

    Args:
        name: The format string name to check.
        media: The media object to extract title information from.
        *args: Additional positional arguments (unused).
        **kwargs: Additional keyword arguments (unused).

    Returns:
        str | None: The formatted title or None if not title-related.
    """
    if name == "track_title" and isinstance(media, Track | Video):
        return name_builder_title(media)
    if name == "mix_name" and isinstance(media, Mix):
        return media.title
    if name == "playlist_name" and isinstance(media, Playlist | UserPlaylist):
        return media.name
    if name == "album_title":
        if isinstance(media, Album):
            return media.name
        if isinstance(media, Track) and media.album is not None:
            return media.album.name
    return None


def _format_names(
    name: str,
    media: MediaTypeUnion,
    delimiter_artist: str = ", ",
    delimiter_album_artist: str = ", ",
    *args: Any,
    use_primary_album_artist: bool = False,
    **kwargs: Any,
) -> str | None:
    """Handle name-related format strings for media.

    Tries to format the provided name as an artist or title, returning
    the first matching result.

    Args:
        name: The format string name to check.
        media: The media object to extract name information from.
        delimiter_artist: Delimiter for artist names.
        delimiter_album_artist: Delimiter for album artist names.
        use_primary_album_artist: Use first album artist for folders.
        *args: Additional positional arguments (unused).
        **kwargs: Additional keyword arguments (unused).

    Returns:
        str | None: The formatted name or None if not name-related.
    """
    # First try artist name formats
    result = _format_artist_names(
        name,
        media,
        delimiter_artist=delimiter_artist,
        delimiter_album_artist=delimiter_album_artist,
        use_primary_album_artist=use_primary_album_artist,
    )
    if result is not None:
        return result

    # Then try title formats
    return _format_titles(name, media)


def _format_numbers(
    name: str,
    media: MediaTypeUnion,
    album_track_num_pad_min: int,
    list_pos: int,
    list_total: int,
    *_args: Any,
    **kwargs: Any,
) -> str | None:
    """Handle number-related format strings.

    Args:
        name: The format string name to check.
        media: The media object to extract number information from.
        album_track_num_pad_min: Minimum padding for track numbers.
        list_pos: Position in a list.
        list_total: Total items in a list.
        *args: Additional positional arguments (unused).
        **kwargs: Additional keyword arguments (unused).

    Returns:
        str | None: The formatted number or None if not number-related.
    """
    if name == "album_track_num" and isinstance(media, Track | Video):
        album_tracks = media.album.num_tracks if media.album is not None else 1
        return calculate_number_padding(
            album_track_num_pad_min,
            media.track_num,
            album_tracks,
        )
    if name == "album_num_tracks" and isinstance(media, Track | Video):
        album_tracks = media.album.num_tracks if media.album is not None else 1
        return str(album_tracks)
    if name == "list_pos" and isinstance(media, Track | Video):
        # TODO(copilot): Rename `album_track_num_pad_min` globally.
        return calculate_number_padding(
            album_track_num_pad_min, list_pos, list_total
        )
    return None


def _format_ids(
    name: str,
    media: MediaTypeUnion,
    *_args: Any,
    **kwargs: Any,
) -> str | None:
    """Handle ID-related format strings.

    Args:
        name: The format string name to check.
        media: The media object to extract ID information from.
        *args: Additional positional arguments (unused).
        **kwargs: Additional keyword arguments (unused).

    Returns:
        str | None: The formatted ID or None if not ID-related.
    """
    # Handle track and playlist IDs
    id_checks = (
        (name == "track_id", Track),
        (name == "playlist_id", Playlist),
        (name == "video_id", Video),
    )
    if any(
        name_match and isinstance(media, media_type)
        for name_match, media_type in id_checks
    ):
        return str(media.id)
    # Handle album IDs
    if name == "album_id" and isinstance(media, Album | Track):
        album = media if isinstance(media, Album) else media.album
        return str(album.id) if album is not None else None
    # Handle ISRC
    if name == "isrc" and isinstance(media, Track):
        return media.isrc
    # Handle artist IDs
    if name == "album_artist_id" and isinstance(media, Album):
        return str(media.artist.id) if media.artist is not None else None
    if name == "track_artist_id" and isinstance(media, Track):
        album = media.album
        artist = album.artist if album is not None else None
        return str(artist.id) if artist is not None else None
    return None


def _format_durations(
    name: str,
    media: MediaTypeUnion,
    *_args: Any,
    **kwargs: Any,
) -> str | None:
    """Handle duration-related format strings.

    Args:
        name: The format string name to check.
        media: The media object to extract duration information from.
        *args: Additional positional arguments (unused).
        **kwargs: Additional keyword arguments (unused).

    Returns:
        str | None: The formatted duration or None if not
            duration-related.
    """
    # Format track durations
    if name == "track_duration_seconds" and isinstance(media, Track | Video):
        return str(media.duration)
    if name == "track_duration_minutes" and isinstance(media, Track | Video):
        minutes, seconds = divmod(media.duration, 60)
        return f"{minutes:01d}:{seconds:02d}"

    # Format album/playlist durations
    duration_seconds = {"album_duration_seconds", "playlist_duration_seconds"}
    duration_minutes = {"album_duration_minutes", "playlist_duration_minutes"}
    if isinstance(media, Album) and name in duration_seconds:
        return str(media.duration)
    if isinstance(media, Album) and name in duration_minutes:
        minutes, seconds = divmod(media.duration, 60)
        return f"{minutes:01d}:{seconds:02d}"

    return None


def _format_dates(
    name: str,
    media: MediaTypeUnion,
    *_args: Any,
    **kwargs: Any,
) -> str | None:
    """Handle date-related format strings.

    Args:
        name: The format string name to check.
        media: The media object to extract date information from.
        *args: Additional positional arguments (unused).
        **kwargs: Additional keyword arguments (unused).

    Returns:
        str | None: The formatted date or None if not date-related.
    """
    if name == "album_year":
        if isinstance(media, Album):
            return str(getattr(media, "year", ""))
        if isinstance(media, Track) and media.album is not None:
            return str(getattr(media.album, "year", ""))
    if name == "album_date":
        if isinstance(media, Album):
            release = getattr(media, "release_date", None)
            return release.strftime("%Y-%m-%d") if release else None
        if isinstance(media, Track) and media.album is not None:
            release = getattr(media.album, "release_date", None)
            return release.strftime("%Y-%m-%d") if release else None

    return None


def _format_metadata(
    name: str,
    media: MediaTypeUnion,
    *_args: Any,
    **kwargs: Any,
) -> str | None:
    """Handle metadata-related format strings.

    Args:
        name: The format string name to check.
        media: The media object to extract metadata from.
        *args: Additional positional arguments (unused).
        **kwargs: Additional keyword arguments (unused).

    Returns:
        str | None: The formatted metadata or None if not
            metadata-related.
    """
    if name == "video_quality" and isinstance(media, Video):
        return media.video_quality
    if name == "track_quality" and isinstance(media, Track):
        raw_tags = getattr(media, "media_metadata_tags", []) or []
        tags: list[str] = [str(tag) for tag in raw_tags]
        return ", ".join(tag for tag in tags if tag)
    if (name == "track_explicit" and isinstance(media, Track | Video)) or (
        name == "album_explicit" and isinstance(media, Album)
    ):
        return FORMAT_TEMPLATE_EXPLICIT if media.explicit else ""
    if name == "media_type":
        if isinstance(media, Album):
            return str(getattr(media, "type", ""))
        if isinstance(media, Track) and media.album is not None:
            return str(getattr(media.album, "type", ""))
    return None


def _format_volumes(
    name: str,
    media: MediaTypeUnion,
    *_args: Any,
    **kwargs: Any,
) -> str | None:
    """Handle volume-related format strings.

    Args:
        name: The format string name to check.
        media: The media object to extract volume information from.
        *args: Additional positional arguments (unused).
        **kwargs: Additional keyword arguments (unused).

    Returns:
        str | None: The formatted volume info or None if not
            volume-related.
    """
    if name == "album_num_volumes" and isinstance(media, Album):
        return str(media.num_volumes)
    if name == "track_volume_num" and isinstance(media, Track | Video):
        return str(media.volume_num)
    if name == "track_volume_num_optional" and isinstance(
        media, Track | Video
    ):
        num_volumes = _get_num_volumes(media)
        return "" if num_volumes == 1 else str(media.volume_num)
    if name == "track_volume_num_optional_CD" and isinstance(
        media, Track | Video
    ):
        num_volumes = _get_num_volumes(media)
        return "" if num_volumes == 1 else f"CD{media.volume_num!s}"
    return None


def _get_num_volumes(media: MediaTypeUnion) -> int:
    """Safely extract the number of volumes from a media object.

    Args:
        media: The media object to inspect.

    Returns:
        int: The number of volumes, defaulting to 1 if unavailable.
    """
    if (album := getattr(media, "album", None)) is None:
        return 1
    return int(getattr(album, "num_volumes", 1))


def calculate_number_padding(
    padding_minimum: int,
    item_position: int,
    items_max: int,
) -> str:
    """Calculate the padded number string for an item.

    Args:
        padding_minimum: Minimum number of digits for padding.
        item_position: The position of the item.
        items_max: The maximum number of items.

    Returns:
        str: The padded number string.
    """
    if items_max > 0:
        count_digits = max(int(math.log10(items_max)) + 1, padding_minimum)
        return str(item_position).zfill(count_digits)
    return str(item_position)


def get_format_template(
    media: MediaTypeUnion | MediaType,
    settings: Settings,
) -> str | bool:
    """Get the format template for a given media type.

    Args:
        media: The media object or media type enum.
        settings: The settings object with format templates.

    Returns:
        str | bool: The format template string or False if not found.
    """
    if isinstance(media, Track) or media == MediaType.TRACK:
        return settings.data.format_track
    if isinstance(media, Album) or media in (
        MediaType.ALBUM,
        MediaType.ARTIST,
    ):
        return settings.data.format_album
    if (
        isinstance(media, Playlist | UserPlaylist)
        or media == MediaType.PLAYLIST
    ):
        return settings.data.format_playlist
    if isinstance(media, Mix) or media == MediaType.MIX:
        return settings.data.format_mix
    if isinstance(media, Video) or media == MediaType.VIDEO:
        return settings.data.format_video
    return False


def path_file_sanitize(
    path_file: pathlib.Path,
    *,
    adapt: bool = False,
    uniquify: bool = False,
) -> pathlib.Path:
    """Sanitize a file path to ensure it is valid and optionally unique.

    Args:
        path_file: The file path to sanitize.
        adapt: Whether to adapt the path in case of errors.
        uniquify: Whether to make the file name unique.

    Returns:
        pathlib.Path: The sanitized file path.
    """
    sanitized_filename = sanitize_filename(
        path_file.name,
        replacement_text="_",
        validate_after_sanitize=True,
        platform="auto",
    )

    if not sanitized_filename.endswith(path_file.suffix):
        sanitized_filename = (
            sanitized_filename[
                : -len(path_file.suffix) - len(FILENAME_SANITIZE_PLACEHOLDER)
            ]
            + FILENAME_SANITIZE_PLACEHOLDER
            + path_file.suffix
        )

    sanitized_path = pathlib.Path(
        *[
            (
                sanitize_filename(
                    part,
                    replacement_text="_",
                    validate_after_sanitize=True,
                    platform="auto",
                )
                if part not in path_file.anchor
                else part
            )
            for part in path_file.parent.parts
        ]
    )

    try:
        sanitized_path = sanitize_filepath(
            sanitized_path,
            replacement_text="_",
            validate_after_sanitize=True,
            platform="auto",
        )
    except ValidationError as e:
        if adapt and str(e).startswith("[PV1101]"):
            sanitized_path = pathlib.Path.home()
        else:
            raise

    result = sanitized_path / sanitized_filename

    return path_file_uniquify(result) if uniquify else result


def path_file_uniquify(path_file: pathlib.Path) -> pathlib.Path:
    """Ensure a file path is unique by appending a suffix if needed.

    Args:
        path_file: The file path to uniquify.

    Returns:
        pathlib.Path: The unique file path.
    """
    if not (unique_suffix := file_unique_suffix(path_file)):
        return path_file

    file_suffix = unique_suffix + path_file.suffix
    # For most OS filename has a character limit of 255.
    combined = path_file.parent / (path_file.stem + unique_suffix)
    if len(str(combined)) > FILENAME_LENGTH_MAX:
        stem_truncated = str(path_file.stem)[: -len(file_suffix)]
        return path_file.parent / (stem_truncated + file_suffix)
    return combined


def file_unique_suffix(path_file: pathlib.Path, separator: str = "_") -> str:
    """Generate a unique suffix for a file path.

    Args:
        path_file: The file path to check for uniqueness.
        separator: The separator to use for the suffix.

    Returns:
        str: The unique suffix, or an empty string if not needed.
    """
    threshold_zfill: int = len(str(UNIQUIFY_THRESHOLD))
    count: int = 0
    path_file_tmp: pathlib.Path = deepcopy(path_file)
    unique_suffix: str = ""

    while check_file_exists(path_file_tmp) and count < UNIQUIFY_THRESHOLD:
        count += 1
        unique_suffix = separator + str(count).zfill(threshold_zfill)
        path_file_tmp = path_file.parent / (
            path_file.stem + unique_suffix + path_file.suffix
        )

    return unique_suffix


def check_file_exists(
    path_file: pathlib.Path,
    *,
    extension_ignore: bool = False,
) -> bool:
    """Check if a file exists.

    Args:
        path_file: The file path to check.
        extension_ignore: Whether to ignore the file extension.

    Returns:
        bool: True if the file exists, False otherwise.
    """
    if extension_ignore:
        path_file_stem: str = pathlib.Path(path_file).stem
        path_parent: pathlib.Path = pathlib.Path(path_file).parent
        path_files: list[str] = [
            str(path_parent.joinpath(path_file_stem + str(extension.value)))
            for extension in AudioExtensions
        ]
    else:
        path_files = [str(path_file)]

    return any(pathlib.Path(_file).is_file() for _file in path_files)


def resource_path(relative_path: str) -> str:
    """Get the absolute path to a resource.

    Args:
        relative_path: The relative path to the resource.

    Returns:
        str: The absolute path to the resource.
    """
    # PyInstaller creates a temp folder and stores path in _MEIPASS
    base_path = getattr(sys, "_MEIPASS", str(pathlib.Path.cwd()))

    return str(pathlib.Path(base_path) / relative_path)


def url_to_filename(url: str) -> str:
    """Convert a URL to a valid filename.

    Args:
        url: The URL to convert.

    Returns:
        str: The corresponding filename.

    Raises:
        ValueError: If the URL contains invalid characters for a
            filename.
    """
    urlpath: str = urlsplit(url).path
    basename: str = posixpath.basename(unquote(urlpath))

    if (
        pathlib.Path(basename).name != basename
        or unquote(posixpath.basename(urlpath)) != basename
    ):
        # Reject '%2f' or 'dir%5Cbasename.ext' on Windows
        raise ValueError

    return basename
