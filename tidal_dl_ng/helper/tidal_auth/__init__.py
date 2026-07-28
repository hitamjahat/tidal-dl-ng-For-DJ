"""HiFi-API OAuth 2.0 Device Authorization flow for TIDAL.

Copyright (c) 2024-2026 TIDAL-Downloader-NG contributors

This package implements the upgraded authentication process that uses
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

The package provides both async and sync entry points so it can be used
from CLI (sync) and GUI (async) contexts.
"""

import asyncio
import re

from tidal_dl_ng.helper.tidal_auth.auth import (
    get_auth_client_credentials,
    get_token_client_credentials,
    get_valid_token,
    get_valid_token_sync,
    run_device_authorization_flow,
    run_device_authorization_flow_sync,
    verify_existing_token,
    verify_existing_token_sync,
)
from tidal_dl_ng.helper.tidal_auth.http_client import (
    get_http_client,
    get_working_proxy,
    load_proxies,
    test_proxy,
    update_global_client,
)
from tidal_dl_ng.helper.tidal_auth.proxy import (
    FALLBACK_TO_DIRECT_CONNECTION,
    MAX_RETRIES,
    PROXIES_FILE,
    ROTATE_PROXIES_ON_REFRESH,
    USE_PROXIES,
)
from tidal_dl_ng.helper.tidal_auth.token_storage import (
    TokenEntry,
    TokenResponse,
    delete_token_entry,
    find_token_entry,
    load_tokens,
    save_token_entry,
)

#: Semaphore to limit concurrent album track requests.
_album_tracks_sem = asyncio.Semaphore(5)


def _extract_uuid_from_tidal_url(url: str) -> str | None:
    """Extract UUID from a TIDAL URL.

    Args:
        url: The TIDAL URL.

    Returns:
        str | None: The extracted UUID, or None if not found.
    """
    match = re.search(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        url,
        re.IGNORECASE,
    )
    return match.group(0) if match else None


__all__ = [
    "FALLBACK_TO_DIRECT_CONNECTION",
    "MAX_RETRIES",
    "PROXIES_FILE",
    "ROTATE_PROXIES_ON_REFRESH",
    "USE_PROXIES",
    "TokenEntry",
    "TokenResponse",
    "delete_token_entry",
    "find_token_entry",
    "get_auth_client_credentials",
    "get_http_client",
    "get_token_client_credentials",
    "get_valid_token",
    "get_valid_token_sync",
    "get_working_proxy",
    "load_proxies",
    "load_tokens",
    "run_device_authorization_flow",
    "run_device_authorization_flow_sync",
    "save_token_entry",
    "test_proxy",
    "update_global_client",
    "verify_existing_token",
    "verify_existing_token_sync",
]
