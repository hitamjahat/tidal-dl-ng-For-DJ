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
import random
import time
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

# --- Proxy support (merged from hifi-api-main/main.py) ---

#: List of proxies loaded from file at module load time.
_proxies: list[str] = []

#: Cache of the last proxy confirmed to be working.
_last_known_good_proxy: str | None = None

#: Maximum number of proxy candidates to test per get_working_proxy() call.
MAX_PROXY_CANDIDATES: int = 10

#: Maximum number of concurrent proxy tests inside get_working_proxy().
_PROXY_TEST_CONCURRENCY: int = 5

#: Whether to use proxies for HTTP requests.
USE_PROXIES: bool = os.getenv("USE_PROXIES", "False").lower() in (
    "true",
    "1",
    "yes",
)

#: Whether to rotate proxies on each token refresh.
ROTATE_PROXIES_ON_REFRESH: bool = os.getenv(
    "ROTATE_PROXIES_ON_REFRESH", "False"
).lower() in ("true", "1", "yes")

#: Path to the proxies file.
PROXIES_FILE: str = os.getenv("PROXIES_FILE", "proxies.txt")

#: Whether to fall back to direct connection if no proxy is available.
FALLBACK_TO_DIRECT_CONNECTION: bool = os.getenv(
    "FALLBACK_TO_DIRECT_CONNECTION", "False"
).lower() in ("true", "1", "yes")

#: Maximum retries for proxy-based requests.
MAX_RETRIES: int = max(1, int(os.getenv("MAX_RETRIES", "2")))

#: Rate limiting retry settings.
_RATE_LIMIT_MAX_RETRIES: int = 3
_RATE_LIMIT_BASE_DELAY: float = 1.0
_RATE_LIMIT_MAX_DELAY: float = 10.0

#: Shared HTTP client for connection reuse.
_http_client: httpx.AsyncClient | None = None
_http_client_proxy_url: str | None = None
_http_client_lock: asyncio.Lock = asyncio.Lock()

#: One lock per credential to avoid global contention during token refreshes.
_refresh_locks: dict[str, asyncio.Lock] = {}

#: Global semaphore to limit concurrent album track fetches.
_album_tracks_sem: asyncio.Semaphore = asyncio.Semaphore(20)


