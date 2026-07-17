"""Download history tracking service with JSON persistence.

Classes:
    HistoryService: Main service for managing download history
        with atomic JSON operations.
"""

import json
import logging
import shutil
import tempfile
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import TypedDict, cast

from tidal_dl_ng.helper.decorator import SingletonMeta
from tidal_dl_ng.helper.path import path_config_base

_logger = logging.getLogger(__name__)


class HistoryFormatError(TypeError):
    """Exception raised when history file format is invalid."""

    def __init__(self) -> None:
        """Initialize with predefined message."""
        super().__init__("Invalid history file format")


class TrackEntry(TypedDict):
    """A single track entry stored in the history file.

    Attributes:
        sourceType: Type of source (playlist, album, manual, mix).
        sourceId: ID of the source or None for manual downloads.
        sourceName: Human-readable name of the source.
        downloadDate: ISO 8601 timestamp of download.
    """

    sourceType: str
    sourceId: str | None
    sourceName: str | None
    downloadDate: str


def _coerce_track_entry(raw: object) -> TrackEntry:
    """Safely coerce a raw value into a TrackEntry TypedDict.

    Args:
        raw: An arbitrary value loaded from JSON. Non-dict values
            degrade gracefully to a "manual" entry with empty fields.

    Returns:
        A TrackEntry with string-coerced values.
    """
    if not isinstance(raw, dict):
        return TrackEntry(
            sourceType="manual",
            sourceId=None,
            sourceName=None,
            downloadDate="",
        )

    data: dict[str, object] = cast("dict[str, object]", raw)
    return TrackEntry(
        sourceType=str(data.get("sourceType", "manual")),
        sourceId=(str(data["sourceId"]) if data.get("sourceId") else None),
        sourceName=(
            str(data["sourceName"]) if data.get("sourceName") else None
        ),
        downloadDate=str(data.get("downloadDate", "")),
    )


class SettingsData(TypedDict):
    """Settings stored alongside the history.

    Attributes:
        preventDuplicates: Whether to skip already-downloaded tracks.
    """

    preventDuplicates: bool


class HistoryFileData(TypedDict):
    """Full schema of the JSON history file.

    Attributes:
        _schema_version: Version number for schema migrations.
        _last_updated: ISO 8601 timestamp of last file update.
        settings: User-configurable settings.
        tracks: Track ID to entry mapping.
    """

    _schema_version: int
    _last_updated: str
    settings: SettingsData
    tracks: dict[str, TrackEntry]


class TrackView(TypedDict):
    """A source-grouped view of a track entry.

    Attributes:
        track_id: The TIDAL track ID.
        source_type: Type of source.
        source_id: ID of the source.
        source_name: Human-readable source name.
        download_date: ISO 8601 download timestamp.
    """

    track_id: str
    source_type: str
    source_id: str | None
    source_name: str | None
    download_date: str


class HistoryStatistics(TypedDict):
    """Statistics about the download history.

    Attributes:
        total_tracks: Total number of downloaded tracks.
        by_source_type: Count per source type.
        oldest_download: ISO date of the oldest download.
        newest_download: ISO date of the newest download.
    """

    total_tracks: int
    by_source_type: dict[str, int]
    oldest_download: str | None
    newest_download: str | None


@dataclass
class DownloadHistoryEntry:
    """Represents a single entry in the download history.

    Attributes:
        source_type: Type of source (playlist, album, manual, mix).
        source_id: ID of the source (UUID or None for manual).
        source_name: Name of the source.
        download_date: ISO 8601 timestamp of download.
    """

    source_type: str
    source_id: str | None
    source_name: str | None
    download_date: str


