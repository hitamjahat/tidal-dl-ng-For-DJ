# Python File Documentation

## Introduction

This document serves as the central reference for the Python source file and its role within the project. It provides a comprehensive overview of the file's architecture, responsibilities, and interactions with the rest of the codebase.

The documentation is intended to help developers quickly understand what the file does, why it exists, how it integrates with other modules, and how it should be maintained. By consolidating technical information into a single location, it reduces onboarding time, simplifies debugging, and promotes consistent development practices.

For each Python file, this document includes:

- **File Path** — The exact location of the file within the project structure.
- **Purpose** — The primary reason the file exists.
- **Description** — A high-level explanation of its responsibilities and behavior.
- **Functions and Classes** — Detailed descriptions of public and important internal components.
- **Dependencies** — External libraries and internal modules that the file imports or relies upon.
- **Relationships** — How the file communicates and interacts with other files and modules.
- **Inputs and Outputs** — Expected data received, processed, and returned.
- **Goals** — The architectural and business objectives the file is designed to achieve.
- **Notes** — Important implementation details, limitations, assumptions, or future improvements.

This documentation should be kept synchronized with the source code to ensure it remains an accurate representation of the project's architecture.

---

## File: stubs/coloredlogs/**init**.pyi

**File Path:** `stubs/coloredlogs/__init__.pyi`

**Purpose:** Type stub for the third-party `coloredlogs` package, enabling static type checking (Pyright/Mypy) of `coloredlogs` imports used in `tidal_dl_ng/logger.py`.

**Description:** Declares the public interface of `coloredlogs` — the `DEFAULT_LEVEL_STYLES` constant and the `ColoredFormatter` class — so the project's strict type checkers can resolve types without the actual package's type information.

**Functions and Classes:**

- `DEFAULT_LEVEL_STYLES` (`dict[str, dict[str, str | bool]]`): Default color/style mapping for each log level.
- `ColoredFormatter.__init__(fmt: str, level_styles: Mapping[str, Mapping[str, str | bool]]) -> None`: Constructs a formatter that applies ANSI colors to log records based on level styles.

**Dependencies:** `logging`, `collections.abc.Mapping`

**Relationships:** Consumed by `tidal_dl_ng/logger.py` (`_build_formatter` uses `coloredlogs.DEFAULT_LEVEL_STYLES` and `coloredlogs.ColoredFormatter`).

**Goals:** Provide minimal but accurate type information for the `coloredlogs` package to satisfy strict type checking without runtime overhead.

**Notes:** This is a stub file (`.pyi`), not executable source. It mirrors the subset of `coloredlogs`'s public API actually used by the project.

---

## File: stubs/ffmpeg/**init**.pyi

**File Path:** `stubs/ffmpeg/__init__.pyi`

**Purpose:** Type stub for the third-party `ffmpeg-python` package, enabling static type checking (Pyright/Mypy/Pylint) of `ffmpeg` imports used in `tidal_dl_ng/download.py`.

**Description:** Declares the public interface of the `ffmpeg` package — the `FFmpeg` class — so the project's strict type checkers can resolve types without the actual package shipping its own type information. The class exposes a fluent (chainable) builder API for constructing FFmpeg command lines, plus a Node.js-style event-emitter surface (`on`, `once`, `emit`, `listeners`, `add_listener`, `remove_listener`, `remove_all_listeners`, `listens_to`).

**Functions and Classes:**

- `FFmpeg.__init__(executable: str | None = None) -> None`: Constructs an FFmpeg wrapper, optionally pointing at a custom binary path.
- `FFmpeg.option(*options: str) -> FFmpeg`: Appends raw CLI options; returns `self` for chaining.
- `FFmpeg.input(video_url: str, **kwargs: object) -> FFmpeg`: Declares an input source with optional ffmpeg kwargs; chainable.
- `FFmpeg.output(video_url: str, **kwargs: object) -> FFmpeg`: Declares an output target with optional ffmpeg kwargs; chainable.
- `FFmpeg.execute(encoding: str = "utf-8", callbacks: Callable[..., object] | None = None) -> str`: Runs the assembled command and returns its stdout.
- `FFmpeg.terminate() -> None`: Stops a running FFmpeg process.
- `FFmpeg.emit(event_name: str, *args: object) -> None`: Emits an event to registered listeners.
- `FFmpeg.on(event_name: str, callback: Callable[..., object]) -> FFmpeg`: Registers a persistent listener; chainable.
- `FFmpeg.once(event_name: str, callback: Callable[..., object]) -> FFmpeg`: Registers a one-shot listener; chainable.
- `FFmpeg.listeners(event_name: str) -> list[Callable[..., object]]`: Returns the listeners registered for an event.
- `FFmpeg.add_listener(event_name: str, callback: Callable[..., object]) -> None`: Alias-style listener registration.
- `FFmpeg.remove_listener(event_name: str, callback: Callable[..., object]) -> None`: Removes a specific listener.
- `FFmpeg.remove_all_listeners(event_name: str | None = None) -> None`: Removes all listeners, optionally scoped to one event.
- `FFmpeg.listens_to(event_name: str) -> Callable[[Callable[..., _T]], Callable[..., _T]]`: Decorator that attaches a callback to an event.
- `FFmpeg.arguments() -> list[str]`: Returns the assembled CLI argument list.

**Dependencies:** `collections.abc.Callable`, `typing.TypeVar`

**Relationships:** Consumed by `tidal_dl_ng/download.py` (`from ffmpeg import FFmpeg`), where it is used in `_convert_video_to_mp4` (option/input/output/execute) and `_extract_flac` (option/input/output/execute). The `path_binary_ffmpeg` setting in `tidal_dl_ng/model/cfg.py` feeds the `executable` constructor argument.

**Inputs and Outputs:**

- **Inputs:** Optional executable path (str); input/output URLs (str); CLI options (str); keyword arguments (object) forwarded to ffmpeg; event names (str); callbacks (`Callable[..., object]`).
- **Outputs:** Chainable `FFmpeg` instances from builder methods; the executed command's stdout (`str`) from `execute()`; the assembled argument list (`list[str]`) from `arguments()`; listener lists from `listeners()`.

**Goals:** Provide minimal but accurate type information for the `ffmpeg-python` package to satisfy strict type checking (`disallow_any_*`) without runtime overhead, while mirroring the subset of the public API used by the project (and the closely related event-emitter surface for completeness).

**Notes:** This is a stub file (`.pyi`), not executable source. It mirrors the public API of `ffmpeg-python`'s `FFmpeg` class. The project explicitly forbids `Any` (per `AGENTS.md`), so `object` is used as the most general parameter/return type and `Callable[..., object]` for callbacks.

---

## File: stubs/mpegdash/__init__.pyi

**File Path:** `stubs/mpegdash/__init__.pyi`

**Purpose:** Package-level type stub for the third-party `mpegdash` package, enabling static type checkers (Pyright/Mypy/Pylint) to resolve `mpegdash` as an importable package and reach its submodules (notably `mpegdash.utils`).