def _tidal_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Build common HTTP headers for TIDAL API calls.

    Matches the Android client headers that TIDAL accepts for
    lossless stream retrieval.

    Args:
        extra: Optional additional headers to merge.

    Returns:
        dict[str, str]: Headers including User-Agent, Accept, and
            platform identifiers.
    """
    h = {
        "User-Agent": HIFI_USER_AGENT,
        "Accept": "*/*",
        "Accept-Encoding": "gzip",
        "Accept-Language": "en-US,en;q=0.9",
        "X-Platform": "android",
        "X-Tidal-Platform": "android",
    }
    if extra:
        h.update(extra)
    return h


_TIDAL_DEFAULT_HEADERS: dict[str, str] = _tidal_headers()


def _auth_headers() -> dict[str, str]:
    """Build headers for OAuth device authorization and token requests.

    Returns:
        dict[str, str]: Headers for OAuth endpoint calls.
    """
    return _tidal_headers()


def _api_headers(access_token: str) -> dict[str, str]:
    """Build headers for authenticated TIDAL API requests.

    Args:
        access_token: The OAuth access token.

    Returns:
        dict[str, str]: Headers including Authorization bearer token.
    """
    return _tidal_headers({"Authorization": f"Bearer {access_token}"})


#: Whether to log upstream responses at DEBUG level (dev mode).
DEV_MODE: bool = os.getenv("DEV_MODE", "False").lower() in (
    "true",
    "1",
    "yes",
)


def _log_response(method: str, url: str, resp: httpx.Response) -> None:
    """Log HTTP response details for debugging.

    Args:
        method: The HTTP method (e.g. "GET", "POST").
        url: The request URL.
        resp: The httpx response object.
    """
    if not DEV_MODE:
        return
    from tidal_dl_ng.logger import fn_logger

    fn_logger.debug(
        "[DEV] %s %s -> %s\n  headers: %s\n  body: %s",
        method,
        url,
        resp.status_code,
        dict(resp.headers),
        resp.text[:2000],
    )


def _pick_credential() -> dict[str, Any]:
    """Pick a random credential from loaded tokens.

    Returns:
        dict[str, Any]: A credential dictionary.

    Raises:
        RuntimeError: If no credentials are available.
    """
    tokens = load_tokens()
    if not tokens:
        raise RuntimeError(
            "No Tidal credentials available; populate token.json"
        )
    return random.choice(tokens)


def _build_http_client(
    proxy_url: str | None = None,
) -> httpx.AsyncClient:
    """Build an httpx AsyncClient with TIDAL headers and optional proxy.

    Args:
        proxy_url: Optional proxy URL to route requests through.

    Returns:
        httpx.AsyncClient: Configured async HTTP client.
    """
    client_kwargs = {
        "http2": True,
        "headers": _tidal_headers(),
        "timeout": httpx.Timeout(connect=3.0, read=12.0, write=8.0, pool=12.0),
        "limits": httpx.Limits(
            max_keepalive_connections=500,
            max_connections=1000,
            keepalive_expiry=30.0,
        ),
    }

    try:
        return httpx.AsyncClient(proxy=proxy_url, **client_kwargs)
    except TypeError:
        legacy_proxies = {"all://": proxy_url} if proxy_url else None
        return httpx.AsyncClient(proxies=legacy_proxies, **client_kwargs)


def _build_proxy_test_client(proxy_url: str) -> httpx.AsyncClient:
    """Build a lightweight httpx client for testing proxy connectivity.

    Args:
        proxy_url: The proxy URL to test.

    Returns:
        httpx.AsyncClient: A client configured to use the proxy.
    """
    try:
        return httpx.AsyncClient(proxy=proxy_url, timeout=5.0)
    except TypeError:
        return httpx.AsyncClient(proxies={"all://": proxy_url}, timeout=5.0)


def load_proxies() -> None:
    """Load proxies from file into the global _proxies list."""
    global _proxies
    if not os.path.exists(PROXIES_FILE):
        _proxies = []
        return
    with open(PROXIES_FILE, "r", encoding="utf-8") as f:
        _proxies = [line.strip() for line in f if line.strip()]


async def test_proxy(proxy_url: str) -> bool:
    """Test if a proxy is working by making a simple request.

    Args:
        proxy_url: The proxy URL to test.

    Returns:
        bool: True if the proxy is working, False otherwise.
    """
    try:
        async with _build_proxy_test_client(proxy_url) as client:
            resp = await client.get("http://example.com")
            return resp.status_code == 200
    except Exception:  # noqa: BLE001
        return False


async def get_working_proxy(
    avoid_proxy: str | None = None,
) -> str | None:
    """Find a working proxy from the loaded proxy list.

    Args:
        avoid_proxy: A proxy URL to skip (e.g. the current one).

    Returns:
        str | None: A working proxy URL, or None if none found.
    """
    global _last_known_good_proxy

    if not _proxies:
        return None

    if _last_known_good_proxy and _last_known_good_proxy != avoid_proxy:
        if await test_proxy(_last_known_good_proxy):
            return _last_known_good_proxy

    shuffled = _proxies[:]
    random.shuffle(shuffled)

    if avoid_proxy:
        candidates = [p for p in shuffled if p != avoid_proxy]
        if not candidates:
            candidates = shuffled
    else:
        candidates = shuffled

    if _last_known_good_proxy:
        candidates = [p for p in candidates if p != _last_known_good_proxy]
    candidates = candidates[:MAX_PROXY_CANDIDATES]

    sem = asyncio.Semaphore(_PROXY_TEST_CONCURRENCY)
    found_event = asyncio.Event()
    selected: list[str | None] = [None]

    async def probe(proxy: str) -> None:
        if found_event.is_set():
            return
        async with sem:
            if found_event.is_set():
                return
            if await test_proxy(proxy):
                if not found_event.is_set():
                    selected[0] = proxy
                    found_event.set()

    await asyncio.gather(
        *[probe(p) for p in candidates], return_exceptions=True
    )

    if selected[0]:
        _last_known_good_proxy = selected[0]
    return selected[0]


async def update_global_client(
    force_new_proxy: bool = False,
) -> None:
    """Update the global HTTP client, optionally with a new proxy.

    Args:
        force_new_proxy: If True, force selection of a new proxy.
    """
    global _http_client, _http_client_proxy_url
    async with _http_client_lock:
        proxy_to_avoid = None
        if force_new_proxy and _http_client_proxy_url:
            proxy_to_avoid = _http_client_proxy_url

        proxy_url = None
        if USE_PROXIES:
            proxy_url = await get_working_proxy(avoid_proxy=proxy_to_avoid)
            if not proxy_url:
                if FALLBACK_TO_DIRECT_CONNECTION:
                    pass
                else:
                    raise RuntimeError("No working proxies available")

        if _http_client and _http_client_proxy_url == proxy_url:
            return

        new_client = _build_http_client(proxy_url)
        old_client = _http_client
        _http_client = new_client
        _http_client_proxy_url = proxy_url

        if old_client is not None:
            asyncio.create_task(_delayed_close(old_client))


async def _delayed_close(client: httpx.AsyncClient) -> None:
    """Close an HTTP client after a short delay.

    Args:
        client: The client to close.
    """
    await asyncio.sleep(15)
    await client.aclose()


async def get_http_client() -> httpx.AsyncClient:
    """Get or create the shared HTTP client.

    Returns:
        httpx.AsyncClient: The shared async HTTP client.
    """
    global _http_client, _http_client_proxy_url
    if _http_client is None:
        async with _http_client_lock:
            if _http_client is None:
                proxy_url = None
                if USE_PROXIES:
                    proxy_url = await get_working_proxy()
                _http_client = _build_http_client(proxy_url)
                _http_client_proxy_url = proxy_url
    return _http_client


def load_tokens() -> list[dict[str, Any]]:
    """Load all stored token entries from the token file.

    Supports both list and dict formats in token.json. Also loads
    credentials from environment variables (CLIENT_ID, CLIENT_SECRET,
    REFRESH_TOKEN, USER_ID) as a fallback, merged with file-based tokens.

    Returns:
        list[dict[str, Any]]: List of token entry dictionaries.
            Returns an empty list if no tokens are available.
    """
    creds: list[dict[str, Any]] = []

    if TOKEN_FILE.exists():
        with TOKEN_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                data = [data]

            for entry in data:
                cred = {
                    "client_id": (
                        entry.get("client_ID") or HIFI_REQUEST_CLIENT_ID
                    ),
                    "client_secret": (
                        entry.get("client_secret")
                        or HIFI_REQUEST_CLIENT_SECRET
                    ),
                    "refresh_token": entry.get("refresh_token") or "",
                    "user_id": entry.get("userID") or "",
                    "access_token": entry.get("access_token"),
                    "expires_at": 0,
                    "client_ID": (
                        entry.get("client_ID") or HIFI_REQUEST_CLIENT_ID
                    ),
                    "client_secret": (
                        entry.get("client_secret")
                        or HIFI_REQUEST_CLIENT_SECRET
                    ),
                    "userID": entry.get("userID") or "",
                    "token_type": entry.get("token_type", "Bearer"),
                }
                if cred["refresh_token"]:
                    creds.append(cred)

    # Add env var credential if available and unique
    env_refresh = os.getenv("REFRESH_TOKEN")
    env_client_id = os.getenv("CLIENT_ID", HIFI_REQUEST_CLIENT_ID)
    env_client_secret = os.getenv("CLIENT_SECRET", HIFI_REQUEST_CLIENT_SECRET)
    env_user_id = os.getenv("USER_ID")

    if env_refresh:
        env_cred = {
            "client_id": env_client_id,
            "client_secret": env_client_secret,
            "refresh_token": env_refresh,
            "user_id": env_user_id or "",
            "access_token": None,
            "expires_at": 0,
            "client_ID": env_client_id,
            "client_secret": env_client_secret,
            "userID": env_user_id or "",
            "token_type": "Bearer",
        }
        if not any(c["refresh_token"] == env_refresh for c in creds):
            creds.append(env_cred)

    return creds


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

    Uses the shared HTTP client with proxy support and retry logic
    for transient failures.

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
    headers = _tidal_headers()
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

            if response.status_code in [400, 401]:
                try:
                    error_data = response.json()
                    if error_data.get("error") in [
                        "invalid_client",
                        "invalid_grant",
                    ]:
                        raise httpx.HTTPStatusError(
                            f"Tidal Auth Error: "
                            f"{error_data.get('error_description')}",
                            request=response.request,
                            response=response,
                        )
                except ValueError:
                    pass

            response.raise_for_status()
            return response.json()
        except httpx.RequestError as e:
            if USE_PROXIES and attempt < max_retries - 1:
                await update_global_client(force_new_proxy=True)
                continue
            raise
        except httpx.HTTPStatusError as e:
            if (
                USE_PROXIES
                and e.response.status_code in [403, 429]
                and attempt < max_retries - 1
            ):
                await update_global_client(force_new_proxy=True)
                continue
            raise


async def verify_token(
    access_token: str,
    track_id: str = HIFI_VERIFICATION_TRACK_ID,
    quality: str = HIFI_VERIFICATION_QUALITY,
) -> dict[str, Any]:
    """Verify a token by requesting playback info for a known track.

    Uses the shared HTTP client for connection reuse.

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
    client = await get_http_client()
    response = await client.get(url, headers=headers)
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


