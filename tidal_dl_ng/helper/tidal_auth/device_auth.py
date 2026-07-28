"""OAuth 2.0 Device Authorization flow for TIDAL.

Copyright (c) 2024-2026 TIDAL-Downloader-NG contributors

This module implements the full device authorization flow for TIDAL,
including device code request, user authorization polling, and token
verification via the playbackinfopostpaywall endpoint.

It uses the shared HTTP client from :mod:`http_client` for connection
pooling, proxy support, and automatic proxy rotation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import asyncio
import webbrowser
from datetime import UTC, datetime

import httpx

from tidal_dl_ng.constants import (
    HIFI_AUTH_CLIENT_ID,
    HIFI_AUTH_CLIENT_SECRET,
    HIFI_DEVICE_AUTH_URL,
    HIFI_OAUTH_GRANT_TYPE_DEVICE,
    HIFI_OAUTH_SCOPE,
    HIFI_REQUEST_CLIENT_ID,
    HIFI_REQUEST_CLIENT_SECRET,
    HIFI_TOKEN_URL,
    HIFI_VERIFICATION_QUALITY,
)
from tidal_dl_ng.helper.tidal_auth.auth import (
    poll_for_authorization,
    verify_token,
)
from tidal_dl_ng.helper.tidal_auth.http_client import (
    auth_headers,
    get_http_client,
)
from tidal_dl_ng.helper.tidal_auth.token_storage import (
    TokenEntry,
    TokenResponse,
    save_token_entry,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    FnPrint = Callable[[str], None]


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

    client = await get_http_client()
    response = await client.post(
        HIFI_DEVICE_AUTH_URL, data=data, headers=headers
    )

    if response.status_code != 200:  # noqa: PLR2004
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
    _user_info = _auth_resp.get("user")
    user_id = ""
    if isinstance(_user_info, dict):
        user_info_dict = _user_info
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