**Description:** A minimal stub containing only a module docstring. It exists so that `from mpegdash import utils` (and similar package-level imports) resolve under strict type checking, since the `mpegdash` package does not ship its own type information. The actual API surface is declared in the sibling `stubs/mpegdash/utils.pyi`.

**Functions and Classes:** None — this stub declares no functions, classes, or constants; it only marks the package as importable for type checkers.

**Dependencies:** None.

**Relationships:** Companion to `stubs/mpegdash/utils.pyi` (which declares the `parse_attr_value`, `parse_child_nodes`, `parse_node_value`, and `write_child_node` functions). Together they let `tidal_dl_ng/helper/mpegdash_patch.py`'s `from mpegdash import utils as mpegdash_utils` import type-check cleanly.

**Inputs and Outputs:** None — the stub has no runtime behavior.

**Goals:** Provide the minimal package marker required for the `mpegdash` submodules' type stubs to be discovered by strict type checkers, without runtime overhead.

**Notes:** This is a stub file (`.pyi`), not executable source. It intentionally contains only a docstring; per PEP 561, an `__init__.pyi` is what makes a directory a typed package from the type checker's perspective. The substantive type declarations live in `utils.pyi`.

---

## File: stubs/mpegdash/utils.pyi

**File Path:** `stubs/mpegdash/utils.pyi`

**Purpose:** Type stub for the `mpegdash.utils` module, enabling static type checking (Pyright/Mypy/Pylint) of `mpegdash` imports used in `tidal_dl_ng/helper/mpegdash_patch.py`.

**Description:** Declares the public interface of `mpegdash.utils` — four XML helper functions used to parse and write nodes/attributes in MPEG-DASH MPD manifests — so the project's strict type checkers can resolve types without the `mpegdash` package shipping its own type information. The functions are generic over the target value type (`_T`), allowing callers to request `int`, `str`, or other conversions from XML text.

**Functions and Classes:**

- `parse_attr_value[T](xmlnode: Element, attr_name: str, value_type: type[T] | list[type[T]]) -> T | None`: Reads an attribute from an XML node and converts it to the requested type (or list of types); returns `None` if absent.
- `parse_child_nodes[T](xmlnode: Element, tag_name: str, node_type: type[T] | str) -> list[T] | None`: Collects child elements matching `tag_name` and converts each to the requested type; returns `None` if none found.
- `parse_node_value[T](xmlnode: Element, value_type: type[T]) -> T | None`: Converts an XML node's text value to the requested type; returns `None` if absent.
- `write_child_node(xmlnode: Element, tag_name: str, node: object | list[object] | None) -> None`: Writes a child node with the given tag and value(s) under the parent element.

**Dependencies:** `xml.dom.minidom.Element`, `typing.TypeVar` (modernized to PEP 695 type parameters)

**Relationships:** Consumed by `tidal_dl_ng/helper/mpegdash_patch.py`, which imports `from mpegdash import utils as mpegdash_utils` and monkey-patches `mpegdash_utils.parse_attr_value` with `patched_parse_attr_value` to gracefully handle TIDAL's non-integer manifest attributes (e.g., `"main"` in `AdaptationSet` `id`/`group`). The patch is applied at startup from `tidal_dl_ng/__init__.py` via `apply_mpegdash_patch()`.

**Inputs and Outputs:**

- **Inputs:** XML nodes (`Element`); attribute/tag names (`str`); target types (`type[T]` or `list[type[T]]`); node values to write (`object | list[object] | None`).
- **Outputs:** Converted attribute/node values (`T | None`); lists of converted child values (`list[T] | None`); `None` from `write_child_node` (side-effect only).

**Goals:** Provide minimal but accurate type information for the `mpegdash.utils` module to satisfy strict type checking (`disallow_any_*`) without runtime overhead, while mirroring the public API surface used (directly or via monkey-patching) by the project.

**Notes:** This is a stub file (`.pyi`), not executable source. The project explicitly forbids `Any` (per `AGENTS.md`); the patched replacement in `mpegdash_patch.py` still returns `Any` at runtime, but the stub itself uses generic `T` so callers that go through the stub are type-safe.

---

## File: stubs/mutagen/flac/**init**.pyi

**File Path:** `stubs/mutagen/flac/__init__.pyi`

**Purpose:** Type stub for the `mutagen.flac` module, enabling static type checking (Pyright/Mypy/Pylint) of `mutagen.flac` imports used in `tidal_dl_ng/metadata.py` and `tests/test_tidal_extras.py`.

**Description:** Declares the public interface of `mutagen.flac` — the `FLAC` file class, the `VCFLACDict` Vorbis-comment container, the `Picture` embedded-image block, and two error classes — so the project's strict type checkers can resolve types without the `mutagen` package shipping its own type information. `FLAC` extends `mutagen.FileType` and `VCFLACDict` extends `mutagen._vorbis.VCommentDict`, so the stub mirrors the real inheritance hierarchy declared in the sibling `mutagen/__init__.pyi` and `mutagen/_vorbis/__init__.pyi` stubs.

**Functions and Classes:**

- `FLACNoHeaderError(MutagenError)`: Raised when a FLAC file has no header block.
- `FLACVorbisError(MutagenError)`: Raised on Vorbis-comment errors specific to FLAC.
- `Picture`: Embedded-picture block with `type: int`, `data: bytes`, `mime: str`, `code: int` attributes plus `load`/`write` methods and a no-arg constructor.
- `VCFLACDict(VCommentDict)`: FLAC-specific Vorbis comment dict; adds `code: int`, `load(fileobj: bytes, errors: str = "strict", framing: bool = True) -> None`, and `write(framing: bool = True) -> bytes`.
- `FLAC(FileType)`: FLAC file wrapper; narrows `tags` (declared as a covariant `@property` returning `VCFLACDict | None`) and adds `metadata_blocks: list[object]`, `add_tags()`, `clear_pictures()`, `add_picture(picture: Picture)`, and `save(filething: str | Path | None = None, deleteid3: bool = False, padding: object = None, **kwargs: object) -> None`.

**Dependencies:** `pathlib.Path`, `mutagen.FileType`, `mutagen.MutagenError`, `mutagen._vorbis.VCommentDict`

**Relationships:** Consumed by `tidal_dl_ng/metadata.py` (`from mutagen import flac`), which pattern-matches on `flac.FLAC()`, constructs `flac.Picture()`, reads/writes `audio.tags` (typed as `VCFLACDict`), and calls `add_picture`, `clear_pictures`, `add_tags`, and `save`. Also used in `tests/test_tidal_extras.py` (`mutagen.flac.FLAC(path)`). Inherits from `FileType` (`stubs/mutagen/__init__.pyi`) and `VCommentDict` (`stubs/mutagen/_vorbis/__init__.pyi`).

**Inputs and Outputs:**

