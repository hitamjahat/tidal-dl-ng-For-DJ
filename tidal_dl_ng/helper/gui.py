"""GUI helper utilities for TIDAL download manager.

This module provides small helper functions and reusable Qt widget classes
that support the main application windows. It groups:

- Data accessors for ``QTreeWidget`` / ``QTreeView`` items backed by
  ``tidalapi`` media objects stored in Qt ``UserRole`` data.
- ``FilterHeader``: a ``QHeaderView`` subclass that embeds filter line
  edits above each column for inline table filtering.
- ``HumanProxyModel``: a ``QSortFilterProxyModel`` subclass that sorts
  numeric substrings in a human-friendly way (e.g. ``"2" < "10"``) and
  supports multi-column AND filtering.

All UI code here is intentionally decoupled from application logic; the
helpers only read/write Qt model data and never perform downloads.
"""

import re
from typing import cast

from PySide6 import QtCore, QtGui, QtWidgets
from tidalapi import Album, Mix, Playlist, Track, UserPlaylist, Video
from tidalapi.artist import Artist
from tidalapi.media import Quality
from tidalapi.playlist import Folder

from tidal_dl_ng.constants import QualityVideo

# Union of every tidalapi media type that can be attached to a Qt item.
MediaItem = (
    Track
    | Video
    | Album
    | Artist
    | Mix
    | Playlist
    | UserPlaylist
    | Folder
    | str
)


def get_table_data(item: QtWidgets.QTreeWidgetItem, column: int) -> MediaItem:
    """Return the user data stored on a tree widget item.

    Args:
        item (QTreeWidgetItem): The item to read from.
        column (int): Column index that holds the data.

    Returns:
        MediaItem: The object previously stored via ``set_table_data``.
    """
    result: MediaItem = item.data(column, QtCore.Qt.ItemDataRole.UserRole)
    return result


def get_table_text(item: QtWidgets.QTreeWidgetItem, column: int) -> str:
    """Return the displayed text of a tree widget item cell.

    Args:
        item (QTreeWidgetItem): The item to read from.
        column (int): Column index to read.

    Returns:
        str: The cell text.
    """
    result: str = item.text(column)
    return result


def get_results_media_item(
    index: QtCore.QModelIndex,
    proxy: QtCore.QSortFilterProxyModel,
    model: QtGui.QStandardItemModel,
) -> MediaItem:
    """Extract the media object backing a results table row.

    The media object is stored in the ``UserRole`` of the dedicated
    "obj" column (column index 1); the proxy index is mapped back to
    the source model before reading.

    Args:
        index (QModelIndex): Proxy model index of the row.
        proxy (QSortFilterProxyModel): Active proxy model.
        model (QStandardItemModel): Underlying source model.

    Returns:
        MediaItem: The media object attached to the row.
    """
    source_index = proxy.mapToSource(index.siblingAtColumn(1))
    item: QtGui.QStandardItem = model.itemFromIndex(source_index)
    result: MediaItem = item.data(QtCore.Qt.ItemDataRole.UserRole)
    return result


def get_user_list_media_item(
    item: QtWidgets.QTreeWidgetItem,
) -> MediaItem:
    """Return the media object stored in a user-list tree item.

    Args:
        item (QTreeWidgetItem): The user-list item to read.

    Returns:
        MediaItem: The stored media object or label string.
    """
    result: MediaItem = get_table_data(item, 1)
    return result


def get_queue_download_media(
    item: QtWidgets.QTreeWidgetItem,
) -> MediaItem:
    """Return the media object stored in a download-queue item.

    Args:
        item (QTreeWidgetItem): The queue item to read.

    Returns:
        MediaItem: The stored media object.
    """
    result: MediaItem = get_table_data(item, 1)
    return result


def get_queue_download_quality(
    item: QtWidgets.QTreeWidgetItem,
    column: int,
) -> str:
    """Return the quality text stored in a download-queue column.

    Args:
        item (QTreeWidgetItem): The queue item to read.
        column (int): Column index holding the quality text.

    Returns:
        str: The quality label.
    """
    result: str = get_table_text(item, column)
    return result


def get_queue_download_quality_audio(
    item: QtWidgets.QTreeWidgetItem,
) -> Quality:
    """Return the audio quality enum for a download-queue item.

    Args:
        item (QTreeWidgetItem): The queue item to read.

    Returns:
        Quality: The parsed audio quality value.
    """
    result: Quality = cast("Quality", get_queue_download_quality(item, 4))
    return result


