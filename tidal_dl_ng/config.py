"""Configuration and TIDAL session management for tidal-dl-ng.

This module provides persistent configuration storage (settings and
auth tokens) and manages the TIDAL API session lifecycle, including
PKCE-based authentication required for lossless (FLAC / HI_RES)
stream retrieval.
"""

# ruff: noqa: T201

import json
import shutil
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from threading import Event, Lock
from typing import Generic, Protocol, TypeVar, cast, runtime_checkable

from tidalapi.media import Quality, VideoQuality
from tidalapi.session import Config, Session

from tidal_dl_ng.constants import (
    ATMOS_CLIENT_ID,
    ATMOS_CLIENT_SECRET,
    ATMOS_REQUEST_QUALITY,
)
from tidal_dl_ng.helper.decorator import SingletonMeta
from tidal_dl_ng.helper.path import (
    path_config_base,
    path_file_settings,
    path_file_token,
)
from tidal_dl_ng.model.cfg import Settings as ModelSettings
from tidal_dl_ng.model.cfg import Token as ModelToken

TConfigData = TypeVar("TConfigData", ModelSettings, ModelToken)


@runtime_checkable
class JsonSerializable(Protocol):
    """Minimal protocol describing dataclasses-json serialization methods."""

    def to_json(self, *args: object, **kwargs: object) -> str:
        """Serialize the instance to a JSON string."""
        raise NotImplementedError

    @classmethod
    def from_json(cls, *args: object, **kwargs: object) -> "JsonSerializable":
        """Deserialize a JSON string into an instance."""
        raise NotImplementedError


class BaseConfig(Generic[TConfigData]):
    """Base class for JSON-backed configuration objects.

    Provides load/save/set-option logic shared by settings and token storage.
    """

    data: TConfigData
    file_path: str
    cls_model: type[TConfigData]
    path_base: str = path_config_base()

    def save(self, config_to_compare: str | None = None) -> None:
        """Persist the current config to disk as pretty-printed JSON.

        Skips writing if the serialized content is identical to
        ``config_to_compare`` (used to avoid redundant writes).
        """
        data_json = cast("JsonSerializable", self.data).to_json()

        # If old and current config is equal, skip the write operation.
        if config_to_compare == data_json:
            return

        # Try to create the base folder.
        Path(self.path_base).mkdir(parents=True, exist_ok=True)

        with Path(self.file_path).open(encoding="utf-8", mode="w") as f:
            # Save it in a pretty format
            obj_json_config = json.loads(data_json)
            json.dump(obj_json_config, f, indent=4)

    def set_option(self, key: str, value: object) -> None:
        """Set a single attribute on the underlying config dataclass.

        Performs type-coercion (bool/int) to match the existing attribute type.

        Args:
            key: Attribute name to set.
            value: New value (will be coerced to match the existing type).
        """
        value_old: object = getattr(self.data, key)

        if isinstance(value_old, bool):
            if isinstance(value, str):
                value = value.lower() in {"true", "1", "yes", "y"}
            else:
                value = bool(value)
        elif isinstance(value_old, int) and not isinstance(value, bool | int):
            value = int(str(value))

        setattr(self.data, key, value)

    def read(self, path: str) -> bool:
        """Load config from disk, creating a default if the file is invalid.

        Args:
            path: Filesystem path of the JSON config file.

        Returns:
            bool: True if an existing valid config was loaded, False if a new
                default config was created.
        """
        result: bool = False
        settings_json: str = ""

        try:
            with Path(path).open(encoding="utf-8") as f:
                settings_json = f.read()

            cls_model = cast("type[JsonSerializable]", self.cls_model)
            self.data = cast("TConfigData", cls_model.from_json(settings_json))
            result = True
        except ValueError as e:
            path_bak = path + ".bak"
            Path(path_bak).unlink(missing_ok=True)
            shutil.move(path, path_bak)
            print(
                "Something is wrong with your config. Maybe it is not "
                "compatible anymore due to a new app version.\n"
                "You can find a backup of your old config here: "
                f"'{path_bak}'. A new default config was created."
            )
            _ = e
            cls_model = cast("type[JsonSerializable]", self.cls_model)
            self.data = cast("TConfigData", cls_model())
        except (TypeError, FileNotFoundError):
            cls_model = cast("type[JsonSerializable]", self.cls_model)
            self.data = cast("TConfigData", cls_model())

        # Call save to update the saved config in case of code changes.
        self.save(settings_json)

        return result


