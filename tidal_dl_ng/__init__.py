#!/usr/bin/env python
"""Package initialization for tidal-dl-ng-For-DJ.

Resolves project metadata (version, repository URL) from either the
local ``pyproject.toml`` or the installed package metadata, and exposes
helpers to detect the runtime environment and check for updates.
"""

import importlib.metadata
from pathlib import Path
from typing import TypedDict, cast
from urllib.parse import urlparse

import requests
import toml

from tidal_dl_ng.constants import REQUESTS_TIMEOUT_SEC

# Apply mpegdash patch before any tidalapi imports to fix TIDAL manifest
# parsing. See: https://github.com/FunWarry/tidal-dl-ng-For-DJ/issues/15
from tidal_dl_ng.helper.mpegdash_patch import apply_mpegdash_patch
from tidal_dl_ng.model.meta import ProjectInformation, ReleaseLatest

apply_mpegdash_patch()


class _PyprojectData(TypedDict):
    """Minimal subset of pyproject.toml we read for metadata."""

    project: dict[str, object]


def metadata_project() -> ProjectInformation:
    """Resolve project metadata from pyproject.toml or package info.

    Returns:
        ProjectInformation: Version and repository URL.
    """
    file_path: Path = Path(__file__)
    tmp_result: _PyprojectData | None = None

    paths: list[Path] = [
        file_path.parent,
        file_path.parent.parent,
        file_path.parent.parent.parent,
    ]

    for pyproject_toml_dir in paths:
        pyproject_toml_file: Path = pyproject_toml_dir / "pyproject.toml"

        if pyproject_toml_file.is_file():
            tmp_result = cast(
                "_PyprojectData",
                toml.load(pyproject_toml_file),
            )
            break

    if tmp_result:
        project = tmp_result["project"]
        urls = cast("dict[str, object]", project["urls"])
        return ProjectInformation(
            version=str(project["version"]),
            repository_url=str(urls["repository"]),
        )

    try:
        meta_info = importlib.metadata.metadata(name_package())
    except importlib.metadata.PackageNotFoundError:
        return ProjectInformation(
            version="0.0.0",
            repository_url=("https://anerroroccur.ed/sorry/for/that"),
        )

    if not (repo_url := meta_info["Home-page"]):
        urls = meta_info.get_all("Project-URL") or []
        # Attempt to parse, else use hardcoded fallback.
        repo_url = next(
            (
                url.split(", ")[1]
                for url in urls
                if url.startswith("Repository")
            ),
            "https://github.com/FunWarry/tidal-dl-ng-For-DJ",
        )

    return ProjectInformation(
        version=str(meta_info["Version"]),
        repository_url=str(repo_url),
    )


def version_app() -> str:
    """Return the application version string.

    Returns:
        str: The version (e.g. "0.32.1").
    """
    metadata: ProjectInformation = metadata_project()
    version: str = metadata.version

    return version


def repository_url() -> str:
    """Return the project repository URL.

    Returns:
        str: The repository URL.
    """
    metadata: ProjectInformation = metadata_project()
    url_repo: str = metadata.repository_url

    return url_repo


def repository_path() -> str:
    """Return the repository path component of the URL.

    Returns:
        str: The URL path (e.g. "/owner/repo").
    """
    url_repo: str = repository_url()
    url_path: str = urlparse(url_repo).path

    return url_path


def latest_version_information() -> ReleaseLatest:
    """Fetch the latest release information from GitHub.

    Returns:
        ReleaseLatest: Latest release data, or a fallback on failure.
    """
    repo_path: str = repository_path()
    url: str = f"https://api.github.com/repos{repo_path}/releases/latest"

    try:
        response = requests.get(url, timeout=REQUESTS_TIMEOUT_SEC)
        release_info_json: dict[str, object] = response.json()

        return ReleaseLatest(
            version=str(release_info_json["tag_name"]),
            url=str(release_info_json["html_url"]),
            release_info=str(release_info_json["body"]),
        )
    except (
        requests.RequestException,
        ValueError,
        KeyError,
    ):
        return ReleaseLatest(
            version="v0.0.0",
            url=url,
            release_info=(
                f"Something went wrong calling {url}. "
                "Check your internet connection."
            ),
        )


def name_package() -> str:
    """Return the current package name.

    Returns:
        str: The package name from ``__package__`` or ``__name__``.
    """
    package_name: str = __package__ or __name__

    return package_name


def is_dev_env() -> bool:
    """Detect whether the package runs from source (dev mode).

    Returns:
        bool: True when running uncompiled and not pip-installed.
    """
    package_name: str = name_package()
    result: bool = False

    # Check if package is running from source code == dev mode.
    # If package is not running in Nuitka environment, try to import it
    # from pip libraries. If this also fails, it is dev mode.
    if "__compiled__" not in globals():
        try:
            importlib.metadata.version(package_name)
        except importlib.metadata.PackageNotFoundError:
            # If package is not installed.
            result = True

    return result


def name_app() -> str:
    """Return the display name of the application.

    Returns:
        str: Package name, suffixed with "-dev" in dev mode.
    """
    app_name: str = name_package()

    if is_dev_env():
        app_name += "-dev"

    return app_name


__name_display__ = name_app()
__version__ = version_app()


def update_available() -> tuple[bool, ReleaseLatest]:
    """Check whether a newer release is available.

    Returns:
        tuple[bool, ReleaseLatest]: (is_update_available, latest_info).
    """
    latest_info: ReleaseLatest = latest_version_information()
    version_current: str = f"v{__version__}"

    result = version_current not in [
        latest_info.version,
        "v0.0.0",
    ]
    return result, latest_info