def get_queue_download_quality_video(
    item: QtWidgets.QTreeWidgetItem,
) -> QualityVideo:
    """Return the video quality enum for a download-queue item.

    Args:
        item (QTreeWidgetItem): The queue item to read.

    Returns:
        QualityVideo: The parsed video quality value.
    """
    result: QualityVideo = cast(
        "QualityVideo", get_queue_download_quality(item, 5)
    )
    return result


def set_table_data(
    item: QtWidgets.QTreeWidgetItem,
    data: MediaItem,
    column: int,
) -> None:
    """Store a media object on a tree widget item.

    Args:
        item (QTreeWidgetItem): The item to write to.
        data (MediaItem): The object to attach.
        column (int): Column index to store the data in.
    """
    item.setData(column, QtCore.Qt.ItemDataRole.UserRole, data)


def set_results_media(
    item: QtWidgets.QTreeWidgetItem,
    media: Track | Video | Album | Artist,
) -> None:
    """Attach a results media object to a tree widget item.

    Args:
        item (QTreeWidgetItem): The item to write to.
        media (Track | Video | Album | Artist): Media to attach.
    """
    set_table_data(item, media, 1)


def set_user_list_media(
    item: QtWidgets.QTreeWidgetItem,
    media: MediaItem,
) -> None:
    """Attach a user-list media object to a tree widget item.

    Args:
        item (QTreeWidgetItem): The item to write to.
        media (MediaItem): Media or label to attach.
    """
    set_table_data(item, media, 1)


def set_queue_download_media(
    item: QtWidgets.QTreeWidgetItem,
    media: MediaItem,
) -> None:
    """Attach a download-queue media object to a tree widget item.

    Args:
        item (QTreeWidgetItem): The item to write to.
        media (MediaItem): Media to attach.
    """
    set_table_data(item, media, 1)


