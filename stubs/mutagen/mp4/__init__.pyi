"""Stub for mutagen.mp4."""

from mutagen import FileType, MutagenError

MP4TagsValueType = (
    str
    | list[str]
    | list[tuple[int, int]]
    | list[int]
    | list[MP4FreeForm]
    | list[MP4Cover]
    | list[bytes]
    | bytes
)

class MP4FreeForm(bytes):
    def __new__(
        cls, data: bytes, dataformat: int = ..., version: int = ...
    ) -> "MP4FreeForm": ...

class MP4Cover(bytes):
    FORMAT_JPEG: int
    FORMAT_PNG: int
    imageformat: int
    def __new__(
        cls, data: bytes, imageformat: int = ...
    ) -> "MP4Cover": ...

class MP4Tags:
    def __setitem__(self, key: str, value: MP4TagsValueType) -> None: ...
    def __getitem__(self, key: str) -> MP4TagsValueType: ...
    def __delitem__(self, key: str) -> None: ...
    def __contains__(self, key: object) -> bool: ...
    def keys(self) -> list[str]: ...
    def items(self) -> list[tuple[str, MP4TagsValueType]]: ...
    def __init__(self) -> None: ...

class MP4(FileType):
    tags: MP4Tags | None
    MP4Tags: type[MP4Tags]
    error: type[MutagenError]
    def add_tags(self) -> None: ...
    def save(
        self,
        filename: str | None = ...,
        padding: object = ...,
    ) -> None: ...
