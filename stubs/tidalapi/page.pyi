"""Stub for tidalapi.page with resolved forward references."""

from typing import List, Optional

from tidalapi.media import Mix

class AllCategories:
    """A category container on a TIDAL page."""

    title: str
    items: List[Mix]

class Page:
    """A TIDAL page response."""

    categories: Optional[List[AllCategories]]

    def __init__(self, *args: object, **kwargs: object) -> None: ...