- **Inputs:** File paths (`str | Path | None`); picture blocks (`Picture`); raw Vorbis data (`bytes`); framing/error flags (`str`, `bool`); padding (`object`).
- **Outputs:** Serialized Vorbis bytes (`bytes`) from `VCFLACDict.write`; mutated in-place `tags`/`metadata_blocks` on `FLAC`; `None` from `save`/`add_tags`/`add_picture`/`clear_pictures` (side-effect only).

**Goals:** Provide minimal but accurate type information for the `mutagen.flac` module to satisfy strict type checking (`disallow_any_*`) without runtime overhead, while mirroring the real inheritance hierarchy and the public API surface used by the project.

**Notes:** This is a stub file (`.pyi`), not executable source. The project explicitly forbids `Any` (per `AGENTS.md`), so `object` is used for `padding`/`metadata_blocks` and for the `fileobj`/`**kwargs` parameters. The `tags` attribute is declared as a read-only `@property` (covariant) on both `FileType` and `FLAC` so the narrowed `VCFLACDict | None` return type satisfies strict override checking without invariance errors; this is safe because the project only reads `tags` (it mutates tags via `add_tags()` and item assignment, never by reassigning the `tags` attribute itself). The `save` signature mirrors the real mutagen `FLAC.save(filething, deleteid3, padding)` and retains `**kwargs` for base-class compatibility.

---

## File: stubs/mutagen/_vorbis/**init**.pyi

**File Path:** `stubs/mutagen/_vorbis/__init__.pyi`

**Purpose:** Type stub for the `mutagen._vorbis` module, enabling static type checking (Pyright/Mypy/Pylint) of the `VCommentDict` base class that `mutagen.flac.VCFLACDict` extends.

**Description:** Declares the public interface of `mutagen._vorbis.VCommentDict` — the Vorbis comment container that `VCommentDict` implements as a `list`-backed mapping (`VCommentDict → VComment → Tags → list → DictMixin → object`). The stub exposes the mapping protocol (`__setitem__`, `__getitem__`, `__delitem__`, `__contains__`, `__iter__`, `keys`) plus `load`/`write` serialization and `get`/`items`/`values`/`as_dict` accessors, so the project's strict type checkers can resolve the inherited members used through `VCFLACDict`.

**Functions and Classes:**

- `VCommentDict`: Vorbis comment dict (list-backed mapping).
  - `__init__(data: object = None, *args: object, **kwargs: object) -> None`: Constructs the dict, optionally seeded from existing comment data.
  - `__setitem__(key: str, value: str | list[str]) -> None`: Sets a comment value (string or list of strings).
  - `__getitem__(key: str) -> list[str]`: Returns the list of values for a key.
  - `__delitem__(key: str) -> None`: Removes all values for a key.
  - `__contains__(key: object) -> bool`: Membership test by key.
  - `__iter__() -> Iterator[tuple[str, str]]`: Iterates over `(key, value)` pairs (flattened).
  - `keys() -> list[str]`: Returns all keys.
  - `get(key: str, default: str | None = None) -> str | None`: Returns the first value for a key or a default.
  - `items() -> list[tuple[str, list[str]]]`: Returns `(key, values)` pairs.
  - `values() -> list[list[str]]`: Returns all value lists.
  - `as_dict() -> dict[str, list[str]]`: Snapshot of the comments as a plain dict.
  - `load(fileobj: object, errors: str = "replace", framing: bool = True) -> None`: Parses Vorbis comments from a file object.
  - `write(framing: bool = True) -> bytes`: Serializes the comments to bytes.

**Dependencies:** `collections.abc.Iterator`

**Relationships:** Base class for `VCFLACDict` declared in `stubs/mutagen/flac/__init__.pyi` (`class VCFLACDict(VCommentDict)`). The mapping methods (`__setitem__`, `__delitem__`, `__iter__`) are exercised by `tidal_dl_ng/metadata.py` through `VCFLACDict` instances obtained from `flac.FLAC.tags` (e.g., `tags["TITLE"] = ...`, `del tags[key]`, `for key, value in tags`).

**Inputs and Outputs:**

- **Inputs:** Comment keys (`str`); comment values (`str | list[str]`); membership keys (`object`); file objects for `load` (`object`); error/framing flags (`str`, `bool`).
- **Outputs:** Value lists (`list[str]`) from `__getitem__`; `(key, value)` pairs (`Iterator[tuple[str, str]]`) from `__iter__`; key lists (`list[str]`) from `keys`; serialized bytes (`bytes`) from `write`; booleans (`bool`) from `__contains__`; snapshots (`dict[str, list[str]]`) from `as_dict`.

**Goals:** Provide minimal but accurate type information for the `mutagen._vorbis.VCommentDict` base class to satisfy strict type checking (`disallow_any_*`) without runtime overhead, while mirroring the real mapping/serialization API that `VCFLACDict` inherits and the project relies on.

**Notes:** This is a stub file (`.pyi`), not executable source. The real `VCommentDict` is a `list` subclass, so `pop` is index-based (`pop(index=-1)`) rather than key-based; the stub omits `pop` because the project never calls it on tags. The project explicitly forbids `Any` (per `AGENTS.md`), so `object` is used for the `fileobj`/`data`/`*args`/`**kwargs` parameters.

## File: stubs/mutagen/id3/**init**.pyi

**File Path:** `stubs/mutagen/id3/__init__.pyi`

**Purpose:** Type stub for the `mutagen.id3` module, enabling static type checking (Pyright/Mypy/Pylint) of ID3v2 tag reading/writing for MP3 files.

**Description:** Declares the public interface of `mutagen.id3` — the ID3 tag container (`ID3`), the MP3 file-type mixin (`ID3FileType`), the picture-type constants (`PictureType`), and the ID3 frame classes (`APIC`, `SYLT`, `TALB`, `TBPM`, `TCOM`, `TCON`, `TCOP`, `TDRC`, `TIT2`, `TOPE`, `TPE1`, `TPUB`, `TRCK`, `TSRC`, `TXXX`, `USLT`, `WOAS`) used by the project to write MP3 metadata. The stub exposes the `ID3` mapping protocol (`add`, `get`, `keys`, `delall`, `getall`, `setall`, `__setitem__`, `__getitem__`, `__contains__`) plus `save`/`load`/`delete` serialization, so the project's strict type checkers can resolve the frame operations performed in `tidal_dl_ng/metadata.py`.

**Functions and Classes:**

