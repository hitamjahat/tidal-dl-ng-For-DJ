"""Stub for mutagen.id3."""

from enum import IntEnum

class PictureType(IntEnum):
    COVER_FRONT: int

class ID3:
    def add(self, frame: object) -> None: ...
    def get(self, key: str, default: object = ...) -> _Frame | None: ...
    def keys(self) -> list[str]: ...
    def delall(self, key: str) -> None: ...
    def __setitem__(self, key: str, value: object) -> None: ...
    def __getitem__(self, key: str) -> object: ...
    def __contains__(self, key: object) -> bool: ...

class ID3FileType:
    tags: ID3 | None
    def add_tags(self, ID3: type[ID3] | None = ...) -> None: ...

class _Frame:
    encoding: int
    text: list[str]

class APIC(_Frame):
    data: bytes
    def __init__(self, encoding: int = ..., data: bytes = ..., **kwargs: object) -> None: ...  # noqa: E501

class SYLT(_Frame):
    desc: str
    def __init__(self, encoding: int = ..., desc: str = ..., text: str = ..., **kwargs: object) -> None: ...  # noqa: E501

class TALB(_Frame):
    def __init__(self, encoding: int = ..., text: str = ..., **kwargs: object) -> None: ...  # noqa: E501

class TBPM(_Frame):
    def __init__(self, encoding: int = ..., text: str = ..., **kwargs: object) -> None: ...  # noqa: E501

class TCOM(_Frame):
    def __init__(self, encoding: int = ..., text: str = ..., **kwargs: object) -> None: ...  # noqa: E501

class TCON(_Frame):
    def __init__(self, encoding: int = ..., text: str = ..., **kwargs: object) -> None: ...  # noqa: E501

class TCOP(_Frame):
    def __init__(self, encoding: int = ..., text: str = ..., **kwargs: object) -> None: ...  # noqa: E501

class TDRC(_Frame):
    def __init__(self, encoding: int = ..., text: str = ..., **kwargs: object) -> None: ...  # noqa: E501

class TIT2(_Frame):
    def __init__(self, encoding: int = ..., text: str = ..., **kwargs: object) -> None: ...  # noqa: E501

class TOPE(_Frame):
    def __init__(self, encoding: int = ..., text: str = ..., **kwargs: object) -> None: ...  # noqa: E501

class TPE1(_Frame):
    def __init__(self, encoding: int = ..., text: str = ..., **kwargs: object) -> None: ...  # noqa: E501

class TPUB(_Frame):
    def __init__(self, encoding: int = ..., text: str = ..., **kwargs: object) -> None: ...  # noqa: E501

class TRCK(_Frame):
    def __init__(self, encoding: int = ..., text: str = ..., **kwargs: object) -> None: ...  # noqa: E501

class TSRC(_Frame):
    def __init__(self, encoding: int = ..., text: str = ..., **kwargs: object) -> None: ...  # noqa: E501

class TXXX(_Frame):
    desc: str
    def __init__(self, encoding: int = ..., desc: str = ..., text: str = ..., **kwargs: object) -> None: ...  # noqa: E501

class USLT(_Frame):
    desc: str
    def __init__(self, encoding: int = ..., desc: str = ..., text: str = ..., **kwargs: object) -> None: ...  # noqa: E501

class WOAS:
    url: str
    def __init__(self, url: str = ..., **kwargs: object) -> None: ...
