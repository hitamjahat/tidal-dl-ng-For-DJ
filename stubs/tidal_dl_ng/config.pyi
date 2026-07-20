"""Stub for tidal_dl_ng.config."""

import threading
from collections.abc import Callable
from typing import Generic, TypeVar

from tidalapi.session import Session

from tidal_dl_ng.model.cfg import Settings as ModelSettings
from tidal_dl_ng.model.cfg import Token as ModelToken

TConfigData = TypeVar("TConfigData")

class BaseConfig(Generic[TConfigData]):
    """Base class for JSON-backed configuration objects."""

    data: TConfigData
    file_path: str
    cls_model: type[TConfigData]
    path_base: str

    def save(self, config_to_compare: str | None = None) -> None: ...
    def set_option(self, key: str, value: object) -> None: ...
    def read(self, path: str) -> bool: ...

class Settings(BaseConfig[ModelSettings]):
    """Singleton holding user-configurable application settings."""

    def __init__(self) -> None: ...

class Token(BaseConfig[ModelToken]):
    """OAuth/PKCE authentication token persisted between sessions."""

    def __init__(self) -> None: ...

class Tidal(BaseConfig[ModelToken]):
    """Manages the TIDAL API session, token persistence, and login flows."""

    session: Session
    token_from_storage: bool
    settings: Settings
    is_pkce: bool

    def __init__(self, settings: Settings | None = None) -> None: ...
    def login(self, fn_print: Callable[[str], None] | None = None) -> bool: ...
    def logout(self) -> bool: ...

class HandlingApp:
    """Holds application-wide control events for abort/run signalling."""

    event_abort: threading.Event
    event_run: threading.Event

    def __init__(self) -> None: ...
