"""Custom exception types for the TIDAL download manager.

This module defines the project-specific exceptions raised across the
downloader and API layers. They are intentionally lightweight markers
that let callers distinguish domain errors (e.g. unavailable media,
unknown manifest formats) from generic Python or network failures.
"""

from typing import override


class TidalDlNgError(Exception):
    """Base class for all project-specific exceptions.

    All custom errors in this module inherit from this class so that
    callers can catch every domain error with a single ``except``.
    """

    @override
    def __str__(self) -> str:
        """Return a human-readable description of the error.

        Returns:
            str: The exception message or its class name when empty.
        """
        if (message := self.args[0] if self.args else None) is not None:
            return str(message)

        return self.__class__.__name__


class LoginError(TidalDlNgError):
    """Raised when authentication with the TIDAL service fails."""


class MediaUnknown(TidalDlNgError):
    """Raised when a media type cannot be resolved to an object."""


class UnknownManifestFormat(TidalDlNgError):
    """Raised when a stream manifest uses an unsupported format."""


class MediaMissing(TidalDlNgError):
    """Raised when expected media is missing from the TIDAL catalog."""
