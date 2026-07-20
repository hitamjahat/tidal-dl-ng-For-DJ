"""Metaclass utilities for the TIDAL downloader.

This module provides ``SingletonMeta``, a thread-safe metaclass that
ensures a class is instantiated only once per process. Subsequent
calls return the cached instance regardless of the arguments passed
to the constructor.
"""

from __future__ import annotations

from typing import Any, ClassVar, cast


class SingletonMeta(type):
    """Metaclass that creates a single shared instance per class.

    The singleton pattern can be implemented in several ways in Python
    (base class, decorator, or metaclass). A metaclass is used here
    because it keeps the derived classes free of boilerplate.
    """

    _instances: ClassVar[dict[type, object]] = {}

    def __call__(
        cls: type,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Return the cached instance, creating it on first use.

        Changes to the ``__init__`` arguments after the first
        instantiation do not affect the returned instance.

        Args:
            *args (Any): Positional arguments for the first call.
            **kwargs (Any): Keyword arguments for the first call.

        Returns:
            Any: The unique instance of ``cls``.
        """
        if cls not in SingletonMeta._instances:
            parent = cast("type", super())
            instance = cast(
                "object",
                parent.__call__(*args, **kwargs),
            )
            SingletonMeta._instances[cls] = instance
            return instance

        return SingletonMeta._instances[cls]
