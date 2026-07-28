from typing import Literal

from collections.abc import Mapping, MutableMapping

import requests

class Requests:
    def __call__(
        self,
        method: Literal["GET", "POST", "PUT", "DELETE"],
        path: str,
        params: Mapping[str, int | str | None] | None = None,
        data: dict[str, object] | None = None,
        headers: MutableMapping[str, str] | None = None,
        base_url: str | None = None,
    ) -> requests.Response: ...
    def request(
        self,
        method: Literal["GET", "POST", "PUT", "DELETE"],
        path: str,
        params: Mapping[str, int | str | None] | None = None,
        data: dict[str, object] | None = None,
        headers: MutableMapping[str, str] | None = None,
        base_url: str | None = None,
    ) -> requests.Response: ...
