"""Stub for mutagen top-level package."""

from pathlib import Path

class MutagenError(Exception): ...

class FileType:
    tags: object
    def add_tags(self) -> None: ...
    def save(self, filename: str | Path | None = ...) -> None: ...

def File(
    filename: str | Path,
    options: list[object] | None = ...,
    easy: bool = ...,
) -> FileType | None: ...
