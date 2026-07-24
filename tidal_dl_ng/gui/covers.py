"""Asynchronous cover loading, caching, and display coordination.

Network and media lookups run on ``QThreadPool`` workers.  ``QPixmap``
creation, cache access, and widget updates are confined to the Qt GUI thread
because pixmaps are GUI resources rather than worker-safe image containers.
"""

from __future__ import annotations

import time
from functools import partial
from http.client import HTTPException
from itertools import islice
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING, cast
from urllib.parse import urljoin, urlsplit

import requests
from PySide6 import QtCore, QtGui
from tidalapi.album import Album

from tidal_dl_ng.cache import CoverPixmapCache
from tidal_dl_ng.constants import REQUESTS_TIMEOUT_SEC
from tidal_dl_ng.helper.path import resource_path
from tidal_dl_ng.logger import logger_gui
from tidal_dl_ng.worker import Worker

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from tidal_dl_ng.ui.info_tab_widget import InfoTabWidget


DEFAULT_COVER_RESOURCE: str = "tidal_dl_ng/ui/default_album_image.png"
MAX_PRELOAD_COVERS: int = 50
COVER_DOWNLOAD_MAX_ATTEMPTS: int = 3
COVER_DOWNLOAD_BACKOFF_SEC: float = 0.5
COVER_DOWNLOAD_MAX_REDIRECTS: int = 3
MAX_COVER_BYTES: int = 20 * 1024 * 1024
HTTP_SUCCESS_MIN: int = 200
HTTP_SUCCESS_MAX_EXCLUSIVE: int = 300
TRANSIENT_HTTP_STATUS_CODES: frozenset[int] = frozenset(
    {408, 425, 429, 500, 502, 503, 504},
)
COVER_URL_ERRORS: tuple[type[Exception], ...] = (
    AttributeError,
    IndexError,
    TypeError,
    ValueError,
)


