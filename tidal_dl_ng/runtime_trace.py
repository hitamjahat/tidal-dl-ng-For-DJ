"""Runtime tracing utilities for diagnosing hangs and stalled operations.

This module provides:
- Persistent file logging setup for runtime diagnostics.
- Structured trace events with operation identifiers.
- A watchdog that emits warnings when progress heartbeats stop.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from logging.handlers import RotatingFileHandler
from typing import Any
from uuid import uuid4

from tidal_dl_ng.helper.path import path_config_base, path_file_log

APP_LOGGER_NAME: str = "tidal_dl_ng"
TRACE_LOGGER_NAME: str = "tidal_dl_ng.trace"
TRACE_LOG_FILE_NAME: str = "runtime_trace.log"

# Marker constants used to identify our own logging handlers without
# relying on protected attributes or ``# type: ignore`` comments.
_MARKER_APP_FILE: str = "_tdlng_app_file"
_MARKER_TRACE_FILE: str = "_tdlng_trace_file"

# Maximum length of a single context value before it is truncated.
_CONTEXT_VALUE_MAX: int = 180
_CONTEXT_VALUE_TRUNCATED: int = 177

_LOG_FORMAT: str = (
    "%(asctime)s %(levelname)s [%(threadName)s] %(name)s: %(message)s"
)
_LOG_MAX_BYTES: int = 10 * 1024 * 1024
_LOG_BACKUP_COUNT: int = 5


@dataclass(frozen=True)
class _WatchConfig:
    """Immutable identity and context for a watchdog operation."""

    operation: str
    op_id: str
    context: dict[str, Any]


@dataclass
class _WatchTiming:
    """Timing thresholds for a watchdog operation."""

    timeout_sec: float
    check_interval_sec: float


@dataclass
class _WatchProgress:
    """Mutable progress state guarded by the watchdog lock."""

    last_progress_time: float
    last_step: str


class _MarkerRotatingFileHandler(RotatingFileHandler):
    """Rotating file handler carrying a typed marker attribute.

    The ``marker`` attribute lets us recognise our own handlers without
    touching protected members or suppressing type errors.
    """

    marker: str = ""

    def __init__(
        self,
        *args: Any,
        marker: str = "",
        **kwargs: Any,
    ) -> None:
        """Initialize the handler and store its marker.

        Args:
            *args: Positional arguments forwarded to the base handler.
            marker (str, optional): Identifier for this handler.
            **kwargs: Keyword arguments forwarded to the base handler.
        """
        super().__init__(*args, **kwargs)
        self.marker = marker


@dataclass
class _LoggingState:
    """Module-level logging initialisation state."""

    ready: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)


_state = _LoggingState()


def _path_file_runtime_trace() -> str:
    """Return the runtime trace log path.

    Returns:
        str: Full path to runtime trace file.
    """
    return os.path.join(path_config_base(), TRACE_LOG_FILE_NAME)


def _format_context(context: dict[str, Any] | None) -> str:
    """Convert context fields to a compact key-value suffix.

    Args:
        context (dict[str, Any] | None): Additional trace context.

    Returns:
        str: Formatted context text.
    """
    if not context:
        return ""

    chunks: list[str] = []
    for key in sorted(context):
        value = context[key]
        value_str = str(value).replace("\n", " ").strip()
        if len(value_str) > _CONTEXT_VALUE_MAX:
            value_str = f"{value_str[:_CONTEXT_VALUE_TRUNCATED]}..."
        chunks.append(f"{key}={value_str}")

    return " " + " ".join(chunks) if chunks else ""


def setup_runtime_file_logging() -> None:
    """Configure persistent file logging for runtime diagnostics.

    Creates rotating handlers:
    - app.log for general logs.
    - runtime_trace.log for structured operation traces.
    """
    if _state.ready:
        return

    with _state.lock:
        if _state.ready:
            return

        os.makedirs(path_config_base(), exist_ok=True)

        formatter = logging.Formatter(_LOG_FORMAT)

        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)

        has_app_handler = any(
            getattr(handler, "marker", "") == _MARKER_APP_FILE
            for handler in root_logger.handlers
        )
        if not has_app_handler:
            app_handler = _MarkerRotatingFileHandler(
                path_file_log(),
                maxBytes=_LOG_MAX_BYTES,
                backupCount=_LOG_BACKUP_COUNT,
                encoding="utf-8",
                marker=_MARKER_APP_FILE,
            )
            app_handler.setLevel(logging.DEBUG)
            app_handler.setFormatter(formatter)
            root_logger.addHandler(app_handler)

        trace_logger = logging.getLogger(TRACE_LOGGER_NAME)
        trace_logger.setLevel(logging.DEBUG)
        trace_logger.propagate = True

        has_trace_handler = any(
            getattr(handler, "marker", "") == _MARKER_TRACE_FILE
            for handler in trace_logger.handlers
        )
        if not has_trace_handler:
            trace_handler = _MarkerRotatingFileHandler(
                _path_file_runtime_trace(),
                maxBytes=_LOG_MAX_BYTES,
                backupCount=_LOG_BACKUP_COUNT,
                encoding="utf-8",
                marker=_MARKER_TRACE_FILE,
            )
            trace_handler.setLevel(logging.DEBUG)
            trace_handler.setFormatter(formatter)
            trace_logger.addHandler(trace_handler)

        _state.ready = True


def new_operation_id(prefix: str) -> str:
    """Create a short operation identifier.

    Args:
        prefix (str): Operation prefix (e.g., "search", "item").

    Returns:
        str: Unique operation identifier.
    """
    return f"{prefix}-{uuid4().hex[:8]}"


# The signature is a deliberate public API used across the codebase; the
# many optional diagnostic fields are intentionally exposed individually.
def trace_event(  # pylint: disable=too-many-arguments
    operation: str,
    stage: str,
    *,
    expected: str | None = None,
    actual: str | None = None,
    op_id: str | None = None,
    level: int = logging.INFO,
    context: dict[str, Any] | None = None,
) -> str:
    """Emit a structured runtime trace event.

    Args:
        operation (str): Logical operation name.
        stage (str): Current stage in the operation.
        expected (str | None, optional): Expected behavior/checkpoint.
        actual (str | None, optional): Actual observed behavior.
        op_id (str | None, optional): Existing operation identifier.
        level (int, optional): Logging level.
        context (dict[str, Any] | None, optional): Additional fields.

    Returns:
        str: Operation identifier used for the emitted event.
    """
    setup_runtime_file_logging()
    operation_id = op_id or new_operation_id(operation)
    expected_text = expected or ""
    actual_text = actual or ""
    message = (
        f"TRACE op={operation} id={operation_id} stage={stage} "
        f"expected={expected_text!r} actual={actual_text!r}"
        f"{_format_context(context)}"
    )
    logging.getLogger(TRACE_LOGGER_NAME).log(level, message)
    return operation_id


class RuntimeWatchdog:
    """Watchdog that reports stalls when heartbeat updates stop.

    Call start() before long-running work, ping() at checkpoints, and stop()
    when the operation completes.
    """

    def __init__(
        self,
        operation: str,
        op_id: str,
        timeout_sec: float = 45.0,
        check_interval_sec: float = 15.0,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Initialize a runtime watchdog.

        Args:
            operation (str): Operation name.
            op_id (str): Correlation id.
            timeout_sec (float, optional): No-progress threshold.
            check_interval_sec (float, optional): Poll interval.
            context (dict[str, Any] | None, optional): Extra context fields.
        """
        self._config = _WatchConfig(
            operation=operation,
            op_id=op_id,
            context=context or {},
        )
        self._timing = _WatchTiming(
            timeout_sec=timeout_sec,
            check_interval_sec=check_interval_sec,
        )
        self._progress = _WatchProgress(
            last_progress_time=time.monotonic(),
            last_step="initialized",
        )
        self._active = threading.Event()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start watchdog monitoring in a daemon thread."""
        if self._active.is_set():
            return

        self._active.set()
        self._progress.last_progress_time = time.monotonic()
        trace_event(
            self._config.operation,
            "watchdog_started",
            expected=(f"heartbeat every <= {self._timing.timeout_sec:.0f}s"),
            actual=(
                f"check_interval=" f"{self._timing.check_interval_sec:.0f}s"
            ),
            op_id=self._config.op_id,
            level=logging.DEBUG,
            context=self._config.context,
        )

        self._thread = threading.Thread(
            target=self._watch_loop,
            name=(
                f"watchdog-{self._config.operation}-" f"{self._config.op_id}"
            ),
            daemon=True,
        )
        self._thread.start()

    def ping(self, step: str) -> None:
        """Register progress at a specific step.

        Args:
            step (str): Human-readable step marker.
        """
        with self._lock:
            self._progress.last_step = step
            self._progress.last_progress_time = time.monotonic()

        trace_event(
            self._config.operation,
            "heartbeat",
            expected="operation keeps progressing",
            actual=f"last_step={step}",
            op_id=self._config.op_id,
            level=logging.DEBUG,
            context=self._config.context,
        )

    def stop(self, final_step: str = "completed") -> None:
        """Stop watchdog monitoring.

        Args:
            final_step (str, optional): Final status marker.
        """
        if not self._active.is_set():
            return

        self._active.clear()
        with self._lock:
            self._progress.last_step = final_step
            self._progress.last_progress_time = time.monotonic()

        trace_event(
            self._config.operation,
            "watchdog_stopped",
            expected="watchdog exits after operation end",
            actual=f"final_step={final_step}",
            op_id=self._config.op_id,
            level=logging.DEBUG,
            context=self._config.context,
        )

    def _watch_loop(self) -> None:
        """Internal watchdog loop that emits stall warnings."""
        while self._active.is_set():
            time.sleep(self._timing.check_interval_sec)

            with self._lock:
                elapsed = time.monotonic() - self._progress.last_progress_time
                step = self._progress.last_step

            if elapsed >= self._timing.timeout_sec:
                trace_event(
                    self._config.operation,
                    "stall_warning",
                    expected=(
                        f"progress heartbeat <= "
                        f"{self._timing.timeout_sec:.0f}s"
                    ),
                    actual=(
                        f"no progress for {elapsed:.1f}s, " f"last_step={step}"
                    ),
                    op_id=self._config.op_id,
                    level=logging.WARNING,
                    context=self._config.context,
                )

                with self._lock:
                    self._progress.last_progress_time = time.monotonic()
