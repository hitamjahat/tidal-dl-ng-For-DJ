class PictureType(int):
    ARTIST: int
    BAND: int
    BAND_LOGOTYPE: int
    COMPOSER: int
    CONDUCTOR: int
    COVER_BACK: int
    COVER_FRONT: int
    DURING_PERFORMANCE: int
    DURING_RECORDING: int
    FILE_ICON: int
    FISH: int
    ILLUSTRATION: int
    LEAD_ARTIST: int
    LEAFLET_PAGE: int
    LYRICIST: int
    MEDIA: int
    OTHER: int
    OTHER_FILE_ICON: int
    PUBLISHER_LOGOTYPE: int
    RECORDING_LOCATION: int
    SCREEN_CAPTURE: int

class ID3:
    def __init__(self, *args: object, **kwargs: object) -> None: ...
    def add(self, frame: object) -> None: ...
    def get(self, key: str, default: object = None) -> object | None: ...
    def getall(self, key: str) -> list[object]: ...
    def setall(self, key: str, values: list[object]) -> None: ...
    def keys(self) -> list[str]: ...
    def delall(self, key: str) -> None: ...
    def __setitem__(self, key: str, value: object) -> None: ...
    def __getitem__(self, key: str) -> object: ...
    def __contains__(self, key: object) -> bool: ...
    def save(
        self,
        filething: object = None,
        v1: int = 1,
        v2_version: int = 4,
        v23_sep: str = "/",
        padding: object = None,
    ) -> None: ...
    def load(
        self,
        filething: object,
        known_frames: object = None,
        translate: bool = True,
        v2_version: int = 4,
        load_v1: bool = True,
    ) -> None: ...
    def delete(
        self,
        filething: object = None,
        delete_v1: bool = True,
        delete_v2: bool = True,
    ) -> None: ...

class ID3FileType:
    @property
    def tags(self) -> ID3 | None: ...
    def add_tags(self, id3_: type[ID3] | None = None) -> None: ...

class _Frame:
    encoding: int
    text: list[str]

    @property
    def HashKey(self) -> str: ...
    def pprint(self) -> str: ...

class TextFrame(_Frame):
    def __init__(
        self,
        encoding: int = 3,
        text: str = "",
        **kwargs: object,
    ) -> None: ...

class UrlFrame(_Frame):
    url: str

    def __init__(self, url: str = "", **kwargs: object) -> None: ...

class APIC(_Frame):
    data: bytes

    def __init__(
        self,
        encoding: int = 3,
        data: bytes = b"",
        **kwargs: object,
    ) -> None: ...

class SYLT(_Frame):
    desc: str

    def __init__(
        self,
        encoding: int = 3,
        desc: str = "",
        text: str = "",
        **kwargs: object,
    ) -> None: ...

class TALB(TextFrame): ...
class TBPM(TextFrame): ...
class TCOM(TextFrame): ...
class TCON(TextFrame): ...
class TCOP(TextFrame): ...
class TDRC(TextFrame): ...
class TIT2(TextFrame): ...
class TOPE(TextFrame): ...
class TPE1(TextFrame): ...
class TPUB(TextFrame): ...
class TRCK(TextFrame): ...
class TSRC(TextFrame): ...

class TXXX(_Frame):
    desc: str

    def __init__(
        self,
        encoding: int = 3,
        desc: str = "",
        text: str = "",
        **kwargs: object,
    ) -> None: ...

class USLT(_Frame):
    desc: str

    def __init__(
        self,
        encoding: int = 3,
        desc: str = "",
        text: str = "",
        **kwargs: object,
    ) -> None: ...

class WOAS(UrlFrame): ...
