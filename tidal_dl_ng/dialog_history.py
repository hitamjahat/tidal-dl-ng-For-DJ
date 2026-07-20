"""dialog_history.py.

Dialog for viewing and managing download history.
"""

from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6 import QtCore, QtWidgets
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices

from tidal_dl_ng.history import HistoryService
from tidal_dl_ng.logger import logger_gui
from tidal_dl_ng.ui.dialog_history import Ui_DialogHistory


class DialogHistory(QtWidgets.QDialog):
    """Dialog for managing download history.

    Displays tracks grouped by source (album, playlist, mix) with ability to:
    - View download dates and source information
    - Export/Import history
    - Clear history or remove selected items
    - View statistics
    """

    ui: Ui_DialogHistory

    def __init__(
        self,
        history_service: HistoryService,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        """Initialize the history dialog.

        Args:
            history_service: The HistoryService instance.
            parent: Parent widget.
        """
        super().__init__(parent)

        self.ui = Ui_DialogHistory()
        self.ui.setupUi(self)
        self.history_service = history_service

        self._init_ui()
        self._connect_signals()
        self._load_history()

        self.exec()

    def _init_ui(self) -> None:
        """Initialize UI elements."""
        # Set file path
        file_path = self.history_service.get_history_file_path()
        self.ui.le_file_path.setText(file_path)

        # Configure tree widget
        self.ui.tw_history.setColumnWidth(0, 400)
        self.ui.tw_history.setColumnWidth(1, 100)
        self.ui.tw_history.setColumnWidth(2, 180)
        self.ui.tw_history.setColumnWidth(3, 100)

        # Set window size
        self.resize(900, 600)

    def _connect_signals(self) -> None:
        """Connect UI signals to handlers."""
        btn_refresh: QtWidgets.QPushButton = vars(self.ui)["pb_refresh"]
        btn_refresh.clicked.connect(self._load_history)
        btn_export: QtWidgets.QPushButton = vars(self.ui)["pb_export"]
        btn_export.clicked.connect(self._on_export)
        btn_import: QtWidgets.QPushButton = vars(self.ui)["pb_import"]
        btn_import.clicked.connect(self._on_import)
        btn_clear: QtWidgets.QPushButton = vars(self.ui)["pb_clear_history"]
        btn_clear.clicked.connect(self._on_clear_history)
        btn_remove: QtWidgets.QPushButton = vars(self.ui)["pb_remove_selected"]
        btn_remove.clicked.connect(self._on_remove_selected)
        btn_close: QtWidgets.QPushButton = vars(self.ui)["pb_close"]
        btn_close.clicked.connect(self.close)
        btn_folder: QtWidgets.QPushButton = vars(self.ui)["pb_open_folder"]
        btn_folder.clicked.connect(self._on_open_folder)

    def _load_history(self) -> None:
        """Load and display the download history."""
        # Clear existing items
        self.ui.tw_history.clear()

        # Get history grouped by source
        grouped_history = self.history_service.get_history_by_source()

        # Get statistics
        stats = self.history_service.get_statistics()
        self._update_statistics(stats)

        # Sort sources by name
        sorted_sources = sorted(grouped_history.items(), key=lambda x: x[0])

        # Populate tree
        for _, tracks in sorted_sources:
            if not tracks:
                continue

            # Create parent item for source
            source_item = self._create_source_item(tracks)
            self.ui.tw_history.addTopLevelItem(source_item)

            # Add tracks as children
            for track_data in sorted(
                tracks, key=lambda x: x.get("download_date", ""), reverse=True
            ):
                track_item = self._create_track_item(track_data)
                source_item.addChild(track_item)

        # Expand all top-level items
        self.ui.tw_history.expandAll()

        total = stats.get("total_tracks", 0)
        logger_gui.info("Loaded %s tracks from history", total)

    def _create_source_item(
        self, tracks: Sequence[Mapping[str, Any]]
    ) -> QtWidgets.QTreeWidgetItem:
        """Create a tree widget item for a source.

        Args:
            tracks: List of track data dictionaries.

        Returns:
            QTreeWidgetItem for the source.
        """
        if not tracks:
            return QtWidgets.QTreeWidgetItem()

        first_track = tracks[0]
        source_type: str = str(first_track.get("source_type", "unknown"))
        source_name: str = str(first_track.get("source_name", "Unknown"))
        source_id: str = str(first_track.get("source_id", ""))

        # Format source name
        if source_type == "manual" or not source_name:
            display_name = f"📝 Manual Downloads ({len(tracks)} tracks)"
        elif source_type == "album":
            display_name = f"💿 {source_name} ({len(tracks)} tracks)"
        elif source_type == "playlist":
            display_name = f"📋 {source_name} ({len(tracks)} tracks)"
        elif source_type == "mix":
            display_name = f"🎵 {source_name} ({len(tracks)} tracks)"
        elif source_type == "track":
            display_name = f"🎼 Individual Tracks ({len(tracks)} tracks)"
        else:
            display_name = f"{source_name} ({len(tracks)} tracks)"

        item = QtWidgets.QTreeWidgetItem()
        item.setText(0, display_name)
        item.setText(1, source_type.capitalize())
        item.setText(2, "")
        item.setText(3, source_id or "")

        # Make it bold
        font = item.font(0)
        font.setBold(True)
        item.setFont(0, font)

        return item

    def _create_track_item(
        self, track_data: Mapping[str, Any]
    ) -> QtWidgets.QTreeWidgetItem:
        """Create a tree widget item for a track.

        Args:
            track_data: Dictionary with track information.

        Returns:
            QTreeWidgetItem for the track.
        """
        track_id: str = str(track_data.get("track_id", ""))
        download_date: str = str(track_data.get("download_date", ""))

        # Format date
        try:
            if download_date:
                dt = datetime.fromisoformat(download_date)
                formatted_date = dt.strftime("%Y-%m-%d %H:%M:%S")
            else:
                formatted_date = "Unknown"
        except ValueError:
            formatted_date = download_date

        item = QtWidgets.QTreeWidgetItem()
        item.setText(0, f"   Track {track_id}")
        item.setText(1, "Track")
        item.setText(2, formatted_date)
        item.setText(3, track_id)

        # Store track ID for later use
        item.setData(0, QtCore.Qt.ItemDataRole.UserRole, track_id)

        return item

    def _update_statistics(self, stats: Mapping[str, Any]) -> None:
        """Update statistics labels.

        Args:
            stats: Dictionary with statistics.
        """
        total: int = int(stats.get("total_tracks", 0))
        by_type: dict[str, int] = stats.get("by_source_type", {})

        self.ui.l_total_tracks.setText(f"Total Tracks: {total}")
        self.ui.l_by_albums.setText(f"Albums: {by_type.get('album', 0)}")
        self.ui.l_by_playlists.setText(
            f"Playlists: {by_type.get('playlist', 0)}"
        )
        self.ui.l_by_mixes.setText(f"Mixes: {by_type.get('mix', 0)}")
        self.ui.l_by_manual.setText(f"Manual: {by_type.get('manual', 0)}")

    def _on_export(self) -> None:
        """Handle export button click."""
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Export Download History",
            "download_history_export.json",
            "JSON Files (*.json)",
        )

        if file_path:
            success, message = self.history_service.export_history(file_path)

            if success:
                QtWidgets.QMessageBox.information(
                    self, "Export Successful", message
                )
                logger_gui.info("Exported history to: %s", file_path)
            else:
                QtWidgets.QMessageBox.critical(
                    self,
                    "Export Failed",
                    f"Failed to export history:\n{message}",
                )
                logger_gui.error("Export failed: %s", message)

    def _on_import(self) -> None:
        """Handle import button click."""
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Import Download History", "", "JSON Files (*.json)"
        )

        if not file_path:
            return

        # Ask merge or replace
        reply = QtWidgets.QMessageBox.question(
            self,
            "Import Mode",
            "Do you want to MERGE with existing history?\n\n"
            "Yes = Merge (add new tracks, keep existing)\n"
            "No = Replace (delete all existing, import only new)\n"
            "Cancel = Abort import",
            QtWidgets.QMessageBox.StandardButton.Yes
            | QtWidgets.QMessageBox.StandardButton.No
            | QtWidgets.QMessageBox.StandardButton.Cancel,
        )

        if reply == QtWidgets.QMessageBox.StandardButton.Cancel:
            return

        merge = reply == QtWidgets.QMessageBox.StandardButton.Yes

        # Perform import
        success, message = self.history_service.import_history(
            file_path, merge=merge
        )

        if success:
            QtWidgets.QMessageBox.information(
                self, "Import Successful", message
            )
            logger_gui.info("Imported history from: %s", file_path)
            self._load_history()  # Refresh display
        else:
            QtWidgets.QMessageBox.critical(
                self, "Import Failed", f"Failed to import history:\n{message}"
            )
            logger_gui.error("Import failed: %s", message)

    def _on_clear_history(self) -> None:
        """Handle clear history button click."""
        reply = QtWidgets.QMessageBox.warning(
            self,
            "Clear Download History",
            "Are you sure you want to clear ALL download history?\n\n"
            "This action cannot be undone!",
            QtWidgets.QMessageBox.StandardButton.Yes
            | QtWidgets.QMessageBox.StandardButton.No,
        )

        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            self.history_service.clear_history()
            QtWidgets.QMessageBox.information(
                self, "History Cleared", "Download history has been cleared."
            )
            logger_gui.info("Download history cleared")
            self._load_history()  # Refresh display

    def _on_remove_selected(self) -> None:
        """Handle remove selected button click."""
        if not (selected_items := self.ui.tw_history.selectedItems()):
            QtWidgets.QMessageBox.warning(
                self,
                "No Selection",
                "Please select one or more tracks to remove.",
            )
            return

        # Collect track IDs from selected items (only child items, not parents)
        track_ids: list[str] = [
            track_id
            for item in selected_items
            if self.ui.tw_history.indexOfTopLevelItem(item) == -1
            and (
                track_id := str(item.data(0, QtCore.Qt.ItemDataRole.UserRole))
            )
            and track_id != "None"
        ]

        if not track_ids:
            QtWidgets.QMessageBox.warning(
                self,
                "No Tracks Selected",
                "Please select individual tracks to remove.",
            )
            return

        reply = QtWidgets.QMessageBox.question(
            self,
            "Remove Tracks",
            f"Are you sure you want to remove {len(track_ids)} "
            "track(s) from history?",
            QtWidgets.QMessageBox.StandardButton.Yes
            | QtWidgets.QMessageBox.StandardButton.No,
        )

        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            removed_count = 0
            for track_id in track_ids:
                if self.history_service.remove_track_from_history(track_id):
                    removed_count += 1

            QtWidgets.QMessageBox.information(
                self,
                "Tracks Removed",
                f"Removed {removed_count} track(s) from history.",
            )
            logger_gui.info("Removed %s tracks from history", removed_count)
            self._load_history()  # Refresh display

    def _on_open_folder(self) -> None:
        """Open the folder containing the history file."""
        file_path = Path(self.history_service.get_history_file_path())
        folder_path = file_path.parent

        opened: bool = QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(folder_path))
        )

        if not opened:
            QtWidgets.QMessageBox.warning(
                self,
                "Cannot Open Folder",
                "Failed to open the folder.",
            )
            logger_gui.error("Failed to open folder: %s", folder_path)
        else:
            logger_gui.info("Opened folder: %s", folder_path)