- `PictureType(int)`: Integer constants for ID3 picture types (e.g., `COVER_FRONT`, `COVER_BACK`, `ARTIST`, `BAND`). Used via `id3.PictureType.COVER_FRONT`.
- `ID3`: ID3v2 tag container (mapping of frame keys to frames).
  - `__init__(*args: object, **kwargs: object) -> None`: Constructs an empty or loaded ID3 tag.
  - `add(frame: object) -> None`: Adds a frame to the tag.
  - `get(key: str, default: object = None) -> object | None`: Returns the first frame for a key or a default.
  - `getall(key: str) -> list[object]`: Returns all frames for a key.
  - `setall(key: str, values: list[object]) -> None`: Replaces all frames for a key.
  - `keys() -> list[str]`: Returns all frame keys.
  - `delall(key: str) -> None`: Removes all frames for a key.
  - `__setitem__(key: str, value: object) -> None`: Sets frames for a key.
  - `__getitem__(key: str) -> object`: Returns frames for a key.
  - `__contains__(key: object) -> bool`: Membership test by key.
  - `save(filething: object = None, v1: int = 1, v2_version: int = 4, v23_sep: str = "/", padding: object = None) -> None`: Writes the tag to a file.
  - `load(filething: object, known_frames: object = None, translate: bool = True, v2_version: int = 4, load_v1: bool = True) -> None`: Loads the tag from a file.
  - `delete(filething: object = None, delete_v1: bool = True, delete_v2: bool = True) -> None`: Removes the tag from a file.
- `ID3FileType`: MP3 file-type mixin providing ID3 tag access.
  - `tags` (property): The `ID3` tag container, or `None` if absent.
  - `add_tags(ID3: type[ID3] | None = None) -> None`: Adds an ID3 tag container to the file.
- `_Frame`: Base class for all ID3 frames.
  - `encoding: int`: Text encoding.
  - `text: list[str]`: Text values.
  - `HashKey` (property): Hash key used by `ID3` for frame deduplication.
  - `pprint() -> str`: Pretty-prints the frame for debugging.
- `TextFrame(_Frame)`: Base class for simple text frames (real mutagen hierarchy).
  - `__init__(encoding: int = 3, text: str = "", **kwargs: object) -> None`.
- `UrlFrame(_Frame)`: Base class for URL frames (real mutagen hierarchy).
  - `url: str`: URL value.
  - `__init__(url: str = "", **kwargs: object) -> None`.
- `APIC(_Frame)`: Attached picture frame.
  - `data: bytes`: Picture data.
  - `__init__(encoding: int = 3, data: bytes = b"", **kwargs: object) -> None`.
- `SYLT(_Frame)`: Synchronised lyrics frame.
  - `desc: str`: Description.
  - `__init__(encoding: int = 3, desc: str = "", text: str = "", **kwargs: object) -> None`.
- `TALB`, `TBPM`, `TCOM`, `TCON`, `TCOP`, `TDRC`, `TIT2`, `TOPE`, `TPE1`, `TPUB`, `TRCK`, `TSRC` (`TextFrame`): Text frames for album, BPM, composer, genre, copyright, date, title, original artist, lead artist, publisher, track number, ISRC. Inherit `__init__` from `TextFrame`.
- `TXXX(_Frame)`: User-defined text frame.
  - `desc: str`: Description.
  - `__init__(encoding: int = 3, desc: str = "", text: str = "", **kwargs: object) -> None`.
- `USLT(_Frame)`: Unsynchronised lyrics frame.
  - `desc: str`: Description.
  - `__init__(encoding: int = 3, desc: str = "", text: str = "", **kwargs: object) -> None`.
- `WOAS(UrlFrame)`: URL frame (official audio source webpage). Inherits `url` and `__init__` from `UrlFrame`.

**Dependencies:** None (pure type declarations).

**Relationships:** Used by `tidal_dl_ng/metadata.py` (`from mutagen.id3 import APIC, ID3, SYLT, TALB, TBPM, TCOM, TCON, TCOP, TDRC, TIT2, TOPE, TPE1, TPUB, TRCK, TSRC, TXXX, USLT, WOAS` and `import mutagen.id3 as id3`). The `ID3FileType` is the base class for `stubs/mutagen/mp3/__init__.pyi`'s `MP3` class (`class MP3(ID3FileType)`). Frame instances are created in `metadata.py`'s `set_mp3()` and added via `tags.add(...)`; `id3.PictureType.COVER_FRONT` is used in `_cover()` for FLAC pictures.

**Inputs and Outputs:**

- **Inputs:** Frame keys (`str`); frames (`object`); picture data (`bytes`); text values (`str`); encoding ints (`int`); file objects for `save`/`load`/`delete` (`object`); URL strings (`str`).
- **Outputs:** Frames (`object | None` from `get`; `object` from `__getitem__`; `list[object]` from `getall`); key lists (`list[str]`); booleans (`bool` from `__contains__`).

**Goals:** Provide minimal but accurate type information for the `mutagen.id3` module to satisfy strict type checking (`disallow_any_*`) without runtime overhead, while mirroring the real ID3 tag and frame API that the project relies on for MP3 metadata writing.

**Notes:** This is a stub file (`.pyi`), not executable source. The real `PictureType` is a plain `int` subclass with class attributes (NOT an `IntEnum`); the stub mirrors this to avoid the "zero members" enum error. The real `ID3FileType.add_tags` parameter is named `ID3` (capitalised) — the stub uses `id3_` (lowercase with trailing underscore) to satisfy naming linters while preserving the real API semantics. The stub introduces `TextFrame` and `UrlFrame` intermediate base classes to mirror the real mutagen class hierarchy (`TALB → TextFrame → Frame`, `WOAS → UrlFrame → Frame`), eliminating duplicated `__init__` signatures and satisfying pylint's `R0903` (too-few-public-methods) via inherited members. The `_Frame` base class declares `HashKey` (property) and `pprint` (method) from the real `Frame` API; `HashKey` is added to `good-names` (pylint) and `ignore-names` (ruff `pep8-naming`) in `pyproject.toml` since it is a real mutagen API name that uses CamelCase. The project explicitly forbids `Any` (per `AGENTS.md`), so `object` is used for `filething`/`known_frames`/`padding`/`*args`/`**kwargs` parameters. Frame `__init__` signatures in the real library are all `(self, *args, **kwargs)`; the stub exposes the named keyword arguments the project actually uses (`encoding`, `text`, `desc`, `data`, `url`) with sensible defaults.

## File: stubs/mutagen/mp3/**init**.pyi

**File Path:** `stubs/mutagen/mp3/__init__.pyi`

**Purpose:** Type stub for the `mutagen.mp3` module, enabling static type checking (Pyright/Mypy/Pylint) of MP3 audio file loading, ID3 tag access, and saving.

**Description:** Declares the public interface of `mutagen.mp3.MP3` — the concrete MP3 file-type class that extends `ID3FileType`. The real `MP3` class overrides nothing from `ID3FileType`/`FileType` (it only sets the `ID3` class attribute at runtime), so the stub is minimal: it declares only the three methods the project actually calls on `MP3` instances — `save`, `delete`, and `pprint` — inheriting `tags`, `add_tags`, and `load` from `ID3FileType` (see `stubs/mutagen/id3/__init__.pyi`).

**Functions and Classes:**

- `MP3(ID3FileType)`: Concrete MP3 audio file-type class.
  - `save(filething: object = None, **kwargs: object) -> None`: Writes the file with ID3 tags.
  - `delete(filething: object = None) -> None`: Removes the tag from the file.
  - `pprint() -> str`: Pretty-prints the file info and tags.

