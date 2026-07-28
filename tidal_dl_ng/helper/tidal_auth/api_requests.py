"""Authenticated HTTP request helpers for TIDAL API.

Copyright (c) 2024-2026 TIDAL-Downloader-NG contributors

This module provides high-level functions for making authenticated
GET requests to TIDAL API endpoints with automatic token refresh,
rate limiting handling, and 404 retry logic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import asyncio
import contextlib

import httpx

from tidal_dl_ng.helper.tidal_auth.http_client import (
    api_headers,
    get_http_client,
)
from tidal_dl_ng.helper.tidal_auth.proxy import (
    HTTP_NOT_FOUND,
    HTTP_TOO_MANY_REQUESTS,
    HTTP_UNAUTHORIZED,
    RATE_LIMIT_BASE_DELAY,
    RATE_LIMIT_MAX_DELAY,
    RATE_LIMIT_MAX_RETRIES,
)
from tidal_dl_ng.helper.tidal_auth.token_refresh import (
    get_tidal_token_for_cred,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from tidal_dl_ng.helper.tidal_auth.token_storage import TokenEntry

    FnPrint = Callable[[str], None]

#: Type alias for HTTP query parameters, compatible with httpx.
QueryParamTypes = (
    str
    | dict[str, str | int | float | bool | None]
    | list[tuple[str, str | int | float | bool | None]]
    | tuple[tuple[str, str | int | float | bool | None], ...]
)


async def _compute_rate_limit_delay(
    response: httpx.Response, attempt: int
) -> float:
    """Compute the exponential backoff delay for rate-limited responses.

    Args:
        response: The HTTP response with a 429 status code.
        attempt: The current retry attempt (0-based).

    Returns:
        float: The delay in seconds before retrying.
    """
    delay = min(
        RATE_LIMIT_BASE_DELAY * (2**attempt),
        RATE_LIMIT_MAX_DELAY,
    )
    if retry_after := response.headers.get("Retry-After"):
        with contextlib.suppress(ValueError):
            delay = float(min(delay, max(float(retry_after), 0.0)))
    return float(min(delay, RATE_LIMIT_MAX_DELAY))


async def _handle_404_retry(
    url: str,
    headers: dict[str, str],
    *,
    params: QueryParamTypes | None,
    token: str,
    cred: TokenEntry,
    client: httpx.AsyncClient,
) -> tuple[httpx.Response, str, TokenEntry]:
    """Handle a 404 by refreshing the token and retrying the request.

    Args:
        url: The URL to request.
        headers: Current request headers.
        params: Optional query parameters.
        token: Current access token.
        cred: Current credential dictionary.
        client: The HTTP client to use.

    Returns:
        tuple[httpx.Response, str, TokenEntry]:
            (response, refreshed_token, refreshed_cred).
    """
    fresh_token, fresh_cred = await get_tidal_token_for_cred(
        force_refresh=True, cred=cred
    )
    if fresh_token != token:
        headers = api_headers(fresh_token)
        response = await client.get(url, headers=headers, params=params)
        return response, fresh_token, fresh_cred
    # Token unchanged; raise to signal no retry is possible
    msg = "No response available for retry"
    raise RuntimeError(msg)


async def authed_get_json(
    url: str,
    *,
    params: QueryParamTypes | None = None,
    token: str | None = None,
    cred: TokenEntry | None = None,
) -> tuple[dict[str, Any], str, TokenEntry]:
    """Perform an authenticated GET, retrying once on 401.

    Args:
        url: The URL to request.
        params: Optional query parameters.
        token: Optional pre-fetched access token.
        cred: Optional pre-fetched credential dict.

    Returns:
        tuple[dict[str, Any], str, TokenEntry]:
            (response_json, access_token, credential_dict).
    """
    if token is None or cred is None:
        token, cred = await get_tidal_token_for_cred(cred=cred)

    client = await get_http_client()
    headers = api_headers(token)

    response: httpx.Response | None = None
    for attempt in range(RATE_LIMIT_MAX_RETRIES + 1):
        response = await client.get(url, headers=headers, params=params)

        if response.status_code == HTTP_UNAUTHORIZED:
            token, cred = await get_tidal_token_for_cred(
                force_refresh=True, cred=cred
            )
            headers = api_headers(token)
            response = await client.get(url, headers=headers, params=params)

        if (
            response.status_code == HTTP_TOO_MANY_REQUESTS
            and attempt < RATE_LIMIT_MAX_RETRIES
        ):
            delay = await _compute_rate_limit_delay(response, attempt)
            await asyncio.sleep(delay)
            continue

        if response.status_code == HTTP_NOT_FOUND:
            response, token, cred = await _handle_404_retry(
                url,
                headers,
                params=params,
                token=token,
                cred=cred,
                client=client,
            )

        break

    if response is None:
        msg = "No response received from server"
        dummy = httpx.Response(
            HTTP_NOT_FOUND, request=httpx.Request("GET", url)
        )
        raise httpx.HTTPStatusError(msg, request=dummy.request, response=dummy)

    response.raise_for_status()
    return response.json(), token, cred


async def make_request(
    url: str,
    token: str | None = None,
    params: QueryParamTypes | None = None,
    cred: TokenEntry | None = None,
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
    headers = api_headers(token)

    response: httpx.Response | None = None
    for attempt in range(RATE_LIMIT_MAX_RETRIES + 1):
        response = await client.get(url, headers=headers, params=params)

        if response.status_code == HTTP_UNAUTHORIZED:
            token, cred = await get_tidal_token_for_cred(
                force_refresh=True, cred=cred
            )
            headers = api_headers(token)
            response = await client.get(url, headers=headers, params=params)

        if (
            response.status_code == HTTP_TOO_MANY_REQUESTS
            and attempt < RATE_LIMIT_MAX_RETRIES
        ):
            delay = await _compute_rate_limit_delay(response, attempt)
            await asyncio.sleep(delay)
            continue

        if response.status_code == HTTP_NOT_FOUND:
            response, token, cred = await _handle_404_retry(
                url,
                headers,
                params=params,
                token=token,
                cred=cred,
                client=client,
            )

        break

    if response is None:
        msg = "No response received from server"
        request = httpx.Request("GET", url)
        dummy = httpx.Response(HTTP_NOT_FOUND, request=request)
        raise httpx.HTTPStatusError(msg, request=request, response=dummy)

    response.raise_for_status()
    return {
        "version": "2.10",
        "data": response.json(),
    }
