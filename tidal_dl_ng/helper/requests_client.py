"""HTTP client helpers for downloading text and binary content."""

from collections.abc import Mapping
from typing import Final

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

_STATUS_FORCELIST: Final[list[int]] = [429, 500, 502, 503, 504]
_RETRY_TOTAL: Final[int] = 5
_RETRY_BACKOFF: Final[float] = 1.0


class RequestsClient:
    """HTTP client for downloading text and binary content."""

    def _build_session(self) -> requests.Session:
        """Create a configured session with retry logic.

        Returns:
            A requests.Session mounted with retry-capable adapters
            for both HTTP and HTTPS schemes.
        """
        session = requests.Session()
        retries = Retry(
            total=_RETRY_TOTAL,
            backoff_factor=_RETRY_BACKOFF,
            status_forcelist=_STATUS_FORCELIST,
        )
        adapter = HTTPAdapter(max_retries=retries)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def download(
        self,
        uri: str,
        timeout: float | None = None,
        headers: Mapping[str, str] | None = None,
        *,
        verify_ssl: bool = True,
    ) -> tuple[str, str]:
        """Download the content of a URI as text.

        Args:
            uri: The URI to download.
            timeout: Timeout in seconds. Defaults to None.
            headers: Optional HTTP headers. Defaults to None.
            verify_ssl: Whether to verify SSL certificates.
                Defaults to True.

        Returns:
            A tuple of (text content, final URL).
        """
        request_headers: dict[str, str] = dict(headers) if headers else {}

        with (
            self._build_session() as session,
            session.get(
                uri,
                timeout=timeout,
                headers=request_headers,
                verify=verify_ssl,
            ) as response,
        ):
            response.raise_for_status()
            return response.text, response.url

    def download_binary(
        self,
        uri: str,
        timeout: float | None = None,
        headers: Mapping[str, str] | None = None,
        *,
        verify_ssl: bool = True,
    ) -> tuple[bytes, str]:
        """Download the content of a URI as raw bytes.

        Args:
            uri: The URI to download.
            timeout: Timeout in seconds. Defaults to None.
            headers: Optional HTTP headers. Defaults to None.
            verify_ssl: Whether to verify SSL certificates.
                Defaults to True.

        Returns:
            A tuple of (binary content, final URL).
        """
        request_headers: dict[str, str] = dict(headers) if headers else {}

        with (
            self._build_session() as session,
            session.get(
                uri,
                timeout=timeout,
                headers=request_headers,
                verify=verify_ssl,
            ) as response,
        ):
            response.raise_for_status()
            return response.content, response.url