**Dependencies:** `mutagen.id3.ID3FileType` (imported from `stubs/mutagen/id3/__init__.pyi`).

**Relationships:** Extends `ID3FileType` from `stubs/mutagen/id3/__init__.pyi`. Used by `tidal_dl_ng/metadata.py` (`from mutagen import flac, id3, mp3, mp4`) — `mp3.MP3` is part of the `_AudioFile` union type, used in `isinstance` checks, `match` statements (`case mp3.MP3()`), and `set_mp3()` / `_cleanup_mp3()` methods for writing ID3 tags to MP3 files.

**Inputs and Outputs:**
- **Inputs:** File paths/objects for `save`/`delete` (`object`); extra save options (`**kwargs: object`).
- **Outputs:** Pretty-printed info (`str` from `pprint`).

**Goals:** Provide minimal but accurate type information for the `mutagen.mp3.MP3` class to satisfy strict type checking (`disallow_any_*`) without runtime overhead, while mirroring the real MP3 file-type API that the project relies on for MP3 metadata writing.

**Notes:** This is a stub file (`.pyi`), not executable source. The real `MP3` class does not override `tags`, `add_tags`, or `load` from `ID3FileType` — those are inherited, so the stub does not redeclare them (redeclaring with different signatures would trigger W0237/W0221). The stub declares only `save`, `delete`, and `pprint` — the three methods the project calls directly on `MP3` instances. The project explicitly forbids `Any` (per `AGENTS.md`), so `object` is used for `filething`/`**kwargs` parameters.

## File: stubs/mutagen/mp4/__init__.pyi

**File Path:** `stubs/mutagen/mp4/__init__.pyi`

**Purpose:** Type stub for the `mutagen.mp4` module, enabling static type checking (Pyright/Mypy/Pylint) of MP4/M4A audio file loading, MP4 atom tag access, and saving.

**Description:** Declares the public interface of `mutagen.mp4.MP4` — the concrete MP4 file-type class that extends `FileType` to provide iTunes/MP4 atom tag access for MPEG-4 audio files. The stub exposes the `tags` property (returning an `MP4Tags` container or `None`), `add_tags` (to attach a tag container), `save` (to write the file with tags), `MP4FreeForm` (for custom iTunes free-form tags), `MP4Cover` (for cover art), and `MP4Tags` (the tag container with mapping protocol), so the project's strict type checkers can resolve the MP4 operations performed in `tidal_dl_ng/metadata.py`.

**Functions and Classes:**

- `MP4FreeForm(bytes)`: Subclass of `bytes` for custom iTunes free-form tags.
  - `__new__(cls, data: bytes, dataformat: int = ..., version: int = ...) -> Self`: Creates a new free-form tag.
- `MP4Cover(bytes)`: Subclass of `bytes` for cover art.
  - `FORMAT_JPEG: int`: JPEG cover art format constant.
  - `FORMAT_PNG: int`: PNG cover art format constant.
  - `imageformat: int`: The image format of this cover.
  - `__new__(cls, data: bytes, imageformat: int = ...) -> Self`: Creates a new cover art object.
- `MP4Tags`: Mapping-like container for MP4 atom tags.
  - `__setitem__(key: str, value: MP4TagsValueType) -> None`: Sets a tag value.
  - `__getitem__(key: str) -> MP4TagsValueType`: Gets a tag value.
  - `__delitem__(key: str) -> None`: Deletes a tag.
  - `__contains__(key: object) -> bool`: Checks if a tag exists.
  - `keys() -> list[str]`: Returns all tag keys.
  - `items() -> list[tuple[str, MP4TagsValueType]]`: Returns all key-value pairs.
  - `__init__() -> None`: Initializes the tag container.
- `MP4(FileType)`: Concrete MP4 audio file-type class.
  - `tags` (property): The `MP4Tags` tag container, or `None` if absent.
  - `error: type[MutagenError]`: The error class for this file type.
  - `add_tags() -> None`: Adds a tag container to the file.
  - `save(filething: str | Path | None = ..., **kwargs: object) -> None`: Writes the file with tags.

**Dependencies:** `mutagen.FileType`, `mutagen.MutagenError` (imported from `stubs/mutagen/__init__.pyi`); `pathlib.Path`, `typing.Self`.

**Relationships:** Extends `FileType` from `stubs/mutagen/__init__.pyi`. Used by `tidal_dl_ng/metadata.py` (`from mutagen import flac, id3, mp3, mp4`) — `mp4.MP4` is part of the `_AudioFile` union type, used in `isinstance` checks, `match` statements (`case mp4.MP4()`), and `set_mp4()` / `_cleanup_mp4()` methods for writing MP4 atom tags to M4A files.

**Inputs and Outputs:**
- **Inputs:** File paths/objects for `save` (`str | Path | None`); extra save options (`**kwargs: object`); tag keys (`str`); tag values (`MP4TagsValueType`); cover art data (`bytes`); free-form tag data (`bytes`).
- **Outputs:** Tag containers (`MP4Tags | None` from `tags`); tag values (`MP4TagsValueType` from `__getitem__`); key lists (`list[str]` from `keys`); key-value pairs (`list[tuple[str, MP4TagsValueType]]` from `items`); booleans (`bool` from `__contains__`).

**Goals:** Provide minimal but accurate type information for the `mutagen.mp4` module to satisfy strict type checking (`disallow_any_*`) without runtime overhead, while mirroring the real MP4 file-type and tag API that the project relies on for M4A metadata writing.

**Notes:** This is a stub file (`.pyi`), not executable source. The `MP4TagsValueType` type alias is defined at the end of the file (after the classes it references) using the PEP 695 `type` keyword. The `__new__` methods of `MP4FreeForm` and `MP4Cover` use `Self` as the return type (per PYI034) since these `bytes` subclasses return `self` at runtime. The `MP4.save` signature matches `FileType.save` (`filething: str | Path | None = ..., **kwargs: object`) to avoid W0221 (variadics removed) and W0237 (parameter renamed) override warnings — the real `MP4.save` is `(self, *args, **kwargs)` which delegates to `FileType.save`. The `MP4Tags: type[MP4Tags]` class attribute is omitted from the stub because it caused a pyright "undefined variable" error (self-referential class attribute). The project explicitly forbids `Any` (per `AGENTS.md`), so `object` is used for `**kwargs` parameters.

---

## File: stubs/tidal_dl_ng/ui/dialog_version.pyi

**File Path:** `stubs/tidal_dl_ng/ui/dialog_version.pyi`

**Purpose:** Type stub for the generated `Ui_DialogVersion` class from the Qt Designer UI file `dialog_version.ui`, enabling static type checking (Pyright/Mypy/Pylint) of the version dialog UI class used in `tidal_dl_ng/gui/updates.py`.

**Description:** Declares the public interface of the auto-generated `Ui_DialogVersion` class — a Qt widget class produced by Qt Designer's `pyuic6` code generator. The class provides `setupUi` and `retranslateUi` methods for constructing the version/update dialog layout, plus typed widget instance attributes for all UI elements (labels, push buttons).