class FilterHeader(QtWidgets.QHeaderView):
    """A ``QHeaderView`` that embeds filter line edits per column.

    Each visible column gets a ``QLineEdit`` positioned above the header
    section. Typing in any editor emits ``filter_activated`` so the
    owning view can re-apply its proxy filter.
    """

    filter_activated = QtCore.Signal()

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        """Initialize the header with per-column filter editors.

        Args:
            parent (QWidget | None, optional): Parent widget.
                Defaults to None.
        """
        super().__init__(QtCore.Qt.Orientation.Horizontal, parent)
        self._editors: list[QtWidgets.QLineEdit] = []
        self._padding: int = 4
        self.setCascadingSectionResizes(True)
        self.setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Interactive)
        self.setStretchLastSection(True)
        self.setDefaultAlignment(
            QtCore.Qt.AlignmentFlag.AlignLeft
            | QtCore.Qt.AlignmentFlag.AlignVCenter
        )
        self.setSortIndicatorShown(False)
        self.setSectionsMovable(True)
        self.sectionResized.connect(self.adjust_positions)
        if isinstance(parent, QtWidgets.QAbstractScrollArea):
            parent.horizontalScrollBar().valueChanged.connect(
                self.adjust_positions
            )

    def set_filter_boxes(self, count: int) -> None:
        """Create ``count`` filter line edits, one per column.

        Args:
            count (int): Number of filter editors to create.
        """
        while self._editors:
            editor = self._editors.pop()
            editor.deleteLater()

        for _ in range(count):
            parent_widget = cast(
                "QtWidgets.QWidget", self.parent()
            )
            editor = QtWidgets.QLineEdit(parent_widget)
            editor.setPlaceholderText("Filter")
            editor.setClearButtonEnabled(True)
            editor.returnPressed.connect(self.filter_activated.emit)
            self._editors.append(editor)

        self.adjust_positions()

    def sizeHint(self) -> QtCore.QSize:
        """Return the header size including editor height.

        Returns:
            QSize: The augmented size hint.
        """
        size = super().sizeHint()

        if self._editors:
            height = self._editors[0].sizeHint().height()
            size.setHeight(size.height() + height + self._padding)

        return size

    def updateGeometries(self) -> None:
        """Update viewport margins to fit the embedded editors."""
        if self._editors:
            height = self._editors[0].sizeHint().height()
            self.setViewportMargins(0, 0, 0, height + self._padding)
        else:
            self.setViewportMargins(0, 0, 0, 0)

        super().updateGeometries()
        self.adjust_positions()

    def adjust_positions(self) -> None:
        """Reposition every filter editor above its column section."""
        for index, editor in enumerate(self._editors):
            height = editor.sizeHint().height()
            editor.move(
                self.sectionPosition(index) - self.offset() + 2,
                height + (self._padding // 2),
            )
            editor.resize(self.sectionSize(index), height)

    def filter_text(self, index: int) -> str:
        """Return the text of the filter editor at ``index``.

        Args:
            index (int): Editor column index.

        Returns:
            str: The editor text, or empty string if out of range.
        """
        if 0 <= index < len(self._editors):
            return self._editors[index].text()

        return ""

    def set_filter_text(self, index: int, text: str) -> None:
        """Set the text of the filter editor at ``index``.

        Args:
            index (int): Editor column index.
            text (str): Text to assign.
        """
        if 0 <= index < len(self._editors):
            self._editors[index].setText(text)

    def clear_filters(self) -> None:
        """Clear the text of every filter editor."""
        for editor in self._editors:
            editor.clear()


class HumanProxyModel(QtCore.QSortFilterProxyModel):
    """A proxy model with human-friendly numeric sorting and filtering.

    Sorting treats embedded number groups as integers so that, for
    example, ``"track 2"`` sorts before ``"track 10"``. Filtering
    supports multiple column patterns that are combined with a logical
    AND.
    """

    def _human_key(self, key: str) -> tuple[str | float, ...]:
        """Split a string into alternating text/number tokens.

        Args:
            key (str): The raw string to tokenize.

        Returns:
            tuple[str | float, ...]: Tokens with numbers as floats.
        """
        parts = re.split(r"(\d*\.\d+|\d+)", key)
        return tuple(
            e.swapcase() if i % 2 == 0 else float(e)
            for i, e in enumerate(parts)
        )

    def lessThan(
        self,
        source_left: QtCore.QModelIndex | QtCore.QPersistentModelIndex,
        source_right: QtCore.QModelIndex | QtCore.QPersistentModelIndex,
    ) -> bool:
        """Compare two source indices using human-friendly ordering.

        Args:
            source_left (QModelIndex): Left index to compare.
            source_right (QModelIndex): Right index to compare.

        Returns:
            bool: True when the left value sorts before the right.
        """
        data_left = source_left.data()
        data_right = source_right.data()

        if isinstance(data_left, str) and isinstance(data_right, str):
            return self._human_key(data_left) < self._human_key(data_right)

        return super().lessThan(source_left, source_right)

    @property
    def filters(self) -> list[tuple[int, str]]:
        """Return the active column/text filter pairs."""
        if not hasattr(self, "_filters"):
            self._filters: list[tuple[int, str]] = []

        return self._filters

    @filters.setter
    def filters(self, filters: list[tuple[int, str]]) -> None:
        """Replace the active filters and refresh the view.

        Args:
            filters (list[tuple[int, str]]): New (column, pattern)
                pairs.
        """
        self._filters = filters
        self.invalidateFilter()

    def filterAcceptsRow(
        self,
        source_row: int,
        source_parent: QtCore.QModelIndex | QtCore.QPersistentModelIndex,
    ) -> bool:
        """Decide whether a source row should remain visible.

        A row is accepted when any of its descendant rows match, or when
        every active column pattern matches the row's cell text. With no
        active filters all rows are accepted.

        Args:
            source_row (int): Row index in the source model.
            source_parent (QModelIndex): Parent index of the row.

        Returns:
            bool: True when the row should be shown.
        """
        model = self.sourceModel()
        source_index = model.index(source_row, 0, source_parent)

        # Show top level children if any descendant matches.
        for child_row in range(model.rowCount(source_index)):
            if self.filterAcceptsRow(child_row, source_index):
                return True

        result: list[bool] = []

        # Filter for actual needle.
        for column, text in self.filters:
            if 0 <= column < self.columnCount():
                cell_index = model.index(source_row, column, source_parent)
                if (data := cell_index.data()) is not None:
                    matches = bool(
                        re.search(
                            rf"{text}",
                            data,
                            re.MULTILINE | re.IGNORECASE,
                        )
                    )
                    # Append results to list for AND operator.
                    result.append(matches)

        # If no filter set, just set the result to True.
        if not result:
            result.append(True)

        return all(result)
