"""TIDAL API key management module.

Provides functions to retrieve and validate TIDAL API client keys
for different platforms. Keys are loaded from a local fallback set
and optionally refreshed from a remote GitHub Gist.
"""

import json
import logging
import re
from typing import TypedDict, cast

import requests

from tidal_dl_ng.constants import REQUESTS_TIMEOUT_SEC

logger = logging.getLogger(__name__)

#: HTTP status code returned on a successful GET request.
HTTP_OK: int = 200


class ApiKey(TypedDict):
    """Structure of a single TIDAL API client key entry."""

    platform: str
    formats: str
    clientId: str
    clientSecret: str
    valid: str
    from_: str


class ApiKeysData(TypedDict):
    """Structure of the full API keys payload."""

    version: str
    keys: list[dict[str, str]]


# See also
# https://github.com/yaronzz/Tidal-Media-Downloader/commit/1d5b8cd8f65fd1def45d6406778248249d6dfbdf
# https://github.com/yaronzz/Tidal-Media-Downloader/pull/840
# https://github.com/nathom/streamrip/tree/main/streamrip

# TODO(Warry): Implement this into `Download`: Session should
# randomize the usage. See issue #1.
# Fallback API keys (JSON with comments stripped before parsing).
__KEYS_JSON__ = """
{
    "version": "1.0.1",
    "keys": [
        {
            "platform": "Fire TV",
            "formats": "Normal/High/HiFi(No Master)",
            "clientId": "OmDtrzFgyVVL6uW56OnFA2COiabqm",
            "clientSecret": "zxen1r3pO0hgtOC7j6twMo9UAqngGrmRiWpV7QC1zJ8=",
            "valid": "False",
            "from": "Fokka-Engineering"
        },
        {
            "platform": "Fire TV",
            "formats": "Master-Only(Else Error)",
            "clientId": "7m7Ap0JC9j1cOM3n",
            "clientSecret": "vRAdA108tlvkJpTsGZS8rGZ7xTlbJ0qaZ2K9saEzsgY=",
            "valid": "True",
            "from": "Dniel97"
        },
        {
            "platform": "Android TV",
            "formats": "Normal/High/HiFi(No Master)",
            "clientId": "Pzd0ExNVHkyZLiYN",
            "clientSecret": "W7X6UvBaho+XOi1MUeCX6ewv2zTdSOV3Y7qC3p3675I=",
            "valid": "False",
            "from": ""
        },
        {
            "platform": "TV",
            "formats": "Normal/High/HiFi/Master",
            "clientId": "8SEZWa4J1NVC5U5Y",
            "clientSecret": "owUYDkxddz+9FpvGX24DlxECNtFEMBxipU0lBfrbq60=",
            "valid": "False",
            "from": "morguldir"
        },
        {
            "platform": "Android Auto",
            "formats": "Normal/High/HiFi/Master",
            "clientId": "zU4XHVVkc2tDPo4t",
            "clientSecret": "VJKhDFqJPqvsPVNBV6ukXTJmwlvbttP7wlMlrc72se4=",
            "valid": "True",
            "from": "1nikolas"
        }
    ]
}
"""


def _strip_json_comments(json_str: str) -> str:
    """Remove // line comments from a JSON string.

    Args:
        json_str: Raw JSON string potentially containing // comments.

    Returns:
        Cleaned JSON string with comments removed.
    """
    return re.sub(r"^\s*//.*$", "", json_str, flags=re.MULTILINE)


def _load_api_keys() -> ApiKeysData:
    """Load API keys from the fallback JSON, stripping comments.

    Returns:
        Parsed API keys dictionary.
    """
    cleaned = _strip_json_comments(__KEYS_JSON__)
    return cast("ApiKeysData", json.loads(cleaned))


_api_keys: ApiKeysData = _load_api_keys()

__ERROR_KEY__: dict[str, str] = {
    "platform": "None",
    "formats": "",
    "clientId": "",
    "clientSecret": "",
    "valid": "False",
}


def get_num() -> int:
    """Get the number of available API keys.

    Returns:
        Total count of API keys.
    """
    return len(_api_keys["keys"])


def get_item(index: int) -> dict[str, str]:
    """Get an API key item by index.

    Args:
        index: The index of the key to retrieve.

    Returns:
        The API key dictionary, or an error key if index is out of range.
    """
    if index < 0 or index >= len(_api_keys["keys"]):
        return __ERROR_KEY__
    return _api_keys["keys"][index]


def is_item_valid(index: int) -> bool:
    """Check if an API key at the given index is valid.

    Args:
        index: The index of the key to check.

    Returns:
        True if the key is marked as valid.
    """
    item = get_item(index)
    return item["valid"] == "True"


def get_items() -> list[dict[str, str]]:
    """Get all API key items.

    Returns:
        List of all API key dictionaries.
    """
    return _api_keys["keys"]


def get_limit_indices() -> list[str]:
    """Get string representations of all valid API key indices.

    Returns:
        List of index strings.
    """
    return [str(i) for i in range(len(_api_keys["keys"]))]


def get_version() -> str:
    """Get the API keys version string.

    Returns:
        Version string from the keys data.
    """
    return _api_keys["version"]


def getNum() -> int:
    """Backward-compatible alias for get_num."""
    return get_num()


def getItem(index: int) -> dict[str, str]:
    """Backward-compatible alias for get_item."""
    return get_item(index)


def isItemValid(index: int) -> bool:
    """Backward-compatible alias for is_item_valid."""
    return is_item_valid(index)


def getItems() -> list[dict[str, str]]:
    """Backward-compatible alias for get_items."""
    return get_items()


def getLimitIndexs() -> list[str]:
    """Backward-compatible alias for get_limit_indices."""
    return get_limit_indices()


def getVersion() -> str:
    """Backward-compatible alias for get_version."""
    return get_version()


# Attempt to refresh API keys from remote GitHub Gist
try:
    response = requests.get(
        "https://api.github.com/gists/48d01f5a24b4b7b37f19443977c22cd6",
        timeout=REQUESTS_TIMEOUT_SEC,
    )
    if response.status_code == HTTP_OK:
        content = response.json()["files"]["tidal-api-key.json"]["content"]
        payload = json.loads(content)
        if (
            isinstance(payload, dict)
            and "version" in payload
            and "keys" in payload
        ):
            _api_keys = cast("ApiKeysData", payload)
            logger.info("API keys refreshed from remote Gist.")
        else:
            logger.warning(
                "Invalid API keys payload from remote Gist. "
                "Using fallback keys."
            )
except (requests.RequestException, json.JSONDecodeError, KeyError) as e:
    logger.warning("Could not refresh API keys from Gist: %s", e)
