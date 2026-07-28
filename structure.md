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

## File: tidal_dl_ng/gui/activate.py

**File Path:** `tidal_dl_ng/gui/activate.py`

**Purpose:** Bootstrap the graphical TIDAL Downloader application by owning process-level Qt configuration: high-DPI behavior, application metadata, global theming, desktop integration, exception reporting, and graceful shutdown.

**Description:** This module is the GUI entry point invoked by `gui_activate()`. It configures the process-wide `QApplication` (high-DPI rounding policy, application name/version/organization, window icon, dark theme), installs a Windows AppUserModelID for taskbar grouping, replaces the process exception hook to log uncaught GUI exceptions, installs signal handlers for graceful shutdown (SIGINT/SIGTERM) with a Qt timer to keep Python signal dispatch alive during the event loop, validates or recovers an injected TIDAL session, and finally loads the `MainWindow` class and runs the Qt event loop. Screen layout and application logic remain in dedicated GUI modules (`main_window.py` and mixins).

**Functions and Classes:**

- `ORGANIZATION_NAME` (`str`): `"exislow"` — organization name for Qt metadata.
- `ORGANIZATION_DOMAIN` (`str`): `"exislow.tidal.dl-ng"` — organization domain for Qt metadata.
- `SIGNAL_POLL_INTERVAL_MS` (`int`): `250` — interval for the signal-dispatch timer.
- `TOOLTIP_STYLE` (`str`): `"QToolTip { border: 0; }"` — additional QSS for tooltips.
- `ICON_RESOURCES` (`tuple[tuple[str, int], ...]`): Multi-resolution icon filenames and sizes.
- `SESSION_RECOVERY_ERRORS` (`tuple[type[Exception], ...]`): Exceptions caught during TIDAL session recovery.
- `_configure_high_dpi() -> None`: Sets Qt 6 high-DPI scale factor rounding policy to `PassThrough`.
- `_get_application() -> QtWidgets.QApplication`: Returns the process `QApplication`, creating it if necessary; raises `RuntimeError` if a non-GUI `QCoreApplication` already exists.
- `_setup_application_metadata(application: QtWidgets.QApplication) -> None`: Sets application name, display name, version, organization name, and domain on the `QApplication`.
- `_resolve_resource_path(relative_path: str) -> Path`: Resolves a packaged resource path for source or frozen builds by delegating to `tidal_dl_ng.helper.path.resource_path`.
- `_create_application_icon() -> QtGui.QIcon`: Builds a multi-resolution `QIcon` from `ICON_RESOURCES`, logging warnings for missing files.
- `_is_frozen_application() -> bool`: Reports whether the process was built by PyInstaller or Nuitka (checks `sys.frozen` or `__compiled__`).
- `_setup_windows_app_id() -> None`: Sets the Windows AppUserModelID for source builds only (frozen builds provide their own); no-ops on non-Windows or frozen processes.
- `_setup_exception_hook() -> None`: Replaces `sys.excepthook` to log uncaught GUI exceptions at `CRITICAL` level before delegating to the default hook.
- `_setup_signal_handlers(application: QtWidgets.QApplication) -> None`: Installs SIGINT/SIGTERM handlers that request `application.quit()`, and starts a `QTimer` to allow Python signal dispatch during Qt event loops.
- `_ensure_tidal_session(tidal: Tidal | None) -> Tidal | None`: Validates an injected TIDAL session via `check_login()`; falls back to `login_token()` recovery; returns `None` if the session is invalid (triggering interactive login in `MainWindow`).
- `_load_main_window_class() -> type[MainWindow]`: Dynamically imports and returns the `MainWindow` class after bootstrap dependencies are initialized.
- `gui_activate(tidal: Tidal | None = None) -> Never`: The main GUI entry point — configures the application, sets up theming/icons/metadata/signal handlers, creates and shows the `MainWindow`, runs the Qt event loop, and raises `SystemExit` with the exit code.

**Dependencies:** `ctypes`, `importlib`, `logging`, `signal`, `sys`, `pathlib.Path`, `typing.TYPE_CHECKING`, `PySide6.QtCore/QtGui/QtWidgets`, `tidalapi.exceptions.TidalAPIError`, `tidal_dl_ng.__name_display__`, `tidal_dl_ng.__version__`, `tidal_dl_ng.logger.enable_debug_and_warnings`, `tidal_dl_ng.config.Tidal`, `tidal_dl_ng.gui.main_window.MainWindow`, `tidal_dl_ng.helper.path.resource_path`, `qdarktheme` (via `importlib.import_module`).

**Relationships:**

- Exported by `tidal_dl_ng/gui/__init__.py` as `gui_activate`.
- Called by `tidal_dl_ng/cli.py` (when `--gui` flag is passed) and by the `tidal-dl-ng-gui` console script entry point.
- Imports `MainWindow` from `tidal_dl_ng.gui.main_window`, which composes all GUI mixins.
- Receives an optional `Tidal` session from `tidal_dl_ng.config` (injected by the CLI when a token is already loaded).
- Uses `enable_debug_and_warnings` from `tidal_dl_ng.logger` to toggle verbose logging.
- Uses `resource_path` from `tidal_dl_ng.helper.path` to resolve icon resources.
- Uses `__name_display__` and `__version__` from `tidal_dl_ng` (the package root) for application metadata.

**Inputs and Outputs:**

- **Inputs:** Optional `Tidal` session object (from CLI injection); `sys.argv` (for `--debug`/`-d` flags); `sys.platform` (for Windows AppUserModelID); Qt Designer UI resources (icon PNG files).
- **Outputs:** Runs the Qt event loop until exit; raises `SystemExit` with the Qt exit code; logs startup/shutdown messages.

**Goals:**

1. Centralize all process-level Qt bootstrap configuration in one module to keep `main_window.py` focused on screen layout and application logic.
2. Ensure consistent high-DPI, theming, and desktop integration across source and frozen builds.
3. Provide robust session recovery so injected CLI sessions are validated before GUI startup.
4. Ensure graceful shutdown and proper exception logging for all GUI crashes.
5. Keep the module importable without side effects (configuration only runs when `gui_activate()` is called).

**Notes:**

- The `qdarktheme` module is imported via `importlib.import_module` at module level to avoid a hard import-time dependency; this allows the module to be imported even if `qdarktheme` is not yet installed (though `gui_activate()` will fail without it).
- `_resolve_resource_path` uses `importlib.import_module` to access `resource_path` to avoid potential circular imports during early bootstrap; however, since `activate.py` is only loaded at GUI startup (after all other modules are initialized), a direct import from `tidal_dl_ng.helper.path` is safe and preferred for DRY compliance.
- The `_allow_python_signal_dispatch` inner function in `_setup_signal_handlers` is currently a no-op (empty body) — it exists solely so the `QTimer` callback has a callable to connect to; Python's signal handling is triggered implicitly by the timer firing and returning control to the Python interpreter.
- `SESSION_RECOVERY_ERRORS` includes `AttributeError`, `OSError`, `TidalAPIError`, `TypeError`, and `ValueError` — these cover the most common failure modes when validating or recovering a TIDAL session (missing attributes, network errors, API errors, type mismatches, and invalid values).
- Frozen builds (PyInstaller/Nuitka) automatically get verbose debug logging enabled, while source builds require the `--debug`/`-d` flag.
- The module uses `from __future__ import annotations` for PEP 604/585 style annotations on Python 3.14.

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

## File: stubs/mpegdash/**init**.pyi

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

## File: stubs/mutagen/mp4/**init**.pyi

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

## File: tidal_dl_ng/helper/tidal_auth/__init__.py

**File Path:** `tidal_dl_ng/helper/tidal_auth/__init__.py`

**Purpose:** HiFi-API OAuth 2.0 Device Authorization flow for TIDAL.

**Description:** This package implements the upgraded authentication process that uses direct OAuth 2.0 Device Authorization Grant with custom credentials, bypassing `tidalapi`'s `login_pkce()` which has known issues with lossless stream retrieval. It exports the public API for the `tidal_auth` package.

**Functions and Classes:**
- Exports functions from `auth.py`, `api_requests.py`, `token_refresh.py`, `http_client.py`, `proxy.py`, and `token_storage.py`.

