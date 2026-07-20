"""Hover Event Manager with Debounce Logic.

This module provides a robust hover event management system for the track list,
implementing debouncing to prevent UI flickering and excessive updates during
rapid mouse movements.

The HoverManager intercepts mouse movement events and triggers callbacks only
after the mouse has remained stationary over an item for a configurable delay.

Architecture:
    - HoverManager: Main coordinator with debounce timer
    - Event filter for capturing mouse movements
    - Signal-based callbacks for decoupled communication

Performance:
    - Configurable debounce delay (default: 350ms)
    - Automatic cleanup of pending timers
    - Thread-safe signal emissions
"""

from contextlib import suppress
from typing import cast, override

from PySide6 import QtCore, QtGui, QtWidgets
from shiboken6 import Shiboken
from tidalapi import Album, Mix, Playlist, Track, Video
from tidalapi.artist import Artist

from tidal_dl_ng.helper.gui import get_results_media_item
from tidal_dl_ng.logger import logger_gui

MediaItem = Track | Video | Album | Mix | Playlist | Artist


class HoverManager(QtCore.QObject):
    """Manages hover events with debouncing to prevent UI flickering.

    This class implements an event filter that intercepts mouse movements over
    a QTreeView and emits signals after a configurable delay to prevent rapid
    updates when the user is just scanning through the list.

    Signals:
        s_hover_confirmed (object): Emitted when hover is confirmed
            after debounce delay.
        s_hover_left: Emitted when mouse leaves the tracked widget.

    Attributes:
        debounce_delay_ms (int): Delay in milliseconds before
            confirming hover.
        tree_view (QTreeView): The tree view to monitor.
        proxy_model (QSortFilterProxyModel): Proxy model for the
            tree view.
        source_model (QStandardItemModel): Source model for the
            tree view.
        debounce_timer (QTimer): Timer for debouncing hover events.
        last_hovered_media (MediaItem | None): Last media item
            hovered.
    """

    # Signals
    s_hover_confirmed: QtCore.Signal = QtCore.Signal(object)
    s_hover_left: QtCore.Signal = QtCore.Signal()

    def __init__(
        self,
        tree_view: QtWidgets.QTreeView,
        proxy_model: QtCore.QSortFilterProxyModel,
        source_model: QtGui.QStandardItemModel,
        debounce_delay_ms: int = 350,
        parent: QtCore.QObject | None = None,
    ) -> None:
        """Initialize the HoverManager.

        Args:
            tree_view (QTreeView): The tree view to monitor for
                hover events.
            proxy_model (QSortFilterProxyModel): Proxy model wrapping
                the source model.
            source_model (QStandardItemModel): Source model containing
                the data.
            debounce_delay_ms (int, optional): Debounce delay in
                milliseconds. Defaults to 350.
            parent (QObject | None, optional): Parent QObject.
                Defaults to None.
        """
        super().__init__(parent)

        self.debounce_delay_ms: int = debounce_delay_ms
        self.tree_view: QtWidgets.QTreeView | None = tree_view
        self.proxy_model: QtCore.QSortFilterProxyModel = proxy_model
        self.source_model: QtGui.QStandardItemModel = source_model
        self.last_hovered_media: MediaItem | None = None

        # Debounce timer (single-shot)
        self.debounce_timer: QtCore.QTimer = QtCore.QTimer(self)
        self.debounce_timer.setSingleShot(True)
        self.debounce_timer.setInterval(self.debounce_delay_ms)
        self.debounce_timer.timeout.connect(self._on_debounce_timeout)

        # Track hover state
        self.pending_media: MediaItem | None = None

        # Install event filter on viewport (where mouse events occur)
        self.tree_view.viewport().installEventFilter(self)
        self.tree_view.viewport().setMouseTracking(True)
        self.tree_view.destroyed.connect(self.stop)

    def stop(self) -> None:
        """Detach event filters and stop timers to avoid dangling refs."""
        tree_view = self.tree_view
        if tree_view is not None and self._is_valid(tree_view):
            with suppress(RuntimeError):
                viewport = tree_view.viewport()
                if self._is_valid(viewport):
                    viewport.removeEventFilter(self)
        self.tree_view = None

        if self.debounce_timer.isActive():
            self.debounce_timer.stop()
        self.pending_media = None

    @override
    def eventFilter(
        self, watched: QtCore.QObject, event: QtCore.QEvent
    ) -> bool:
        """Filter events to detect mouse movements over tree items."""
        tree_view = self.tree_view
        viewport = (
            tree_view.viewport()
            if tree_view is not None and self._is_valid(tree_view)
            else None
        )
        if viewport is not None and watched == viewport:
            if event.type() == QtCore.QEvent.Type.MouseMove:
                mouse_event = cast("QtGui.QMouseEvent", event)
                self._handle_mouse_move(mouse_event)
            elif event.type() == QtCore.QEvent.Type.Leave:
                self._handle_mouse_leave()

        # Don't consume the event - let it propagate
        return False

    @staticmethod
    def _is_valid(widget: QtCore.QObject | None) -> bool:
        """Return True if the Qt object still owns a C++ instance."""
        return widget is not None and Shiboken.isValid(widget)

    def _handle_mouse_move(self, event: QtGui.QMouseEvent) -> None:
        """Handle mouse move events over the tree view.

        Args:
            event (QMouseEvent): The mouse move event.
        """
        # Get the index under the cursor
        if (tree_view := self.tree_view) is None:
            return
        pos = event.position().toPoint()
        index = tree_view.indexAt(pos)

        if not index.isValid():
            # Mouse is not over a valid item
            self._cancel_pending_hover()
            return

        try:
            # Extract media from the index
            media = get_results_media_item(
                index, self.proxy_model, self.source_model
            )
        except (AttributeError, TypeError, ValueError) as err:
            logger_gui.debug("Error extracting media from hover: %s", err)
            self._cancel_pending_hover()
            return

        if not media:
            self._cancel_pending_hover()
            return

        # Check if we're hovering over a different item
        if media != self.pending_media:
            # Cancel previous timer and start new one
            self.pending_media = media
            self.debounce_timer.stop()
            self.debounce_timer.start()

    def _handle_mouse_leave(self) -> None:
        """Handle mouse leaving the tree view."""
        self._cancel_pending_hover()
        self.s_hover_left.emit()

    def _cancel_pending_hover(self) -> None:
        """Cancel any pending hover confirmation."""
        self.debounce_timer.stop()
        self.pending_media = None

    def _on_debounce_timeout(self) -> None:
        """Handle debounce timer timeout - hover is confirmed."""
        if self.pending_media:
            self.last_hovered_media = self.pending_media
            self.s_hover_confirmed.emit(self.pending_media)

    def reset(self) -> None:
        """Reset the hover manager state."""
        self._cancel_pending_hover()
        self.last_hovered_media = None

    def set_debounce_delay(self, delay_ms: int) -> None:
        """Change the debounce delay.

        Args:
            delay_ms (int): New delay in milliseconds.
        """
        self.debounce_delay_ms = delay_ms
        self.debounce_timer.setInterval(delay_ms)
        logger_gui.debug("Hover debounce delay set to %sms", delay_ms)
