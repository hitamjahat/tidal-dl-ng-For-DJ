from enum import Enum

type JsonObj = dict[str, object]

class AlbumOrder(Enum):
    Artist = "ARTIST"
    DateAdded = "DATE"
    Name = "NAME"
    ReleaseDate = "RELEASE_DATE"

class ArtistOrder(Enum):
    DateAdded = "DATE"
    Name = "NAME"
