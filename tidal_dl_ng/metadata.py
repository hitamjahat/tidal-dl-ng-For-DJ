"""Audio metadata model and tag writing for TIDAL downloads.

This module defines :class:`Metadata`, a data container that collects
the fields required to tag a downloaded audio file and writes them to
FLAC, MP3 and MP4 containers via :mod:`mutagen`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import mutagen
from mutagen import flac, id3, mp3, mp4
from mutagen.id3 import (
    APIC,
    ID3,
    SYLT,
    TALB,
    TBPM,
    TCOM,
    TCON,
    TCOP,
    TDRC,
    TIT2,
    TOPE,
    TPE1,
    TPUB,
    TRCK,
    TSRC,
    TXXX,
    USLT,
    WOAS,
)
from mutagen.mp4 import MP4FreeForm, MP4Tags

if TYPE_CHECKING:
    from pathlib import Path

    from mutagen.flac import VCFLACDict


# Union of the three supported concrete mutagen file types.
_AudioFile = flac.FLAC | mp3.MP3 | mp4.MP4


def _open_audio(path: str | Path) -> _AudioFile:
    """Open an audio file and return a typed mutagen instance.

    Args:
        path: Path to the audio file.

    Returns:
        A concrete FLAC, MP3 or MP4 mutagen instance.

    Raises:
        mutagen.MutagenError: If the file cannot be opened or the
            format is not supported.
    """
    raw = mutagen.File(path)
    if isinstance(raw, (flac.FLAC, mp3.MP3, mp4.MP4)):
        return raw
    msg = f"Unsupported or unreadable audio file: {path}"
    raise mutagen.MutagenError(msg)


@dataclass
# The container intentionally mirrors a rich audio-tagging schema;
# the many fields are a deliberate public API consumed by the download
# pipeline.
# pylint: disable=too-many-instance-attributes
class Metadata:
    """Collect and write audio metadata for a downloaded file.

    Attributes:
        path_file: Location of the audio file to tag.
        target_upc: Mapping of container format to the UPC tag name.
        album: Album title.
        title: Track title.
        artists: Performer/artist string.
        copy_right: Copyright notice.
        tracknumber: Position of the track on the release.
        discnumber: Disc/volume number.
        totaltrack: Total tracks on the disc.
        totaldisc: Total discs in the release.
        composer: Primary composer (falls back to composers_detailed).
        isrc: International Standard Recording Code.
        albumartist: Album artist / ensemble.
        date: Release date string.
        lyrics: Synchronised lyrics.
        lyrics_unsynced: Plain-text lyrics.
        cover_data: Raw cover image bytes (None when absent).
        album_replay_gain: Album replay-gain value.
        album_peak_amplitude: Album peak amplitude.
        track_replay_gain: Track replay-gain value.
        track_peak_amplitude: Track peak amplitude.
        url_share: Share URL to embed.
        replay_gain_write: Whether to write replay-gain tags.
        upc: Universal Product Code of the release.
        explicit: Whether the track is explicit.
        genre: Genre label.
        label: Record label.
        bpm: Beats-per-minute (None when unknown).
        producers: Producer credit string.
        composers_detailed: Detailed composer credit string.
        lyricists: Lyricist credit string.
        m: Loaded mutagen file object (populated in __post_init__).
    """

    path_file: str | Path
    target_upc: dict[str, str]
    album: str = ""
    title: str = ""
    artists: str = ""
    copy_right: str = ""
    tracknumber: int = 0
    discnumber: int = 0
    totaltrack: int = 0
    totaldisc: int = 0
    composer: str = ""
    isrc: str = ""
    albumartist: str = ""
    date: str = ""
    lyrics: str = ""
    lyrics_unsynced: str = ""
    cover_data: bytes | None = None
    album_replay_gain: float = 1.0
    album_peak_amplitude: float = 1.0
    track_replay_gain: float = 1.0
    track_peak_amplitude: float = 1.0
    url_share: str = ""
    replay_gain_write: bool = True
    upc: str = ""
    explicit: bool = False
    genre: str = ""
    label: str = ""
    bpm: int | None = None
    producers: str = ""
    composers_detailed: str = ""
    lyricists: str = ""
    m: _AudioFile | None = field(init=False, default=None)

    def __post_init__(self) -> None:
        """Load the underlying mutagen file object.

        Raises:
            mutagen.MutagenError: If the file cannot be opened or the
                format is not supported.
        """
        self.m = _open_audio(self.path_file)

    def _require_m(self) -> _AudioFile:
        """Return the audio file object, raising if uninitialised.

        Returns:
            The concrete mutagen audio file instance.

        Raises:
            mutagen.MutagenError: If the audio file is not loaded.
        """
        if self.m is None:
            msg = f"Audio file not loaded: {self.path_file}"
            raise mutagen.MutagenError(msg)
        return self.m

    def _ensure_tags(self, audio: _AudioFile) -> None:
        """Ensure the mutagen file has an initialised tags container.

        Args:
            audio: The concrete mutagen file instance.
        """
        if audio.tags is None:
            audio.add_tags()

    def _cover(self) -> bool:
        """Embed cover_data into the audio file when present.

        Returns:
            True when a cover was embedded, else False.
        """
        if not self.cover_data:
            return False

        audio = self._require_m()
        self._ensure_tags(audio)

        match audio:
            case flac.FLAC():
                flac_cover = flac.Picture()
                flac_cover.type = id3.PictureType.COVER_FRONT
                flac_cover.data = self.cover_data
                flac_cover.mime = "image/jpeg"
                audio.clear_pictures()
                audio.add_picture(flac_cover)
            case mp3.MP3():
                if audio.tags is not None:
                    audio.tags.add(APIC(encoding=3, data=self.cover_data))
            case _:
                if audio.tags is not None:
                    audio.tags["covr"] = [mp4.MP4Cover(self.cover_data)]

        return True

    def save(self) -> bool:
        """Write all collected metadata to the audio file.

        Returns:
            True once the file is saved.

        Raises:
            mutagen.MutagenError: If the audio file is not loaded.
        """
        audio = self._require_m()
        self._ensure_tags(audio)

        match audio:
            case flac.FLAC():
                self.set_flac()
            case mp3.MP3():
                self.set_mp3()
            case _:
                self.set_mp4()

        self._cover()
        self.cleanup_tags()
        audio.save()

        return True

    def set_flac(self) -> None:
        """Write Vorbis/FLAC comment tags.

        Raises:
            mutagen.MutagenError: If the audio file is not loaded or
                the tags container could not be initialised.
        """
        audio = self._require_m()
        if not isinstance(audio, flac.FLAC):
            return
        self._ensure_tags(audio)
        if audio.tags is None:
            msg = "FLAC tags unavailable after add_tags"
            raise mutagen.MutagenError(msg)
        tags: VCFLACDict = audio.tags

        composer = self.composer or self.composers_detailed
        tags["TITLE"] = self.title
        tags["ALBUM"] = self.album
        tags["ALBUMARTIST"] = self.albumartist
        tags["ARTIST"] = self.artists
        tags["COPYRIGHT"] = self.copy_right
        tags["TRACKNUMBER"] = str(self.tracknumber)
        tags["TRACKTOTAL"] = str(self.totaltrack)
        tags["DISCNUMBER"] = str(self.discnumber)
        tags["DISCTOTAL"] = str(self.totaldisc)
        tags["DATE"] = self.date
        tags["COMPOSER"] = composer
        tags["ISRC"] = self.isrc
        tags["LYRICS"] = self.lyrics
        tags["UNSYNCEDLYRICS"] = self.lyrics_unsynced
        tags["URL"] = self.url_share
        tags[self.target_upc["FLAC"]] = self.upc

        # Enriched optional fields
        if self.genre:
            tags["GENRE"] = self.genre
        if self.label:
            # LABEL is widely recognised in Vorbis; PUBLISHER fallback.
            tags["LABEL"] = self.label
        if self.bpm is not None:
            tags["BPM"] = str(self.bpm)
        if self.producers:
            tags["PRODUCER"] = self.producers
        if self.lyricists:
            tags["LYRICIST"] = self.lyricists

        if self.replay_gain_write:
            tags["REPLAYGAIN_ALBUM_GAIN"] = str(self.album_replay_gain)
            tags["REPLAYGAIN_ALBUM_PEAK"] = str(self.album_peak_amplitude)
            tags["REPLAYGAIN_TRACK_GAIN"] = str(self.track_replay_gain)
            tags["REPLAYGAIN_TRACK_PEAK"] = str(self.track_peak_amplitude)

    def set_mp3(self) -> None:
        """Write ID3 tags.

        Frame overview: https://exiftool.org/TagNames/ID3.html
        Mapping overview: https://docs.mp3tag.de/mapping/

        Raises:
            mutagen.MutagenError: If the audio file is not loaded or
                the tags container could not be initialised.
        """
        audio = self._require_m()
        if not isinstance(audio, mp3.MP3):
            return
        self._ensure_tags(audio)
        if audio.tags is None:
            msg = "MP3 ID3 tags unavailable after add_tags"
            raise mutagen.MutagenError(msg)
        tags: ID3 = audio.tags

        composer = self.composer or self.composers_detailed
        tags.add(TIT2(encoding=3, text=self.title))
        tags.add(TALB(encoding=3, text=self.album))
        tags.add(TOPE(encoding=3, text=self.albumartist))
        tags.add(TPE1(encoding=3, text=self.artists))
        tags.add(TCOP(encoding=3, text=self.copy_right))
        tags.add(TRCK(encoding=3, text=str(self.tracknumber)))
        tags.add(TRCK(encoding=3, text=str(self.discnumber)))
        tags.add(TDRC(encoding=3, text=self.date))
        tags.add(TCOM(encoding=3, text=composer))
        tags.add(TSRC(encoding=3, text=self.isrc))
        tags.add(SYLT(encoding=3, desc="text", text=self.lyrics))
        tags.add(USLT(encoding=3, desc="text", text=self.lyrics_unsynced))
        tags.add(WOAS(url=self.url_share))
        tags.add(
            TXXX(
                encoding=3,
                desc=self.target_upc["MP3"],
                text=self.upc,
            )
        )

        # Enriched optional fields
        if self.genre:
            tags.add(TCON(encoding=3, text=self.genre))
        if self.label:
            tags.add(TPUB(encoding=3, text=self.label))
        if self.bpm is not None:
            tags.add(TBPM(encoding=3, text=str(self.bpm)))
        if self.producers:
            tags.add(TXXX(encoding=3, desc="PRODUCER", text=self.producers))
        if self.lyricists:
            tags.add(
                TXXX(
                    encoding=3,
                    desc="LYRICIST",
                    text=self.lyricists,
                )
            )

        if self.replay_gain_write:
            tags.add(
                TXXX(
                    encoding=3,
                    desc="REPLAYGAIN_ALBUM_GAIN",
                    text=str(self.album_replay_gain),
                )
            )
            tags.add(
                TXXX(
                    encoding=3,
                    desc="REPLAYGAIN_ALBUM_PEAK",
                    text=str(self.album_peak_amplitude),
                )
            )
            tags.add(
                TXXX(
                    encoding=3,
                    desc="REPLAYGAIN_TRACK_GAIN",
                    text=str(self.track_replay_gain),
                )
            )
            tags.add(
                TXXX(
                    encoding=3,
                    desc="REPLAYGAIN_TRACK_PEAK",
                    text=str(self.track_peak_amplitude),
                )
            )

    def set_mp4(self) -> None:
        """Write iTunes/MP4 atom tags.

        Raises:
            mutagen.MutagenError: If the audio file is not loaded or
                the tags container could not be initialised.
        """
        audio = self._require_m()
        if not isinstance(audio, mp4.MP4):
            return
        self._ensure_tags(audio)
        if audio.tags is None:
            msg = "MP4 tags unavailable after add_tags"
            raise mutagen.MutagenError(msg)
        tags: MP4Tags = audio.tags

        composer = self.composer or self.composers_detailed
        tags["\xa9nam"] = self.title
        tags["\xa9alb"] = self.album
        tags["aART"] = self.albumartist
        tags["\xa9ART"] = self.artists
        tags["cprt"] = self.copy_right
        tags["trkn"] = [(self.tracknumber, self.totaltrack)]
        tags["disk"] = [(self.discnumber, self.totaldisc)]
        if self.genre:
            tags["\xa9gen"] = self.genre
        tags["\xa9day"] = self.date
        tags["\xa9wrt"] = composer
        tags["\xa9lyr"] = self.lyrics
        upc_key = f"----:com.apple.iTunes:{self.target_upc['MP4']}"
        tags["----:com.apple.iTunes:UNSYNCEDLYRICS"] = [
            MP4FreeForm(self.lyrics_unsynced.encode("utf-8"))
        ]
        tags["isrc"] = self.isrc
        tags["\xa9url"] = self.url_share
        tags[upc_key] = [MP4FreeForm(self.upc.encode("utf-8"))]
        tags["rtng"] = [1 if self.explicit else 0]

        # Custom iTunes free-form tags for label / credits
        if self.label:
            tags["----:com.apple.iTunes:LABEL"] = [
                MP4FreeForm(self.label.encode("utf-8"))
            ]
        if self.producers:
            tags["----:com.apple.iTunes:PRODUCER"] = [
                MP4FreeForm(self.producers.encode("utf-8"))
            ]
        if self.lyricists:
            tags["----:com.apple.iTunes:LYRICIST"] = [
                MP4FreeForm(self.lyricists.encode("utf-8"))
            ]
        if self.bpm is not None:
            # Standard MP4 tempo atom
            tags["tmpo"] = [int(self.bpm)]

        if self.replay_gain_write:
            tags["----:com.apple.iTunes:REPLAYGAIN_ALBUM_GAIN"] = [
                MP4FreeForm(str(self.album_replay_gain).encode("utf-8"))
            ]
            tags["----:com.apple.iTunes:REPLAYGAIN_ALBUM_PEAK"] = [
                MP4FreeForm(str(self.album_peak_amplitude).encode("utf-8"))
            ]
            tags["----:com.apple.iTunes:REPLAYGAIN_TRACK_GAIN"] = [
                MP4FreeForm(str(self.track_replay_gain).encode("utf-8"))
            ]
            tags["----:com.apple.iTunes:REPLAYGAIN_TRACK_PEAK"] = [
                MP4FreeForm(str(self.track_peak_amplitude).encode("utf-8"))
            ]

    def _cleanup_flac(self, audio: flac.FLAC) -> None:
        """Remove empty Vorbis comment values.

        Args:
            audio: The FLAC mutagen instance.
        """
        if audio.tags is None:
            return
        tags: VCFLACDict = audio.tags
        empty_keys = [key for key, value in tags if value in ("", [""])]
        for key in empty_keys:
            del tags[key]

    def _cleanup_mp3(self, audio: mp3.MP3) -> None:
        """Remove empty ID3 frames.

        Args:
            audio: The MP3 mutagen instance.
        """
        if audio.tags is None:
            return
        tags: ID3 = audio.tags
        dead_keys: list[str] = []
        for key in list(tags.keys()):
            frame = tags.get(key)
            if (
                frame is not None
                and hasattr(frame, "text")
                and frame.text in ([""], [])
            ):
                dead_keys.append(key)
        for key in dead_keys:
            tags.delall(key)

    def _cleanup_mp4(self, audio: mp4.MP4) -> None:
        """Remove empty MP4 atom values.

        Args:
            audio: The MP4 mutagen instance.
        """
        if audio.tags is None:
            return
        tags: MP4Tags = audio.tags
        empty_keys = [
            key for key, value in tags.items() if value in ("", [""])
        ]
        for key in empty_keys:
            del tags[key]

    def cleanup_tags(self) -> None:
        """Remove empty tag values left by optional fields."""
        audio = self._require_m()
        match audio:
            case flac.FLAC():
                self._cleanup_flac(audio)
            case mp3.MP3():
                self._cleanup_mp3(audio)
            case _:
                self._cleanup_mp4(audio)
