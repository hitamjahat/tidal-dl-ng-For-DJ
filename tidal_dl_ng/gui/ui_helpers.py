"""UI helpers mixin for MainWindow.

Handles UI helper functions like spinners, logs, and status bar messages.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ansi2html import Ansi2HTMLConverter
from PySide6 import QtCore, QtGui, QtWidgets

from tidal_dl_ng.ui.spinner import QtWaitingSpinner

if TYPE_CHECKING:
    from tidal_dl_ng.model.gui_data import StatusbarMessage


class UIHelpersMixin:
    """Mixin containing UI helper methods."""

    if TYPE_CHECKING:
        # Attributes provided by MainWindow at runtime.
        spinners: dict[QtWidgets.QWidget, QtWaitingSpinner]
        statusbar: QtWidgets.QStatusBar
        te_debug: QtWidgets.QPlainTextEdit
        pb_reload_user_lists: QtWidgets.QPushButton
        converter_ansi_html: Ansi2HTMLConverter

    def on_spinner_start(self, parent: QtWidgets.QWidget) -> None:
        """Start a loading spinner on the given parent widget.

        If a spinner already exists for ``parent`` it is stopped and
        replaced with a fresh one to avoid stacking duplicate spinners.

        Args:
            parent: Widget that hosts and centers the spinner.
        """
        if parent in self.spinners:
            existing = self.spinners[parent]
            existing.stop()
            existing.deleteLater()
            del self.spinners[parent]

        center_on_parent = True
        disable_parent = True
        spinner = QtWaitingSpinner(parent, center_on_parent, disable_parent)
        spinner.setColor(QtCore.Qt.GlobalColor.white)
        spinner.start()
        self.spinners[parent] = spinner

    def on_spinner_stop(self) -> None:
        """Stop and tear down every active loading spinner."""
        for spinner in list(self.spinners.values()):
            spinner.stop()
            spinner.deleteLater()
        self.spinners.clear()

    def on_statusbar_message(self, data: StatusbarMessage) -> None:
        """Show a transient message in the status bar.

        Args:
            data: Message text and display timeout in milliseconds.
        """
        self.statusbar.showMessage(data.message, data.timeout)

    def _log_output(self, text: str) -> None:
        """Redirect log output to the debug text area as HTML.

        Args:
            text: Raw log line (may contain ANSI escape sequences).
        """
        cursor = self.te_debug.textCursor()
        html = self.converter_ansi_html.convert(text)

        cursor.movePosition(QtGui.QTextCursor.MoveOperation.End)
        cursor.insertHtml(html)
        self.te_debug.setTextCursor(cursor)
        self.te_debug.ensureCursorVisible()

    def button_reload_status(self, status: bool) -> None:
        """Update the reload button's enabled state and label.

        Args:
            status: ``True`` when reloading finished (button enabled and
                labelled "Reload"); ``False`` while reloading is in progress.
        """
        button_text = "Reloading..." if not status else "Reload"
        self.pb_reload_user_lists.setEnabled(status)
        self.pb_reload_user_lists.setText(button_text)
