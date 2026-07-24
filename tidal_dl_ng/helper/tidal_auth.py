"""HiFi-API OAuth 2.0 Device Authorization flow for TIDAL.

This module implements the upgraded authentication process that uses
direct OAuth 2.0 Device Authorization Grant with custom credentials,
bypassing ``tidalapi``'s ``login_pkce()`` which has known issues with
lossless stream retrieval.

Key features:
  * Uses separate auth and request credential pairs (the request pair
    is what TIDAL trusts for lossless/HI_RES streams).
  * Custom ``User-Agent: okhttp/5.3.2`` (Android client) which TIDAL
    accepts for lossless playback.
  * Stores tokens as a list in ``token.json`` for multi-account support.
  * Verifies token validity via the ``playbackinfopostpaywall`` endpoint.
  * Supports token refresh via the OAuth refresh_token grant.

The module provides both async and sync entry points so it can be used
from CLI (sync) and GUI (async) contexts.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import webbrowser
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from tidal_dl_ng.constants import (
    HIFI_AUTH_CLIENT_ID,
    HIFI_AUTH_CLIENT_SECRET,
    HIFI_DEVICE_AUTH_URL,
    HIFI_OAUTH_GRANT_TYPE_DEVICE,
    HIFI_OAUTH_GRANT_TYPE_REFRESH,
    HIFI_OAUTH_SCOPE,
    HIFI_PLAYBACK_INFO_URL_TEMPLATE,
    HIFI_POLL_INTERVAL_SEC,
    HIFI_REQUEST_CLIENT_ID,
    HIFI_REQUEST_CLIENT_SECRET,
    HIFI_TOKEN_URL,
    HIFI_USER_AGENT,
    HIFI_VERIFICATION_QUALITY,
    HIFI_VERIFICATION_TRACK_ID,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable

    from typing import Any

    FnPrint = Callable[[str], None]

#: Default token file path, overridable via ``TOKEN_FILE`` env var.
TOKEN_FILE: Path = Path(
    os.getenv(
        "TOKEN_FILE",
        Path(__file__).resolve().parent.parent.parent / "token.json",
    )
)


def _auth_headers() -> dict[str, str]:
    """Build common HTTP headers for TIDAL OAuth API calls.

    Returns:
        dict[str, str]: Headers including User-Agent, Accept, and
            platform identifiers matching the Android client.
    """
    return {
        "User-Agent": HIFI_USER_AGENT,
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "Accept-Language": "en-US,en;q=0.9",
        "X-Platform": "android",
    }


def _api_headers(access_token: str) -> dict[str, str]:
    """Build HTTP headers for authenticated TIDAL API calls.

    Args:
        access_token: The OAuth access token to use as Bearer.

    Returns:
        dict[str, str]: Headers including Authorization and platform
            identifiers.
    """
    return {
        **_auth_headers(),
        "authorization": f"Bearer {access_token}",
        "X-Tidal-Platform": "android",
    }


def load_tokens() -> list[dict[str, Any]]:
    """Load all stored token entries from the token file.

    Returns:
        list[dict[str, Any]]: List of token entry dictionaries.
            Returns an empty list if the file does not exist.
    """
    if TOKEN_FILE.exists():
        with TOKEN_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            return [data]
    return []


def save_token_entry(entry: dict[str, Any]) -> None:
    """Persist a token entry, replacing any existing entry with the same
    client_ID and refresh_token.

    Args:
        entry: The token entry dictionary to save.
    """
    tokens = load_tokens()
    tokens = [
        t
        for t in tokens
        if not (
            t.get("client_ID") == entry.get("client_ID")
            and t.get("refresh_token") == entry.get("refresh_token")
        )
    ]
    tokens.append(entry)
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    with TOKEN_FILE.open("w", encoding="utf-8") as f:
        json.dump(tokens, f, indent=4)


def delete_token_entry(client_id: str, refresh_token: str) -> None:
    """Remove a specific token entry from the token file.

    Args:
        client_id: The client_ID of the entry to remove.
        refresh_token: The refresh_token of the entry to remove.
    """
    tokens = load_tokens()
    tokens = [
        t
        for t in tokens
        if not (
            t.get("client_ID") == client_id
            and t.get("refresh_token") == refresh_token
        )
    ]
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    with TOKEN_FILE.open("w", encoding="utf-8") as f:
        json.dump(tokens, f, indent=4)


def find_token_entry(
    client_id: str | None = None,
) -> dict[str, Any] | None:
    """Find a stored token entry, optionally matching a client_id.

    Args:
        client_id: If provided, only entries matching this client_ID
            are considered. If None, the first entry is returned.

    Returns:
        dict[str, Any] | None: The matching token entry, or None.
    """
    tokens = load_tokens()
    if client_id is not None:
        for entry in tokens:
            if entry.get("client_ID") == client_id:
                return entry
    if tokens:
        return tokens[0]
    return None


async def poll_for_authorization(
    url: str,
    data: dict[str, Any],
    auth: tuple[str, str],
) -> dict[str, Any]:
    """Poll the TIDAL token endpoint until authorization is complete.

    Args:
        url: The OAuth token endpoint URL.
        data: The form data for the token request.
        auth: HTTP basic auth tuple of (client_id, client_secret).

    Returns:
        dict[str, Any]: The JSON response from the token endpoint
            containing access_token, refresh_token, etc.
    """
    headers = _auth_headers()
    async with httpx.AsyncClient(headers=headers) as client:
        while True:
            response = await client.post(url, data=data, auth=auth)
            if response.status_code == 200:
                return response.json()
            await asyncio.sleep(HIFI_POLL_INTERVAL_SEC)


async def refresh_access_token(
    refresh_token: str,
    client_id: str = HIFI_REQUEST_CLIENT_ID,
    client_secret: str = HIFI_REQUEST_CLIENT_SECRET,
) -> dict[str, Any]:
    """Refresh an OAuth access token using the refresh_token grant.

    Args:
        refresh_token: The refresh token to use.
        client_id: The client ID for the refresh request.
        client_secret: The client secret for the refresh request.

    Returns:
        dict[str, Any]: The JSON response containing the new
            access_token and related fields.

    Raises:
        httpx.HTTPStatusError: If the refresh request fails.
    """
    headers = _auth_headers()
    data = {
        "client_id": client_id,
        "refresh_token": refresh_token,
        "grant_type": HIFI_OAUTH_GRANT_TYPE_REFRESH,
        "scope": HIFI_OAUTH_SCOPE,
    }
    async with httpx.AsyncClient(headers=headers) as client:
        response = await client.post(
            HIFI_TOKEN_URL, data=data, auth=(client_id, client_secret)
        )
        response.raise_for_status()
        return response.json()


async def verify_token(
    access_token: str,
    track_id: str = HIFI_VERIFICATION_TRACK_ID,
    quality: str = HIFI_VERIFICATION_QUALITY,
) -> dict[str, Any]:
    """Verify a token by requesting playback info for a known track.

    Args:
        access_token: The OAuth access token to verify.
        track_id: The track ID to use for verification.
        quality: The audio quality to request (e.g. "HI_RES").

    Returns:
        dict[str, Any]: The JSON response from the playbackinfopostpaywall
            endpoint, which includes audioQuality and stream info.
    """
    url = HIFI_PLAYBACK_INFO_URL_TEMPLATE.format(
        track_id=track_id, quality=quality
    )
    headers = _api_headers(access_token)
    async with httpx.AsyncClient(headers=headers) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.json()


async def run_device_authorization_flow(
    fn_print: FnPrint,
    *,
    open_browser: bool = True,
) -> dict[str, Any] | None:
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
        dict[str, Any] | None: The saved token entry, or None if the
            flow failed.
    """
    fn_print(f"Trying Client ID: {HIFI_AUTH_CLIENT_ID}")

    # Step 1: Request device code
    headers = _auth_headers()
    data = {"client_id": HIFI_AUTH_CLIENT_ID, "scope": HIFI_OAUTH_SCOPE}

    async with httpx.AsyncClient(headers=headers) as client:
        response = await client.post(
            HIFI_DEVICE_AUTH_URL, data=data, headers=headers
        )

    if response.status_code != 200:
        fn_print(f"Error {response.status_code} during device authorization.")
        return None

    res = response.json()
    verify_url = res["verificationUriComplete"]
    device_code = res["deviceCode"]
    expires_in = int(res.get("expiresIn", 0))

    fn_print(f"Verification URL: {verify_url}")
    fn_print(f"Device code: {device_code}")
    fn_print(f"Expires in: {expires_in} seconds")

    if open_browser:
        webbrowser.open(verify_url)

    # Step 2: Poll for authorization
    token_data = {
        "client_id": HIFI_AUTH_CLIENT_ID,
        "scope": HIFI_OAUTH_SCOPE,
        "device_code": device_code,
        "grant_type": HIFI_OAUTH_GRANT_TYPE_DEVICE,
    }
    basic = (HIFI_AUTH_CLIENT_ID, HIFI_AUTH_CLIENT_SECRET)

    fn_print("Waiting for authorization... (polling)")
    auth_response = await poll_for_authorization(
        HIFI_TOKEN_URL, token_data, basic
    )

    access_token = auth_response["access_token"]
    refresh_token = auth_response["refresh_token"]
    user_id = auth_response["user"]["userId"]

    entry: dict[str, Any] = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "userID": user_id,
        "client_ID": HIFI_REQUEST_CLIENT_ID,
        "client_secret": HIFI_REQUEST_CLIENT_SECRET,
        "token_type": auth_response.get("token_type", "Bearer"),
        "expires_in": auth_response.get("expires_in", 0),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    save_token_entry(entry)
    fn_print(f"Token saved for user ID: {user_id}")

    # Step 3: Verify the token
    try:
        verification = await verify_token(access_token)
        audio_quality = verification.get("audioQuality", "UNKNOWN")
        fn_print(f"Token verified. Audio quality: {audio_quality}")
        if audio_quality == HIFI_VERIFICATION_QUALITY:
            fn_print("Token is valid for HI_RES lossless streams!")
        else:
            fn_print(
                f"WARNING: Token is capped at '{audio_quality}' "
                f"instead of {HIFI_VERIFICATION_QUALITY}."
            )
    except Exception as e:  # noqa: BLE001
        fn_print(f"WARNING: Could not verify token: {e}")

    return entry


