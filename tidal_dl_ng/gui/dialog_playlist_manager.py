"""Responsive dialog for managing a track's playlist memberships.

The dialog uses Qt's model/view architecture instead of creating one widget
hierarchy per playlist.  API mutations run on ``QThreadPool`` workers and
return immutable transaction results through a Qt signal, keeping all model
and widget updates on the GUI thread.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, override

from PySide6 import QtCore, QtGui, QtWidgets
from tidalapi.exceptions import TidalAPIError

from tidal_dl_ng.helper.playlist_api import (
    add_track_to_playlist,
    remove_track_from_playlist,
)
from tidal_dl_ng.logger import logger_gui
from tidal_dl_ng.worker import Worker

if TYPE_CHECKING:
    from tidalapi.media import Track
    from tidalapi.session import Session

    from tidal_dl_ng.gui.playlist_membership import ThreadSafePlaylistCache


SPACING_SMALL: int = 6
SPACING_MEDIUM: int = 12
SPACING_LARGE: int = 24
TITLE_POINT_SIZE: int = 20
MINIMUM_DIALOG_WIDTH: int = 520
MINIMUM_DIALOG_HEIGHT: int = 420
DEFAULT_DIALOG_WIDTH: int = 640
DEFAULT_DIALOG_HEIGHT: int = 600

PLAYLIST_OPERATION_ERRORS: tuple[type[Exception], ...] = (
    AttributeError,
    OSError,
    RuntimeError,
    TidalAPIError,
    TypeError,
    ValueError,
)

type ModelIndex = QtCore.QModelIndex | QtCore.QPersistentModelIndex

ROOT_MODEL_INDEX: QtCore.QModelIndex = QtCore.QModelIndex()


class PlaylistAction(StrEnum):
    """Supported playlist membership mutations."""

    ADD = "add"
    REMOVE = "remove"


@dataclass(slots=True)
class PlaylistMembership:
    """Mutable presentation state for one playlist row."""

    playlist_id: str
    name: str
    item_count: int
    checked: bool
    pending: bool = False
    error_message: str = ""


@dataclass(frozen=True, slots=True)
class PlaylistTransaction:
    """Immutable request executed by a worker thread."""

    playlist_id: str
    track_id: str
    action: PlaylistAction


@dataclass(frozen=True, slots=True)
class PlaylistTransactionResult:
    """Immutable worker result delivered to the GUI thread."""

    request: PlaylistTransaction
    success: bool
    message: str = ""


@dataclass(frozen=True, slots=True)
class PlaylistDialogWidgets:
    """Widget references created by the dialog's UI builder."""

    title_label: QtWidgets.QLabel
    track_label: QtWidgets.QLabel
    search_edit: QtWidgets.QLineEdit
    list_view: QtWidgets.QListView
    empty_label: QtWidgets.QLabel
    status_label: QtWidgets.QLabel
    progress_bar: QtWidgets.QProgressBar
    close_button: QtWidgets.QPushButton
    content_layout: QtWidgets.QVBoxLayout


