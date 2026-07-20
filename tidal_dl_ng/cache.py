"""Cache management for GUI - LRU caches for performance optimization.

Provides thread-safe LRU (Least Recently Used) caches backed by Qt's
read/write locks to avoid redundant network or compute work in the GUI
thread (e.g. fetching track metadata or cover pixmaps).
"""

from collections.abc import Mapping, MutableMapping

from PySide6 import QtCore, QtGui


class _LruCache[V]:
    """Thread-safe LRU cache base using a Qt read/write lock.

    The value type is parameterized by ``_V``. Eviction removes the
    least recently used entry once ``max_size`` is exceeded.
    """

    #: Name of the instance attribute holding the backing mapping.
    _store_name: str = ""
    #: Maximum number of entries retained before eviction.
    _max_size: int

    def __init__(self, max_size: int = 256) -> None:
        """Initialize the cache with a maximum capacity.

        Args:
            max_size: Maximum number of entries to retain. Defaults
                to 256.
        """
        self._lock = QtCore.QReadWriteLock()
        self._order: list[str] = []
        self._max_size = max_size

    def _store(self) -> MutableMapping[str, V]:
        """Return the backing mapping for this cache instance.

        Returns:
            MutableMapping[str, _V]: The value store.
        """
        return getattr(self, self._store_name)

    def get(self, key: str) -> V | None:
        """Return the cached value for ``key`` if present.

        Args:
            key: Identifier of the cached entry.

        Returns:
            _V | None: The cached value or None when absent.
        """
        with QtCore.QReadLocker(self._lock):
            return self._store().get(key)

    def set(self, key: str, value: V) -> None:
        """Store ``value`` under ``key`` applying LRU eviction.

        Args:
            key: Identifier of the entry to cache.
            value: The value to store.
        """
        store = self._store()
        with QtCore.QWriteLocker(self._lock):
            if key in store:
                self._order.remove(key)
            store[key] = value
            self._order.append(key)
            if len(self._order) > self._max_size:
                oldest = self._order.pop(0)
                store.pop(oldest, None)


class TrackExtrasCache(_LruCache[Mapping[str, object]]):
    """Thread-safe LRU cache for track extra metadata."""

    _store_name = "_data"

    def __init__(self, max_size: int = 256) -> None:
        """Initialize the track extras cache.

        Args:
            max_size: Maximum number of tracks to retain. Defaults
                to 256.
        """
        super().__init__(max_size=max_size)
        self._data: dict[str, Mapping[str, object]] = {}


class CoverPixmapCache(_LruCache[QtGui.QPixmap]):
    """Thread-safe LRU cache for cover pixmaps to avoid re-downloading."""

    _store_name = "_pixmaps"

    def __init__(self, max_size: int = 100) -> None:
        """Initialize the cover pixmap cache.

        Args:
            max_size: Maximum number of covers to retain. Defaults
                to 100.
        """
        super().__init__(max_size=max_size)
        self._pixmaps: dict[str, QtGui.QPixmap] = {}