class Settings(BaseConfig[ModelSettings], metaclass=SingletonMeta):
    """Singleton holding user-configurable application settings."""

    def __init__(self) -> None:
        """Initialize settings from the config file path."""
        self.cls_model = ModelSettings
        self.file_path = path_file_settings()
        self.read(self.file_path)


class Tidal(BaseConfig[ModelToken], metaclass=SingletonMeta):
    """Manages the TIDAL API session, token persistence, and login flows.

    Handles PKCE-based authentication (required for lossless streams),
    Atmos/Normal session switching, and lossless capability verification.
    """

    # pylint: disable=too-many-instance-attributes

    session: Session
    token_from_storage: bool = False
    settings: Settings
    is_pkce: bool

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialize TIDAL session and load persisted token if available."""
        self.cls_model = ModelToken
        tidal_config: Config = Config(item_limit=10000)
        self.session = Session(tidal_config)
        self.original_client_id = self.session.config.client_id
        self.original_client_secret = self.session.config.client_secret
        # Lock to ensure session-switching is thread-safe.
        # This lock protects against a race condition where one thread
        # changes the session credentials while another is using them.
        # It is intentionally held by Download._get_stream_info
        # for the *entire* duration of the credential switch AND
        # the get_stream() call.
        self.stream_lock = Lock()
        # State-tracking flag to prevent redundant, expensive
        # session re-authentication when the session is already in the
        # correct mode (Atmos or Normal).
        self.is_atmos_session = False
        self.file_path = path_file_token()
        self.token_from_storage = self.read(self.file_path)

        # If a token was loaded from storage, update the "original" client ID
        # to match the session's active credentials (which may be PKCE).
        # Also ensure the PKCE client ID/secret is active for lossless streams.
        if self.token_from_storage:
            self.is_pkce = getattr(self.data, "is_pkce", True)
            self.original_client_id = self.session.config.client_id
            self.original_client_secret = self.session.config.client_secret
            if self.is_pkce:
                self.session.client_enable_hires()
                self.original_client_id = self.session.config.client_id
                self.original_client_secret = self.session.config.client_secret
        else:
            self.is_pkce = True

        if settings:
            self.settings = settings
            self.settings_apply()

    @staticmethod
    def _normalize_expiry_time(
        expiry_time: datetime | float | None,
    ) -> datetime | None:
        """Normalize persisted token expiry for tidalapi session loading.

        Older config versions stored expiry_time as unix timestamp (float).
        tidalapi expects datetime.datetime, so convert timestamps safely.

        Args:
            expiry_time: Token expiry as datetime, UNIX timestamp, or None.

        Returns:
            datetime | None: Timezone-aware datetime, or None if unset.
        """
        if expiry_time is None:
            return None

        if isinstance(expiry_time, datetime):
            return expiry_time

        # At this point expiry_time is float | int (narrowed by annotation)
        return datetime.fromtimestamp(float(expiry_time), tz=UTC)

    def settings_apply(self, settings: Settings | None = None) -> bool:
        """Apply the user's settings to the active TIDAL session.

        Args:
            settings: Optional settings instance to apply. If omitted, the
                already-bound ``self.settings`` is used.

        Returns:
            bool: True after the session quality/video settings are applied.
        """
        if settings:
            self.settings = settings

        if not self.is_atmos_session:
            # `quality_audio` is a `Quality` enum. Passing the enum
            # object directly to `Quality(...)` resolves to the WRONG
            # quality (e.g. hi_res_lossless
            # -> HIGH). We must pass the enum's string *value* so the session
            # requests the correct tier.
            quality_val = getattr(
                self.settings.data.quality_audio,
                "value",
                self.settings.data.quality_audio,
            )
            self.session.audio_quality = Quality(str(quality_val))
        self.session.video_quality = VideoQuality.high

        return True

    def login_token(self, do_pkce: bool | None = None) -> bool:
        """Load a stored OAuth/PKCE token.

        Args:
            do_pkce: If None (default), reads the PKCE flag from the persisted
                token file. If True/False, explicitly forces PKCE or legacy
                mode (used for Atmos session credential switching).

                IMPORTANT: PKCE is the ONLY way to get lossless
                (FLAC / FLAC_HIRES) streams from TIDAL via the
                playbackinfopostpaywall endpoint. Non-PKCE (legacy OAuth)
                tokens are capped at AAC 320 (HIGH) even when a higher
                audio_quality is requested. See:
                https://github.com/EbbLabs/python-tidal/issues
                (lossless capped at HIGH).

                This method NO LONGER silently falls back to non-PKCE if PKCE
                load fails — doing so would silently downgrade all downloads
                to AAC 320. Instead, the invalid token is deleted and the
                caller must perform a fresh PKCE login.

        Returns:
            bool: True if the token loaded successfully.
        """
        result = False

        # Determine PKCE mode: explicit override, persisted, or default
        if do_pkce is not None:
            self.is_pkce = do_pkce
        else:
            self.is_pkce = getattr(self.data, "is_pkce", True)

        if self.token_from_storage:
            try:
                expiry_time = self._normalize_expiry_time(
                    self.data.expiry_time
                )
                token_type = self.data.token_type or ""
                access_token = self.data.access_token or ""
                refresh_token = self.data.refresh_token or ""
                result = self.session.load_oauth_session(
                    token_type,
                    access_token,
                    refresh_token,
                    expiry_time,
                    is_pkce=self.is_pkce,
                )

                # If session check fails, try using the refresh token
                if result and not self.session.check_login() and refresh_token:
                    print("Access token invalid. Attempting to refresh...")
                    if self.session.token_refresh(refresh_token):
                        self.token_persist()
                        result = self.session.load_oauth_session(
                            self.session.token_type,
                            self.session.access_token,
                            self.session.refresh_token,
                            self.session.expiry_time,
                            is_pkce=self.is_pkce,
                        )
                    else:
                        result = False
            except (OSError, Exception) as e:  # noqa: BLE001
                print(f"Error loading or refreshing session: {e}")
                result = False

            if result and self.is_pkce:
                # Swap to the PKCE client ID/secret required for lossless
                # streams. Without this, TIDAL's playbackinfopostpaywall
                # endpoint returns AAC 320 (HIGH) for all tracks.
                self.session.client_enable_hires()
                self.original_client_id = self.session.config.client_id
                self.original_client_secret = self.session.config.client_secret

            if not result:
                # Token is invalid or incompatible with PKCE (e.g. a legacy
                # OAuth token). Delete it and force a fresh PKCE login.
                self.token_from_storage = False
                Path(self.file_path).unlink(missing_ok=True)

                print(
                    "The stored token is invalid or incompatible with the "
                    "current login scheme. A fresh login via PKCE is "
                    "required to enable lossless (FLAC/HI_RES) downloads."
                )

        return result

    def login_finalize(self) -> bool:
        """Finalize a PKCE login and enable lossless (HiRes) streams.

        Checks login validity, swaps to the PKCE client credentials (required
        for lossless), persists the token, and verifies lossless capability.

        Returns:
            bool: True if the login is valid and finalized successfully.
        """
        if result := bool(self.session.check_login()):
            self.is_pkce = True
            # tidalapi's login_pkce() does NOT call client_enable_hires()
            # (the call is commented out at line 476). We must swap to the
            # PKCE client ID/secret here so that the playbackinfopostpaywall
            # endpoint returns lossless streams. Without this, the session
            # uses the default (Android Auto) client ID which TIDAL now
            # caps at HIGH (AAC 320) — see report2 follow-up.
            self.session.client_enable_hires()
            # Update our "original" reference so that restore_normal_session()
            # uses the correct PKCE credentials (not the pre-PKCE default).
            # See report2: the default Android Auto client ID is restricted to
            # HIGH only; the PKCE client ID is required for lossless streams.
            self.original_client_id = self.session.config.client_id
            self.original_client_secret = self.session.config.client_secret
            self.token_persist()
            self.verify_lossless_capability()

        return result

    def finalize_and_enable_hires(self) -> bool:
        """Finalize login and ensure the session is configured for lossless.

        After a successful login (via any OAuth flow), this method:
        1. Checks login validity.
        2. Swaps to the PKCE (HiRes-enabled) client ID/secret so that the
           playbackinfopostpaywall endpoint returns lossless streams even
           if the token was obtained via the device authorization flow
           (which uses the Android Auto client ID, capped at HIGH).
        3. Updates the stored "original" credentials reference.
        4. Persists the token.
        5. Verifies lossless capability.

        See report2: "authenticate with the old Client ID/Secret and then
        switch to the Client ID/Secret for the normal Android client."

        Returns:
            bool: True if login is valid and HiRes is enabled.
        """
        if not self.session.check_login():
            return False

        # Swap to the PKCE client ID/secret required for lossless streams.
        # tidalapi stores these as client_id_pkce / client_secret_pkce.
        self.session.client_enable_hires()

        self.is_pkce = True
        self.original_client_id = self.session.config.client_id
        self.original_client_secret = self.session.config.client_secret
        self.token_persist()
        self.verify_lossless_capability()
        return True

    def verify_lossless_capability(self) -> bool:
        """Verify that the current session token can retrieve lossless streams.

        Makes a lightweight API call to the playbackinfopostpaywall endpoint
        for a known track ID and checks that the returned audioQuality is at
        least LOSSLESS (not HIGH). This catches tokens that are capped at AAC
        320 — e.g. legacy OAuth tokens or tokens issued by restricted
        client IDs (like Android Auto, which TIDAL recently capped at HIGH).

        Only runs when the user's configured audio quality requires lossless
        (hi_res_lossless or high_lossless), to avoid unnecessary API calls for
        users who only download lossy AAC.

        Returns:
            bool: True if lossless-capable, False if capped.
        """
        # Only verify if the user actually needs lossless.
        quality_val = str(
            getattr(
                self.settings.data.quality_audio,
                "value",
                self.settings.data.quality_audio,
            )
        )
        if quality_val not in (
            str(
                getattr(Quality.high_lossless, "value", Quality.high_lossless)
            ),
            str(
                getattr(
                    Quality.hi_res_lossless, "value", Quality.hi_res_lossless
                )
            ),
        ):
            return True

        # Check user subscription highestSoundQuality
        try:
            sub = self.session.request.basic_request(
                "GET", f"users/{self.session.user.id}/subscription"
            ).json()
            highest_quality = sub.get("highestSoundQuality", "HIGH")
        except Exception:  # noqa: BLE001
            highest_quality = "HI_RES"

        # Use a well-known track ID that supports lossless (Billie Jean).
        try:
            track = self.session.track("1781887", with_album=True)
            stream = track.get_stream()
            quality = stream.audio_quality
        except (
            Exception
        ) as exc:  # noqa: BLE001  # pylint: disable=broad-exception-caught
            print(f"WARNING: Could not verify lossless capability: {exc}")
            # Don't block login — the token may still work for some tracks.
            return True

        lossless_tiers: tuple[str, ...] = (
            str(
                getattr(Quality.high_lossless, "value", Quality.high_lossless)
            ),
            str(
                getattr(
                    Quality.hi_res_lossless,
                    "value",
                    Quality.hi_res_lossless,
                )
            ),
        )
        if quality in lossless_tiers:
            return True

        # If user's plan doesn't support lossless, don't flag as capped
        if highest_quality not in ("HI_RES", "LOSSLESS"):
            return True

        print(
            f"WARNING: Token is capped at '{quality}' instead of a "
            f"lossless tier ({lossless_tiers}). Downloads will be limited "
            "to AAC 320kbps. A fresh PKCE login is required for lossless "
            "(FLAC/HI_RES) downloads."
        )
        return False

    def token_persist(self) -> None:
        """Persist the current session token and PKCE flag to disk."""
        self.set_option("token_type", self.session.token_type)
        self.set_option("access_token", self.session.access_token)
        self.set_option("refresh_token", self.session.refresh_token)
        self.set_option("expiry_time", self.session.expiry_time)
        self.set_option("is_pkce", self.is_pkce)
        self.save()

    def switch_to_atmos_session(self) -> bool:
        """Switches the shared session to Dolby Atmos credentials.

        Only re-authenticates if not already in Atmos mode.

        Returns:
            bool: True if successful or already in Atmos mode, False otherwise.
        """
        # If we are already in Atmos mode, do nothing.
        if self.is_atmos_session:
            return True

        print("Switching session context to Dolby Atmos...")
        self.session.config.client_id = ATMOS_CLIENT_ID
        self.session.config.client_secret = ATMOS_CLIENT_SECRET
        self.session.audio_quality = ATMOS_REQUEST_QUALITY

        # Re-login with new credentials
        if not self.login_token(do_pkce=self.is_pkce):
            print("Warning: Atmos session authentication failed.")
            # Try to switch back to normal to be safe
            self.restore_normal_session(force=True)
            return False

        self.is_atmos_session = True  # Set the flag
        print("Session is now in Atmos mode.")
        return True

    def restore_normal_session(
        self,
        force: bool = False,
    ) -> bool:
        """Restores the shared session to the original user credentials.

        Only re-authenticates if not already in Normal mode.

        Args:
            force: If True, forces restoration even if already in Normal.

        Returns:
            bool: True if successful or already in Normal mode.
        """
        # If we are already in Normal mode (and not forced), skip.
        if not self.is_atmos_session and not force:
            return True

        print("Restoring session context to Normal...")
        self.session.config.client_id = self.original_client_id
        self.session.config.client_secret = self.original_client_secret

        # Explicitly restore audio quality to user's configured setting
        quality_val = getattr(
            self.settings.data.quality_audio,
            "value",
            self.settings.data.quality_audio,
        )
        self.session.audio_quality = Quality(str(quality_val))

        # Re-login with original credentials
        if not self.login_token(do_pkce=self.is_pkce):
            print(
                "Warning: Restoring the original session context failed. "
                "Please restart the application."
            )
            return False

        self.is_atmos_session = False  # Set the flag
        print("Session is now in Normal mode.")
        return True

    def login(self, fn_print: Callable[[str], None]) -> bool:
        """Perform the full login flow (token load or interactive PKCE login).

        Args:
            fn_print: Callback used to print status messages to the user.

        Returns:
            bool: True if the user is logged in with a valid (lossless-capable)
                token by the end of the flow.
        """
        result: bool = False

        if is_token := self.login_token():
            fn_print("Yep, looks good! You are logged in.")

            # Verify the token can actually retrieve lossless streams.
            # Some tokens (legacy OAuth, Android Auto client ID) are capped at
            # AAC 320 (HIGH) even if PKCE-loaded.
            if not self.verify_lossless_capability():
                fn_print(
                    "Your token is limited to AAC 320kbps. A fresh PKCE "
                    "login is required for lossless (FLAC/HI_RES) downloads."
                )
                fn_print("No worries, we will handle this...")
                self.logout()
                is_token = False

        if not is_token:
            fn_print(
                "You either do not have a token or your token is invalid."
            )
            fn_print("No worries, we will handle this...")
            # IMPORTANT: PKCE is the ONLY way to get lossless
            # (FLAC / FLAC_HIRES) streams from TIDAL. Legacy OAuth tokens
            # are capped at AAC 320 (HIGH) even when a higher audio_quality
            # is requested. See python-tidal issues.
            self.session.login_pkce(fn_print)

            if self.login_finalize():
                fn_print(
                    "The login was successful. I have stored your "
                    "credentials (token)."
                )
                result = True
            else:
                fn_print(
                    "Something went wrong. Did you login using your browser "
                    "correctly? May try again..."
                )

        return result

    def logout(self) -> bool:
        """Remove the stored token and invalidate the current session.

        Returns:
            bool: True after the token file has been removed.
        """
        Path(self.file_path).unlink(missing_ok=True)
        self.token_from_storage = False

        # Reset session instead of deleting it to avoid AttributeErrors
        tidal_config = Config(item_limit=10000)
        self.session = Session(tidal_config)
        self.original_client_id = self.session.config.client_id
        self.original_client_secret = self.session.config.client_secret
        self.is_atmos_session = False

        return True

    def login_hifi_api(self, fn_print: Callable[[str], None]) -> bool:
        """Perform login using the HiFi-API OAuth 2.0 Device Authorization flow.

        This is the upgraded auth flow that uses direct OAuth 2.0 with
        custom credentials, bypassing ``tidalapi``'s ``login_pkce()``
        which has known issues with lossless stream retrieval.

        The flow:
          1. Tries to load and verify an existing token from storage.
          2. If no valid token exists, runs the device authorization flow.
          3. Verifies the token can retrieve HI_RES lossless streams.

        Args:
            fn_print: Callback used to print status messages to the user.

        Returns:
            bool: True if the user is logged in with a valid token.
        """
        from tidal_dl_ng.helper.tidal_auth import (
            get_valid_token_sync,
            run_device_authorization_flow_sync,
            verify_existing_token_sync,
        )

        # Try to use an existing token from storage.
        fn_print("Checking for existing TIDAL token...")
        token_result = get_valid_token_sync()

        if token_result is not None:
            access_token, entry = token_result
            fn_print(
                f"Found token for user ID: {entry.get('userID', 'unknown')}"
            )

            # Verify the token is still valid.
            if verify_existing_token_sync(access_token):
                fn_print("Token is valid. Loading into session...")
                self._load_hifi_token_into_session(entry)
                fn_print("Authentication successful!")
                return True

            fn_print("Token is invalid or expired. Attempting refresh...")
            # Try with forced refresh.
            token_result = get_valid_token_sync(force_refresh=True)
            if token_result is not None:
                access_token, entry = token_result
                if verify_existing_token_sync(access_token):
                    fn_print("Token refreshed successfully.")
                    self._load_hifi_token_into_session(entry)
                    return True

        # No valid token — run the interactive device authorization flow.
        fn_print(
            "No valid token found. Starting OAuth device authorization "
            "flow..."
        )
        entry = run_device_authorization_flow_sync(fn_print)

        if entry is not None:
            self._load_hifi_token_into_session(entry)
            fn_print("Authentication successful!")
            return True

        fn_print("Authentication failed. Please try again.")
        return False

    def _load_hifi_token_into_session(self, entry: dict[str, object]) -> None:
        """Load a HiFi-API token entry into the tidalapi session.

        Args:
            entry: The token entry dictionary containing access_token,
                refresh_token, client_ID, client_secret, etc.
        """
        access_token = str(entry.get("access_token", ""))
        refresh_token = str(entry.get("refresh_token", ""))
        token_type = str(entry.get("token_type", "Bearer"))
        client_id = str(entry.get("client_ID", ""))
        client_secret = str(entry.get("client_secret", ""))

        # Set the PKCE client credentials for lossless streams.
        self.session.config.client_id = client_id
        self.session.config.client_secret = client_secret
        self.is_pkce = True
        self.original_client_id = client_id
        self.original_client_secret = client_secret

        # Load the token into the session.
        self.session.load_oauth_session(
            token_type,
            access_token,
            refresh_token,
            None,
            is_pkce=True,
        )

        # Persist the token in the legacy format for compatibility.
        self.set_option("token_type", token_type)
        self.set_option("access_token", access_token)
        self.set_option("refresh_token", refresh_token)
        self.set_option("is_pkce", True)
        self.save()

    def login(self, fn_print: Callable[[str], None]) -> bool:
        """Perform the full login flow using the upgraded HiFi-API auth.

        This method now uses the HiFi-API OAuth 2.0 Device Authorization
        flow, which provides lossless (HI_RES) stream capability.

        Args:
            fn_print: Callback used to print status messages to the user.

        Returns:
            bool: True if the user is logged in with a valid (lossless-capable)
                token by the end of the flow.
        """
        return self.login_hifi_api(fn_print)

    def is_authentication_error(self, error: Exception) -> bool:
        """Check if an error is related to authentication/OAuth issues.

        Args:
            error (Exception): The exception to check.

        Returns:
            bool: True if the error is authentication-related, False otherwise.
        """
        error_msg = str(error)
        return (
            "401" in error_msg
            or "OAuth" in error_msg
            or "token" in error_msg.lower()
        )


class HandlingApp(metaclass=SingletonMeta):
    # pylint: disable=too-few-public-methods
    """Holds application-wide control events for abort/run signalling."""

    event_abort: Event = Event()
    event_run: Event = Event()

    def __init__(self) -> None:
        """Initialize and set the run event by default."""
        self.event_run.set()
