# Stub for tidalapi.request to expose the request method.

from collections.abc import Mapping, MutableMapping
from typing import Any, Literal

import requests

class Requests:
    # HTTP request helper used by tidalapi Session.

    def __call__(
        self,
        method: Literal["GET", "POST", "PUT", "DELETE"],
        path: str,
        params: Mapping[str, int | str | None] | None = ...,
        data: dict[str, Any] | None = ...,
        headers: MutableMapping[str, str] | None = ...,
        base_url: str | None = ...,
    ) -> requests.Response: ...
    def request(
        self,
        method: Literal["GET", "POST", "PUT", "DELETE"],
        path: str,
        params: Mapping[str, int | str | None] | None = ...,
        data: dict[str, Any] | None = ...,
        headers: MutableMapping[str, str] | None = ...,
        base_url: str | None = ...,
    ) -> requests.Response: ...
