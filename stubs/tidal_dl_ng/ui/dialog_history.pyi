"""Stub for generated Ui_DialogHistory."""

from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QTreeWidget,
)

class Ui_DialogHistory:
    """UI for history dialog."""

    def setupUi(self, dialog: QDialog) -> None: ...
    def retranslateUi(self, dialog: QDialog) -> None: ...
    tw_history: QTreeWidget
    le_file_path: QLineEdit
    l_total_tracks: QLabel
    l_by_albums: QLabel
    l_by_playlists: QLabel
    l_by_mixes: QLabel
    l_by_manual: QLabel
    l_info: QLabel
    pb_refresh: QPushButton
    pb_export: QPushButton
    pb_import: QPushButton
    pb_clear_history: QPushButton
    pb_remove_selected: QPushButton
    pb_close: QPushButton
    pb_open_folder: QPushButton
