from mutagen.id3 import ID3FileType

class MP3(ID3FileType):
    def save(
        self,
        filething: object = None,
        **kwargs: object,
    ) -> None: ...
    def delete(self, filething: object = None) -> None: ...
    def pprint(self) -> str: ...