**Dependencies:** Internal modules within `tidal_dl_ng.helper.tidal_auth`.

**Relationships:** Used by `tidal_dl_ng/config.py`, `tidal_dl_ng/gui/tidal_session.py`, and `tidal_dl_ng/helper/hifi_api.py`.

**Goals:** Provide a clean, unified public API for TIDAL authentication and proxy management.

---

## File: tidal_dl_ng/helper/tidal_auth/auth.py

**File Path:** `tidal_dl_ng/helper/tidal_auth/auth.py`

**Purpose:** Core OAuth token refresh and verification logic.

**Description:** Handles refreshing access tokens using the OAuth refresh_token grant and verifying tokens via the playbackinfopostpaywall endpoint.

**Functions and Classes:**
- `poll_for_authorization`: Polls the TIDAL token endpoint until authorization is complete.
- `refresh_access_token`: Refreshes an OAuth access token.
- `verify_token`: Verifies a token by requesting playback info for a known track.

**Dependencies:** `httpx`, `tidal_dl_ng.constants`, `tidal_dl_ng.helper.tidal_auth.http_client`, `tidal_dl_ng.helper.tidal_auth.proxy`.

**Relationships:** Used by `token_refresh.py`.

**Goals:** Provide robust token refresh and verification with proxy support and retry logic.

---

## File: tidal_dl_ng/helper/tidal_auth/device_auth.py

**File Path:** `tidal_dl_ng/helper/tidal_auth/device_auth.py`

**Purpose:** OAuth 2.0 Device Authorization flow implementation.

**Description:** Executes the full OAuth 2.0 Device Authorization flow, including requesting a device code, polling for authorization, and saving the resulting token. Uses the shared HTTP client from `http_client.py` for connection pooling, proxy support, and automatic proxy rotation. Delegates `poll_for_authorization` and `verify_token` to `auth.py` to avoid code duplication.

**Functions and Classes:**
- `run_device_authorization_flow`: Executes the async device authorization flow.
- `run_device_authorization_flow_sync`: Synchronous wrapper for the device authorization flow.

**Dependencies:** `asyncio`, `datetime`, `webbrowser`, `tidal_dl_ng.constants`, `tidal_dl_ng.helper.tidal_auth.auth`, `tidal_dl_ng.helper.tidal_auth.http_client`, `tidal_dl_ng.helper.tidal_auth.token_storage`.

**Relationships:** Exported by `__init__.py` and used by CLI/GUI for initial login.

**Goals:** Provide a reliable way to obtain TIDAL tokens using the device authorization grant, leveraging shared HTTP client infrastructure for proxy support and connection reuse.

---

## File: tidal_dl_ng/helper/tidal_auth/api_requests.py

**File Path:** `tidal_dl_ng/helper/tidal_auth/api_requests.py`

**Purpose:** Client credentials grant implementation.

**Description:** Handles obtaining tokens using the client credentials grant for API requests.

**Functions and Classes:**
- `get_token_client_credentials`: Obtains a token using the client credentials grant.
- `get_auth_client_credentials`: Obtains auth client credentials.

**Dependencies:** `httpx`, `tidal_dl_ng.constants`, `tidal_dl_ng.helper.tidal_auth.http_client`.

**Relationships:** Exported by `__init__.py`.

**Goals:** Support client credentials grant for specific API operations.

---

## File: tidal_dl_ng/helper/tidal_auth/token_refresh.py

**File Path:** `tidal_dl_ng/helper/tidal_auth/token_refresh.py`

**Purpose:** High-level token retrieval and refresh logic with per-credential locking.

**Description:** Provides async functions to retrieve a valid TIDAL access token for a given credential, automatically refreshing it if expired. Uses per-credential `asyncio.Lock` to prevent concurrent refresh storms, supports proxy rotation on refresh, and falls back to a single retry when proxies are disabled.

**Functions and Classes:**
- `_refresh_locks` (`dict[str, asyncio.Lock]`): Module-level registry of per-credential locks.
- `_lock_for_cred(cred: TokenEntry) -> asyncio.Lock`: Gets or creates a lock for a specific credential set.
- `_refresh_cred_token(cred: TokenEntry) -> tuple[str, TokenEntry]`: Refreshes a credential's access token via the OAuth refresh grant, with retry logic.
- `get_tidal_token_for_cred(force_refresh: bool = False, cred: TokenEntry | None = None) -> tuple[str, TokenEntry]`: Retrieves an access token for a specific credential, refreshing if needed.
- `get_tidal_token(force_refresh: bool = False) -> tuple[str, TokenEntry]`: Retrieves an access token using the first available credential.

**Dependencies:** `asyncio`, `time`, `httpx`, `tidal_dl_ng.constants`, `tidal_dl_ng.helper.tidal_auth.auth`, `tidal_dl_ng.helper.tidal_auth.http_client`, `tidal_dl_ng.helper.tidal_auth.proxy`, `tidal_dl_ng.helper.tidal_auth.token_storage`.

**Relationships:** Exported by `__init__.py` and used by `api_requests.py`, `hifi_api.py`, and `tidal_dl_ng/config.py` to ensure valid tokens before API calls.

**Goals:** Ensure the application always has a valid TIDAL access token with per-credential concurrency safety.

---

## File: tidal_dl_ng/helper/tidal_auth/http_client.py

**File Path:** `tidal_dl_ng/helper/tidal_auth/http_client.py`

**Purpose:** Shared HTTP client management.

**Description:** Provides a shared `httpx.AsyncClient` with connection pooling, proxy support, and automatic proxy rotation for rate limiting. Delegates proxy loading, testing, and selection to `proxy.py`.

**Functions and Classes:**
- `get_http_client`: Gets or creates the shared HTTP client.
- `update_global_client`: Updates the global HTTP client, optionally with a new proxy.
- `auth_headers`: Builds headers for OAuth device authorization and token requests.
- `api_headers`: Builds headers for authenticated TIDAL API requests.

**Dependencies:** `asyncio`, `httpx`, `tidal_dl_ng.constants`, `tidal_dl_ng.helper.tidal_auth.proxy`.

**Relationships:** Used by all modules in `tidal_auth` that make HTTP requests.

**Goals:** Optimize HTTP connections and handle proxy rotation seamlessly.

---

## File: tidal_dl_ng/helper/tidal_auth/proxy.py

**File Path:** `tidal_dl_ng/helper/tidal_auth/proxy.py`

**Purpose:** Proxy management and testing.

**Description:** Handles loading, testing, and selecting working proxies for HTTP requests to the TIDAL API.

**Functions and Classes:**
- `load_proxies`: Loads proxies from a file.
- `test_proxy`: Tests if a proxy is working.
- `get_working_proxy`: Finds a working proxy from the loaded list.

**Dependencies:** `asyncio`, `os`, `secrets`, `pathlib`, `httpx`.

**Relationships:** Used by `http_client.py` and `token_refresh.py`.

**Goals:** Provide reliable proxy support to bypass rate limits and geo-restrictions.

---

## File: tidal_dl_ng/helper/tidal_auth/token_storage.py

**File Path:** `tidal_dl_ng/helper/tidal_auth/token_storage.py`

**Purpose:** Token persistence and management.

**Description:** Handles loading, saving, finding, and deleting TIDAL OAuth tokens from the local filesystem (`token.json`).

**Functions and Classes:**
- `TokenResponse`: TypedDict for TIDAL API token responses.
- `TokenEntry`: TypedDict for stored token entries.
- `load_tokens`: Loads all tokens from the storage file.
- `save_token_entry`: Saves or updates a token entry.
- `delete_token_entry`: Deletes a token entry.
- `find_token_entry`: Finds a token entry by client ID or user ID.

**Dependencies:** `json`, `os`, `pathlib`, `tidal_dl_ng.constants`.

**Relationships:** Used by `auth.py` and `token_refresh.py`.

**Goals:** Securely and reliably store TIDAL authentication tokens across sessions.

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

---

## File: tidal_dl_ng/gui/context_menus.py

**File Path:** `tidal_dl_ng/gui/context_menus.py`