class PlaylistMembershipModel(QtCore.QAbstractListModel):
    """Checkable list model representing playlist membership state."""

    membership_toggled = QtCore.Signal(str, bool)

    def __init__(
        self,
        memberships: list[PlaylistMembership],
        parent: QtCore.QObject | None = None,
    ) -> None:
        """Initialize the model with sorted membership records.

        Args:
            memberships (list[PlaylistMembership]): Rows to expose.
            parent (QtCore.QObject | None): QObject owner.

        Returns:
            None: The model owns the supplied row records.
        """
        super().__init__(parent)
        self._memberships: list[PlaylistMembership] = memberships
        self._rows_by_id: dict[str, int] = {
            membership.playlist_id: row
            for row, membership in enumerate(memberships)
        }

    @override
    def rowCount(
        self,
        parent: ModelIndex = ROOT_MODEL_INDEX,
    ) -> int:
        """Return the number of top-level playlist rows.

        Args:
            parent (ModelIndex): Parent index, unused for a flat model.

        Returns:
            int: Playlist count for root indexes, otherwise zero.
        """
        return 0 if parent.isValid() else len(self._memberships)

    @override
    def data(
        self,
        index: ModelIndex,
        role: int = QtCore.Qt.ItemDataRole.DisplayRole,
    ) -> object:
        """Return display, check, accessibility, and status data.

        Args:
            index (ModelIndex): Requested model index.
            role (int): Qt item-data role.

        Returns:
            object: Role-specific value, or ``None`` for invalid requests.
        """
        if (membership := self._membership_at(index)) is None:
            return None

        result: object = None
        match role:
            case QtCore.Qt.ItemDataRole.DisplayRole:
                result = self._display_text(membership)
            case QtCore.Qt.ItemDataRole.CheckStateRole:
                result = (
                    QtCore.Qt.CheckState.Checked
                    if membership.checked
                    else QtCore.Qt.CheckState.Unchecked
                )
            case QtCore.Qt.ItemDataRole.UserRole:
                result = membership.playlist_id
            case QtCore.Qt.ItemDataRole.ToolTipRole:
                result = self._tooltip_text(membership)
            case QtCore.Qt.ItemDataRole.AccessibleTextRole:
                state = "included" if membership.checked else "not included"
                result = f"{membership.name}, {state}"
            case QtCore.Qt.ItemDataRole.FontRole if membership.pending:
                font = QtGui.QFont()
                font.setItalic(True)
                result = font
            case QtCore.Qt.ItemDataRole.ForegroundRole if (
                membership.error_message
            ):
                palette = QtWidgets.QApplication.palette()
                result = palette.brush(
                    QtGui.QPalette.ColorRole.BrightText,
                )
            case _:
                pass
        return result

    @override
    def flags(self, index: ModelIndex) -> QtCore.Qt.ItemFlag:
        """Return interactive flags for a playlist row.

        Args:
            index (ModelIndex): Requested model index.

        Returns:
            QtCore.Qt.ItemFlag: Selectable/checkable flags when not pending.
        """
        if (membership := self._membership_at(index)) is None:
            return QtCore.Qt.ItemFlag.NoItemFlags

        flags = (
            QtCore.Qt.ItemFlag.ItemIsEnabled
            | QtCore.Qt.ItemFlag.ItemIsSelectable
        )
        if not membership.pending:
            flags |= QtCore.Qt.ItemFlag.ItemIsUserCheckable
        return flags

    @override
    def setData(
        self,
        index: ModelIndex,
        value: object,
        role: int = QtCore.Qt.ItemDataRole.EditRole,
    ) -> bool:
        """Apply a user-requested check-state change.

        Args:
            index (ModelIndex): Playlist row being changed.
            value (object): New Qt check-state value.
            role (int): Data role associated with the edit.

        Returns:
            bool: ``True`` when a new transaction was requested.
        """
        membership = self._membership_at(index)
        if (
            membership is None
            or membership.pending
            or role != QtCore.Qt.ItemDataRole.CheckStateRole
        ):
            return False

        checked = value in {
            QtCore.Qt.CheckState.Checked,
            QtCore.Qt.CheckState.Checked.value,
        }
        if checked == membership.checked:
            return False

        membership.checked = checked
        membership.pending = True
        membership.error_message = ""
        self._emit_row_changed(index.row())
        self.membership_toggled.emit(membership.playlist_id, checked)
        return True

    def finish_transaction(
        self,
        playlist_id: str,
        checked: bool,
        error_message: str = "",
    ) -> None:
        """Apply a completed transaction to one model row.

        Args:
            playlist_id (str): Playlist whose request completed.
            checked (bool): Final membership state.
            error_message (str): User-facing failure details.

        Returns:
            None: Matching row state and roles are refreshed.
        """
        if (row := self._rows_by_id.get(playlist_id)) is None:
            return
        membership = self._memberships[row]
        membership.checked = checked
        membership.pending = False
        membership.error_message = error_message
        self._emit_row_changed(row)

    def playlist_name(self, playlist_id: str) -> str:
        """Return a playlist display name by identifier.

        Args:
            playlist_id (str): Playlist identifier.

        Returns:
            str: Display name, falling back to the identifier.
        """
        if (row := self._rows_by_id.get(playlist_id)) is None:
            return playlist_id
        return self._memberships[row].name

    def _membership_at(self, index: ModelIndex) -> PlaylistMembership | None:
        """Return a row record for a valid model index.

        Args:
            index (ModelIndex): Index to resolve.

        Returns:
            PlaylistMembership | None: Matching record or ``None``.
        """
        if not index.isValid() or not 0 <= index.row() < len(
            self._memberships
        ):
            return None
        return self._memberships[index.row()]

    @staticmethod
    def _display_text(membership: PlaylistMembership) -> str:
        """Build concise primary text for a playlist row."""
        item_word = "item" if membership.item_count == 1 else "items"
        suffix = " — Saving…" if membership.pending else ""
        return (
            f"{membership.name}  ({membership.item_count} {item_word}){suffix}"
        )

    @staticmethod
    def _tooltip_text(membership: PlaylistMembership) -> str:
        """Build tooltip text describing a playlist row's state."""
        if membership.error_message:
            return membership.error_message
        if membership.pending:
            return "Saving playlist membership…"
        return "Check to include this track in the playlist."

    def _emit_row_changed(self, row: int) -> None:
        """Notify views that all presentation roles changed for a row."""
        index = self.index(row, 0)
        roles = [
            QtCore.Qt.ItemDataRole.DisplayRole,
            QtCore.Qt.ItemDataRole.CheckStateRole,
            QtCore.Qt.ItemDataRole.ToolTipRole,
            QtCore.Qt.ItemDataRole.FontRole,
            QtCore.Qt.ItemDataRole.ForegroundRole,
            QtCore.Qt.ItemDataRole.AccessibleTextRole,
        ]
        self.dataChanged.emit(index, index, roles)