**Functions and Classes:**

- `Ui_DialogVersion`: Qt widget UI class generated from `dialog_version.ui`.
  - `setupUi(dialog: QDialog) -> None`: Sets up the dialog layout — creates and arranges all child widgets within the provided `QDialog` instance.
  - `retranslateUi(dialog: QDialog) -> None`: Updates all UI text strings for the current locale.
  - `l_version: QLabel`: Label showing the currently installed version.
  - `l_error: QLabel`: Label showing error messages.
  - `l_error_details: QLabel`: Label showing detailed error information.
  - `l_h_version: QLabel`: Header label for the installed version.
  - `l_h_version_new: QLabel`: Header label for the new version.
  - `l_version_new: QLabel`: Label showing the available new version.
  - `l_changelog: QLabel`: Label for the changelog section.
  - `l_changelog_details: QLabel`: Label showing changelog details.
  - `l_name_app: QLabel`: Label showing the application name.
  - `l_url_github: QLabel`: Label with a link to the GitHub repository.
  - `pb_download: QPushButton`: Button to download the new version.

**Dependencies:** `PySide6.QtWidgets.QDialog`, `PySide6.QtWidgets.QLabel`, `PySide6.QtWidgets.QPushButton`.

**Relationships:** Consumed by `tidal_dl_ng/gui/updates.py` which instantiates `Ui_DialogVersion()` and calls `setupUi(dialog)` to build the version/update dialog. The dialog is used for checking and displaying application updates.

**Inputs and Outputs:**
- **Inputs:** `QDialog` instance passed to `setupUi` and `retranslateUi`.
- **Outputs:** Mutated `QDialog` with all child widgets laid out; no return values from `setupUi` or `retranslateUi`.

**Goals:** Provide minimal but accurate type information for the auto-generated `Ui_DialogVersion` class to satisfy strict type checking (`disallow_any_*`) without runtime overhead, while mirroring the Qt UI class interface that the project relies on for the version dialog.

**Notes:** This is a stub file (`.pyi`), not executable source. The class name `Ui_DialogVersion` and method names `setupUi`/`retranslateUi` are Qt Designer-generated names that do not follow PEP 8 snake_case conventions — they are added to `good-names` and `ignore-names` in `pyproject.toml`. The stub omits the module docstring and class docstring per PEP 695/PYI021 (no docstrings in `.pyi` files). The real source is generated from `dialog_version.ui` by `pyuic6` and should not be manually edited. The stub removes `pb_check_update` and `pb_close` which do not exist in the real source, and adds `l_h_version`, `l_name_app`, `l_url_github` which were missing.

---

## File: stubs/tidal_dl_ng/config.pyi

**File Path:** `stubs/tidal_dl_ng/config.pyi`

**Purpose:** Type stub for `tidal_dl_ng.config`, providing static type information for the application's configuration management layer — JSON-backed config objects, TIDAL API session management, and application-wide control events.

**Description:** Declares the public interface of the configuration module which handles: (1) JSON serialization/deserialization protocol, (2) base configuration class with save/load/set-option logic shared by settings and token storage, (3) singleton `Settings` class for user-configurable application settings, (4) singleton `Tidal` class managing the TIDAL API session, token persistence, and login flows (PKCE, HiFi API, lossless verification), and (5) `HandlingApp` class holding application-wide control events for abort/run signalling.

**Functions and Classes:**

- `JsonSerializable`: Protocol describing dataclasses-json serialization methods.
  - `to_json(*args: object, **kwargs: object) -> str`: Serialize the instance to a JSON string.
  - `from_json(cls, *args: object, **kwargs: object) -> JsonSerializable`: Deserialize a JSON string into an instance.
- `BaseConfig[T]`: Base class for JSON-backed configuration objects.
  - `data: T`: The underlying config dataclass instance.
  - `file_path: str`: Filesystem path of the JSON config file.
  - `cls_model: type[T]`: The dataclass type used for serialization.
  - `path_base: str`: Base directory for config files.
  - `save(config_to_compare: str | None = None) -> None`: Persist the current config to disk as pretty-printed JSON.
  - `set_option(key: str, value: object) -> None`: Set a single attribute on the underlying config dataclass.
  - `read(path: str) -> bool`: Load config from disk, creating a default if the file is invalid.
- `Settings(BaseConfig[ModelSettings])`: Singleton holding user-configurable application settings.
  - `__init__() -> None`: Initialize settings from the config file path.
- `Tidal(BaseConfig[ModelToken])`: Manages the TIDAL API session, token persistence, and login flows.
  - `session: Session`: The TIDAL API session.
  - `token_from_storage: bool`: Whether the token was loaded from storage.
  - `settings: Settings`: The application settings instance.
  - `is_pkce: bool`: Whether PKCE authentication is used.
  - `__init__(settings: Settings | None = None) -> None`: Initialize TIDAL session and load persisted token if available.
  - `login(fn_print: Callable[[str], None]) -> bool`: Perform the full login flow (token load or interactive PKCE login).
  - `login_token(do_pkce: bool | None = None) -> bool`: Load or create an authentication token.
  - `login_finalize() -> bool`: Finalize the login flow after PKCE authentication.
  - `login_hifi_api(fn_print: Callable[[str], None]) -> bool`: Perform HiFi API login.
  - `finalize_and_enable_hires() -> bool`: Enable Hi-Res streaming after successful login.
  - `verify_lossless_capability() -> bool`: Verify the token can retrieve lossless streams.
  - `logout() -> bool`: Remove the stored token and invalidate the current session.
  - `settings_apply(settings: Settings | None = None) -> bool`: Apply the user's settings to the active TIDAL session.
- `HandlingApp`: Holds application-wide control events for abort/run signalling.
  - `event_abort: threading.Event`: Event signalling abort.
  - `event_run: threading.Event`: Event signalling run.
  - `__init__() -> None`: Initialize control events.

**Dependencies:** `threading`, `collections.abc.Callable`, `tidalapi.session.Session`, `tidal_dl_ng.model.cfg.Settings` (as `ModelSettings`), `tidal_dl_ng.model.cfg.Token` (as `ModelToken`).

**Relationships:** Consumed by `tidal_dl_ng/cli.py`, `tidal_dl_ng/download.py`, `tidal_dl_ng/worker.py`, and `tidal_dl_ng/gui/` modules which instantiate `Settings`, `Tidal`, and `HandlingApp` singletons to manage configuration, API sessions, and application lifecycle.

**Inputs and Outputs:**
- **Inputs:** JSON config files on disk, user settings, TIDAL credentials.
- **Outputs:** Loaded config objects, authenticated TIDAL session, control events.

**Goals:** Provide minimal but accurate type information for the configuration module to satisfy strict type checking (`disallow_any_*`) without runtime overhead, while mirroring the real source interface.

