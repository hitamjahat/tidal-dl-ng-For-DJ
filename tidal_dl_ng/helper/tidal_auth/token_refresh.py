# Copyright (c) 2026 exislow
# Licensed under the MIT License.

"""OAuth token refresh logic for TIDAL authentication.

This module handles refreshing access tokens using the OAuth refresh_token
grant, with support for proxy rotation and retry logic.
"""

from __future__ import annotations

import asyncio
import time

import httpx

from tidal_dl_ng.constants import (
    HIFI_OAUTH_GRANT_TYPE_REFRESH,
    HIFI_OAUTH_SCOPE,
    HIFI_TOKEN_URL,
)
from tidal_dl_ng.helper.tidal_auth.auth import (
    handle_refresh_error,
    handle_request_error,
    handle_status_error,
)
from tidal_dl_ng.helper.tidal_auth.http_client import (
    get_http_client,
    update_global_client,
)
from tidal_dl_ng.helper.tidal_auth.proxy import (
    MAX_RETRIES,
    ROTATE_PROXIES_ON_REFRESH,
    USE_PROXIES,
)
from tidal_dl_ng.helper.tidal_auth.token_storage import TokenEntry, load_tokens

#: One lock per credential to avoid global contention during token refreshes.
_refresh_locks: dict[str, asyncio.Lock] = {}


def _lock_for_cred(cred: TokenEntry) -> asyncio.Lock:
    """Get or create a lock for a specific credential set.

    Args:
        cred: The credential dictionary.

    Returns:
        asyncio.Lock: A lock specific to this credential.
    """
    key = f"{cred.get('client_id', '')}:{cred.get('refresh_token', '')}"
    return _refresh_locks.setdefault(key, asyncio.Lock())


async def _refresh_cred_token(
    cred: TokenEntry,
) -> tuple[str, TokenEntry]:
    """Refresh a credential's access token via the OAuth refresh grant.

    Args:
        cred: The credential dictionary to refresh.

    Returns:
        tuple[str, TokenEntry]: (new_access_token, updated_cred).

    Raises:
        httpx.HTTPStatusError: If the refresh request fails after retries.
        httpx.RequestError: If the request fails after retries.
    """
    max_retries = MAX_RETRIES if USE_PROXIES else 1
    for attempt in range(max_retries):
        try:
            client = await get_http_client()
            response = await client.post(
                HIFI_TOKEN_URL,
                data={
                    "client_id": str(cred.get("client_id", "")),
                    "refresh_token": str(cred.get("refresh_token", "")),
                    "grant_type": HIFI_OAUTH_GRANT_TYPE_REFRESH,
                    "scope": HIFI_OAUTH_SCOPE,
                },
                auth=(
                    str(cred.get("client_id", "")),
                    str(cred.get("client_secret", "")),
                ),
            )

            await handle_refresh_error(response)
            data = response.json()
            new_token = str(data["access_token"])
            expires_in = int(data.get("expires_in", 3600))

            cred["access_token"] = new_token
            cred["expires_at"] = int(time.time() + expires_in - 60)
        except httpx.RequestError:
            await handle_request_error(attempt, max_retries)
            continue
        except httpx.HTTPStatusError as e:
            await handle_status_error(e, attempt, max_retries)
            continue
        return new_token, cred
    msg = "Token refresh failed after all retries"
    raise RuntimeError(msg)  # pragma: no cover


async def get_tidal_token_for_cred(
    force_refresh: bool = False,
    cred: TokenEntry | None = None,
) -> tuple[str, TokenEntry]:
    """Retrieve an access token for a specific credential.

    Args:
        force_refresh: If True, always refresh the token.
        cred: The credential dictionary. If None, picks the first
            available credential.

    Returns:
        tuple[str, TokenEntry]: (access_token, credential_dict).
    """
    if cred is None:
        if not (tokens := load_tokens()):
            msg = "No Tidal credentials available"
            raise RuntimeError(msg)
        cred = tokens[0]

    async with _lock_for_cred(cred):
        if (
            cred.get("access_token")
            and cred.get("expires_at", 0) > time.time()
        ):
            return str(cred.get("access_token", "")), cred

        if USE_PROXIES and ROTATE_PROXIES_ON_REFRESH:
            await update_global_client(force_new_proxy=True)

        return await _refresh_cred_token(cred)


async def get_tidal_token(
    force_refresh: bool = False,
) -> tuple[str, TokenEntry]:
    """Retrieve an access token using the first available credential.

    Args:
        force_refresh: If True, always refresh the token.

    Returns:
        tuple[str, TokenEntry]: (access_token, credential_dict).
    """
    return await get_tidal_token_for_cred(force_refresh=force_refresh)
