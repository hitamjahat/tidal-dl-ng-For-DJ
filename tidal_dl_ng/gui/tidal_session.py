"""Tidal session mixin for MainWindow.

Handles Tidal authentication and session management.
"""

import sys
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import TYPE_CHECKING, Any

from requests.exceptions import HTTPError

from tidal_dl_ng.config import Tidal
from tidal_dl_ng.dialog import DialogLogin
from tidal_dl_ng.logger import logger_gui

if TYPE_CHECKING:
    from tidal_dl_ng.config import Settings


class TidalSessionMixin:
    """Mixin containing Tidal session management methods."""

    # Attributes and methods provided by MainWindow at runtime.
    settings: "Settings"
    tidal: Tidal
    playlist_manager: Any
    thread_it: Any

    _init_dl: Any
    init_playlist_membership_manager: Any

    def init_tidal(self, tidal: Tidal | None = None) -> None:
        """Initialize Tidal session and handle login flow."""
        result: bool = False

        if tidal:
            self.tidal = tidal
            with_logged_in = False
            try:
                with_logged_in = bool(self.tidal.session.check_login())
            except Exception:
                with_logged_in = False

            result = with_logged_in
            if with_logged_in:
                logger_gui.info(
                    "Authentication status: already authenticated via injected TIDAL session."
                )
            else:
                logger_gui.warning(
                    "Authentication status: injected TIDAL session is not authenticated."
                )
        else:
            self.tidal = Tidal(self.settings)

            logger_gui.info(
                "Authentication status: attempting token-based login."
            )
            result = self.tidal.login_token()

            if result:
                logger_gui.info(
                    "Authentication status: token login successful (login dialog not required)."
                )
            else:
                logger_gui.info(
                    "Authentication status: token login failed or missing token; showing login dialog."
                )

            if not result:
                hint: str = (
                    "After you have finished the TIDAL login via web browser click the 'OK' button."
                )

                while not result:
                    # Leverage the updated tidalapi oauth flow
                    login, future = self.tidal.session.login_oauth()
                    expires_in = int(getattr(login, "expires_in", 300))

                    d_login: DialogLogin = DialogLogin(
                        url_login=login.verification_uri_complete,
                        hint=hint,
                        expires_in=expires_in,
                        parent=self,
                    )

                    if d_login.return_code == 1:
                        try:
                            # Wait briefly for the background polling thread to complete
                            # in case the user clicked OK immediately after authorizing on the browser.
                            try:
                                future.result(timeout=4.0)
                            except FutureTimeoutError:
                                logger_gui.debug(
                                    "Background login polling didn't complete within timeout. "
                                    "Proceeding to finalize check."
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
                                hint = "Login authorization was not completed. Please try again."
                                logger_gui.warning(
                                    "Login flow finished but authentication was not finalized."
                                )
                        except HTTPError as e:
                            hint = "Something was wrong with your redirect url. Please try again!"
                            logger_gui.exception(
                                f"Login failed due to HTTP error: {e}"
                            )
                        except Exception as e:
                            hint = "Something was wrong with your redirect url. Please try again!"
                            logger_gui.exception(
                                f"Login not successful. Try again... Error: {e}"
                            )
                    else:
                        logger_gui.error(
                            "Authentication status: login dialog was cancelled by user."
                        )
                        sys.exit(1)

        if result:
            logger_gui.info(
                "Authentication status: authenticated. Initializing download and playlist modules."
            )
            self._init_dl()
            self.thread_it(self.playlist_manager.tidal_user_lists)
            # Initialize playlist membership manager
            self.init_playlist_membership_manager()
        else:
            logger_gui.error(
                "Authentication status: not authenticated; startup initialization skipped."
            )

    def on_logout(self) -> None:
        """Log out from TIDAL and close the application."""
        result: bool = self.tidal.logout()
        if result:
            sys.exit(0)