class PlaylistFilterProxyModel(QtCore.QSortFilterProxyModel):
    """Case-insensitive filter and sorter for playlist rows."""

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        """Initialize sorting and filtering defaults.

        Args:
            parent (QtCore.QObject | None): QObject owner.

        Returns:
            None: Proxy settings are initialized in place.
        """
        super().__init__(parent)
        self.setDynamicSortFilter(True)
        self.setFilterCaseSensitivity(
            QtCore.Qt.CaseSensitivity.CaseInsensitive,
        )
        self.setSortCaseSensitivity(
            QtCore.Qt.CaseSensitivity.CaseInsensitive,
        )
        self.setFilterRole(QtCore.Qt.ItemDataRole.DisplayRole)


class PlaylistManagerDialog(QtWidgets.QDialog):
    """Manage one track's playlist memberships without blocking Qt."""

    playlist_added = QtCore.Signal(str, str)
    playlist_removed = QtCore.Signal(str, str)
    transaction_finished = QtCore.Signal(object)

    def __init__(
        self,
        track: Track,
        cache: ThreadSafePlaylistCache,
        session: Session,
        threadpool: QtCore.QThreadPool,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        """Initialize the playlist manager dialog.

        Args:
            track (Track): Track whose memberships will be edited.
            cache (ThreadSafePlaylistCache): Preloaded membership cache.
            session (Session): Authenticated TIDAL session.
            threadpool (QtCore.QThreadPool): Pool for API mutations.
            parent (QtWidgets.QWidget | None): Owning window.

        Returns:
            None: The responsive dialog is fully initialized.
        """
        super().__init__(parent)
        self.track: Track = track
        self.cache: ThreadSafePlaylistCache = cache
        self.session: Session = session
        self.threadpool: QtCore.QThreadPool = threadpool
        track_id = track.id
        if not isinstance(track_id, int | str) or not track_id:
            message = "The playlist manager requires a valid track ID."
            raise ValueError(message)
        self._track_id: str = str(track_id)
        self._original_states: dict[str, bool] = {}
        self._pending_tasks: dict[str, Worker] = {}
        self._accept_results: bool = True

        memberships = self._build_memberships()
        self.membership_model = PlaylistMembershipModel(memberships, self)
        self.proxy_model = PlaylistFilterProxyModel(self)
        self.proxy_model.setSourceModel(self.membership_model)
        self.proxy_model.sort(0)

        self.widgets = self._build_ui(str(track.name))
        self.container_layout = self.widgets.content_layout
        self._connect_signals()
        self._update_empty_state()

    def _build_memberships(self) -> list[PlaylistMembership]:
        """Create sorted model records from the membership cache.

        Returns:
            list[PlaylistMembership]: Alphabetically sorted playlist rows.
        """
        memberships: list[PlaylistMembership] = []
        for playlist_id in self.cache.get_all_playlists():
            checked = self.cache.is_track_in_playlist(
                self._track_id,
                playlist_id,
            )
            self._original_states[playlist_id] = checked
            memberships.append(
                PlaylistMembership(
                    playlist_id=playlist_id,
                    name=self.cache.get_playlist_name(playlist_id),
                    item_count=self.cache.get_playlist_count(playlist_id),
                    checked=checked,
                ),
            )
        memberships.sort(key=lambda membership: membership.name.casefold())
        return memberships

    def _build_ui(self, track_title: str) -> PlaylistDialogWidgets:
        """Build the dialog exclusively with responsive Qt layouts.

        Args:
            track_title (str): Plain-text track title to display.

        Returns:
            PlaylistDialogWidgets: References needed by dialog logic.
        """
        root_layout = self._create_root_layout()
        title_label, track_label = self._build_header(
            root_layout,
            track_title,
        )
        search_edit, list_view, empty_label, content_layout = (
            self._build_content(root_layout)
        )
        status_label, progress_bar, close_button = self._build_footer(
            root_layout,
        )
        return PlaylistDialogWidgets(
            title_label=title_label,
            track_label=track_label,
            search_edit=search_edit,
            list_view=list_view,
            empty_label=empty_label,
            status_label=status_label,
            progress_bar=progress_bar,
            close_button=close_button,
            content_layout=content_layout,
        )

    def _create_root_layout(self) -> QtWidgets.QVBoxLayout:
        """Configure dialog geometry and return its root layout."""
        self.setObjectName("PlaylistManagerDialog")
        self.setWindowTitle(self.tr("Manage playlists"))
        self.setMinimumSize(MINIMUM_DIALOG_WIDTH, MINIMUM_DIALOG_HEIGHT)
        self.resize(DEFAULT_DIALOG_WIDTH, DEFAULT_DIALOG_HEIGHT)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(
            SPACING_LARGE,
            SPACING_LARGE,
            SPACING_LARGE,
            SPACING_LARGE,
        )
        layout.setSpacing(SPACING_MEDIUM)
        return layout

    def _build_header(
        self,
        root_layout: QtWidgets.QVBoxLayout,
        track_title: str,
    ) -> tuple[QtWidgets.QLabel, QtWidgets.QLabel]:
        """Build and attach the title and track-name panel."""
        header_panel = QtWidgets.QFrame(self)
        header_panel.setObjectName("playlistHeaderPanel")
        header_layout = QtWidgets.QVBoxLayout(header_panel)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(SPACING_SMALL)

        title_label = QtWidgets.QLabel(
            self.tr("Manage playlist membership"),
            header_panel,
        )
        title_label.setObjectName("playlistDialogTitle")
        title_font = QtGui.QFont(self.font())
        title_font.setPointSize(TITLE_POINT_SIZE)
        title_font.setWeight(QtGui.QFont.Weight.DemiBold)
        title_label.setFont(title_font)

        track_label = QtWidgets.QLabel(track_title, header_panel)
        track_label.setObjectName("playlistTrackTitle")
        track_label.setWordWrap(True)
        track_label.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.TextSelectableByMouse,
        )
        header_layout.addWidget(title_label)
        header_layout.addWidget(track_label)
        root_layout.addWidget(header_panel)
        return title_label, track_label

    def _build_content(
        self,
        root_layout: QtWidgets.QVBoxLayout,
    ) -> tuple[
        QtWidgets.QLineEdit,
        QtWidgets.QListView,
        QtWidgets.QLabel,
        QtWidgets.QVBoxLayout,
    ]:
        """Build and attach the searchable model/view content panel."""
        content_panel = QtWidgets.QGroupBox(
            self.tr("Playlists"),
            self,
        )
        content_layout = QtWidgets.QVBoxLayout(content_panel)
        content_layout.setContentsMargins(
            SPACING_MEDIUM,
            SPACING_MEDIUM,
            SPACING_MEDIUM,
            SPACING_MEDIUM,
        )
        content_layout.setSpacing(SPACING_MEDIUM)

        search_edit = QtWidgets.QLineEdit(content_panel)
        search_edit.setObjectName("playlistSearchEdit")
        search_edit.setPlaceholderText(self.tr("Filter playlists…"))
        search_edit.setClearButtonEnabled(True)
        search_edit.setAccessibleName(self.tr("Filter playlists"))

        list_view = QtWidgets.QListView(content_panel)
        list_view.setObjectName("playlistMembershipView")
        list_view.setModel(self.proxy_model)
        list_view.setAlternatingRowColors(True)
        list_view.setUniformItemSizes(True)
        list_view.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.SingleSelection,
        )
        list_view.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers,
        )
        list_view.setAccessibleName(self.tr("Playlist memberships"))

        empty_label = QtWidgets.QLabel(content_panel)
        empty_label.setObjectName("playlistEmptyState")
        empty_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        empty_label.setWordWrap(True)

        content_layout.addWidget(search_edit)
        content_layout.addWidget(list_view, stretch=1)
        content_layout.addWidget(empty_label, stretch=1)
        root_layout.addWidget(content_panel, stretch=1)
        return search_edit, list_view, empty_label, content_layout

    def _build_footer(
        self,
        root_layout: QtWidgets.QVBoxLayout,
    ) -> tuple[
        QtWidgets.QLabel,
        QtWidgets.QProgressBar,
        QtWidgets.QPushButton,
    ]:
        """Build and attach progress, status, and close controls."""
        footer_panel = QtWidgets.QFrame(self)
        footer_panel.setObjectName("playlistFooterPanel")
        footer_layout = QtWidgets.QHBoxLayout(footer_panel)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        footer_layout.setSpacing(SPACING_MEDIUM)

        progress_bar = QtWidgets.QProgressBar(footer_panel)
        progress_bar.setObjectName("playlistTransactionProgress")
        progress_bar.setRange(0, 0)
        progress_bar.setTextVisible(False)
        progress_bar.setFixedWidth(80)
        progress_bar.hide()

        status_label = QtWidgets.QLabel(footer_panel)
        status_label.setObjectName("playlistStatusLabel")
        status_label.setWordWrap(True)
        status_label.setAccessibleName(self.tr("Playlist operation status"))

        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Close,
            parent=footer_panel,
        )
        close_button = button_box.button(
            QtWidgets.QDialogButtonBox.StandardButton.Close,
        )
        close_button.setObjectName("playlistCloseButton")
        close_button.setProperty("class", "secondary")
        button_box.rejected.connect(self.reject)

        footer_layout.addWidget(progress_bar)
        footer_layout.addWidget(status_label, stretch=1)
        footer_layout.addWidget(button_box)
        root_layout.addWidget(footer_panel)

        close_shortcut = QtGui.QShortcut(
            QtGui.QKeySequence.StandardKey.Close,
            self,
        )
        close_shortcut.activated.connect(self.reject)
        return status_label, progress_bar, close_button

    def _connect_signals(self) -> None:
        """Connect model, filter, and worker-result signals."""
        self.membership_model.membership_toggled.connect(
            self._queue_transaction,
        )
        self.widgets.search_edit.textChanged.connect(
            self._apply_filter,
        )
        self.transaction_finished.connect(self._on_transaction_finished)

    @QtCore.Slot(str)
    def _apply_filter(self, text: str) -> None:
        """Apply escaped user text to the playlist proxy model.

        Args:
            text (str): Filter text from the search editor.

        Returns:
            None: Proxy filtering and empty state update immediately.
        """
        expression = QtCore.QRegularExpression(
            QtCore.QRegularExpression.escape(text.strip()),
        )
        expression.setPatternOptions(
            QtCore.QRegularExpression.PatternOption.CaseInsensitiveOption,
        )
        self.proxy_model.setFilterRegularExpression(expression)
        self._update_empty_state()

    def _update_empty_state(self) -> None:
        """Show a clear empty or no-results state when appropriate."""
        has_cached_playlists = self.membership_model.rowCount() > 0
        has_visible_playlists = self.proxy_model.rowCount() > 0
        self.widgets.list_view.setVisible(has_visible_playlists)
        self.widgets.empty_label.setVisible(not has_visible_playlists)
        if not has_cached_playlists:
            self.widgets.empty_label.setText(
                self.tr("No playlists are available for this account."),
            )
            initial_status = self.tr("Playlist data is unavailable.")
        else:
            self.widgets.empty_label.setText(
                self.tr("No playlists match this filter."),
            )
            initial_status = self.tr("Changes are saved automatically.")
        if not self.widgets.status_label.text():
            self.widgets.status_label.setText(initial_status)

    @QtCore.Slot(str, bool)
    def _queue_transaction(self, playlist_id: str, checked: bool) -> None:
        """Create and queue a playlist mutation worker.

        Args:
            playlist_id (str): Playlist selected by the user.
            checked (bool): Requested final membership state.

        Returns:
            None: A typed worker is registered and started.
        """
        if playlist_id in self._pending_tasks:
            return
        action = PlaylistAction.ADD if checked else PlaylistAction.REMOVE
        request = PlaylistTransaction(
            playlist_id=playlist_id,
            track_id=self._track_id,
            action=action,
        )
        worker = Worker(self._execute_transaction, request)
        self._pending_tasks[playlist_id] = worker
        self._update_busy_state()
        self.threadpool.start(worker)

    def _execute_transaction(self, request: PlaylistTransaction) -> None:
        """Execute one API mutation and update the thread-safe cache.

        Args:
            request (PlaylistTransaction): Immutable operation request.

        Returns:
            None: A result is emitted to the GUI thread.
        """
        try:
            match request.action:
                case PlaylistAction.ADD:
                    add_track_to_playlist(
                        self.session,
                        request.playlist_id,
                        request.track_id,
                    )
                    self.cache.add_track_to_playlist(
                        request.track_id,
                        request.playlist_id,
                    )
                case PlaylistAction.REMOVE:
                    remove_track_from_playlist(
                        self.session,
                        request.playlist_id,
                        request.track_id,
                    )
                    self.cache.remove_track_from_playlist(
                        request.track_id,
                        request.playlist_id,
                    )
        except PLAYLIST_OPERATION_ERRORS:
            logger_gui.exception(
                "Playlist %s failed for track %s and playlist %s.",
                request.action,
                request.track_id,
                request.playlist_id,
            )
            result = PlaylistTransactionResult(
                request=request,
                success=False,
                message=self._operation_error_message(request.action),
            )
        else:
            result = PlaylistTransactionResult(
                request=request,
                success=True,
            )
        self.transaction_finished.emit(result)

    def _api_add_track_to_playlist(
        self,
        track_id: str,
        playlist_id: str,
    ) -> None:
        """Execute an add transaction in the current worker thread.

        Args:
            track_id (str): TIDAL track identifier.
            playlist_id (str): TIDAL playlist identifier.

        Returns:
            None: Completion is emitted through ``transaction_finished``.
        """
        self._execute_transaction(
            PlaylistTransaction(
                playlist_id=playlist_id,
                track_id=track_id,
                action=PlaylistAction.ADD,
            ),
        )

    def _api_remove_track_from_playlist(
        self,
        track_id: str,
        playlist_id: str,
    ) -> None:
        """Execute a remove transaction in the current worker thread.

        Args:
            track_id (str): TIDAL track identifier.
            playlist_id (str): TIDAL playlist identifier.

        Returns:
            None: Completion is emitted through ``transaction_finished``.
        """
        self._execute_transaction(
            PlaylistTransaction(
                playlist_id=playlist_id,
                track_id=track_id,
                action=PlaylistAction.REMOVE,
            ),
        )

    @staticmethod
    def _operation_error_message(
        action: PlaylistAction,
    ) -> str:
        """Build a concise user-facing operation error.

        Args:
            action (PlaylistAction): Failed mutation type.

        Returns:
            str: Safe error text suitable for the dialog footer.
        """
        action_text = (
            "add the track to"
            if action is PlaylistAction.ADD
            else ("remove the track from")
        )
        return f"Unable to {action_text} the playlist. Please try again."

    @QtCore.Slot(object)
    def _on_transaction_finished(self, value: object) -> None:
        """Apply one worker result on the GUI thread.

        Args:
            value (object): Expected ``PlaylistTransactionResult`` instance.

        Returns:
            None: Model, signals, and status UI are synchronized.
        """
        if not isinstance(value, PlaylistTransactionResult):
            logger_gui.error(
                "Received an invalid playlist transaction result."
            )
            return
        result = value
        request = result.request
        self._pending_tasks.pop(request.playlist_id, None)
        if not self._accept_results:
            return

        requested_checked = request.action is PlaylistAction.ADD
        previous_checked = self._original_states.get(
            request.playlist_id,
            not requested_checked,
        )
        final_checked = (
            requested_checked if result.success else previous_checked
        )
        self.membership_model.finish_transaction(
            request.playlist_id,
            final_checked,
            "" if result.success else result.message,
        )

        if result.success:
            self._original_states[request.playlist_id] = requested_checked
            self._emit_membership_change(request)
            playlist_name = self.membership_model.playlist_name(
                request.playlist_id,
            )
            verb = "Added to" if requested_checked else "Removed from"
            self._show_status(f"{verb} {playlist_name}.", is_error=False)
        else:
            self._show_error_notification(result.message)
        self._update_busy_state()

    def _emit_membership_change(self, request: PlaylistTransaction) -> None:
        """Emit the public signal corresponding to a successful mutation.

        Args:
            request (PlaylistTransaction): Successful operation.

        Returns:
            None: Exactly one public membership signal is emitted.
        """
        if request.action is PlaylistAction.ADD:
            self.playlist_added.emit(request.track_id, request.playlist_id)
        else:
            self.playlist_removed.emit(request.track_id, request.playlist_id)

    def _update_busy_state(self) -> None:
        """Synchronize progress visibility with pending worker count."""
        pending_count = len(self._pending_tasks)
        self.widgets.progress_bar.setVisible(pending_count > 0)
        if pending_count:
            task_word = "change" if pending_count == 1 else "changes"
            self.widgets.status_label.setText(
                f"Saving {pending_count} {task_word}…",
            )
            self.widgets.status_label.setToolTip("")

    def _show_error_notification(self, message: str) -> None:
        """Display a non-blocking error state in the dialog footer.

        Args:
            message (str): User-facing failure details.

        Returns:
            None: Status text and accessibility tooltip are updated.
        """
        self._show_status(message, is_error=True)
        logger_gui.warning(
            "PlaylistManagerDialog notification: %s",
            message,
        )

    def _show_status(self, message: str, *, is_error: bool) -> None:
        """Show accessible success or error feedback without a modal popup.

        Args:
            message (str): Status text to display.
            is_error (bool): Whether the message represents a failure.

        Returns:
            None: Footer presentation is updated in place.
        """
        self.widgets.status_label.setText(message)
        self.widgets.status_label.setToolTip(message if is_error else "")
        self.widgets.status_label.setProperty(
            "status",
            "error" if is_error else "success",
        )
        self.widgets.status_label.style().unpolish(self.widgets.status_label)
        self.widgets.status_label.style().polish(self.widgets.status_label)

    def _cancel_pending_tasks(self) -> None:
        """Cancel queued workers and ignore results from running workers."""
        if not self._accept_results:
            return
        self._accept_results = False
        for worker in self._pending_tasks.values():
            try:
                self.threadpool.tryTake(worker)
            except RuntimeError:
                logger_gui.debug(
                    "Playlist worker completed before cancellation.",
                )
        self._pending_tasks.clear()

    @override
    def done(self, result: int) -> None:
        """Finish the dialog and detach pending asynchronous results.

        Args:
            result (int): QDialog result code.

        Returns:
            None: Pending queued workers are cancelled before completion.
        """
        self._cancel_pending_tasks()
        super().done(result)

    @override
    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        """Handle window-manager close requests safely.

        Args:
            event (QtGui.QCloseEvent): Close event from Qt.

        Returns:
            None: Pending results are detached before normal close handling.
        """
        self._cancel_pending_tasks()
        super().closeEvent(event)