**Notes:** This is a stub file (`.pyi`), not executable source. Uses PEP 695 type parameters (`class BaseConfig[T]:`) per UP046. The `Token` class is not declared in this stub — it lives in `tidal_dl_ng.model.cfg` and is imported as `ModelToken`. The stub omits docstrings per PYI021. The real source uses `metaclass=SingletonMeta` which is omitted in the stub as it's an implementation detail. The `login` method signature requires `fn_print` (no default) per the real source.

---

## File: stubs/tidalapi/album.pyi

**File Path:** `stubs/tidalapi/album.pyi`

**Purpose:** Type stub for the `tidalapi.album` module, providing static type information for the `Album` class — a TIDAL album object containing metadata, tracks, videos, and related methods.

**Description:** Declares the public interface of the `Album` class from the `tidalapi` library. The class represents a TIDAL album with attributes for metadata (id, name, cover, duration, release dates, copyright, UPC, etc.), artist information, audio quality settings, and methods for retrieving tracks, items (tracks + videos), album images, video covers, similar albums, reviews, and audio resolution data.

**Functions and Classes:**

- `Album`: TIDAL album object.
  - **Attributes:** `id`, `name`, `cover`, `video_cover`, `type`, `duration`, `available`, `ad_supported_ready`, `dj_ready`, `allow_streaming`, `premium_streaming_only`, `num_tracks`, `num_videos`, `num_volumes`, `tidal_release_date`, `release_date`, `copyright`, `upc`, `version`, `explicit`, `universal_product_number`, `popularity`, `user_date_added`, `audio_quality`, `audio_modes`, `media_metadata_tags`, `artist`, `artists`, `listen_url`, `share_url`.
  - **Properties:** `year` (derived from `available_release_date`), `available_release_date` (release date or tidal release date).
  - `image(dimensions: int | str = 320, default: str = ...) -> str`: URL to an album image cover.
  - `tracks(limit: int | None = None, offset: int = 0, sparse_album: bool = False) -> list[Track]`: Returns tracks in the album.
  - `items(limit: int = 100, offset: int = 0, sparse_album: bool = False) -> list[Track | Video]`: Gets tracks and videos in the album.
  - `video(dimensions: int | str = 320) -> str`: URL to an mp4 video cover for the album.
  - `page() -> Page`: Retrieve the album page as seen on TIDAL.
  - `similar() -> list[Album]`: Retrieve albums similar to the current one.
  - `review() -> str`: Retrieve the album review.
  - `get_audio_resolution(individual_tracks: bool = False) -> list[list[int]]`: Retrieve the audio resolution for the album track(s).

**Dependencies:** `datetime.datetime`, `tidalapi.artist.Artist`, `tidalapi.media.Track`, `tidalapi.media.Video`, `tidalapi.page.Page`.

**Relationships:** Consumed by `tidal_dl_ng/download.py`, `tidal_dl_ng/metadata.py`, and other modules that interact with TIDAL album data. The `Album` class is instantiated by the `tidalapi` session and returned from API calls.

**Inputs and Outputs:**
- **Inputs:** TIDAL API responses (JSON), session configuration.
- **Outputs:** Album metadata, track/video lists, image URLs, review text, audio resolution data.

**Goals:** Provide accurate type information for the `tidalapi.album.Album` class to satisfy strict type checking (`disallow_any_*`) without runtime overhead, mirroring the real source interface.

**Notes:** This is a stub file (`.pyi`), not executable source. The stub omits docstrings per PYI021. Uses modern Python 3.14 syntax (`list`, `X | None`, PEP 695). The `year` and `available_release_date` are `@property` methods in the real source, not plain attributes. The `DEFAULT_ALBUM_IMG` constant from the real source is not declared in the stub since it's only used as a default parameter value (represented as `...` in stubs).

---

## File: stubs/tidalapi/artist.pyi

**File Path:** `stubs/tidalapi/artist.pyi`

**Purpose:** Type stub for the `tidalapi.artist` module, providing static type information for the `Artist` class (TIDAL artist object) and the `Role` enum (artist role enumeration).

**Description:** Declares the public interface of the `Artist` class from the `tidalapi` library. The class represents a TIDAL artist with metadata attributes (id, name, roles, picture, bio, etc.) and methods for retrieving albums, EP/singles, top tracks, videos, biography, similar artists, radio tracks, radio mix, artist page, and image URLs. The `Role` enum defines the different roles an artist can have (main, featured, contributor, artist).

**Functions and Classes:**

- `Artist`: TIDAL artist object.
  - **Attributes:** `id`, `name`, `roles`, `role`, `picture`, `user_date_added`, `bio`, `listen_url`, `share_url`.
  - `__init__(session: Session, artist_id: str | None) -> None`: Initialize the Artist object with a TIDAL session and artist ID.
  - `get_albums(limit: int | None = None, offset: int = 0) -> list[Album]`: Queries TIDAL for the artist's albums.
  - `get_albums_ep_singles(limit: int | None = None, offset: int = 0) -> list[Album]`: Deprecated; use `get_ep_singles` instead.
  - `get_ep_singles(limit: int | None = None, offset: int = 0) -> list[Album]`: Queries TIDAL for the artist's extended plays and singles.
  - `get_albums_other(limit: int | None = None, offset: int = 0) -> list[Album]`: Deprecated; use `get_other` instead.
  - `get_other(limit: int | None = None, offset: int = 0) -> list[Album]`: Queries TIDAL for albums the artist has appeared on as a featured artist.
  - `get_top_tracks(limit: int | None = None, offset: int = 0) -> list[Track]`: Queries TIDAL for the artist's tracks sorted by popularity.
  - `get_videos(limit: int | None = None, offset: int = 0) -> list[Video]`: Queries TIDAL for the artist's videos.
  - `get_bio() -> str`: Queries TIDAL for the artist's biography.
  - `get_similar() -> list[Artist]`: Queries TIDAL for similar artists.
  - `get_radio(limit: int = 100) -> list[Track]`: Queries TIDAL for the artist radio (tracks similar to this artist).
  - `get_radio_mix() -> Mix`: Queries TIDAL for the artist radio mix.
  - `items() -> list[NoReturn]`: Returns an empty list (exists for symmetry with other model types).
  - `image(dimensions: int = 320) -> str`: Returns a URL to an artist picture.
  - `page() -> Page`: Retrieves the artist page as seen on TIDAL.
- `Role(Enum)`: An Enum with different roles an artist can have.
  - `main = "MAIN"`: Main artist role.
  - `featured = "FEATURED"`: Featured artist role.
  - `contributor = "CONTRIBUTOR"`: Contributor artist role.
  - `artist = "ARTIST"`: Artist role.

**Dependencies:** `datetime.datetime`, `enum.Enum`, `typing.NoReturn`, `tidalapi.album.Album`, `tidalapi.media.Track`, `tidalapi.media.Video`, `tidalapi.mix.Mix`, `tidalapi.page.Page`, `tidalapi.session.Session`.

