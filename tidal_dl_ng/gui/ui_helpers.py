"""UI helpers mixin for MainWindow.

Handles UI helper functions like spinners, logs, and status bar messages.
"""

from typing import Any

from PySide6 import QtGui, QtWidgets

from tidal_dl_ng.model.gui_data import StatusbarMessage
from tidal_dl_ng.ui.spinner import QtWaitingSpinner


class UIHelpersMixin:
    """Mixin containing UI helper methods."""

    # Attributes provided by MainWindow at runtime.
    spinners: dict[QtWidgets.QWidget, QtWaitingSpinner]
    statusbar: QtWidgets.QStatusBar
    te_debug: QtWidgets.QTextEdit
    pb_reload_user_lists: QtWidgets.QPushButton
    converter_ansi_html: Any

    def on_spinner_start(self, parent: QtWidgets.QWidget) -> None:
        """Start a loading spinner on the given parent widget."""
        if parent in self.spinners:
            spinner = self.spinners[parent]
            spinner.stop()
            spinner.deleteLater()
            del self.spinners[parent]

        spinner = QtWaitingSpinner(parent, True, True)
        spinner.setColor(QtGui.QColor(255, 255, 255))
        spinner.start()
        self.spinners[parent] = spinner

    def on_spinner_stop(self) -> None:
        """Stop all active loading spinners."""
        for spinner in list(self.spinners.values()):
            spinner.stop()
            spinner.deleteLater()
        self.spinners.clear()

    def on_statusbar_message(self, data: StatusbarMessage) -> None:
        """Show a message in the status bar."""
        self.statusbar.showMessage(data.message, data.timeout)

    def _log_output(self, text: str) -> None:
        """Redirect log output to the debug text area."""
        cursor: QtGui.QTextCursor = self.te_debug.textCursor()
        html = self.converter_ansi_html.convert(text)

        cursor.movePosition(QtGui.QTextCursor.MoveOperation.End)
        cursor.insertHtml(html)
        self.te_debug.setTextCursor(cursor)
        self.te_debug.ensureCursorVisible()

    def button_reload_status(self, status: bool) -> None:
        """Update the reload button's state and text."""
        button_text: str = "Reloading..." if not status else "Reload"
        self.pb_reload_user_lists.setEnabled(status)
        self.pb_reload_user_lists.setText(button_text)