# --- Authenticated HTTP request helpers (merged from hifi-api-main/main.py) ---


async def _lock_for_cred(cred: dict[str, Any]) -> asyncio.Lock:
    """Get or create a lock for a specific credential set.

    Args:
        cred: The credential dictionary.

    Returns:
        asyncio.Lock: A lock specific to this credential.
    """
    key = f"{cred.get('client_id', '')}:{cred.get('refresh_token', '')}"
    lock = _refresh_locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _refresh_locks[key] = lock
    return lock


async def get_tidal_token_for_cred(
    force_refresh: bool = False,
    cred: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Retrieve an access token for a specific credential.

    Args:
        force_refresh: If True, always refresh the token.
        cred: The credential dictionary. If None, picks the first
            available credential.

    Returns:
        tuple[str, dict[str, Any]]: (access_token, credential_dict).
    """
    if cred is None:
        tokens = load_tokens()
        if not tokens:
            raise RuntimeError("No Tidal credentials available")
        cred = tokens[0]

    async with await _lock_for_cred(cred):
        if (
            cred.get("access_token")
            and cred.get("expires_at", 0) > time.time()
        ):
            return cred["access_token"], cred

        if USE_PROXIES and ROTATE_PROXIES_ON_REFRESH:
            await update_global_client(force_new_proxy=True)

        max_retries = MAX_RETRIES if USE_PROXIES else 1
        for attempt in range(max_retries):
            try:
                client = await get_http_client()
                response = await client.post(
                    HIFI_TOKEN_URL,
                    data={
                        "client_id": cred["client_id"],
                        "refresh_token": cred["refresh_token"],
                        "grant_type": HIFI_OAUTH_GRANT_TYPE_REFRESH,
                        "scope": HIFI_OAUTH_SCOPE,
                    },
                    auth=(
                        cred["client_id"],
                        cred["client_secret"],
                    ),
                )

                if response.status_code in [400, 401]:
                    try:
                        error_data = response.json()
                        if error_data.get("error") in [
                            "invalid_client",
                            "invalid_grant",
                        ]:
                            raise httpx.HTTPStatusError(
                                f"Tidal Auth Error: "
                                f"{error_data.get('error_description')}",
                                request=response.request,
                                response=response,
                            )
                    except ValueError:
                        pass

                response.raise_for_status()
                data = response.json()
                new_token = data["access_token"]
                expires_in = data.get("expires_in", 3600)

                cred["access_token"] = new_token
                cred["expires_at"] = time.time() + expires_in - 60

                return new_token, cred
            except httpx.RequestError:
                if USE_PROXIES and attempt < max_retries - 1:
                    await update_global_client(force_new_proxy=True)
                    continue
                raise
            except httpx.HTTPStatusError as e:
                if (
                    USE_PROXIES
                    and e.response.status_code in [403, 429]
                    and attempt < max_retries - 1
                ):
                    await update_global_client(force_new_proxy=True)
                    continue
                raise


async def get_tidal_token(
    force_refresh: bool = False,
) -> tuple[str, dict[str, Any]]:
    """Retrieve an access token, picking a random credential.

    Args:
        force_refresh: If True, always refresh the token.

    Returns:
        tuple[str, dict[str, Any]]: (access_token, credential_dict).
    """
    return await get_tidal_token_for_cred(force_refresh=force_refresh)


async def authed_get_json(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    token: str | None = None,
    cred: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    """Perform an authenticated GET, retrying once on 401.

    Args:
        url: The URL to request.
        params: Optional query parameters.
        token: Optional pre-fetched access token.
        cred: Optional pre-fetched credential dict.

    Returns:
        tuple[dict[str, Any], str, dict[str, Any]]:
            (response_json, access_token, credential_dict).
    """
    if token is None or cred is None:
        token, cred = await get_tidal_token_for_cred(cred=cred)

    client = await get_http_client()
    headers = _api_headers(token)

    for attempt in range(_RATE_LIMIT_MAX_RETRIES + 1):
        response = await client.get(url, headers=headers, params=params)

        if response.status_code == 401:
            token, cred = await get_tidal_token_for_cred(
                force_refresh=True, cred=cred
            )
            headers = _api_headers(token)
            response = await client.get(url, headers=headers, params=params)

        if response.status_code == 429 and attempt < _RATE_LIMIT_MAX_RETRIES:
            delay = min(
                _RATE_LIMIT_BASE_DELAY * (2**attempt),
                _RATE_LIMIT_MAX_DELAY,
            )
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    delay = min(delay, max(float(retry_after), 0))
                except ValueError:
                    pass
            delay = min(delay, _RATE_LIMIT_MAX_DELAY)
            await asyncio.sleep(delay)
            continue

        if response.status_code == 404:
            fresh_token, fresh_cred = await get_tidal_token_for_cred(
                force_refresh=True, cred=cred
            )
            if fresh_token != token:
                headers = _api_headers(fresh_token)
                response = await client.get(
                    url, headers=headers, params=params
                )
                token, cred = fresh_token, fresh_cred

        break

    response.raise_for_status()
    return response.json(), token, cred


async def make_request(
    url: str,
    token: str | None = None,
    params: dict[str, Any] | None = None,
    cred: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Make an authenticated GET request to a TIDAL API endpoint.

    Args:
        url: The URL to request.
        token: Optional pre-fetched access token.
        params: Optional query parameters.
        cred: Optional pre-fetched credential dict.

    Returns:
        dict[str, Any]: Response payload with version info.
    """
    if token is None or cred is None:
        token, cred = await get_tidal_token_for_cred(cred=cred)

    client = await get_http_client()
    headers = _api_headers(token)

    for attempt in range(_RATE_LIMIT_MAX_RETRIES + 1):
        response = await client.get(url, headers=headers, params=params)

        if response.status_code == 401:
            token, cred = await get_tidal_token_for_cred(
                force_refresh=True, cred=cred
            )
            headers = _api_headers(token)
            response = await client.get(url, headers=headers, params=params)

        if response.status_code == 429 and attempt < _RATE_LIMIT_MAX_RETRIES:
            delay = min(
                _RATE_LIMIT_BASE_DELAY * (2**attempt),
                _RATE_LIMIT_MAX_DELAY,
            )
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    delay = min(delay, max(float(retry_after), 0))
                except ValueError:
                    pass
            delay = min(delay, _RATE_LIMIT_MAX_DELAY)
            await asyncio.sleep(delay)
            continue

        if response.status_code == 404:
            fresh_token, fresh_cred = await get_tidal_token_for_cred(
                force_refresh=True, cred=cred
            )
            if fresh_token != token:
                headers = _api_headers(fresh_token)
                response = await client.get(
                    url, headers=headers, params=params
                )
                token, cred = fresh_token, fresh_cred

        break

    response.raise_for_status()
    return {"version": "2.10", "data": response.json()}


def _extract_uuid_from_tidal_url(href: str) -> str | None:
    """Extract and reconstruct a hyphenated UUID from a Tidal URL.

    Args:
        href: A Tidal resource URL containing UUID path segments.

    Returns:
        str | None: The reconstructed UUID, or None if not found.
    """
    parts = href.split("/") if href else []
    return "-".join(parts[4:9]) if len(parts) >= 9 else None
