"""Data models for project and release metadata.

These lightweight dataclasses carry version and repository information
used across the application for display and update checks.
"""

from dataclasses import dataclass


@dataclass
class ReleaseLatest:
    """Information about the latest available release."""

    version: str
    """Tag name of the latest release (e.g. ``"v1.2.3"``)."""

    url: str
    """HTML URL of the latest release on the repository host."""

    release_info: str
    """Release notes / body text of the latest release."""


@dataclass
class ProjectInformation:
    """Resolved metadata for the current project."""

    version: str
    """Installed or source version (e.g. ``"0.32.1"``)."""

    repository_url: str
    """URL of the project's source code repository."""
