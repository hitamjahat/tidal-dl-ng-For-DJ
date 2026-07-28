"""OAuth 2.0 Device Authorization flow for TIDAL authentication.

Copyright (c) 2024-2026 TIDAL-Downloader-NG contributors

This module implements the full OAuth 2.0 Device Authorization Grant flow
for TIDAL, including device code request, user authorization polling,
token verification, and token refresh.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import asyncio
import webbrowser
from datetime import UTC, datetime

import httpx

from tidal_dl_ng.constants import (
    HIFI_AUTH_CLIENT_ID,
    HIFI_AUTH_CLIENT_SECRET,
    HIFI_DEVICE_AUTH_URL,
    HIFI_OAUTH_GRANT_TYPE_DEVICE,
    HIFI_OAUTH_GRANT_TYPE_REFRESH,
    HIFI_OAUTH_SCOPE,
    HIFI_PLAYBACK_INFO_URL_TEMPLATE,
    HIFI_REQUEST_CLIENT_ID,
    HIFI_REQUEST_CLIENT_SECRET,
    HIFI_TOKEN_URL,
    HIFI_VERIFICATION_QUALITY,
    HIFI_VERIFICATION_TRACK_ID,
)
from tidal_dl_ng.helper.tidal_auth.http_client import (
    api_headers,
    auth_headers,
    get_http_client,
    update_global_client,
)
from tidal_dl_ng.helper.tidal_auth.proxy import (
    INVALID_CREDENTIAL_STATUS_CODES,
    MAX_RETRIES,
    RATE_LIMITED_STATUS_CODES,
    USE_PROXIES,
)
from tidal_dl_ng.helper.tidal_auth.token_storage import (
    TokenEntry,
    TokenResponse,
    find_token_entry,
    save_token_entry,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    FnPrint = Callable[[str], None]

#: HTTP status code indicating success.
_HTTP_OK: int = 200


async def poll_for_authorization(
    url: str,
    data: TokenEntry,
    auth: tuple[str, str],
) -> TokenResponse:
    """Poll the TIDAL token endpoint until authorization is complete.

    Args:
        url: The OAuth token endpoint URL.
        data: The form data for the token request.
        auth: HTTP basic auth tuple of (client_id, client_secret).

    Returns:
        TokenResponse: The JSON response from the token endpoint
            containing access_token, refresh_token, etc.
    """
    headers = auth_headers()
    async with httpx.AsyncClient(headers=headers) as client:
        while True:
            response = await client.post(url, data=data, auth=auth)
            if response.status_code == _HTTP_OK:
                result: TokenResponse = response.json()
                return result


async def handle_refresh_error(
    response: httpx.Response,
) -> None:
    """Handle errors from the token refresh endpoint.

    Args:
        response: The HTTP response to check.

    Raises:
        httpx.HTTPStatusError: If the response indicates an error.
    """
    if response.status_code in INVALID_CREDENTIAL_STATUS_CODES:
        try:
            error_data = response.json()
            error = error_data.get("error")
            if error in {"invalid_client", "invalid_grant"}:
                error_desc = str(
                    error_data.get("error_description", "Unknown error")
                )
                msg = f"Tidal Auth Error: {error_desc}"
                raise httpx.HTTPStatusError(
                    msg,
                    request=response.request,
                    response=response,
                )
        except ValueError:
            pass
    response.raise_for_status()


async def handle_request_error(attempt: int, max_retries: int) -> None:
    """Handle request errors during token refresh.

    Args:
        attempt: The current attempt number.
        max_retries: The maximum number of retries.

    Raises:
        httpx.RequestError: If the request fails after retries.
    """
    if USE_PROXIES and attempt < max_retries - 1:
        await update_global_client(force_new_proxy=True)
        return
    msg = "Request failed"
    raise httpx.RequestError(msg)


async def handle_status_error(
    e: httpx.HTTPStatusError, attempt: int, max_retries: int
) -> None:
    """Handle HTTP status errors during token refresh.

    Args:
        e: The HTTP status error.
        attempt: The current attempt number.
        max_retries: The maximum number of retries.

    Raises:
        httpx.HTTPStatusError: If the error is not rate limiting or
            retries are exhausted.
    """
    if (
        USE_PROXIES
        and e.response.status_code in RATE_LIMITED_STATUS_CODES
        and attempt < max_retries - 1
    ):
        await update_global_client(force_new_proxy=True)
        return
    raise e


async def refresh_access_token(
    refresh_token: str,
    client_id: str = HIFI_REQUEST_CLIENT_ID,
    client_secret: str = HIFI_REQUEST_CLIENT_SECRET,
) -> TokenEntry:
    """Refresh an OAuth access token using the refresh_token grant.

    Uses the shared HTTP client with proxy support and retry logic
    for transient failures.

    Args:
        refresh_token: The refresh token to use.
        client_id: The client ID for the refresh request.
        client_secret: The client secret for the refresh request.

    Returns:
        TokenEntry: The JSON response containing the new
            access_token and related fields.

    Raises:
        httpx.HTTPStatusError: If the refresh request fails.
    """
    data = {
        "client_id": client_id,
        "refresh_token": refresh_token,
        "grant_type": HIFI_OAUTH_GRANT_TYPE_REFRESH,
        "scope": HIFI_OAUTH_SCOPE,
    }

    max_retries = MAX_RETRIES if USE_PROXIES else 1
    for attempt in range(max_retries):
        try:
            client = await get_http_client()
            response = await client.post(
                HIFI_TOKEN_URL,
                data=data,
                auth=(client_id, client_secret),
            )

            await handle_refresh_error(response)
            return cast("TokenEntry", response.json())
        except httpx.RequestError:
            await handle_request_error(attempt, max_retries)
            continue
        except httpx.HTTPStatusError as e:
            await handle_status_error(e, attempt, max_retries)
            continue
    msg = "Token refresh failed after all retries"
    raise RuntimeError(msg)  # pragma: no cover


async def verify_token(
    access_token: str,
    track_id: str = HIFI_VERIFICATION_TRACK_ID,
    quality: str = HIFI_VERIFICATION_QUALITY,
) -> TokenEntry:
    """Verify a token by requesting playback info for a known track.

    Uses the shared HTTP client for connection reuse.

    Args:
        access_token: The OAuth access token to verify.
        track_id: The track ID to use for verification.
        quality: The audio quality to request (e.g. "HI_RES").

    Returns:
        TokenEntry: The JSON response from the playbackinfopostpaywall
            endpoint, which includes audioQuality and stream info.
    """
    url = HIFI_PLAYBACK_INFO_URL_TEMPLATE.format(
        track_id=track_id, quality=quality
    )
    headers = api_headers(access_token)
    client = await get_http_client()
    response = await client.get(url, headers=headers)
    response.raise_for_status()
    return cast("TokenEntry", response.json())


async def run_device_authorization_flow(
    fn_print: FnPrint,
    *,
    open_browser: bool = True,
) -> TokenEntry | None:
    """Execute the full OAuth 2.0 Device Authorization flow.

    This function:
      1. Requests a device code from TIDAL's device_authorization endpoint.
      2. Opens the verification URL in a browser (if ``open_browser``).
      3. Polls the token endpoint until the user authorizes the device.
      4. Saves the resulting token entry.
      5. Verifies the token via the playbackinfopostpaywall endpoint.

    Args:
        fn_print: Callback for printing status messages to the user.
        open_browser: Whether to automatically open the verification URL.

    Returns:
        TokenEntry | None: The saved token entry, or None if the
            flow failed.
    """
    fn_print(f"Trying Client ID: {HIFI_AUTH_CLIENT_ID}")

    # Step 1: Request device code
    headers = auth_headers()
    data = {"client_id": HIFI_AUTH_CLIENT_ID, "scope": HIFI_OAUTH_SCOPE}

    async with httpx.AsyncClient(headers=headers) as client:
        response = await client.post(
            HIFI_DEVICE_AUTH_URL, data=data, headers=headers
        )

    if response.status_code != _HTTP_OK:
        fn_print(f"Error {response.status_code} during device authorization.")
        return None

    res = response.json()
    verify_url = str(res["verificationUriComplete"])
    device_code = str(res["deviceCode"])
    expires_in = int(res.get("expiresIn", 0))

    fn_print(f"Verification URL: {verify_url}")
    fn_print(f"Device code: {device_code}")
    fn_print(f"Expires in: {expires_in} seconds")

    if open_browser:
        webbrowser.open(verify_url)

    # Step 2: Poll for authorization
    token_data: TokenResponse = {
        "client_id": HIFI_AUTH_CLIENT_ID,
        "scope": HIFI_OAUTH_SCOPE,
        "device_code": device_code,
        "grant_type": HIFI_OAUTH_GRANT_TYPE_DEVICE,
        "expires_in": 0,
        "error": None,
        "error_description": None,
    }
    basic = (HIFI_AUTH_CLIENT_ID, HIFI_AUTH_CLIENT_SECRET)

    fn_print("Waiting for authorization... (polling)")
    auth_response = await poll_for_authorization(
        HIFI_TOKEN_URL, cast("TokenEntry", token_data), basic
    )

    access_token = str(auth_response.get("access_token", ""))
    refresh_token = str(auth_response.get("refresh_token", ""))
    _auth_resp: TokenResponse = auth_response
    _user_info: Any = _auth_resp.get("user")
    user_id = ""
    if isinstance(_user_info, dict):
        user_info_dict = cast("dict[str, Any]", _user_info)
        if (user_id_val := user_info_dict.get("userId", "")) is not None:
            user_id = str(user_id_val)

    entry = TokenEntry(
        client_id=HIFI_REQUEST_CLIENT_ID,
        client_secret=HIFI_REQUEST_CLIENT_SECRET,
        refresh_token=refresh_token,
        user_id=user_id,
        access_token=access_token,
        expires_at=0,
        client_ID=HIFI_REQUEST_CLIENT_ID,
        userID=user_id,
        token_type=str(auth_response.get("token_type", "Bearer")),
        expires_in=int(auth_response.get("expires_in", 0)),
        created_at=datetime.now(UTC).isoformat(),
    )

    save_token_entry(entry)
    fn_print(f"Token saved for user ID: {user_id}")

    # Step 3: Verify the token
    try:
        verification = await verify_token(access_token)
        audio_quality = str(verification.get("audioQuality", "UNKNOWN"))
        fn_print(f"Token verified. Audio quality: {audio_quality}")
        if audio_quality == HIFI_VERIFICATION_QUALITY:
            fn_print("Token is valid for HI_RES lossless streams!")
        else:
            fn_print(
                f"WARNING: Token is capped at '{audio_quality}' "
                f"instead of {HIFI_VERIFICATION_QUALITY}."
            )
    except (httpx.HTTPError, KeyError) as e:
        fn_print(f"WARNING: Could not verify token: {e}")

    return entry


def run_device_authorization_flow_sync(
    fn_print: FnPrint,
    *,
    open_browser: bool = True,
) -> TokenEntry | None:
    """Synchronous wrapper for :func:`run_device_authorization_flow`.

    Args:
        fn_print: Callback for printing status messages to the user.
        open_browser: Whether to automatically open the verification URL.

    Returns:
        TokenEntry | None: The saved token entry, or None if failed.
    """
    return asyncio.run(
        run_device_authorization_flow(fn_print, open_browser=open_browser)
    )


async def get_valid_token(
    client_id: str | None = None,
    *,
    force_refresh: bool = False,
) -> tuple[str, TokenEntry] | None:
    """Retrieve a valid access token, refreshing if necessary.

    Args:
        client_id: If provided, only entries matching this client_ID
            are considered.
        force_refresh: If True, always refresh the token.

    Returns:
        tuple[str, TokenEntry] | None: A tuple of (access_token,
            token_entry), or None if no valid token is available.
    """
    if (entry := find_token_entry(client_id)) is None:
        return None

    access_token = str(entry.get("access_token", ""))
    if not access_token or force_refresh:
        if not (refresh_token := str(entry.get("refresh_token", ""))):
            return None
        try:
            refreshed = await refresh_access_token(refresh_token)
            access_token = str(refreshed.get("access_token", ""))
            entry["access_token"] = access_token
            entry["refresh_token"] = str(
                refreshed.get("refresh_token", refresh_token)
            )
            entry["expires_in"] = int(refreshed.get("expires_in", 0))
            entry["created_at"] = datetime.now(UTC).isoformat()
            save_token_entry(entry)
        except httpx.HTTPError:
            return None
        except KeyError:
            return None

    return access_token, entry


def get_valid_token_sync(
    client_id: str | None = None,
    *,
    force_refresh: bool = False,
) -> tuple[str, TokenEntry] | None:
    """Synchronous wrapper for :func:`get_valid_token`.

    Args:
        client_id: If provided, only entries matching this client_ID
            are considered.
        force_refresh: If True, always refresh the token.

    Returns:
        tuple[str, TokenEntry] | None: A tuple of (access_token,
            token_entry), or None if no valid token is available.
    """
    return asyncio.run(get_valid_token(client_id, force_refresh=force_refresh))


async def verify_existing_token(
    access_token: str,
) -> bool:
    """Check if an existing access token is still valid.

    Args:
        access_token: The access token to verify.

    Returns:
        bool: True if the token is valid, False otherwise.
    """
    try:
        await verify_token(access_token)
    except httpx.HTTPError:
        return False
    return True


def verify_existing_token_sync(access_token: str) -> bool:
    """Synchronous wrapper for :func:`verify_existing_token`.

    Args:
        access_token: The access token to verify.

    Returns:
        bool: True if the token is valid, False otherwise.
    """
    return asyncio.run(verify_existing_token(access_token))


def get_token_client_credentials() -> tuple[str, str]:
    """Return the request client credentials for API calls.

    Returns:
        tuple[str, str]: (client_id, client_secret) for making
            authenticated API requests.
    """
    return HIFI_REQUEST_CLIENT_ID, HIFI_REQUEST_CLIENT_SECRET


def get_auth_client_credentials() -> tuple[str, str]:
    """Return the auth client credentials for device authorization.

    Returns:
        tuple[str, str]: (client_id, client_secret) for the device
            authorization flow.
    """
    return HIFI_AUTH_CLIENT_ID, HIFI_AUTH_CLIENT_SECRET
