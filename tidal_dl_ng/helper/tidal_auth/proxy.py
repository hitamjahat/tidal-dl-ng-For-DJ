"""Proxy management and shared HTTP client for TIDAL API requests.

Copyright (c) 2024-2026 TIDAL-Downloader-NG contributors

This module handles loading, testing, and selecting working proxies
for HTTP requests to the TIDAL API. It supports proxy rotation,
fallback to direct connections, and concurrent proxy testing.
Also provides a shared httpx.AsyncClient with connection pooling.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import asyncio
import os
import secrets
from pathlib import Path

import httpx

if TYPE_CHECKING:
    from collections.abc import Callable

    FnPrint = Callable[[str], None]

#: Mutable container for proxies loaded from file at module load time.
_proxies: list[str] = []

#: Mutable container for the last proxy confirmed to be working.
_last_known_good_proxy: list[str | None] = [None]

#: Maximum number of proxy candidates to test per get_working_proxy() call.
MAX_PROXY_CANDIDATES: int = 10

#: Maximum number of concurrent proxy tests inside get_working_proxy().
PROXY_TEST_CONCURRENCY: int = 5

#: Whether to use proxies for HTTP requests.
USE_PROXIES: bool = os.getenv("USE_PROXIES", "False").lower() in {
    "true",
    "1",
    "yes",
}

#: Whether to rotate proxies on each token refresh.
ROTATE_PROXIES_ON_REFRESH: bool = os.getenv(
    "ROTATE_PROXIES_ON_REFRESH", "False"
).lower() in {"true", "1", "yes"}

#: Path to the proxies file.
PROXIES_FILE: str = os.getenv("PROXIES_FILE", "proxies.txt")

#: Whether to fall back to direct connection if no proxy is available.
FALLBACK_TO_DIRECT_CONNECTION: bool = os.getenv(
    "FALLBACK_TO_DIRECT_CONNECTION", "False"
).lower() in {"true", "1", "yes"}

#: Maximum retries for proxy-based requests.
MAX_RETRIES: int = max(1, int(os.getenv("MAX_RETRIES", "2")))

#: Rate limiting retry settings.
RATE_LIMIT_MAX_RETRIES: int = 3
RATE_LIMIT_BASE_DELAY: float = 1.0
RATE_LIMIT_MAX_DELAY: float = 10.0

#: HTTP status codes that indicate rate limiting or temporary blocks.
RATE_LIMITED_STATUS_CODES: frozenset[int] = frozenset({403, 429})

#: HTTP status codes that indicate invalid credentials.
INVALID_CREDENTIAL_STATUS_CODES: frozenset[int] = frozenset({400, 401})

#: HTTP status code indicating success.
HTTP_OK: int = 200

#: HTTP status code indicating unauthorized.
HTTP_UNAUTHORIZED: int = 401

#: HTTP status code indicating not found.
HTTP_NOT_FOUND: int = 404

#: HTTP status code indicating too many requests.
HTTP_TOO_MANY_REQUESTS: int = 429

#: Timeout for proxy connectivity tests.
PROXY_TEST_TIMEOUT_SEC: float = 5.0

#: Delay (seconds) before closing an old HTTP client.
DELAYED_CLOSE_DELAY_SEC: float = 15.0

#: HTTP client timeout configuration.
HTTP_CLIENT_TIMEOUT: httpx.Timeout = httpx.Timeout(
    connect=3.0, read=12.0, write=8.0, pool=12.0
)

#: HTTP client connection limits.
HTTP_CLIENT_LIMITS: httpx.Limits = httpx.Limits(
    max_keepalive_connections=500,
    max_connections=1000,
    keepalive_expiry=30.0,
)


def load_proxies() -> None:
    """Load proxies from file into the global _proxies list."""
    proxies_path = Path(PROXIES_FILE)
    if not proxies_path.exists():
        _proxies.clear()
        return
    with proxies_path.open(encoding="utf-8") as f:
        _proxies[:] = [line.strip() for line in f if line.strip()]


def _build_proxy_test_client(proxy_url: str) -> httpx.AsyncClient:
    """Build a lightweight httpx client for testing proxy connectivity.

    Args:
        proxy_url: The proxy URL to test.

    Returns:
        httpx.AsyncClient: A client configured to use the proxy.
    """
    return httpx.AsyncClient(proxy=proxy_url, timeout=PROXY_TEST_TIMEOUT_SEC)


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
            return resp.status_code == HTTP_OK
    except httpx.HTTPError:
        return False


async def _filter_proxy_candidates(
    shuffled: list[str],
    avoid_proxy: str | None,
) -> list[str]:
    """Filter and limit proxy candidates for testing.

    Args:
        shuffled: Proxies in random order.
        avoid_proxy: A proxy URL to skip.

    Returns:
        list[str]: Filtered candidates, limited to MAX_PROXY_CANDIDATES.
    """
    if avoid_proxy:
        if not (candidates := [p for p in shuffled if p != avoid_proxy]):
            candidates = shuffled
    else:
        candidates = shuffled

    if _last_known_good_proxy[0] is not None:
        candidates = [p for p in candidates if p != _last_known_good_proxy[0]]
    return candidates[:MAX_PROXY_CANDIDATES]


async def get_working_proxy(
    avoid_proxy: str | None = None,
) -> str | None:
    """Find a working proxy from the loaded proxy list.

    Args:
        avoid_proxy: A proxy URL to skip (e.g. the current one).

    Returns:
        str | None: A working proxy URL, or None if none found.
    """
    if not _proxies:
        return None

    if (
        _last_known_good_proxy[0] is not None
        and _last_known_good_proxy[0] != avoid_proxy
        and await test_proxy(_last_known_good_proxy[0])
    ):
        return _last_known_good_proxy[0]

    shuffled = _proxies[:]
    secrets.SystemRandom().shuffle(shuffled)
    candidates = await _filter_proxy_candidates(shuffled, avoid_proxy)

    sem = asyncio.Semaphore(PROXY_TEST_CONCURRENCY)
    found_event = asyncio.Event()
    selected: list[str | None] = [None]

    async def probe(proxy: str) -> None:
        if found_event.is_set():
            return
        async with sem:
            if found_event.is_set():
                return
            if await test_proxy(proxy) and not found_event.is_set():
                selected[0] = proxy
                found_event.set()

    await asyncio.gather(
        *[probe(p) for p in candidates], return_exceptions=True
    )

    if selected[0]:
        _last_known_good_proxy[0] = selected[0]
    return selected[0]
