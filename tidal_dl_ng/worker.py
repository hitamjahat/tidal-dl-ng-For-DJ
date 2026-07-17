"""Worker thread utilities for PySide6 applications.

This module provides a :class:`Worker` wrapper around
:class:`PySide6.QtCore.QRunnable` so arbitrary callables can be executed
on a :class:`PySide6.QtCore.QThreadPool` while emitting structured runtime
trace events for diagnostics.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, ParamSpec, TypeVar

from PySide6 import QtCore

from tidal_dl_ng.runtime_trace import (
    new_operation_id,
    trace_event,
)

# Taken from
# https://www.pythonguis.com/tutorials/multithreading-pyside6-applications-qthreadpool/

_P = ParamSpec("_P")
_R = TypeVar("_R")

__all__ = ["Worker"]


class Worker(QtCore.QRunnable):
    """Execute a callable on a ``QThreadPool`` worker thread.

    Inherits from :class:`PySide6.QtCore.QRunnable` to handle worker thread
    setup, execution and wrap-up. Each run is wrapped with structured trace
    events so stalled or failing operations can be diagnosed.

    Args:
        fn (Callable): The callback executed on the worker thread. Supplied
            ``args`` and ``kwargs`` are forwarded to it.
        *args: Positional arguments forwarded to ``fn``.
        **kwargs: Keyword arguments forwarded to ``fn``.
    """

    def __init__(
        self,
        fn: Callable[_P, _R],
        *args: _P.args,
        **kwargs: _P.kwargs,
    ) -> None:
        """Initialize the worker and store the callback with its arguments."""
        super().__init__()
        # Store constructor arguments (re-used for processing)
        self.fn: Callable[..., Any] = fn
        self.args: tuple[Any, ...] = tuple(args)
        self.kwargs: dict[str, Any] = dict(kwargs)

    @QtCore.Slot()  # QtCore.Slot
    def run(self) -> None:
        """Run the stored callback, emitting trace events around execution."""
        op_id = new_operation_id("worker")
        fn_name = self._describe(self.fn)
        started_at = time.monotonic()

        trace_event(
            "worker",
            "start",
            expected="qrunnable executes callback and returns",
            actual=f"fn={fn_name}",
            op_id=op_id,
        )

        try:
            self.fn(*self.args, **self.kwargs)
        except Exception as error:
            trace_event(
                "worker",
                "failed",
                expected=("callback completes without uncaught exception"),
                actual=f"fn={fn_name}, error={error}",
                op_id=op_id,
            )
            raise
        finally:
            elapsed = time.monotonic() - started_at
            trace_event(
                "worker",
                "end",
                expected="worker thread exits",
                actual=f"fn={fn_name}, elapsed_sec={elapsed:.3f}",
                op_id=op_id,
            )

    @staticmethod
    def _describe(fn: Callable[..., Any]) -> str:
        """Return a human-readable name for a callable.

        Args:
            fn (Callable): The callable to describe.

        Returns:
            str: The callable's ``__name__`` or a repr fallback.
        """
        name = getattr(fn, "__name__", None)
        if isinstance(name, str):
            return name
        return repr(fn)

    def thread(self) -> QtCore.QThread:
        """Return the thread currently executing this runnable.

        Returns:
            PySide6.QtCore.QThread: The active thread, or ``None`` if not
            running inside one.
        """
        return QtCore.QThread.currentThread()
