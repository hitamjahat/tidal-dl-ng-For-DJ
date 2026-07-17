"""HTTP client helpers for downloading text and binary content."""

import requests
from requests.adapters import HTTPAdapter
from typing import Any
from urllib3.util.retry import Retry


class RequestsClient:
    """HTTP client for downloading text content from a URI."""

    def download(
        self,
        uri: str,
        timeout: float | None = None,
        headers: dict[str, Any] | None = None,
        verify_ssl: bool = True,
    ) -> tuple[str, str]:
        """Download the content of a URI as text.

        Args:
            uri (str): The URI to download.
            timeout (float | None, optional): Timeout in seconds.
                Defaults to None.
            headers (dict[str, Any] | None, optional): HTTP headers.
                Defaults to None.
            verify_ssl (bool, optional): Whether to verify SSL.
                Defaults to True.

        Returns:
            tuple[str, str]: Tuple of (text content, final URL).
        """
        if not headers:
            headers = {}

        with requests.Session() as session:
            retries = Retry(
                total=5,
                backoff_factor=1,
                status_forcelist=[429, 500, 502, 503, 504],
            )
            session.mount("https://", HTTPAdapter(max_retries=retries))
            session.mount("http://", HTTPAdapter(max_retries=retries))
            with session.get(
                uri, timeout=timeout, headers=headers, verify=verify_ssl
            ) as response:
                response.raise_for_status()
                return response.text, response.url

    def download_binary(
        self,
        uri: str,
        timeout: float | None = None,
        headers: dict[str, Any] | None = None,
        verify_ssl: bool = True,
    ) -> tuple[bytes, str]:
        """Download the content of a URI as raw bytes.

        Args:
            uri (str): The URI to download.
            timeout (float | None, optional): Timeout in seconds.
                Defaults to None.
            headers (dict[str, Any] | None, optional): HTTP headers.
                Defaults to None.
            verify_ssl (bool, optional): Whether to verify SSL.
                Defaults to True.

        Returns:
            tuple[bytes, str]: Tuple of (binary content, final URL).
        """
        if not headers:
            headers = {}

        with requests.Session() as session:
            retries = Retry(
                total=5,
                backoff_factor=1,
                status_forcelist=[429, 500, 502, 503, 504],
            )
            session.mount("https://", HTTPAdapter(max_retries=retries))
            session.mount("http://", HTTPAdapter(max_retries=retries))
            with session.get(
                uri, timeout=timeout, headers=headers, verify=verify_ssl
            ) as response:
                response.raise_for_status()
                return response.content, response.url
