"""Shared HTTP client management for TIDAL API requests.

Copyright (c) 2024-2026 TIDAL-Downloader-NG contributors

This module provides a shared httpx.AsyncClient with connection pooling,
proxy support, and automatic proxy rotation for rate limiting.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import asyncio

import httpx

from tidal_dl_ng.constants import HIFI_USER_AGENT
from tidal_dl_ng.helper.tidal_auth.proxy import (
    DELAYED_CLOSE_DELAY_SEC,
    FALLBACK_TO_DIRECT_CONNECTION,
    HTTP_CLIENT_LIMITS,
    HTTP_CLIENT_TIMEOUT,
    USE_PROXIES,
    get_working_proxy,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    FnPrint = Callable[[str], None]


#: Mutable container for the shared HTTP client.
_http_client: list[httpx.AsyncClient | None] = [None]
_http_client_proxy_url: list[str | None] = [None]
_http_client_lock: asyncio.Lock = asyncio.Lock()

#: Pending client close tasks.
_pending_client_closes: set[asyncio.Task[None]] = set()


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


def auth_headers() -> dict[str, str]:
    """Build headers for OAuth device authorization and token requests.

    Returns:
        dict[str, str]: Headers for OAuth endpoint calls.
    """
    return _tidal_headers()


def api_headers(access_token: str) -> dict[str, str]:
    """Build headers for authenticated TIDAL API requests.

    Args:
        access_token: The OAuth access token.

    Returns:
        dict[str, str]: Headers including Authorization bearer token.
    """
    return _tidal_headers({"Authorization": f"Bearer {access_token}"})


def _build_http_client(
    proxy_url: str | None = None,
) -> httpx.AsyncClient:
    """Build an httpx AsyncClient with TIDAL headers and optional proxy.

    Args:
        proxy_url: Optional proxy URL to route requests through.

    Returns:
        httpx.AsyncClient: Configured async HTTP client.
    """
    return httpx.AsyncClient(
        proxy=proxy_url,
        http2=True,
        headers=auth_headers(),
        timeout=HTTP_CLIENT_TIMEOUT,
        limits=HTTP_CLIENT_LIMITS,
    )


async def update_global_client(
    force_new_proxy: bool = False,
) -> None:
    """Update the global HTTP client, optionally with a new proxy.

    Args:
        force_new_proxy: If True, force selection of a new proxy.
    """
    async with _http_client_lock:
        proxy_to_avoid = None
        if force_new_proxy and _http_client_proxy_url[0]:
            proxy_to_avoid = _http_client_proxy_url[0]

        proxy_url = None
        if USE_PROXIES:
            proxy_url = await get_working_proxy(avoid_proxy=proxy_to_avoid)
            if not proxy_url and not FALLBACK_TO_DIRECT_CONNECTION:
                msg = "No working proxies available"
                raise RuntimeError(msg)

        if (
            _http_client[0] is not None
            and _http_client_proxy_url[0] == proxy_url
        ):
            return

        new_client = _build_http_client(proxy_url)
        old_client = _http_client[0]
        _http_client[0] = new_client
        _http_client_proxy_url[0] = proxy_url

        if old_client is not None:
            task = asyncio.create_task(_delayed_close(old_client))
            _pending_client_closes.add(task)
            task.add_done_callback(_pending_client_closes.discard)


async def _delayed_close(client: httpx.AsyncClient) -> None:
    """Close an HTTP client after a short delay.

    Args:
        client: The client to close.
    """
    await asyncio.sleep(DELAYED_CLOSE_DELAY_SEC)
    await client.aclose()


async def get_http_client() -> httpx.AsyncClient:
    """Get or create the shared HTTP client.

    Returns:
        httpx.AsyncClient: The shared async HTTP client.
    """
    if _http_client[0] is None:
        async with _http_client_lock:
            if _http_client[0] is None:
                proxy_url = None
                if USE_PROXIES:
                    proxy_url = await get_working_proxy()
                _http_client[0] = _build_http_client(proxy_url)
                _http_client_proxy_url[0] = proxy_url
    return _http_client[0]
