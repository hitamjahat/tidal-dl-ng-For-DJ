# Copyright (c) 2026 exislow
# Licensed under the MIT License.

"""Token storage and management for TIDAL OAuth credentials.

This module handles loading, saving, and managing OAuth token entries
stored in token.json. It supports both file-based and environment
variable-based credentials.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypedDict, cast

import json
import os
from pathlib import Path

from tidal_dl_ng.constants import (
    HIFI_REQUEST_CLIENT_ID,
    HIFI_REQUEST_CLIENT_SECRET,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    FnPrint = Callable[[str], None]


class TokenResponse(TypedDict, total=False):
    """A token response from the TIDAL API.

    All keys are optional since different endpoints return
    different fields.
    """

    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int
    expiresIn: int
    user: TokenEntry | None
    error: str | None
    error_description: str | None
    verificationUriComplete: str
    deviceCode: str
    device_code: str
    grant_type: str
    client_id: str
    scope: str


class TokenEntry(TypedDict, total=False):
    """A normalized TIDAL OAuth credential entry.

    All keys are optional since entries may be incomplete
    (e.g. env-var credentials without access tokens).

    Attributes:
        client_id: The OAuth client ID.
        client_secret: The OAuth client secret.
        refresh_token: The OAuth refresh token.
        user_id: The TIDAL user ID.
        access_token: The current access token, if available.
        expires_at: Unix timestamp of token expiry.
        client_ID: Original-case client ID key (for compat).
        userID: Original-case user ID key (for compat).
        token_type: The token type (e.g. "Bearer").
        expires_in: Seconds until token expiry (from auth response).
        created_at: ISO 8601 timestamp of token creation.
        scope: OAuth scope string.
        version: Token version identifier.
    """

    client_id: str
    client_secret: str
    refresh_token: str
    user_id: str
    access_token: str | None
    expires_at: int
    client_ID: str
    userID: str
    token_type: str
    expires_in: int
    created_at: str
    scope: str | None
    version: str | None


#: Default token file path, overridable via ``TOKEN_FILE`` env var.
TOKEN_FILE: Path = Path(
    os.getenv(
        "TOKEN_FILE",
        Path(__file__).resolve().parent.parent.parent.parent / "token.json",
    )
)

#: Default OAuth token type value.
_TOKEN_TYPE_BEARER = "Bearer"  # noqa: S105


def _build_cred_entry(
    entry: TokenEntry,
    default_client_id: str,
    default_client_secret: str,
) -> TokenEntry:
    """Normalize a raw token entry into the standard credential format.

    Args:
        entry: Raw token entry from token.json.
        default_client_id: Fallback client ID.
        default_client_secret: Fallback client secret.

    Returns:
        TokenEntry: Normalized credential dictionary with both
            lowercase and original-case key variants.
    """
    client_id = str(entry.get("client_ID") or default_client_id)
    client_secret = str(entry.get("client_secret") or default_client_secret)
    user_id = str(entry.get("userID") or "")
    return TokenEntry(
        client_id=client_id,
        client_secret=client_secret,
        refresh_token=str(entry.get("refresh_token") or ""),
        user_id=user_id,
        access_token=entry.get("access_token"),
        expires_at=0,
        client_ID=client_id,
        userID=user_id,
        token_type=str(entry.get("token_type", "Bearer")),
        expires_in=0,
        created_at="",
    )


def load_tokens() -> list[TokenEntry]:
    """Load all stored token entries from the token file.

    Supports both list and dict formats in token.json. Also loads
    credentials from environment variables (CLIENT_ID, CLIENT_SECRET,
    REFRESH_TOKEN, USER_ID) as a fallback, merged with file-based tokens.

    Returns:
        list[TokenEntry]: List of token entry dictionaries.
            Returns an empty list if no tokens are available.
    """
    creds: list[TokenEntry] = []

    if TOKEN_FILE.exists():
        with TOKEN_FILE.open(encoding="utf-8") as f:
            data: Any = json.load(f)
            if isinstance(data, dict):
                data = [data]

            if isinstance(data, list):
                for item in data:
                    if not isinstance(item, dict):
                        continue
                    item_dict = cast("dict[str, Any]", item)
                    cred = _build_cred_entry(
                        cast("TokenEntry", item_dict),
                        HIFI_REQUEST_CLIENT_ID,
                        HIFI_REQUEST_CLIENT_SECRET,
                    )
                    if cred.get("refresh_token"):
                        creds.append(cred)

    # Add env var credential if available and unique
    env_refresh = os.getenv("REFRESH_TOKEN")
    env_client_id = os.getenv("CLIENT_ID", HIFI_REQUEST_CLIENT_ID)
    env_client_secret = os.getenv("CLIENT_SECRET", HIFI_REQUEST_CLIENT_SECRET)
    env_user_id = os.getenv("USER_ID")

    if env_refresh:
        env_cred = TokenEntry(
            client_id=env_client_id,
            client_secret=env_client_secret,
            refresh_token=env_refresh,
            user_id=env_user_id or "",
            access_token=None,
            expires_at=0,
            client_ID=env_client_id,
            userID=env_user_id or "",
            token_type=_TOKEN_TYPE_BEARER,
        )
        if not any(c.get("refresh_token") == env_refresh for c in creds):
            creds.append(env_cred)

    return creds


def save_token_entry(entry: TokenEntry) -> None:
    """Persist a token entry, replacing duplicates.

    Replaces any existing entry with the same client_ID and
    refresh_token.

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
) -> TokenEntry | None:
    """Find a stored token entry, optionally matching a client_id.

    Args:
        client_id: If provided, only entries matching this client_ID
            are considered. If None, the first entry is returned.

    Returns:
        TokenEntry | None: The matching token entry, or None.
    """
    tokens = load_tokens()
    if client_id is not None:
        for entry in tokens:
            if entry.get("client_ID") == client_id:
                return entry
    if tokens:
        return tokens[0]
    return None