**Purpose:** Provide context-menu actions for the main TIDAL Downloader window — results tree, download queue, and user lists — while delegating expensive work to the application's worker thread.

**Description:** This module defines the `ContextMenusMixin` class, a GUI mixin composed into `MainWindow` alongside other mixins (`DownloadsMixin`, `PlaylistMembershipMixin`, etc.). It coordinates context-menu display and user-initiated actions (download full album, mark track as downloaded/not-downloaded, copy share URL, remove queue items, download all albums from a playlist/mix, in-app search, and browser search). The mixin only handles menu coordination and GUI-thread scheduling; API clients, queue managers, and history services use explicit typed interfaces so failures are caught before the GUI is launched. Session validation (`_ensure_session_valid`) and album loading with rate limiting (`_load_albums_with_rate_limiting`) are also provided here, sharing the same `SESSION_ERRORS` exception tuple used in `tidal_dl_ng/gui/downloads.py` and `tidal_dl_ng/gui/activate.py`.

**Functions and Classes:**

- `SearchMediaType` (`type[Track | Video | Album | Artist | Playlist | Mix]`): PEP 695 type alias for TIDAL media types used in search.
- `SEARCH_TYPE_MAP` (`dict[str, SearchMediaType]`): Maps lowercase category names to their corresponding TIDAL media type classes.
- `SESSION_ERRORS` (`tuple[type[Exception], ...]`): Exceptions caught during TIDAL session validation and recovery — `AttributeError`, `OSError`, `TidalAPIError`, `TypeError`, `ValueError`. This duplicates the same tuple in `downloads.py` (which additionally includes `RuntimeError`) and `activate.py` (as `SESSION_RECOVERY_ERRORS`).
- `ContextMenusMixin`: Mixin class providing context-menu coordination for the main window.
  - **Class Attributes:** Typed declarations for all GUI widgets and managers the mixin expects from `MainWindow` (`tidal`, `settings`, `s_statusbar_message`, `tr_results`, `tr_queue_download`, `tr_lists_user`, `proxy_tr_results`, `model_tr_results`, `history_service`, `playlist_manager`, `queue_manager`, `search_manager`, `cb_search_type`, `l_search`, `thread_it`, `on_mark_track_as_not_downloaded`, `on_mark_track_as_downloaded`).
  - `_ALBUM_FETCH_MAX_RETRIES` (`int`): Maximum retry attempts when loading albums (default: 2).
  - `_ensure_session_valid() -> bool`: Validates the TIDAL session via `check_login()`; falls back to `login_token()` recovery; emits a status-bar message on failure.
  - `menu_context_tree_results(point: QPoint) -> None`: Shows context menu for a result row (download full album, mark downloaded/not-downloaded, copy share URL).
  - `menu_context_queue_download(point: QPoint) -> None`: Shows removal action for a waiting queue item.
  - `on_queue_download_remove_item(item: QTreeWidgetItem) -> None`: Removes a top-level waiting item from the download queue.
  - `on_copy_url_share(tree_target, point) -> None`: Copies the selected media item's share URL to the clipboard.
  - `_share_url(media: MediaItem) -> str`: Static method returning a validated share URL from a media object.
  - `thread_download_list_media(point: QPoint) -> None`: Schedules media download from a selected list on the worker thread.
  - `thread_download_album_from_track(point: QPoint) -> None`: Schedules loading the full album for a selected track on the worker thread.
  - `on_download_album_from_track(point: QPoint) -> None`: Loads a selected track's album and adds it to the queue (direct call).
  - `_album_id_at(point: QPoint) -> str | None`: Resolves an album ID from a result row.
  - `_download_album_by_id(album_id: str) -> None`: Loads one album and schedules its GUI queue insertion.
  - `_enqueue_item_on_gui_thread(queue_item: QueueDownloadItem) -> None`: Posts a queue insertion to the queue widget's Qt thread via `QTimer.singleShot`.
  - `on_download_all_albums_from_playlist(point: QPoint) -> None`: Fetches every unique album in a playlist or mix and queues them with rate limiting.
  - `_media_list_name(media_list: Playlist | UserPlaylist | Mix) -> str`: Static method returning a display name for a playlist or mix.
  - `_extract_album_ids_from_tracks(media_items: list[object]) -> dict[str, Album]`: Extracts unique album objects from track and video results.
  - `_load_albums_with_rate_limiting(album_ids: dict[str, Album]) -> dict[str, Album]`: Loads albums with configurable batching and retry behavior.
  - `_handle_album_load_error(error: Exception, album_id: str) -> bool`: Handles one album load error and decides whether to continue.
  - `_is_authentication_error(error: Exception) -> bool`: Static method identifying common authentication failures by message content.
  - `_queue_loaded_albums(albums: dict[str, Album]) -> None`: Converts loaded albums to queue items and enqueues them.
  - `on_search_in_app(search_term: str, search_type: str) -> None`: Schedules an in-app search using the selected media category.
  - `on_search_in_browser(search_term: str, search_type: str) -> None`: Opens a TIDAL search URL in the default browser.

**Dependencies:** `time`, `urllib.parse`, `functools.partial`, `typing.TYPE_CHECKING`, `typing.cast`, `PySide6.QtCore`, `PySide6.QtGui`, `PySide6.QtWidgets`, `tidalapi.album.Album`, `tidalapi.artist.Artist`, `tidalapi.exceptions.TidalAPIError`, `tidalapi.media.Track`, `tidalapi.media.Video`, `tidalapi.mix.Mix`, `tidalapi.playlist.Playlist`, `tidalapi.playlist.UserPlaylist`, `tidal_dl_ng.constants.QueueDownloadStatus`, `tidal_dl_ng.helper.tidal` (as `tidal_helper`), `tidal_dl_ng.helper.gui.MediaItem`, `tidal_dl_ng.helper.gui.get_results_media_item`, `tidal_dl_ng.helper.gui.get_user_list_media_item`, `tidal_dl_ng.helper.tidal.name_builder_artist`, `tidal_dl_ng.logger.logger_gui`, `tidal_dl_ng.model.gui_data.QueueDownloadItem`, `tidal_dl_ng.model.gui_data.StatusbarMessage`.

**Relationships:**

- Composed into `MainWindow` via `tidal_dl_ng/gui/main_window.py` (line 93: `ContextMenusMixin` in the class bases).
- Shares `SESSION_ERRORS` with `tidal_dl_ng/gui/downloads.py` (which defines a slightly different tuple including `RuntimeError`) and `tidal_dl_ng/gui/activate.py` (as `SESSION_RECOVERY_ERRORS`).
- Uses `get_results_media_item` and `get_user_list_media_item` from `tidal_dl_ng.helper.gui` to resolve media items from tree views.
- Uses `items_results_all` from `tidal_dl_ng.helper.tidal` to fetch all tracks from a playlist or mix.
- Uses `name_builder_artist` from `tidal_dl_ng.helper.tidal` to build artist display names.
- Delegates download queue management to `GuiQueueManager` (via `queue_manager.media_to_queue_download_model` and `queue_manager.queue_download_media`).
- Delegates playlist download to `GuiPlaylistManager` (via `playlist_manager.on_download_list_media`).
- Delegates search to `GuiSearchManager` (via `search_manager.search_populate_results`).
- Uses `HistoryService` (via `history_service.is_downloaded`) to check download status.
- Uses `StatusbarMessage` from `tidal_dl_ng.model.gui_data` to emit status-bar messages.

**Inputs and Outputs:**

- **Inputs:** `QtCore.QPoint` (context menu position), `QtWidgets.QTreeWidgetItem` (queue item), `str` (search term, search type, album ID), `dict[str, Album]` (loaded albums), `list[object]` (media items from TIDAL), `Exception` (album load error).
- **Outputs:** Context menus (shown synchronously), status-bar messages (emitted via `s_statusbar_message`), queue items (enqueued via `QTimer.singleShot`), browser URLs (opened via `QDesktopServices.openUrl`).

**Goals:**