class HistoryService(metaclass=SingletonMeta):
    """Service for managing download history with JSON persistence.

    This service provides thread-safe operations for tracking
    downloaded tracks. The history is stored in a track-centric
    JSON file (trackId -> metadata). All write operations are
    atomic to prevent corruption.

    Attributes:
        history_data: In-memory dictionary of track IDs to entries.
        file_path: Path to the JSON history file.
        _lock: Thread lock for concurrent access safety.
    """

    SCHEMA_VERSION: int = 1

    def __init__(self) -> None:
        """Initialize the history service and load existing data."""
        self.file_path: Path = (
            Path(path_config_base()) / "downloaded_history.json"
        )
        self.history_data: dict[str, TrackEntry] = {}
        self.settings_data: SettingsData = {"preventDuplicates": True}
        self._lock: Lock = Lock()
        self._load_history()

    def _load_history(self) -> None:
        """Load history from JSON file.

        If the file doesn't exist, creates a new empty history.
        If the file is corrupted, backs it up and starts fresh.
        Thread-safe operation.
        """
        with self._lock:
            try:
                if not self.file_path.exists():
                    self.file_path.parent.mkdir(parents=True, exist_ok=True)
                    self._save_history_internal()
                    return

                with self.file_path.open(encoding="utf-8") as f:
                    raw: object = json.load(f)

                if not isinstance(raw, dict):
                    raise HistoryFormatError

                data: dict[str, object] = cast("dict[str, object]", raw)
                settings_raw = data.get("settings", {})
                if isinstance(settings_raw, dict):
                    settings: dict[str, object] = cast(
                        "dict[str, object]", settings_raw
                    )
                    self.settings_data = {
                        "preventDuplicates": bool(
                            settings.get("preventDuplicates", True)
                        )
                    }

                tracks_section = data.get("tracks")
                if isinstance(tracks_section, dict):
                    tracks: dict[str, object] = cast(
                        "dict[str, object]", tracks_section
                    )
                    self.history_data = {
                        k: _coerce_track_entry(cast("dict[str, object]", v))
                        for k, v in tracks.items()
                        if isinstance(v, dict)
                    }
                else:
                    self.history_data = {
                        k: _coerce_track_entry(cast("dict[str, object]", v))
                        for k, v in data.items()
                        if not k.startswith("_")
                        and k != "settings"
                        and isinstance(v, dict)
                    }

            except (json.JSONDecodeError, FileNotFoundError):
                self._backup_corrupted_file()
                self.history_data = {}
                self.settings_data = {"preventDuplicates": True}
                self._save_history_internal()

    def _backup_corrupted_file(self) -> None:
        """Backup a corrupted history file with an incremental suffix."""
        if not self.file_path.exists():
            return
        backup_path = self.file_path.with_suffix(".json.bak")
        counter = 1
        while backup_path.exists():
            backup_path = self.file_path.with_suffix(f".json.bak.{counter}")
            counter += 1
        shutil.copy2(self.file_path, backup_path)
        _logger.warning(
            "Download history file was corrupted. Backup saved to: %s",
            backup_path,
        )

    def _save_history_internal(self) -> None:
        """Save history to JSON file atomically.

        Uses atomic write (write to temp file, then rename) to
        prevent corruption. Assumes lock is already held by caller.
        """
        self.file_path.parent.mkdir(parents=True, exist_ok=True)

        data_to_save: HistoryFileData = {
            "_schema_version": self.SCHEMA_VERSION,
            "_last_updated": datetime.now(UTC).isoformat(),
            "settings": self.settings_data,
            "tracks": self.history_data,
        }

        tmp_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.file_path.parent,
                delete=False,
                suffix=".tmp",
            ) as tmp_file:
                json.dump(data_to_save, tmp_file, indent=2, ensure_ascii=False)
                tmp_path = tmp_file.name

            Path(tmp_path).replace(self.file_path)
            tmp_path = None

        finally:
            if tmp_path is not None:
                with suppress(OSError):
                    Path(tmp_path).unlink(missing_ok=True)

    def save_history(self) -> None:
        """Save history to disk (thread-safe, acquires lock)."""
        with self._lock:
            self._save_history_internal()

    def get_settings(self) -> SettingsData:
        """Return a copy of history-related settings.

        Returns:
            A copy of the current settings dictionary.
        """
        with self._lock:
            return self.settings_data.copy()

    def update_settings(
        self, *, prevent_duplicates: bool | None = None
    ) -> None:
        """Update history settings and persist immediately.

        Args:
            prevent_duplicates: When provided, updates the
                preventDuplicates setting.
        """
        with self._lock:
            if prevent_duplicates is not None:
                self.settings_data["preventDuplicates"] = prevent_duplicates
            self._save_history_internal()

    def should_skip_download(self, track_id: str) -> bool:
        """Return True if track should be skipped based on settings.

        Args:
            track_id: The TIDAL track ID to check.

        Returns:
            True if the track should be skipped.
        """
        with self._lock:
            prevent = self.settings_data.get("preventDuplicates", True)
            return prevent and track_id in self.history_data

    def is_downloaded(self, track_id: str) -> bool:
        """Check if a track has been downloaded.

        Args:
            track_id: The TIDAL track ID to check.

        Returns:
            True if track is in download history, False otherwise.
        """
        with self._lock:
            return track_id in self.history_data

    def add_track_to_history(
        self,
        track_id: str,
        source_type: str = "manual",
        source_id: str | None = None,
        source_name: str | None = None,
    ) -> None:
        """Add a track to download history.

        Args:
            track_id: The TIDAL track ID.
            source_type: Type of source (playlist, album, manual, mix).
            source_id: ID of the source or None for manual.
            source_name: Name of the source for display purposes.
        """
        with self._lock:
            self.history_data[track_id] = {
                "sourceType": source_type,
                "sourceId": source_id,
                "sourceName": source_name,
                "downloadDate": datetime.now(UTC).isoformat(),
            }
            self._save_history_internal()

    def remove_track_from_history(self, track_id: str) -> bool:
        """Remove a track from download history.

        Args:
            track_id: The TIDAL track ID to remove.

        Returns:
            True if track was removed, False if not found.
        """
        with self._lock:
            if track_id in self.history_data:
                del self.history_data[track_id]
                self._save_history_internal()
                return True
            return False

    def get_history_by_source(
        self,
    ) -> dict[str, list[TrackView]]:
        """Transform track-centric history to source-centric view.

        Returns:
            Dictionary grouped by source with format:
            {
                "source_key": [
                    {
                        "track_id": "123",
                        "download_date": "2025-11-15T...",
                        ...
                    }
                ]
            }
            where source_key is "{sourceType}_{sourceId}" or
            "{sourceType}_manual" for manual downloads.
        """
        with self._lock:
            grouped: dict[str, list[TrackView]] = {}

            for track_id, entry in self.history_data.items():
                source_type: str = entry.get("sourceType", "manual")
                source_id: str | None = entry.get("sourceId")
                source_name: str | None = entry.get("sourceName", "Unknown")
                source_key = (
                    f"{source_type}_{source_id}"
                    if source_id
                    else f"{source_type}_manual"
                )
                grouped.setdefault(source_key, []).append(
                    {
                        "track_id": track_id,
                        "source_type": source_type,
                        "source_id": source_id,
                        "source_name": source_name,
                        "download_date": entry.get("downloadDate", ""),
                    }
                )

            return grouped

    def get_track_info(self, track_id: str) -> TrackEntry | None:
        """Get download history info for a specific track.

        Args:
            track_id: The TIDAL track ID.

        Returns:
            TrackEntry dict or None if not found.
        """
        with self._lock:
            return self.history_data.get(track_id)

    def get_history_file_path(self) -> str:
        """Get the absolute path to the history file.

        Returns:
            Absolute path as string.
        """
        return str(self.file_path.absolute())

    def _extract_tracks_from_data(
        self, data: dict[str, object]
    ) -> dict[str, TrackEntry]:
        """Extract valid track entries from import data.

        Args:
            data: Import data dictionary.

        Returns:
            Dictionary of validated TrackEntry values.
        """
        tracks_node = data.get("tracks")
        source: dict[str, object] = cast(
            "dict[str, object]",
            (
                tracks_node
                if isinstance(tracks_node, dict)
                else {
                    k: v
                    for k, v in data.items()
                    if not k.startswith("_") and k != "settings"
                }
            ),
        )
        return {
            k: _coerce_track_entry(cast("dict[str, object]", v))
            for k, v in source.items()
            if isinstance(v, dict)
        }

    def _validate_tracks(
        self, tracks: dict[str, TrackEntry]
    ) -> tuple[bool, str]:
        """Validate track entries have required fields.

        Args:
            tracks: Dictionary of tracks to validate.

        Returns:
            Tuple of (valid, error_message).
        """
        required_keys: frozenset[str] = frozenset(
            {"sourceType", "downloadDate"}
        )
        for track_id, entry in tracks.items():
            if not required_keys.issubset(entry.keys()):
                return False, (f"Missing required fields for track {track_id}")
        return True, ""

    def import_history(
        self, file_path: str, *, merge: bool = True
    ) -> tuple[bool, str]:
        """Import history from an external JSON file.

        Args:
            file_path: Path to the JSON file to import.
            merge: If True, merge with existing history.
                   If False, replace.

        Returns:
            Tuple of (success, message).
        """
        try:
            with Path(file_path).open(encoding="utf-8") as f:
                raw: object = json.load(f)
        except json.JSONDecodeError as exc:
            return False, f"Invalid JSON file: {exc!s}"
        except OSError as exc:
            return False, f"Import failed: {exc!s}"

        if not isinstance(raw, dict):
            return False, "Invalid file format: expected JSON object"

        data: dict[str, object] = cast("dict[str, object]", raw)
        imported_settings_raw = data.get("settings", {})
        imported_tracks = self._extract_tracks_from_data(data)

        valid, error_msg = self._validate_tracks(imported_tracks)
        if not valid:
            return False, error_msg

        with self._lock:
            if merge:
                self.history_data.update(imported_tracks)
                message = f"Successfully merged {len(imported_tracks)} tracks"
            else:
                self.history_data = imported_tracks
                count = len(imported_tracks)
                message = (
                    f"Successfully imported {count} tracks "
                    f"(replaced existing)"
                )

            if (
                isinstance(imported_settings_raw, dict)
                and "preventDuplicates" in imported_settings_raw
            ):
                imported_settings: dict[str, object] = cast(
                    "dict[str, object]", imported_settings_raw
                )
                self.settings_data["preventDuplicates"] = bool(
                    imported_settings.get("preventDuplicates", True)
                )

            self._save_history_internal()

        return True, message

    def export_history(self, file_path: str) -> tuple[bool, str]:
        """Export history to an external JSON file.

        Args:
            file_path: Destination path for the exported JSON file.

        Returns:
            Tuple of (success, message).
        """
        try:
            with self._lock:
                data_to_export = {
                    "_schema_version": self.SCHEMA_VERSION,
                    "_exported_date": datetime.now(UTC).isoformat(),
                    "_total_tracks": len(self.history_data),
                    "settings": self.settings_data,
                    "tracks": self.history_data,
                }

                with Path(file_path).open("w", encoding="utf-8") as f:
                    json.dump(data_to_export, f, indent=2, ensure_ascii=False)

                return (
                    True,
                    f"Successfully exported "
                    f"{len(self.history_data)} tracks",
                )

        except OSError as exc:
            return False, f"Export failed: {exc!s}"

    def clear_history(self) -> None:
        """Clear all download history.

        This is a destructive operation — use with caution.
        """
        with self._lock:
            self.history_data = {}
            self._save_history_internal()

    def get_statistics(self) -> HistoryStatistics:
        """Get statistics about the download history.

        Returns:
            HistoryStatistics with total tracks, by source type,
            and oldest/newest download dates.
        """
        with self._lock:
            by_source: dict[str, int] = {}
            dates: list[str] = []

            for entry in self.history_data.values():
                source_type: str = entry.get("sourceType", "unknown")
                by_source[source_type] = by_source.get(source_type, 0) + 1
                if download_date := entry.get("downloadDate"):
                    dates.append(download_date)

            return {
                "total_tracks": len(self.history_data),
                "by_source_type": by_source,
                "oldest_download": min(dates) if dates else None,
                "newest_download": max(dates) if dates else None,
            }
