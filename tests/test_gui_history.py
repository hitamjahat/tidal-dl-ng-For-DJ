"""Regression tests for main-window history coordination."""

from __future__ import annotations

from typing import cast
from unittest.mock import Mock

from PySide6 import QtCore, QtGui
from tidalapi.album import Album
from tidalapi.media import Track

from tidal_dl_ng.gui.history import DOWNLOADED_MARKER, HistoryMixin
from tidal_dl_ng.helper.gui import HumanProxyModel
from tidal_dl_ng.history import HistoryService
from tidal_dl_ng.model.gui_data import StatusbarMessage


class _HistoryHost(QtCore.QObject, HistoryMixin):
    """Provide concrete model, service, and signal dependencies for tests."""

    s_statusbar_message = QtCore.Signal(object)

    def __init__(self, history_service: HistoryService) -> None:
        """Initialize a test host with an empty results model.

        Args:
            history_service (HistoryService): Mocked persistence service.

        Returns:
            None: The test host is ready for history actions.
        """
        super().__init__()
        self.history_service = history_service
        self.model_tr_results = QtGui.QStandardItemModel()
        self.proxy_tr_results = HumanProxyModel()
        self.proxy_tr_results.setSourceModel(self.model_tr_results)

    def append_result_row(
        self,
    ) -> tuple[QtCore.QModelIndex, list[QtGui.QStandardItem]]:
        """Append a result row and return its proxy index and items.

        Returns:
            tuple[QModelIndex, list[QStandardItem]]: Proxy index and row items.
        """
        row_items = [QtGui.QStandardItem() for _ in range(9)]
        self.model_tr_results.appendRow(row_items)
        source_index = self.model_tr_results.index(0, 0)
        return self.proxy_tr_results.mapFromSource(source_index), row_items


def _mock_history_service() -> tuple[HistoryService, Mock]:
    """Create a typed history-service mock.

    Returns:
        tuple[HistoryService, Mock]: Typed service view and assertion mock.
    """
    service_mock = Mock(spec=HistoryService)
    return cast("HistoryService", service_mock), service_mock


def _mock_track() -> Track:
    """Create a typed track mock with album source metadata.

    Returns:
        Track: Track test double accepted by the public handler.
    """
    album_mock = Mock(spec=Album)
    album_mock.id = "album-456"
    album_mock.name = "Album name"

    track_mock = Mock(spec=Track)
    track_mock.id = "track-123"
    track_mock.name = "Track name"
    track_mock.album = album_mock
    return cast("Track", track_mock)


def test_toggle_duplicate_prevention_uses_current_service_api() -> None:
    """The GUI should use the service's snake-case keyword API."""
    history_service, service_mock = _mock_history_service()
    host = _HistoryHost(history_service)
    messages: list[StatusbarMessage] = []

    def collect_message(message: object) -> None:
        """Collect one strongly typed status message.

        Args:
            message (object): Payload emitted by the Qt signal.

        Returns:
            None: Valid messages are appended to the local collection.
        """
        if isinstance(message, StatusbarMessage):
            messages.append(message)

    host.s_statusbar_message.connect(collect_message)
    host.on_toggle_duplicate_prevention(enabled=True)

    service_mock.update_settings.assert_called_once_with(
        prevent_duplicates=True,
    )
    assert messages[-1].message == "Duplicate prevention enabled."


def test_mark_track_as_downloaded_persists_and_updates_marker() -> None:
    """Successful persistence should set the downloaded-column marker."""
    history_service, service_mock = _mock_history_service()
    host = _HistoryHost(history_service)
    proxy_index, row_items = host.append_result_row()

    host.on_mark_track_as_downloaded(_mock_track(), proxy_index)

    service_mock.add_track_to_history.assert_called_once_with(
        track_id="track-123",
        source_type="album",
        source_id="album-456",
        source_name="Album name",
    )
    assert row_items[host.DOWNLOADED_COLUMN].text() == DOWNLOADED_MARKER
    assert row_items[host.DOWNLOADED_COLUMN].textAlignment() == int(
        QtCore.Qt.AlignmentFlag.AlignCenter,
    )


def test_unmark_missing_history_entry_preserves_marker() -> None:
    """A missing history record should leave the displayed marker intact."""
    history_service, service_mock = _mock_history_service()
    service_mock.remove_track_from_history.return_value = False
    host = _HistoryHost(history_service)
    proxy_index, row_items = host.append_result_row()
    downloaded_item = row_items[host.DOWNLOADED_COLUMN]
    downloaded_item.setText(DOWNLOADED_MARKER)

    host.on_mark_track_as_not_downloaded("track-123", proxy_index)

    assert downloaded_item.text() == DOWNLOADED_MARKER