1. Centralize all context-menu coordination logic in a single mixin to keep `MainWindow` focused on screen layout and application state.
2. Ensure expensive operations (album loading, playlist fetching) are delegated to the worker thread via `thread_it` or `QTimer.singleShot`.
3. Provide robust session validation and recovery before API calls.
4. Implement rate-limited album loading with retry logic for bulk playlist operations.
5. Keep the mixin importable without side effects (no module-level code execution).

**Notes:**

- `SESSION_ERRORS` is duplicated across `context_menus.py`, `downloads.py`, and `activate.py` (as `SESSION_RECOVERY_ERRORS`). The `downloads.py` version includes `RuntimeError` which the other two omit — this is a potential inconsistency that should be resolved by centralizing the tuple in a shared location (e.g., `tidal_dl_ng/constants.py`).
- The `_ensure_session_valid` method in `context_menus.py` differs slightly from `_ensure_tidal_session` in `downloads.py` — the former uses `self.tidal` (instance attribute) while the latter takes `tidal` as a parameter. Both share the same logic pattern.
- The `_is_authentication_error` method uses string matching on error messages to detect auth failures — this is a heuristic that could be replaced with proper exception type checking if the TIDAL API provides specific exception types for authentication errors.
- `on_search_in_browser` constructs TIDAL search URLs using `urllib.parse.quote` for safe URL encoding.
- The mixin uses `functools.partial` extensively to bind method arguments for Qt signal/slot connections.
- `on_search_in_app` uses `SEARCH_TYPE_MAP` to map category names to media types, with a fallback to the current combo box selection.
- The `_enqueue_item_on_gui_thread` method uses `QTimer.singleShot(0, ...)` to post queue insertions to the Qt event loop, ensuring thread safety.
- `_download_album_by_id` and `on_download_album_from_track` share the `_album_id_at` helper, demonstrating good DRY practice within the mixin.

---

## File: tidal_dl_ng/gui/downloads.py

**File Path:** `tidal_dl_ng/gui/downloads.py`

**Purpose:** Provide download orchestration and queue integration for the main TIDAL Downloader window — converting selected result rows into queue entries and translating GUI download requests into downloader request models.

**Description:** This module defines the `DownloadsMixin` class, a GUI mixin composed into `MainWindow` alongside other mixins (`ContextMenusMixin`, `PlaylistMembershipMixin`, etc.). It owns queue state and widget updates, providing worker-safe service methods that translate GUI download requests into downloader request models. The mixin handles session validation and recovery (`_ensure_tidal_session`), source info resolution (`_resolve_source_info`), result-to-queue conversion (`on_download_results`), download execution (`download`), and result aggregation (`_aggregate_download_results`). It uses `TypeGuard` functions (`_is_downloadable`, `_is_queueable`) for type-safe filtering of TIDAL media objects, and delegates actual download work to the `Download` service via `ItemRequest` models.

**Functions and Classes:**

- `DownloadableMedia` (`type`): PEP 695 type alias for media accepted by the downloader — `Track | Video | Album | Playlist | UserPlaylist | Mix`.
- `QueueableMedia` (`type`): PEP 695 type alias for media that can be queued — `DownloadableMedia | Artist`.
- `SESSION_ERRORS` (`tuple[type[Exception], ...]`): Exceptions caught during TIDAL session validation and recovery — `TidalAPIError`, `AttributeError`, `OSError`, `RuntimeError`, `TypeError`, `ValueError`.
- `DOWNLOAD_ERRORS` (`tuple[type[Exception], ...]`): Alias for `SESSION_ERRORS`, used during download execution.
- `_is_downloadable(media: object) -> TypeGuard[DownloadableMedia]`: Type guard checking if an object is accepted by the downloader.
- `_is_queueable(media: object) -> TypeGuard[QueueableMedia]`: Type guard checking if an object can be added to the GUI queue.
- `DownloadsMixin`: Mixin class providing result-to-queue and download services to `MainWindow`.
  - **Class Attributes:** Typed declarations for all GUI widgets and managers the mixin expects from `MainWindow` (`tr_results`, `proxy_tr_results`, `model_tr_results`, `queue_manager`, `tidal`, `settings`, `dl`, and signal instances for queue/download lifecycle).
  - `_ensure_tidal_session(tidal: Tidal) -> bool` (static): Validates the TIDAL session via `check_login()`; falls back to `login_token()` recovery.
  - `_resolve_source_info(media: DownloadableMedia) -> tuple[str, str | None, str | None]` (static): Builds history provenance for a media object.
  - `on_download_results() -> None`: Adds every selected results row to the download queue.
  - `_report_queued_results(queued_count: int) -> None`: Reports how many selected rows entered the queue.
  - `queue_download_media(queue_item: QueueDownloadItem) -> None`: Adds a prepared item through the central queue manager.
  - `watcher_queue_download() -> None`: Starts the queue manager's compatibility watcher entry point.
  - `on_queue_download_item_downloading(item: QTreeWidgetItem) -> None`: Marks a queue item as downloading on the GUI thread.
  - `on_queue_download_item_finished(item: QTreeWidgetItem) -> None`: Marks a queue item as finished on the GUI thread.
  - `on_queue_download_item_failed(item: QTreeWidgetItem) -> None`: Marks a queue item as failed on the GUI thread.
  - `on_queue_download_item_skipped(item: QTreeWidgetItem) -> None`: Marks a queue item as skipped on the GUI thread.
  - `queue_download_item_status(item: QTreeWidgetItem, status: str) -> None`: Sets a queue item's status through the queue manager.
  - `on_queue_download(media: QueueableMedia, quality_audio: Quality | None, quality_video: QualityVideo | None) -> QueueDownloadStatus`: Downloads queued media and returns its aggregate status.
  - `_aggregate_download_results(results: list[QueueDownloadStatus]) -> QueueDownloadStatus` (static): Combines item results into one queue status.
  - `download(media: DownloadableMedia, downloader: Download, delay_track: bool, quality_audio: Quality | None, quality_video: QualityVideo | None) -> QueueDownloadStatus`: Downloads one item or collection through the request-object API.
  - `_report_download_failure(reason: str) -> None`: Publishes a contextual download failure to the status bar.

**Dependencies:** `typing.TYPE_CHECKING`, `typing.TypeGuard`, `PySide6.QtCore`, `PySide6.QtGui`, `PySide6.QtWidgets`, `tidalapi.album.Album`, `tidalapi.artist.Artist`, `tidalapi.exceptions.TidalAPIError`, `tidalapi.media.Quality`, `tidalapi.media.Track`, `tidalapi.media.Video`, `tidalapi.mix.Mix`, `tidalapi.playlist.Playlist`, `tidalapi.playlist.UserPlaylist`, `tidal_dl_ng.config.HandlingApp`, `tidal_dl_ng.config.Settings`, `tidal_dl_ng.config.Tidal`, `tidal_dl_ng.constants.QualityVideo`, `tidal_dl_ng.constants.QueueDownloadStatus`, `tidal_dl_ng.download.Download`, `tidal_dl_ng.helper.gui.get_results_media_item`, `tidal_dl_ng.helper.gui.HumanProxyModel`, `tidal_dl_ng.helper.path.get_format_template`, `tidal_dl_ng.helper.tidal.items_results_all`, `tidal_dl_ng.logger.logger_gui`, `tidal_dl_ng.model.downloader.ItemRequest`, `tidal_dl_ng.model.gui_data.QueueDownloadItem`, `tidal_dl_ng.model.gui_data.StatusbarMessage`, `tidal_dl_ng.gui.queue.GuiQueueManager`.

**Relationships:**

- Composed into `MainWindow` via `tidal_dl_ng/gui/main_window.py` (line 21: imports `DownloadsMixin`).
- Shares `SESSION_ERRORS` with `tidal_dl_ng/gui/context_menus.py` (which omits `RuntimeError`) and `tidal_dl_ng/gui/activate.py` (as `SESSION_RECOVERY_ERRORS`, which also omits `RuntimeError`).
- Uses `get_results_media_item` from `tidal_dl_ng.helper.gui` to resolve media items from tree views.
- Uses `items_results_all` from `tidal_dl_ng.helper.tidal` to fetch all tracks from an artist.
- Uses `get_format_template` from `tidal_dl_ng.helper.path` to resolve file template configuration.
- Uses `ItemRequest` from `tidal_dl_ng.model.downloader` to construct download request models.
- Uses `HandlingApp` from `tidal_dl_ng.config` for abort coordination.
- Delegates download queue management to `GuiQueueManager` (via `queue_manager.media_to_queue_download_model`, `queue_manager.queue_download_media`, etc.).
- Delegates actual download work to `Download` service (via `downloader.item()` and `downloader.items()`).
- Uses `StatusbarMessage` from `tidal_dl_ng.model.gui_data` to emit status-bar messages.
- Uses `QueueDownloadStatus` from `tidal_dl_ng.constants` for download result enumeration.

