"""Stub for tidalapi.request to expose the request method."""

from typing import Any, Literal, Mapping, MutableMapping, Optional

import requests

class Requests:
    """HTTP request helper used by tidalapi Session."""

    def __call__(
        self,
        method: Literal["GET", "POST", "PUT", "DELETE"],
        path: str,
        params: Optional[Mapping[str, int | str | None]] = ...,
        data: Optional[dict[str, Any]] = ...,
        headers: Optional[MutableMapping[str, str]] = ...,
        base_url: Optional[str] = ...,
    ) -> requests.Response: ...
    def request(
        self,
        method: Literal["GET", "POST", "PUT", "DELETE"],
        path: str,
        params: Optional[Mapping[str, int | str | None]] = ...,
        data: Optional[dict[str, Any]] = ...,
        headers: Optional[MutableMapping[str, str]] = ...,
        base_url: Optional[str] = ...,
    ) -> requests.Response: ...
