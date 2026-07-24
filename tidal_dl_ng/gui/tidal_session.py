"""Tidal session mixin for MainWindow.

Handles Tidal authentication and session management.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any, cast

from requests.exceptions import RequestException

from tidal_dl_ng.config import Tidal
from tidal_dl_ng.dialog import DialogLogin
from tidal_dl_ng.logger import logger_gui

if TYPE_CHECKING:
    from PySide6 import QtWidgets

    from tidal_dl_ng.config import Settings

# Exceptions that may surface while verifying or finalizing a session.
LOGINERROR = (RequestException, ValueError, AttributeError)


class TidalSessionMixin:
    """Mixin containing Tidal session management methods."""

    # Attributes and methods provided by MainWindow at runtime.
    settings: Settings
    tidal: Tidal
    playlist_manager: Any
    thread_it: Any

    _init_dl: Any
    init_playlist_membership_manager: Any

    def init_tidal(self, tidal: Tidal | None = None) -> None:
        """Initialize Tidal session and handle login flow.

        Args:
            tidal: An already-constructed TIDAL session to reuse, or
                ``None`` to create and authenticate a new one.
        """
        if tidal:
            result = self._init_from_injected(tidal)
        else:
            result = self._init_with_login()

        if result:
            logger_gui.info(
                "Authentication status: authenticated. Initializing "
                "download and playlist modules."
            )
            self._init_dl()
            self.thread_it(self.playlist_manager.tidal_user_lists)
            # Initialize playlist membership manager.
            self.init_playlist_membership_manager()
        else:
            logger_gui.error(
                "Authentication status: not authenticated; startup "
                "initialization skipped."
            )

    def _init_from_injected(self, tidal: Tidal) -> bool:
        """Use a pre-built session, verifying its login state.

        Args:
            tidal: The injected TIDAL session.

        Returns:
            ``True`` when the session is already authenticated.
        """
        self.tidal = tidal
        try:
            with_logged_in = bool(self.tidal.session.check_login())
        except LOGINERROR:
            with_logged_in = False

        if with_logged_in:
            logger_gui.info(
                "Authentication status: already authenticated via "
                "injected TIDAL session."
            )
        else:
            logger_gui.warning(
                "Authentication status: injected TIDAL session is "
                "not authenticated."
            )

        return with_logged_in

    def _init_with_login(self) -> bool:
        """Create a session and authenticate via token or OAuth dialog.

        Returns:
            ``True`` once the session is authenticated.
        """
        self.tidal = Tidal(self.settings)

        logger_gui.info("Authentication status: attempting token-based login.")
        result = self.tidal.login_token()

        if result:
            logger_gui.info(
                "Authentication status: token login successful "
                "(login dialog not required)."
            )
            return result

        logger_gui.info(
            "Authentication status: token login failed or missing "
            "token; showing login dialog."
        )
        return self._run_hifi_login()

    def _run_hifi_login(self) -> bool:
        """Drive the HiFi-API OAuth device authorization login flow.

        Uses the upgraded HiFi-API auth flow which provides lossless
        (HI_RES) stream capability.

        Returns:
            ``True`` once the user completes the OAuth flow.
        """
        hint = (
            "After you have finished the TIDAL login via web browser "
            "click the 'OK' button."
        )
        parent = cast("QtWidgets.QWidget", self)

        while True:
            from tidal_dl_ng.helper.tidal_auth import (
                run_device_authorization_flow_sync,
            )

            def fn_print(msg: str) -> None:
                logger_gui.info(msg)

            # Run the device authorization flow. This will open the
            # browser for the user to authorize.
            entry = run_device_authorization_flow_sync(fn_print)

            if entry is None:
                logger_gui.error(
                    "Authentication status: login flow returned no token."
                )
                return False

            # Show the dialog so the user knows to complete the flow.
            d_login = DialogLogin(
                url_login="",
                hint=hint,
                expires_in=3600,
                parent=parent,
            )

            if d_login.return_code != 1:
                logger_gui.error(
                    "Authentication status: login dialog was "
                    "cancelled by user."
                )
                sys.exit(1)

            # Load the token into the session.
            self.tidal._load_hifi_token_into_session(entry)

            if self.tidal.session.check_login():
                logger_gui.info("Login successful. Have fun!")
                logger_gui.info(
                    "Authentication status: authenticated via "
                    "HiFi-API login dialog."
                )
                return True

            hint = "Login authorization was not completed. Please try again."

    def on_logout(self) -> None:
        """Log out from TIDAL and close the application."""
        result: bool = self.tidal.logout()
        if result:
            sys.exit(0)