**Inputs and Outputs:**

- **Inputs:** `QtCore.QModelIndex` (selected result rows), `QueueDownloadItem` (prepared queue entry), `QueueableMedia` (media or artist queued for download), `DownloadableMedia` (item or collection to download), `Quality | None` (audio quality), `QualityVideo | None` (video quality), `bool` (track delay flag), `Download` (configured downloader service).
- **Outputs:** `QueueDownloadStatus` (Finished, Skipped, or Failed), `StatusbarMessage` (emitted via `s_statusbar_message`), `None` (queue operations and widget updates).

**Goals:**

1. Centralize all download orchestration and queue integration logic in a single mixin to keep `MainWindow` focused on screen layout and application state.
2. Provide type-safe filtering of TIDAL media objects using `TypeGuard` functions for downloadability and queueability.
3. Ensure session validation and recovery before API calls, with graceful fallback to interactive login.
4. Convert selected result rows into queue entries with proper error handling and user feedback.
5. Translate GUI download requests into downloader request models (`ItemRequest`) with source provenance tracking.
6. Aggregate individual download results into a single queue status for the caller.
7. Keep the mixin importable without side effects (no module-level code execution).

**Notes:**

- `SESSION_ERRORS` is duplicated across `context_menus.py`, `downloads.py`, and `activate.py` (as `SESSION_RECOVERY_ERRORS`). The `downloads.py` version includes `RuntimeError` which the other two omit — this is a potential inconsistency that should be resolved by centralizing the tuple in a shared location (e.g., `tidal_dl_ng/constants.py`).
- The `_ensure_tidal_session` method in `downloads.py` differs slightly from `_ensure_session_valid` in `context_menus.py` — the former takes `tidal` as a parameter while the latter uses `self.tidal` (instance attribute). Both share the same logic pattern.
- `DOWNLOAD_ERRORS` is an alias for `SESSION_ERRORS`, used in the `download` method's exception handler to catch the same set of errors during download execution.
- The `_is_downloadable` and `_is_queueable` functions use `TypeGuard` for type narrowing, enabling the type checker to infer the correct type after the guard check.
- The `download` method uses `isinstance(media, Track | Video)` to distinguish single-item downloads (via `downloader.item()`) from collection downloads (via `downloader.items()`).
- The `_resolve_source_info` method handles all `DownloadableMedia` types, extracting source type, ID, and name for history provenance.
- The `_aggregate_download_results` method prioritizes `Failed` over `Finished` over `Skipped` when combining results.
- The `on_download_results` method reschedules itself on the GUI thread if called from a worker thread, using `QTimer.singleShot`.

---

## File: tidal_dl_ng/gui/history.py

**File Path:** `tidal_dl_ng/gui/history.py`

**Purpose:** Coordinate download-history actions for the main application window — connecting history services to dialogs, status messages, and the results model.

**Description:** This module defines the `HistoryMixin` class, a GUI mixin composed into `MainWindow` alongside other mixins (`DownloadsMixin`, `ContextMenusMixin`, etc.). It bridges the persistent history service (`tidal_dl_ng.history.HistoryService`) with the GUI layer, providing methods for viewing download history, toggling duplicate-download prevention, marking tracks as downloaded/not-downloaded, opening preferences, and saving settings. The mixin uses a `Protocol` (`_HistorySignalOwner`) to structurally type the Qt signals supplied by the concrete main window, and delegates concrete implementations of `apply_settings` and `_init_dl` to the host class. Persistent history work remains in `tidal_dl_ng.history`, while dialog construction remains in dedicated dialog modules.

**Functions and Classes:**

- `DOWNLOADED_MARKER` (`str`): Unicode check mark used to mark downloaded tracks in the results model (`\N{WHITE HEAVY CHECK MARK}`).
- `STATUS_TIMEOUT_SHORT_MS` (`int`): Short status message timeout (2,500ms).
- `STATUS_TIMEOUT_ERROR_MS` (`int`): Error status message timeout (3,000ms).
- `HISTORY_WRITE_ERRORS` (`tuple[type[Exception], ...]`): Exceptions caught during history write operations — `OSError`, `TypeError`, `ValueError`.
- `_HistorySignalOwner` (`Protocol`): Structural protocol describing Qt signals supplied by the concrete main window (`s_settings_save`, `s_statusbar_message`).
- `HistoryMixin`: Mixin class coordinating history operations supplied by the main window.
  - **Class Attributes:** Typed declarations for all GUI widgets and services the mixin expects from `MainWindow` (`DOWNLOADED_COLUMN`, `history_service`, `proxy_tr_results`, `model_tr_results`, `settings`).
  - `_track_source_info(track: Track) -> tuple[str, str | None, str | None]` (static): Resolves the most useful source metadata for a track.
  - `on_view_history() -> None`: Opens the modal download-history dialog.
  - `on_toggle_duplicate_prevention(enabled: bool) -> None`: Persists the duplicate-download prevention preference.
  - `on_mark_track_as_downloaded(track: Track, index: QModelIndex) -> None`: Adds a track to history and updates its results-model marker.
  - `on_mark_track_as_not_downloaded(track_id: str, index: QModelIndex) -> None`: Removes a track from history and clears its model marker.
  - `_update_downloaded_column(index: QModelIndex, *, is_downloaded: bool) -> None`: Updates the downloaded marker for a results-model row.
  - `on_preferences() -> None`: Opens the modal application-preferences dialog.
  - `on_settings_save() -> None`: Persists settings, reapplies them, and rebuilds download services.
  - `apply_settings(settings: Settings) -> None`: Applies settings through the concrete main-window implementation.
  - `_init_dl() -> None`: Rebuilds download services in the concrete main window.
  - `_show_status(message: str, timeout: int) -> None`: Emits a transient main-window status message.
  - `_signal_owner() -> _HistorySignalOwner`: Returns a structural view of main-window history signals.
  - `_dialog_parent() -> QWidget | None`: Returns this mixin's concrete Qt widget for dialog ownership.

**Dependencies:** `typing.TYPE_CHECKING`, `typing.cast`, `PySide6.QtCore`, `PySide6.QtGui`, `PySide6.QtWidgets`, `tidal_dl_ng.dialog.DialogPreferences`, `tidal_dl_ng.dialog_history.DialogHistory`, `tidal_dl_ng.logger.logger_gui`, `tidal_dl_ng.model.gui_data.StatusbarMessage`, `tidalapi.media.Track` (TYPE_CHECKING), `tidal_dl_ng.config.Settings` (TYPE_CHECKING), `tidal_dl_ng.helper.gui.HumanProxyModel` (TYPE_CHECKING), `tidal_dl_ng.history.HistoryService` (TYPE_CHECKING).

**Relationships:**

- Composed into `MainWindow` via `tidal_dl_ng/gui/main_window.py` (line 22: imports `HistoryMixin`).
- Uses `HistoryService` from `tidal_dl_ng.history` for persistent download history operations.
- Uses `DialogHistory` from `tidal_dl_ng.dialog_history` to display the download history dialog.
- Uses `DialogPreferences` from `tidal_dl_ng.dialog` to display the application preferences dialog.
- Uses `StatusbarMessage` from `tidal_dl_ng.model.gui_data` to emit status-bar messages.
- Uses `HumanProxyModel` from `tidal_dl_ng.helper.gui` for proxy-model index mapping.
- Uses `DOWNLOADED_MARKER` constant in tests (`tests/test_gui_history.py`).
- The `_HistorySignalOwner` Protocol provides structural typing for Qt signals, avoiding hard coupling to `MainWindow`.
- `HISTORY_WRITE_ERRORS` is similar to but distinct from `SESSION_ERRORS` in `downloads.py`/`context_menus.py` and `COVER_URL_ERRORS` in `covers.py` — it catches errors specific to history write operations.

