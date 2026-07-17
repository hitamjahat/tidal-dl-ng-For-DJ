"""Stub for mutagen.mp3."""

from mutagen.id3 import ID3, ID3FileType

class MP3(ID3FileType):
    tags: ID3 | None
    ID3: type[ID3]
    def add_tags(self, ID3: type[ID3] | None = ...) -> None: ...
    def save(
        self,
        filename: str | None = ...,
        v1: int = ...,
        v2_version: int = ...,
        v23_sep: str | None = ...,
        padding: object = ...,
    ) -> None: ...