def run_device_authorization_flow_sync(
    fn_print: FnPrint,
    *,
    open_browser: bool = True,
) -> dict[str, Any] | None:
    """Synchronous wrapper for :func:`run_device_authorization_flow`.

    Args:
        fn_print: Callback for printing status messages to the user.
        open_browser: Whether to automatically open the verification URL.

    Returns:
        dict[str, Any] | None: The saved token entry, or None if failed.
    """
    return asyncio.run(
        run_device_authorization_flow(fn_print, open_browser=open_browser)
    )


async def get_valid_token(
    client_id: str | None = None,
    *,
    force_refresh: bool = False,
) -> tuple[str, dict[str, Any]] | None:
    """Retrieve a valid access token, refreshing if necessary.

    Args:
        client_id: If provided, only entries matching this client_ID
            are considered.
        force_refresh: If True, always refresh the token.

    Returns:
        tuple[str, dict[str, Any]] | None: A tuple of (access_token,
            token_entry), or None if no valid token is available.
    """
    entry = find_token_entry(client_id)
    if entry is None:
        return None

    access_token = entry.get("access_token", "")
    if not access_token or force_refresh:
        refresh_token = entry.get("refresh_token", "")
        if not refresh_token:
            return None
        try:
            refreshed = await refresh_access_token(refresh_token)
            access_token = refreshed["access_token"]
            entry["access_token"] = access_token
            entry["refresh_token"] = refreshed.get(
                "refresh_token", refresh_token
            )
            entry["expires_in"] = refreshed.get("expires_in", 0)
            entry["created_at"] = datetime.now(timezone.utc).isoformat()
            save_token_entry(entry)
        except Exception:  # noqa: BLE001
            return None

    return access_token, entry


def get_valid_token_sync(
    client_id: str | None = None,
    *,
    force_refresh: bool = False,
) -> tuple[str, dict[str, Any]] | None:
    """Synchronous wrapper for :func:`get_valid_token`.

    Args:
        client_id: If provided, only entries matching this client_ID
            are considered.
        force_refresh: If True, always refresh the token.

    Returns:
        tuple[str, dict[str, Any]] | None: A tuple of (access_token,
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
        return True
    except Exception:  # noqa: BLE001
        return False


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