**Inputs and Outputs:**

- **Inputs:** `Track` (TIDAL track object), `QModelIndex` (proxy-model index for track row), `str` (track ID, status message), `bool` (duplicate prevention enabled, downloaded state), `int` (status timeout in milliseconds), `Settings` (application settings).
- **Outputs:** `StatusbarMessage` (emitted via `s_statusbar_message`), `None` (dialog operations, model updates, settings persistence).

**Goals:**

1. Centralize all download-history GUI coordination in a single mixin to keep `MainWindow` focused on screen layout and application state.
2. Bridge the persistent history service with the GUI layer using structural typing (`Protocol`) for Qt signal access.
3. Provide user feedback through status-bar messages for all history operations (success and failure).
4. Update the results model to reflect downloaded/not-downloaded state with visual markers.
5. Keep the mixin importable without side effects (no module-level code execution).
6. Delegate concrete settings application and download service initialization to the host `MainWindow`.

**Notes:**

- `HISTORY_WRITE_ERRORS` (`OSError`, `TypeError`, `ValueError`) is similar to but distinct from `SESSION_ERRORS` in `downloads.py`/`context_menus.py` and `COVER_URL_ERRORS` in `covers.py` — it catches errors specific to history write operations (file I/O, type mismatches, invalid values).
- The `_HistorySignalOwner` Protocol uses `@property` with `raise NotImplementedError` to provide type information without runtime implementation — the concrete `MainWindow` supplies the actual signal instances.
- The `_signal_owner` method uses `cast("_HistorySignalOwner", self)` to provide structural typing, since the mixin is composed into `MainWindow` which provides the required signals.
- The `_track_source_info` method prefers album metadata for normal search results, falling back to track-level metadata when album info is unavailable.
- The `_update_downloaded_column` method maps proxy-model indices to source indices and updates the `DOWNLOADED_COLUMN` item text and alignment.
- The `on_mark_track_as_not_downloaded` method checks if a track was actually in history before updating the model (avoiding unnecessary UI updates).
- The `apply_settings` and `_init_dl` methods raise `NotImplementedError` — they are intended to be overridden by the concrete `MainWindow` class.
- The `_dialog_parent` method checks `isinstance(self, QtWidgets.QWidget)` to handle both real `MainWindow` instances and test doubles.

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

---

## File: tidal_dl_ng/gui/covers.py

**File Path:** `tidal_dl_ng/gui/covers.py`

**Purpose:** Coordinate asynchronous cover image loading, caching, and display for the TIDAL Downloader GUI — downloading cover bytes on worker threads and confining `QPixmap` creation and widget updates to the Qt GUI thread.

**Description:** This module defines the `CoverManager` class, a GUI component composed into `MainWindow` (alongside `ContextMenusMixin`, `DownloadsMixin`, etc.). It manages the full lifecycle of cover image display: extracting cover URLs from TIDAL media objects, downloading image bytes with retry/backoff/redirect handling on `QThreadPool` workers, caching decoded pixmaps in a thread-safe LRU cache (`CoverPixmapCache`), and posting GUI-thread callbacks for pixmap creation and widget updates. The manager ensures the newest cover request always wins (preventing stale downloads from overwriting more recent selections), preloads covers for playlists in bounded batches, and coordinates spinner visibility for user feedback. All `QPixmap` operations are confined to the GUI thread because pixmaps are GUI resources rather than worker-safe image containers.

**Functions and Classes:**

- `DEFAULT_COVER_RESOURCE` (`str`): Path to the packaged fallback cover image.
- `MAX_PRELOAD_COVERS` (`int`): Maximum number of playlist covers to preload (default: 50).
- `COVER_DOWNLOAD_MAX_ATTEMPTS` (`int`): Maximum retry attempts for cover downloads (default: 3).
- `COVER_DOWNLOAD_BACKOFF_SEC` (`float`): Base backoff seconds between retries (default: 0.5).
- `COVER_DOWNLOAD_MAX_REDIRECTS` (`int`): Maximum HTTP redirects to follow (default: 3).
- `MAX_COVER_BYTES` (`int`): Maximum cover response size in bytes (default: 20 MB).
- `HTTP_SUCCESS_MIN` (`int`): Minimum HTTP success status code (200).
- `HTTP_SUCCESS_MAX_EXCLUSIVE` (`int`): Exclusive upper bound for HTTP success (300).
- `TRANSIENT_HTTP_STATUS_CODES` (`frozenset[int]`): HTTP status codes eligible for retry (408, 425, 429, 500, 502, 503, 504).
- `COVER_URL_ERRORS` (`tuple[type[Exception], ...]`): Exceptions caught when extracting cover URLs (`AttributeError`, `IndexError`, `TypeError`, `ValueError`).
- `CoverManager`: Class coordinating non-blocking cover downloads and GUI display updates.
  - `__init__(parent_window, threadpool, info_tab_widget) -> None`: Initializes cover state, worker dependencies, and spinner signals.
  - `_get_signal(parent_window, name) -> SignalInstance`: Static method returning a required Qt signal from the parent window.
  - `_coerce_cover_bytes(data_cover) -> bytes`: Static method normalizing downloaded cover payload to immutable bytes.
  - `_pixmap_from_bytes(data_cover) -> QPixmap`: Static method creating a pixmap from cover data on the GUI thread.
  - `load_cover(media, use_cache_check=True) -> None`: Loads and displays a media cover without blocking the GUI.
  - `_load_cover_async(cover_url, spinner_started) -> None`: Downloads one cover in a worker and posts its result to the GUI.
  - `_download_cover_bytes(cover_url) -> bytes`: Static method downloading cover bytes with timeout, retry, and response cleanup.
  - `_request_cover_bytes(cover_url) -> tuple[int, bytes, str | None]`: Static method performing one validated HTTP cover request.
  - `_handle_cover_bytes(cover_url, data_cover, spinner_started) -> None`: Decodes, caches, and conditionally displays downloaded cover bytes.
  - `_get_cover_url(media) -> str | None`: Static method extracting and validating a cover URL from a TIDAL media object.
  - `_normalize_url(value) -> str | None`: Static method returning a stripped URL from an arbitrary image-method result.
  - `_display_cover(pixmap, url) -> None`: Displays a valid pixmap and synchronizes current-cover state.
  - `_display_default_cover() -> None`: Displays the packaged fallback cover and resets URL state.
  - `preload_covers_for_playlist(items) -> None`: Preloads a bounded set of playlist covers in one worker.
  - `_cache_preloaded_cover(cover_url, data_cover) -> None`: Decodes and caches one preloaded cover on the GUI thread.
  - `_queue_cover_fetch(media) -> None`: Queues a thread-safe foreground cover request.
  - `_fetch_cover_pixmap(media, use_cache_check) -> QPixmap | None`: Returns a cached pixmap or queues a non-blocking cover fetch.
  - `_start_spinner() -> bool`: Starts the cover spinner when its target widget is available.
  - `_post_to_gui(callback) -> None`: Schedules a callback on the info controller's Qt thread.
  - `_is_gui_thread() -> bool`: Checks whether the caller is running on the info tab's Qt thread.
  - `_reserve_url(cover_url) -> bool`: Reserves a URL to avoid duplicate foreground downloads.
  - `_release_url(cover_url) -> None`: Releases a completed foreground URL reservation.

**Dependencies:** `time`, `functools.partial`, `http.client.HTTPException`, `itertools.islice`, `pathlib.Path`, `threading.Lock`, `typing.TYPE_CHECKING`, `typing.cast`, `urllib.parse.urljoin`, `urllib.parse.urlsplit`, `requests`, `PySide6.QtCore`, `PySide6.QtGui`, `tidalapi.album.Album`, `tidal_dl_ng.cache.CoverPixmapCache`, `tidal_dl_ng.constants.REQUESTS_TIMEOUT_SEC`, `tidal_dl_ng.helper.path.resource_path`, `tidal_dl_ng.logger.logger_gui`, `tidal_dl_ng.worker.Worker`.