**Relationships:** Consumed by `tidal_dl_ng/download.py`, `tidal_dl_ng/metadata.py`, and other modules that interact with TIDAL artist data. The `Artist` class is instantiated by the `tidalapi` session and returned from API calls. `Album` and `Artist` have a circular dependency (Album imports Artist, Artist imports Album) which is handled via TYPE_CHECKING in the real source.

**Inputs and Outputs:**
- **Inputs:** TIDAL API responses (JSON), session configuration.
- **Outputs:** Artist metadata, album/track/video lists, biography text, image URLs.

**Goals:** Provide accurate type information for the `tidalapi.artist.Artist` and `Role` classes to satisfy strict type checking (`disallow_any_*`) without runtime overhead, mirroring the real source interface.

**Notes:** This is a stub file (`.pyi`), not executable source. The stub omits docstrings per PYI021. Uses modern Python 3.14 syntax (`list`, `X | None`). The `Role` enum members (`main`, `featured`, `contributor`, `artist`) are added to `good-names-rgxs` and `ignore-names` in `pyproject.toml` since they are TIDAL API enum values that don't follow UPPER_CASE naming conventions. The `Role` enum is defined after `Artist` in the stub to match the real source order. The `__init__` signature uses `str | None` for `artist_id` (matching the real source's `Optional[str]`).

---

## File: stubs/tidalapi/page.pyi

**File Path:** `stubs/tidalapi/page.pyi`

**Purpose:** Type stub for the `tidalapi.page` module, providing static type information for TIDAL page-based content — the `Page` class (iterable page of mixed content categories), `PageCategory`/`PageCategoryV2` base classes, list-style category subclasses (`SimpleList`, `ShortcutList`, `HorizontalList`, `HorizontalListWithContext`, `TrackList`, `FeaturedItems`, `PageLinks`, `ItemList`, `LinkList`), and supporting types (`More`, `PageLink`, `PageItem`, `TextBlock`).

**Description:** Declares the public interface of the `tidalapi.page` module. The `Page` class is iterable and lazily yields content (tracks, albums, artists, playlists, mixes, page items, links, text blocks) from TIDAL's page API. `PageCategory` and `PageCategoryV2` are base classes for different page category types, with `PageCategoryV2` using a registry pattern (`register_subclass` decorator and `_type_map`) to dispatch parsing of different category types (SHORTCUT_LIST, HORIZONTAL_LIST, TRACK_LIST, etc.). The stub also declares type aliases (`TidalItem`, `PageContent`, `PageCategories`, `AllCategories`, `PageCategoriesV2`, `AllCategoriesV2`) for the union types used throughout.

**Functions and Classes:**

- **Type Aliases:** `TidalItem`, `PageContent`, `PageCategories`, `AllCategories`, `PageCategoriesV2`, `AllCategoriesV2` — union types covering all TIDAL media items, page content, and page category types.
- `Page`: Iterable page of mixed content categories with `__init__`, `__iter__`, `__next__`, `next`, `parse`, and `get` methods.
- `More` (dataclass): "Show more" link with `api_path` and `title` attributes and a `parse` classmethod.
- `PageCategory`: Base class for v1 page categories with `category_type`, `title`, `description`, `session`, `request`, `item_types`, `_more` attributes and `parse`/`show_more` methods.
- `PageCategoryV2`: Base class for v2 page categories with registry pattern (`_type_map`, `register_subclass` decorator) and `parse_item`, `_parse_base`, `parse`, `view_all` methods.
- `SimpleList(PageCategoryV2)`: Simple list of TIDAL items with `items` attribute and `parse`/`get_item` methods.
- `ShortcutList(SimpleList)`: Shortcut links list (registered for "SHORTCUT_LIST").
- `HorizontalList(SimpleList)`: Horizontal scrollable row (registered for "HORIZONTAL_LIST").
- `HorizontalListWithContext(HorizontalList)`: Horizontal list with context (registered for "HORIZONTAL_LIST_WITH_CONTEXT").
- `TrackList(PageCategoryV2)`: Track list with `items: list[Track]` (registered for "TRACK_LIST").
- `FeaturedItems(PageCategory)`: Featured items category with `items: list[PageItem] | None`.
- `PageLinks(PageCategory)`: Page links category with `items: list[PageLink] | None`.
- `ItemList(PageCategory)`: Generic items category with `items: list[TidalItem] | None`.
- `PageLink`: Link to another TIDAL page with `title`, `icon`, `image_id`, `api_path` attributes and `__init__`/`get` methods.
- `PageItem`: Single page item with `header`, `short_header`, `short_sub_header`, `image_id`, `type`, `artifact_id`, `text`, `featured` attributes and `__init__`/`get` methods.
- `TextBlock`: Text block with `text`, `icon`, `items` attributes and `__init__`/`parse` methods.
- `LinkList(PageCategory)`: Link list category with `items`, `title`, `description` attributes and `parse` method.

**Dependencies:** `collections.abc.Callable, Iterator, Mapping`, `dataclasses.dataclass`, `tidalapi.album.Album`, `tidalapi.artist.Artist`, `tidalapi.media.Track, Video`, `tidalapi.mix.Mix`, `tidalapi.playlist.Playlist, UserPlaylist`, `tidalapi.request.Requests`, `tidalapi.session.Session`.

**Relationships:** Consumed by `tidal_dl_ng/download.py`, `tidal_dl_ng/metadata.py`, `tidal_dl_ng/gui/` modules, and other code that interacts with TIDAL page-based content. The `Page` class is instantiated by the `tidalapi` session and returned from API calls. `PageCategoryV2` subclasses use the registry pattern (`register_subclass` decorator) to map TIDAL category type strings to Python classes.

**Inputs and Outputs:**
- **Inputs:** TIDAL API JSON responses (as `Mapping[str, object]`), session configuration.
- **Outputs:** Parsed page content (tracks, albums, artists, playlists, mixes, page items, links, text blocks), `Page` objects, `PageCategoryV2` subclass instances.

**Goals:** Provide accurate type information for the `tidalapi.page` module to satisfy strict type checking (`disallow_any_*`) without runtime overhead, mirroring the real source interface.

**Notes:** This is a stub file (`.pyi`), not executable source. The stub omits docstrings per PYI021. Uses modern Python 3.14 syntax (`list`, `X | None`, PEP 695 type aliases, `type[X]` for class objects). The `category_type` attribute name (instead of `type`) is used to avoid shadowing the built-in `type` when used in type annotations like `type[PageCategoryV2]` in `_type_map` and `register_subclass` return type — mypy reports "Variable PageCategoryV2.type is not valid as a type" when the attribute is named `type`. The `ItemHeader` class was removed as it does not exist in the real `tidalapi.page` source and was not referenced anywhere in the codebase. Subclasses that override `__init__` (SimpleList, TrackList, FeaturedItems) do not declare `__init__` in the stub to avoid PYI010 ("Function body must contain only `...`") and W0231 ("super-init-not-called") — the `items` attribute is declared at class level instead, which is sufficient for type checking.