class CoverManager:
    """Coordinate non-blocking cover downloads and GUI display updates."""

    def __init__(
        self,
        parent_window: object,
        threadpool: QtCore.QThreadPool,
        info_tab_widget: InfoTabWidget,
    ) -> None:
        """Initialize cover state and worker dependencies.

        Args:
            parent_window (object): Window providing Qt spinner signals.
            threadpool (QtCore.QThreadPool): Pool used for network work.
            info_tab_widget (InfoTabWidget): Cover display controller.

        Returns:
            None: A ready cover manager is initialized in place.
        """
        self.threadpool: QtCore.QThreadPool = threadpool
        self.info_tab: InfoTabWidget = info_tab_widget
        self.cache: CoverPixmapCache = CoverPixmapCache()
        self.cover_url_current: str = ""

        self._spinner_start = self._get_signal(
            parent_window,
            "s_spinner_start",
        )
        self._spinner_stop = self._get_signal(
            parent_window,
            "s_spinner_stop",
        )
        self._requested_cover_url: str | None = None
        self._pending_urls: set[str] = set()
        self._state_lock: Lock = Lock()

    @staticmethod
    def _get_signal(parent_window: object, name: str) -> QtCore.SignalInstance:
        """Return a required Qt signal from the parent window.

        Args:
            parent_window (object): Object expected to own the signal.
            name (str): Signal attribute name.

        Returns:
            QtCore.SignalInstance: Validated bound Qt signal.

        Raises:
            TypeError: If the required signal is absent or invalid.
        """
        signal = cast("object", getattr(parent_window, name, None))
        if isinstance(signal, QtCore.SignalInstance):
            return signal
        message = f"Parent window does not provide Qt signal {name!r}."
        raise TypeError(message)

    @staticmethod
    def _coerce_cover_bytes(
        data_cover: bytes | bytearray | memoryview | str | None,
    ) -> bytes:
        """Normalize a downloaded cover payload to immutable bytes.

        Args:
            data_cover (bytes | bytearray | memoryview | str | None): Raw
                payload returned by a cover provider.

        Returns:
            bytes: Immutable image data, or empty bytes when absent.
        """
        if data_cover is None:
            return b""
        if isinstance(data_cover, bytes):
            return data_cover
        if isinstance(data_cover, bytearray | memoryview):
            return bytes(data_cover)
        return data_cover.encode("utf-8", errors="ignore")

    @staticmethod
    def _pixmap_from_bytes(
        data_cover: bytes | bytearray | memoryview | str | None,
    ) -> QtGui.QPixmap:
        """Create a pixmap from cover data on the calling GUI thread.

        Args:
            data_cover (bytes | bytearray | memoryview | str | None): Raw
                image payload.

        Returns:
            QtGui.QPixmap: Decoded pixmap, which is null for invalid data.
        """
        pixmap = QtGui.QPixmap()
        pixmap.loadFromData(CoverManager._coerce_cover_bytes(data_cover))
        return pixmap

    def load_cover(
        self,
        media: object,
        use_cache_check: bool = True,
    ) -> None:
        """Load and display a media cover without blocking the GUI.

        Calls arriving from a worker are first posted to the GUI thread.  The
        newest request owns the display, preventing slow earlier downloads
        from replacing a more recently selected cover.

        Args:
            media (object): TIDAL media object with ``album`` or ``image``.
            use_cache_check (bool): Whether to reuse an existing pixmap.

        Returns:
            None: Network work and display delivery are asynchronous.
        """
        if not self._is_gui_thread():
            self._post_to_gui(
                partial(self.load_cover, media, use_cache_check),
            )
            return

        cover_url = self._get_cover_url(media)
        self._requested_cover_url = cover_url
        if cover_url is None:
            self._display_default_cover()
            return

        if use_cache_check:
            if cover_url == self.cover_url_current:
                return
            if (cached_pixmap := self.cache.get(cover_url)) is not None:
                self._display_cover(cached_pixmap, cover_url)
                return

        if not self._reserve_url(cover_url):
            return

        spinner_started = self._start_spinner()
        worker = Worker(
            self._load_cover_async,
            cover_url,
            spinner_started,
        )
        self.threadpool.start(worker)

    def _load_cover_async(
        self,
        cover_url: str,
        spinner_started: bool,
    ) -> None:
        """Download one cover in a worker and post its result to the GUI.

        Args:
            cover_url (str): Remote image URL.
            spinner_started (bool): Whether this request owns a spinner count.

        Returns:
            None: A GUI-thread callback receives the downloaded bytes.
        """
        data_cover = self._download_cover_bytes(cover_url)
        self._post_to_gui(
            partial(
                self._handle_cover_bytes,
                cover_url,
                data_cover,
                spinner_started,
            ),
        )

    @staticmethod
    def _download_cover_bytes(cover_url: str) -> bytes:
        """Download cover bytes with timeout, retry, and response cleanup.

        Args:
            cover_url (str): Remote image URL.

        Returns:
            bytes: Downloaded image data, or empty bytes after final failure.
        """
        request_url = cover_url
        redirect_count = 0
        attempt = 1

        while attempt <= COVER_DOWNLOAD_MAX_ATTEMPTS:
            retryable = True
            try:
                status_code, data_cover, redirect_url = (
                    CoverManager._request_cover_bytes(request_url)
                )
            except (HTTPException, OSError, ValueError) as error:
                logger_gui.warning(
                    "Cover request failed for %s: %s.",
                    request_url,
                    error,
                )
            else:
                if (
                    HTTP_SUCCESS_MIN
                    <= status_code
                    < HTTP_SUCCESS_MAX_EXCLUSIVE
                ):
                    return data_cover
                if redirect_url is not None:
                    redirect_count += 1
                    if redirect_count > COVER_DOWNLOAD_MAX_REDIRECTS:
                        logger_gui.warning(
                            "Cover request exceeded %s redirects for %s.",
                            COVER_DOWNLOAD_MAX_REDIRECTS,
                            cover_url,
                        )
                        break
                    request_url = urljoin(request_url, redirect_url)
                    continue

                retryable = status_code in TRANSIENT_HTTP_STATUS_CODES
                logger_gui.warning(
                    "Cover request failed with HTTP %s for %s.",
                    status_code,
                    request_url,
                )

            if not retryable or attempt >= COVER_DOWNLOAD_MAX_ATTEMPTS:
                break

            time.sleep(COVER_DOWNLOAD_BACKOFF_SEC * attempt)
            attempt += 1

        return b""

    @staticmethod
    def _request_cover_bytes(
        cover_url: str,
    ) -> tuple[int, bytes, str | None]:
        """Perform one validated HTTP cover request.

        Args:
            cover_url (str): Absolute HTTP or HTTPS cover URL.

        Returns:
            tuple[int, bytes, str | None]: Status, body, and redirect URL.

        Raises:
            requests.RequestException: If the HTTP exchange fails.
            ValueError: If the URL is unsupported or malformed.
        """
        parsed_url = urlsplit(cover_url)
        if parsed_url.scheme not in {"http", "https"}:
            message = f"Unsupported cover URL scheme: {parsed_url.scheme}"
            raise ValueError(message)
        if parsed_url.hostname is None:
            message = "Cover URL does not contain a hostname."
            raise ValueError(message)

        response = requests.get(
            cover_url,
            headers={"User-Agent": "tidal-dl-ng-for-dj"},
            timeout=REQUESTS_TIMEOUT_SEC,
            stream=True,
        )
        try:
            response_data = response.raw.read(MAX_COVER_BYTES + 1)
            if len(response_data) > MAX_COVER_BYTES:
                message = "Cover response exceeds the maximum allowed size."
                raise ValueError(message)
            return (
                response.status_code,
                response_data,
                response.headers.get("Location"),
            )
        finally:
            response.close()

    def _handle_cover_bytes(
        self,
        cover_url: str,
        data_cover: bytes,
        spinner_started: bool,
    ) -> None:
        """Decode, cache, and conditionally display downloaded cover bytes.

        Args:
            cover_url (str): URL associated with the payload.
            data_cover (bytes): Downloaded image data.
            spinner_started (bool): Whether to stop a spinner for the request.

        Returns:
            None: Cache and UI state are updated on the GUI thread.
        """
        try:
            pixmap = self._pixmap_from_bytes(data_cover)
            if pixmap.isNull():
                logger_gui.warning("Cover data is invalid for %s.", cover_url)
                if self._requested_cover_url == cover_url:
                    self._display_default_cover()
                return

            self.cache.set(cover_url, pixmap)
            if self._requested_cover_url == cover_url:
                self._display_cover(pixmap, cover_url)
        finally:
            self._release_url(cover_url)
            if spinner_started:
                self._spinner_stop.emit()

    @staticmethod
    def _get_cover_url(media: object) -> str | None:
        """Extract and validate a cover URL from a TIDAL media object.

        Args:
            media (object): Object exposing an album or image method.

        Returns:
            str | None: Non-empty cover URL when one is available.
        """
        try:
            album = cast("object", getattr(media, "album", None))
            if isinstance(album, Album):
                return CoverManager._normalize_url(album.image())

            image_attribute = cast("object", getattr(media, "image", None))
            if callable(image_attribute):
                image_method = cast("Callable[[], object]", image_attribute)
                return CoverManager._normalize_url(image_method())
        except COVER_URL_ERRORS as error:
            logger_gui.debug(
                "Unable to determine cover URL for %s: %s",
                type(media).__name__,
                error,
            )
        return None

    @staticmethod
    def _normalize_url(value: object) -> str | None:
        """Return a stripped URL from an arbitrary image-method result.

        Args:
            value (object): Result returned by a media image method.

        Returns:
            str | None: Non-empty normalized URL, or ``None``.
        """
        if not isinstance(value, str):
            return None
        return normalized_url if (normalized_url := value.strip()) else None

    def _display_cover(self, pixmap: QtGui.QPixmap, url: str) -> None:
        """Display a valid pixmap and synchronize current-cover state.

        Args:
            pixmap (QtGui.QPixmap): Decoded cover pixmap.
            url (str): URL represented by the pixmap.

        Returns:
            None: The info tab and manager are updated in place.
        """
        self.info_tab.set_cover_pixmap(pixmap)
        self.info_tab.cover_url_current = url
        self.cover_url_current = url

    def _display_default_cover(self) -> None:
        """Display the packaged fallback cover and reset URL state.

        Returns:
            None: The fallback pixmap is installed on the info tab.
        """
        try:
            image_path = Path(
                resource_path(DEFAULT_COVER_RESOURCE),
            ).resolve()
            pixmap = QtGui.QPixmap(str(image_path))
        except OSError:
            logger_gui.exception(
                "Unable to load the default cover resource: %s",
                DEFAULT_COVER_RESOURCE,
            )
            pixmap = QtGui.QPixmap()
        self.info_tab.set_cover_pixmap(pixmap)
        self.info_tab.cover_url_current = ""
        self.cover_url_current = ""

    def preload_covers_for_playlist(
        self,
        items: Iterable[object],
    ) -> None:
        """Preload a bounded set of playlist covers in one worker.

        Args:
            items (Iterable[object]): Track or video items to inspect.

        Returns:
            None: Unique cover downloads are queued in the thread pool.
        """
        preload_items = tuple(islice(items, MAX_PRELOAD_COVERS))
        if not self._is_gui_thread():
            self._post_to_gui(
                partial(self.preload_covers_for_playlist, preload_items),
            )
            return

        cover_urls = {
            cover_url
            for item in preload_items
            if (cover_url := self._get_cover_url(item)) is not None
            and self.cache.get(cover_url) is None
        }
        if not cover_urls:
            return

        def preload_worker() -> None:
            """Download unique uncached covers without touching pixmaps."""
            for cover_url in cover_urls:
                if data_cover := self._download_cover_bytes(cover_url):
                    self._post_to_gui(
                        partial(
                            self._cache_preloaded_cover,
                            cover_url,
                            data_cover,
                        ),
                    )

        self.threadpool.start(Worker(preload_worker))

    def _cache_preloaded_cover(
        self,
        cover_url: str,
        data_cover: bytes,
    ) -> None:
        """Decode and cache one preloaded cover on the GUI thread.

        Args:
            cover_url (str): URL associated with the image data.
            data_cover (bytes): Downloaded image payload.

        Returns:
            None: Valid pixmaps are inserted into the cache.
        """
        pixmap = self._pixmap_from_bytes(data_cover)
        if pixmap.isNull():
            return
        self.cache.set(cover_url, pixmap)

    def _queue_cover_fetch(self, media: object) -> None:
        """Queue a thread-safe foreground cover request.

        Args:
            media (object): TIDAL media object to inspect.

        Returns:
            None: ``load_cover`` routes the request to the GUI thread.
        """
        self.load_cover(media)

    def _fetch_cover_pixmap(
        self,
        media: object,
        use_cache_check: bool,
    ) -> QtGui.QPixmap | None:
        """Return a cached pixmap or queue a non-blocking cover fetch.

        Args:
            media (object): TIDAL media object to inspect.
            use_cache_check (bool): Whether to return a cached pixmap.

        Returns:
            QtGui.QPixmap | None: Cached pixmap, or ``None`` while loading.
        """
        if not self._is_gui_thread():
            self._queue_cover_fetch(media)
            return None

        if (cover_url := self._get_cover_url(media)) is None:
            return None
        if (
            use_cache_check
            and (cached_pixmap := self.cache.get(cover_url)) is not None
        ):
            return cached_pixmap
        self.load_cover(media, use_cache_check=use_cache_check)
        return None

    def _start_spinner(self) -> bool:
        """Start the cover spinner when its target widget is available.

        Returns:
            bool: ``True`` when a matching stop signal will be required.
        """
        if (tab_widget := self.info_tab.tab_widget) is None:
            return False
        self._spinner_start.emit(tab_widget)
        return True

    def _post_to_gui(self, callback: Callable[[], None]) -> None:
        """Schedule a callback on the info controller's Qt thread.

        Args:
            callback (Callable[[], None]): GUI-safe work to execute.

        Returns:
            None: Qt queues the callback asynchronously.
        """
        QtCore.QTimer.singleShot(0, self.info_tab, callback)

    def _is_gui_thread(self) -> bool:
        """Check whether the caller is running on the info tab's Qt thread.

        Returns:
            bool: ``True`` when GUI resources may be accessed safely.
        """
        return QtCore.QThread.currentThread() == self.info_tab.thread()

    def _reserve_url(self, cover_url: str) -> bool:
        """Reserve a URL to avoid duplicate foreground downloads.

        Args:
            cover_url (str): Cover URL to reserve.

        Returns:
            bool: ``True`` when the caller owns the new reservation.
        """
        with self._state_lock:
            if cover_url in self._pending_urls:
                return False
            self._pending_urls.add(cover_url)
            return True

    def _release_url(self, cover_url: str) -> None:
        """Release a completed foreground URL reservation.

        Args:
            cover_url (str): Completed cover URL.

        Returns:
            None: The reservation is removed if present.
        """
        with self._state_lock:
            self._pending_urls.discard(cover_url)