**Relationships:**

- Composed into `MainWindow` via `tidal_dl_ng/gui/main_window.py` (line 115: `cover_manager: CoverManager`, line 235: `self.cover_manager = CoverManager(...)`).
- Referenced by `tidal_dl_ng/gui/signals.py` (line 94: `cover_manager: CoverManager` in `MainWindowSignals`).
- Referenced by `tidal_dl_ng/gui/track_extras.py` (line 41: `cover_manager: CoverManager`).
- Referenced by `tidal_dl_ng/gui/trees_results.py` (line 65: `cover_manager: "CoverManager"`).
- Uses `CoverPixmapCache` from `tidal_dl_ng.cache` for thread-safe LRU pixmap caching.
- Uses `Worker` from `tidal_dl_ng.worker` for thread pool task execution.
- Uses `resource_path` from `tidal_dl_ng.helper.path` to resolve the default cover resource path.
- Uses `REQUESTS_TIMEOUT_SEC` from `tidal_dl_ng.constants` for HTTP request timeouts.
- Uses `logger_gui` from `tidal_dl_ng.logger` for logging.
- Uses `Album` from `tidalapi.album` to type-check media objects with album covers.

**Inputs and Outputs:**

- **Inputs:** `object` (TIDAL media objects with `album` or `image` attributes), `QtCore.QThreadPool` (for worker execution), `InfoTabWidget` (for display updates), `str` (cover URLs), `bytes` (downloaded image data), `Iterable[object]` (playlist items for preloading).
- **Outputs:** `QtGui.QPixmap` (displayed covers, cached or returned), `QtCore.SignalInstance` (spinner start/stop signals), `None` (async operations post callbacks to the GUI thread).

**Goals:**

1. Centralize all cover image loading, caching, and display logic in a single manager to keep `MainWindow` focused on screen layout and application state.
2. Ensure `QPixmap` creation and widget updates are confined to the Qt GUI thread, while network downloads run on worker threads.
3. Prevent stale cover downloads from overwriting more recently selected covers (newest-request-wins semantics).
4. Implement robust HTTP download with timeout, retry with backoff, redirect following, and size limits.
5. Preload covers for playlists in bounded batches to improve perceived performance.
6. Coordinate spinner visibility for user feedback during cover loading.

**Notes:**

- The `COVER_URL_ERRORS` tuple (`AttributeError`, `IndexError`, `TypeError`, `ValueError`) is similar to but distinct from `SESSION_ERRORS` in `context_menus.py` and `activate.py` — it catches errors specific to URL extraction from media objects.
- The `_get_cover_url` method handles both `Album` objects (via `album.image()`) and generic media objects (via `media.image()` callable), providing flexibility for different TIDAL media types.
- The `_normalize_url` method uses the walrus operator (`:=`) for concise URL stripping and validation.
- The `_download_cover_bytes` method implements a retry loop with exponential backoff (`COVER_DOWNLOAD_BACKOFF_SEC * attempt`) and redirect following, with a maximum of `COVER_DOWNLOAD_MAX_REDIRECTS` redirects.
- The `_request_cover_bytes` method validates URL scheme and hostname before making the HTTP request, and reads at most `MAX_COVER_BYTES + 1` bytes to enforce the size limit.
- The `preload_covers_for_playlist` method uses `itertools.islice` to bound the number of preloaded covers and a set comprehension to deduplicate URLs.
- The `_post_to_gui` method uses `QTimer.singleShot(0, ...)` to post callbacks to the Qt event loop, ensuring thread safety.
- The `_is_gui_thread` method compares `QThread.currentThread()` with the info tab's thread to determine if GUI resources can be accessed safely.
- The `_reserve_url`/`_release_url` methods use a `threading.Lock` to coordinate URL reservations and prevent duplicate foreground downloads.
- The `COVER_URL_ERRORS` tuple is defined at module level for reuse and consistency, similar to `SESSION_ERRORS` in other GUI modules.

---

## File: tidal_dl_ng/gui/dialog_playlist_manager.py

**File Path:** `tidal_dl_ng/gui/dialog_playlist_manager.py`

**Purpose:** Responsive modal dialog for managing a track's playlist memberships — adding/removing tracks from playlists via the TIDAL API without blocking the Qt GUI thread.

**Description:** This module defines `PlaylistManagerDialog`, a `QDialog` subclass that uses Qt's model/view architecture (custom `QAbstractListModel` + `QSortFilterProxyModel`) instead of creating one widget hierarchy per playlist. API mutations run on `QThreadPool` workers via the `Worker` class and return immutable `PlaylistTransactionResult` dataclass instances through a Qt signal (`transaction_finished`), keeping all model and widget updates on the GUI thread. The dialog provides real-time search filtering, pending state visualization (italic font, progress bar), error display, and automatic result acceptance/cancellation on close. It integrates with `ThreadSafePlaylistCache` for thread-safe cache updates and `playlist_api.py` for centralized TIDAL API calls.

**Functions and Classes:**

- `SPACING_SMALL` (`int`): Small spacing constant (6px).
- `SPACING_MEDIUM` (`int`): Medium spacing constant (12px).
- `SPACING_LARGE` (`int`): Large spacing constant (24px).
- `TITLE_POINT_SIZE` (`int`): Title font point size (20).
- `MINIMUM_DIALOG_WIDTH` (`int`): Minimum dialog width (520px).
- `MINIMUM_DIALOG_HEIGHT` (`int`): Minimum dialog height (420px).
- `DEFAULT_DIALOG_WIDTH` (`int`): Default dialog width (640px).
- `DEFAULT_DIALOG_HEIGHT` (`int`): Default dialog height (600px).
- `PLAYLIST_OPERATION_ERRORS` (`tuple[type[Exception], ...]`): Exceptions caught during playlist API operations (`AttributeError`, `OSError`, `RuntimeError`, `TidalAPIError`, `TypeError`, `ValueError`).
- `ModelIndex` (`type`): Union of `QtCore.QModelIndex` and `QtCore.QPersistentModelIndex`.
- `ROOT_MODEL_INDEX` (`QtCore.QModelIndex`): Default root model index for `rowCount`.
- `PlaylistAction` (`StrEnum`): Supported playlist membership mutations (`ADD`, `REMOVE`).
- `PlaylistMembership` (`dataclass`): Mutable presentation state for one playlist row (`playlist_id`, `name`, `item_count`, `checked`, `pending`, `error_message`).
- `_playlist_name_sort_key(membership)` (`Callable`): Returns a case-insensitive sort key for a playlist membership.
- `PlaylistTransaction` (`dataclass`, frozen, slots): Immutable request executed by a worker thread (`playlist_id`, `track_id`, `action`).
- `PlaylistTransactionResult` (`dataclass`, frozen, slots): Immutable worker result delivered to the GUI thread (`request`, `success`, `message`).
- `PlaylistDialogWidgets` (`dataclass`, frozen, slots): Widget references created by the dialog's UI builder.
- `PlaylistMembershipModel` (`QtCore.QAbstractListModel`): Checkable list model representing playlist membership state.
  - `__init__(memberships, parent)`: Initializes the model with sorted membership records.
  - `rowCount(parent)`: Returns the number of top-level playlist rows.
  - `data(index, role)`: Returns display, check, accessibility, and status data.
  - `flags(index)`: Returns interactive flags for a playlist row.
  - `setData(index, value, role)`: Applies a user-requested check-state change.
  - `finish_transaction(playlist_id, checked, error_message)`: Applies a completed transaction to one model row.
  - `playlist_name(playlist_id)`: Returns a playlist display name by identifier.
  - `_membership_at(index)`: Returns a row record for a valid model index.
  - `_display_text(membership)` (static): Builds concise primary text for a playlist row.
  - `_tooltip_text(membership)` (static): Builds tooltip text describing a playlist row's state.
  - `_emit_row_changed(row)`: Notifies views that all presentation roles changed for a row.
