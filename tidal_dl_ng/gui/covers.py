"""Cover management for GUI - Handles cover loading, caching and display."""

from contextlib import suppress
from typing import TYPE_CHECKING, Any, Protocol, cast

from PySide6 import QtCore, QtGui

from tidal_dl_ng.cache import CoverPixmapCache
from tidal_dl_ng.download import Download
from tidal_dl_ng.helper.path import resource_path
from tidal_dl_ng.logger import logger_gui
from tidal_dl_ng.worker import Worker

if TYPE_CHECKING:
    from tidal_dl_ng.ui.info_tab_widget import InfoTabWidget


class _SignalEmitter(Protocol):
    def emit(self, *args: Any, **kwargs: Any) -> None: ...


class _CoverParentWindow(Protocol):
    s_spinner_start: _SignalEmitter
    s_spinner_stop: _SignalEmitter


class _InfoTabWidgetLike(Protocol):
    tab_widget: QtCore.QObject | None
    cover_url_current: str

    def set_cover_pixmap(self, pixmap: QtGui.QPixmap) -> None: ...


class CoverManager:
    """Manages cover art loading, caching and display operations."""

    def __init__(
        self,
        parent_window: _CoverParentWindow,
        threadpool: QtCore.QThreadPool,
        info_tab_widget: "InfoTabWidget",
    ) -> None:
        """Initialize the cover manager.

        Args:
            parent_window: Main window instance
            threadpool: QThreadPool for async operations
            info_tab_widget: InfoTabWidget instance for display
        """
        self.parent: _CoverParentWindow = parent_window
        self.threadpool: QtCore.QThreadPool = threadpool
        self.info_tab: _InfoTabWidgetLike = cast(
            _InfoTabWidgetLike, info_tab_widget
        )
        self.cache: CoverPixmapCache = CoverPixmapCache()
        self.cover_url_current: str = ""

    @staticmethod
    def _coerce_cover_bytes(
        data_cover: bytes | bytearray | memoryview | str | None,
    ) -> bytes:
        """Normalize cover payload to bytes for QPixmap.loadFromData."""
        if data_cover is None:
            return b""
        if isinstance(data_cover, bytes):
            return data_cover
        if isinstance(data_cover, (bytearray, memoryview)):
            return bytes(data_cover)
        return data_cover.encode("utf-8", errors="ignore")

    @staticmethod
    def _pixmap_from_bytes(
        data_cover: bytes | bytearray | memoryview | str | None,
    ) -> QtGui.QPixmap:
        """Create a QPixmap from arbitrary cover payload data."""
        pixmap = QtGui.QPixmap()
        pixmap.loadFromData(CoverManager._coerce_cover_bytes(data_cover))
        return pixmap

    def load_cover(self, media: Any, use_cache_check: bool = True) -> None:
        """Load and display cover for media item.

        Args:
            media: Media object (Track, Album, etc.)
            use_cache_check: If True, check cache before loading
        """
        if use_cache_check:
            # Try cache first for instant display
            cover_url = self._get_cover_url(media)
            if cover_url:
                if cover_url == self.cover_url_current:
                    return  # Already displayed

                cached_pixmap = self.cache.get(cover_url)
                if cached_pixmap:
                    self._display_cover(cached_pixmap, cover_url)
                    return

        # Load asynchronously
        worker_ctor = cast(Any, Worker)
        worker = worker_ctor(self._load_cover_async, media)
        self.threadpool.start(worker)

    def _load_cover_async(self, media: Any) -> None:
        """Load cover in background thread."""
        # Emit spinner on tab widget instead of InfoTabWidget (which is QObject, not QWidget)
        tab_widget = self.info_tab.tab_widget
        if tab_widget:
            self.parent.s_spinner_start.emit(tab_widget)

        try:
            cover_url = self._get_cover_url(media)

            if cover_url and self.cover_url_current != cover_url:
                # Check cache again (thread-safe)
                cached_pixmap = self.cache.get(cover_url)
                if cached_pixmap:
                    self._display_cover(cached_pixmap, cover_url)
                else:
                    # Download and cache
                    data_cover = Download.cover_data(cover_url)
                    pixmap = self._pixmap_from_bytes(data_cover)
                    self.cache.set(cover_url, pixmap)
                    self._display_cover(pixmap, cover_url)
            elif not cover_url:
                self._display_default_cover()
        except Exception as e:
            logger_gui.warning(f"Failed to load cover: {e}")
            self._display_default_cover()
        finally:
            self.parent.s_spinner_stop.emit()

    def _get_cover_url(self, media: Any) -> str | None:
        """Extract cover URL from media object."""
        with suppress(Exception):
            if hasattr(media, "album") and media.album:
                album_image = media.album.image()
                return str(album_image) if album_image else None
            if hasattr(media, "image") and callable(
                getattr(media, "image", None)
            ):
                image = media.image()
                return str(image) if image else None
        return None

    def _display_cover(self, pixmap: QtGui.QPixmap, url: str) -> None:
        """Display a pixmap on the info tab."""
        self.info_tab.set_cover_pixmap(pixmap)
        self.info_tab.cover_url_current = url
        self.cover_url_current = url

    def _display_default_cover(self) -> None:
        """Display default cover image."""
        path_image = resource_path("tidal_dl_ng/ui/default_album_image.png")
        pixmap = QtGui.QPixmap(path_image)
        self.info_tab.set_cover_pixmap(pixmap)
        self.info_tab.cover_url_current = ""
        self.cover_url_current = ""

    def preload_covers_for_playlist(self, items: list[Any]) -> None:
        """Preload cover pixmaps for a list of tracks in background.

        Args:
            items: List of Track/Video objects to preload covers for.
        """

        def worker() -> None:
            # Extract unique cover URLs
            cover_urls: set[str] = set()
            for item in items[:50]:  # Limit to first 50
                with suppress(Exception):
                    url = self._get_cover_url(item)
                    if url:
                        cover_urls.add(url)

            # Preload each unique cover
            for cover_url in cover_urls:
                if self.cache.get(cover_url):
                    continue  # Already cached

                with suppress(Exception):
                    data_cover = Download.cover_data(cover_url)
                    pixmap = self._pixmap_from_bytes(data_cover)
                    self.cache.set(cover_url, pixmap)
                    logger_gui.debug(f"Preloaded cover: {cover_url[:50]}...")

        worker_ctor = cast(Any, Worker)
        worker_obj = worker_ctor(worker)
        self.threadpool.start(worker_obj)

    def _queue_cover_fetch(self, media: Any) -> None:
        """Queue a cover fetch operation for a media item."""
        with suppress(Exception):
            # previously try/except/pass
            worker_ctor = cast(Any, Worker)
            worker = worker_ctor(self.load_cover, media)
            self.threadpool.start(worker)

    def _fetch_cover_pixmap(
        self, media: Any, use_cache_check: bool
    ) -> QtGui.QPixmap | None:
        """Fetch cover pixmap for media, with optional cache check."""
        _ = use_cache_check
        with suppress(Exception):
            # previously try/except/continue inside loop
            cover_url = self._get_cover_url(media)
            if cover_url:
                pixmap = self.cache.get(cover_url)
                if pixmap:
                    return pixmap

            # If not in cache, download cover
            if cover_url:
                data_cover = Download.cover_data(cover_url)
                pixmap = self._pixmap_from_bytes(data_cover)
                self.cache.set(cover_url, pixmap)
                return pixmap

        return None
