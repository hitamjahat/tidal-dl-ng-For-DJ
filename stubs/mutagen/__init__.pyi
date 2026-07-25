from pathlib import Path

class MutagenError(Exception): ...

class FileType:
    @property
    def tags(self) -> object | None: ...
    def add_tags(self) -> None: ...
    def save(
        self, filething: str | Path | None = ..., **kwargs: object
    ) -> None: ...

def File(
    filething: str | Path,
    options: list[object] | None = ...,
    easy: bool = ...,
) -> FileType | None: ...