- `PlaylistFilterProxyModel` (`QtCore.QSortFilterProxyModel`): Case-insensitive filter and sorter for playlist rows.
- `PlaylistManagerDialog` (`QtWidgets.QDialog`): Manage one track's playlist memberships without blocking Qt.
  - `__init__(track, cache, session, threadpool, parent)`: Initializes the playlist manager dialog.
  - `_build_memberships()`: Creates sorted model records from the membership cache.
  - `_build_ui(track_title)`: Builds the dialog exclusively with responsive Qt layouts.
  - `_create_root_layout()`: Configures dialog geometry and returns its root layout.
  - `_build_header(root_layout, track_title)`: Builds and attaches the title and track-name panel.
  - `_build_content(root_layout)`: Builds and attaches the searchable model/view content panel.
  - `_build_footer(root_layout)`: Builds and attaches progress, status, and close controls.
  - `_connect_signals()`: Connects model, filter, and worker-result signals.
  - `_apply_filter(text)`: Applies escaped user text to the playlist proxy model.
  - `_update_empty_state()`: Shows a clear empty or no-results state when appropriate.
  - `_queue_transaction(playlist_id, checked)`: Creates and queues a playlist mutation worker.
  - `_execute_transaction(request)`: Executes one API mutation and updates the thread-safe cache.
  - `_api_add_track_to_playlist(track_id, playlist_id)`: Executes an add transaction in the current worker thread.
  - `_api_remove_track_from_playlist(track_id, playlist_id)`: Executes a remove transaction in the current worker thread.
  - `_operation_error_message(action)` (static): Builds a concise user-facing operation error.
  - `_on_transaction_finished(value)`: Applies one worker result on the GUI thread.
  - `_emit_membership_change(request)`: Emits the public signal corresponding to a successful mutation.
  - `_update_busy_state()`: Synchronizes progress visibility with pending worker count.
  - `_show_error_notification(message)`: Displays a non-blocking error state in the dialog footer.
  - `_show_status(message, is_error)`: Shows accessible success or error feedback without a modal popup.
  - `_cancel_pending_tasks()`: Cancels queued workers and ignores results from running workers.
  - `done(result)`: Finishes the dialog and detaches pending asynchronous results.
  - `closeEvent(event)`: Handles window-manager close requests safely.

**Dependencies:** `dataclasses.dataclass`, `enum.StrEnum`, `typing.TYPE_CHECKING`, `typing.override`, `PySide6.QtCore`, `PySide6.QtGui`, `PySide6.QtWidgets`, `tidalapi.exceptions.TidalAPIError`, `tidal_dl_ng.helper.playlist_api.add_track_to_playlist`, `tidal_dl_ng.helper.playlist_api.remove_track_from_playlist`, `tidal_dl_ng.logger.logger_gui`, `tidal_dl_ng.worker.Worker`, `tidalapi.media.Track` (TYPE_CHECKING), `tidalapi.session.Session` (TYPE_CHECKING), `tidal_dl_ng.gui.playlist_membership.ThreadSafePlaylistCache` (TYPE_CHECKING).

**Relationships:**

- Composed into `MainWindow` via `tidal_dl_ng/gui/playlist_membership_mixin.py` (line 14: imports `PlaylistManagerDialog`, line 331: creates dialog instance).
- Re-exported through `tidal_dl_ng/ui/__init__.py` (lines 18-37: bridges `Ui_DialogPlaylistManager` with `PlaylistManagerDialog` implementation).
- Uses `ThreadSafePlaylistCache` from `tidal_dl_ng.gui.playlist_membership` for thread-safe playlist cache updates.
- Uses `Worker` from `tidal_dl_ng.worker` for thread pool task execution.
- Uses `add_track_to_playlist` and `remove_track_from_playlist` from `tidal_dl_ng.helper.playlist_api` for centralized TIDAL API calls.
- Uses `logger_gui` from `tidal_dl_ng.logger` for logging.
- Uses `TidalAPIError` from `tidalapi.exceptions` for API error handling.
- Referenced by `tests/test_playlist_manager.py` (line 23: imports `PlaylistManagerDialog`, extensive test coverage).
- Referenced by `scripts/verify_playlist_integration.py` (line 46: integration verification).

**Inputs and Outputs:**

- **Inputs:** `Track` (TIDAL media object with `id` and `name`), `ThreadSafePlaylistCache` (preloaded membership cache), `Session` (authenticated TIDAL session), `QtCore.QThreadPool` (for API mutation workers), `QtWidgets.QWidget` (owning window), `str` (filter text from search editor).
- **Outputs:** `PlaylistTransactionResult` (immutable worker results delivered via `transaction_finished` signal), `playlist_added`/`playlist_removed` signals (public membership change events), `QtCore.SignalInstance` (spinner start/stop, status updates), `None` (async operations emit results to the GUI thread).

**Goals:**

1. Provide a responsive modal dialog for managing a track's playlist memberships without blocking the Qt GUI thread.
2. Use Qt's model/view architecture (custom `QAbstractListModel` + `QSortFilterProxyModel`) instead of creating one widget hierarchy per playlist.
3. Run API mutations on `QThreadPool` workers and return immutable transaction results through Qt signals, keeping all model and widget updates on the GUI thread.
4. Implement real-time search filtering with escaped regular expressions for safe user input.
5. Visualize pending state (italic font, progress bar) and display errors without modal popups.
6. Coordinate pending worker lifecycle with automatic result acceptance/cancellation on dialog close.
7. Integrate with `ThreadSafePlaylistCache` for thread-safe cache updates and `playlist_api.py` for centralized TIDAL API calls.

**Notes:**

- The `PLAYLIST_OPERATION_ERRORS` tuple (`AttributeError`, `OSError`, `RuntimeError`, `TidalAPIError`, `TypeError`, `ValueError`) is similar to but distinct from `SESSION_ERRORS` in `context_menus.py`/`activate.py` and `COVER_URL_ERRORS` in `covers.py` — it catches errors specific to playlist API operations.
- The `PlaylistAction` enum uses `StrEnum` (Python 3.11+) for string-valued enum members, enabling direct string comparison.
- The `PlaylistTransaction` and `PlaylistTransactionResult` dataclasses use `frozen=True` and `slots=True` for immutability and memory efficiency.
- The `PlaylistMembership` dataclass uses `slots=True` for memory efficiency.
- The `ModelIndex` type alias uses PEP 695 syntax (`type ModelIndex = ...`) for Python 3.14 compatibility.
- The `data` method uses structural pattern matching (`match`/`case`) with guard clauses for clean role-based data dispatch.
- The `_apply_filter` method uses `QRegularExpression.escape()` to safely handle user input in the filter.
- The `_cancel_pending_tasks` method uses `threadpool.tryTake()` to cancel queued workers and sets `_accept_results = False` to ignore results from running workers.
- The `done` and `closeEvent` overrides both call `_cancel_pending_tasks` to ensure clean shutdown.
- The `_api_add_track_to_playlist` and `_api_remove_track_from_playlist` methods are public API wrappers around `_execute_transaction`, providing a clean interface for external callers.
- The `_show_status` method uses `style().unpolish()`/`style().polish()` to trigger style updates when the status property changes.

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

**Dependencies:** `datetime.datetime`, `enum.Enum`, `typing.NoReturn`, `tidalapi.album.Album`, `tidalapi.media.Track`, `tidalapi.media.Video`, `tidalapi.mix.Mix`, `tidalapi.playlist.Playlist`, `tidalapi.playlist.UserPlaylist`, `tidalapi.request.Requests`, `tidalapi.session.Session`.

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

**Description:** Declares the public interface of the `tidalapi.page` module. The `Page` class is iterable and lazily yields content (tracks, albums, artists, playlists, mixes, page items, links, text blocks) from TIDAL's page API. `PageCategory` and `PageCategoryV2` are base classes for different page category types, with `PageCategoryV2` using a registry pattern (`_type_map`, `register_subclass` decorator) to dispatch parsing of different category types (SHORTCUT_LIST, HORIZONTAL_LIST, TRACK_LIST, etc.). The stub also declares type aliases (`TidalItem`, `PageContent`, `PageCategories`, `AllCategories`, `PageCategoriesV2`, `AllCategoriesV2`) for the union types used throughout.

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
