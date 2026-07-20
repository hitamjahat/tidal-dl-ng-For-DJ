"""Tidal session mixin for MainWindow.

Handles Tidal authentication and session management.
"""

from __future__ import annotations

import sys
from concurrent.futures import Future
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import TYPE_CHECKING, Any, cast

from requests.exceptions import RequestException

from tidal_dl_ng.config import Tidal
from tidal_dl_ng.dialog import DialogLogin
from tidal_dl_ng.logger import logger_gui

if TYPE_CHECKING:
    from PySide6 import QtWidgets
    from tidalapi.session import LinkLogin

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
        return self._run_oauth_login()

    def _run_oauth_login(self) -> bool:
        """Drive the OAuth login dialog loop until success or cancel.

        Returns:
            ``True`` once the user completes the OAuth flow.
        """
        hint = (
            "After you have finished the TIDAL login via web browser "
            "click the 'OK' button."
        )
        parent = cast("QtWidgets.QWidget", self)

        while True:
            login: LinkLogin
            future: Future[object]
            login, future = self.tidal.session.login_oauth()
            expires_in = int(login.expires_in)

            d_login = DialogLogin(
                url_login=login.verification_uri_complete,
                hint=hint,
                expires_in=expires_in,
                parent=parent,
            )

            if d_login.return_code != 1:
                logger_gui.error(
                    "Authentication status: login dialog was "
                    "cancelled by user."
                )
                sys.exit(1)

            if self._finalize_oauth(future):
                return True

            hint = "Login authorization was not completed. Please try again."

    def _finalize_oauth(self, future: Future[object]) -> bool:
        """Wait for OAuth polling and finalize the session.

        Args:
            future: The background polling future from ``login_oauth``.

        Returns:
            ``True`` when the session was successfully authenticated.
        """
        try:
            # Wait briefly for the background polling thread to complete
            # in case the user clicked OK immediately after authorizing.
            try:
                future.result(timeout=4.0)
            except FutureTimeoutError:
                logger_gui.debug(
                    "Background login polling didn't complete within "
                    "timeout. Proceeding to finalize check."
                )
            finally:
                future.cancel()

            result = self.tidal.finalize_and_enable_hires()
            if result:
                logger_gui.info("Login successful. Have fun!")
                logger_gui.info(
                    "Authentication status: authenticated via login dialog."
                )
            else:
                logger_gui.warning(
                    "Login flow finished but authentication was not "
                    "finalized."
                )
        except LOGINERROR as error:
            logger_gui.exception(
                "Login not successful. Try again... Error: %s",
                error,
            )
            return False
        else:
            return result

    def on_logout(self) -> None:
        """Log out from TIDAL and close the application."""
        result: bool = self.tidal.logout()
        if result:
            sys.exit(0)
