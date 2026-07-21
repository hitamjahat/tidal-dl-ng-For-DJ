from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass

from tidalapi.album import Album
from tidalapi.artist import Artist
from tidalapi.media import Track, Video
from tidalapi.mix import Mix
from tidalapi.playlist import Playlist, UserPlaylist
from tidalapi.request import Requests
from tidalapi.session import Session

type TidalItem = Album | Artist | Mix | Playlist | Track | UserPlaylist | Video
type PageContent = TidalItem | PageItem | PageLink | Mapping[str, object] | str
type PageCategories = (
    Album | PageLinks | FeaturedItems | ItemList | TextBlock | LinkList | Mix
)
type AllCategories = Artist | PageCategories
type PageCategoriesV2 = (
    TrackList | ShortcutList | HorizontalList | HorizontalListWithContext
)
type AllCategoriesV2 = PageCategoriesV2

class Page:
    title: str
    categories: list[AllCategories | AllCategoriesV2] | None
    page_category: PageCategory
    page_category_v2: PageCategoryV2
    request: Requests
    _categories_iter: Iterator[AllCategories | AllCategoriesV2] | None
    _items_iter: Iterator[PageContent] | None
    _category: AllCategories | AllCategoriesV2

    def __init__(self, session: Session, title: str) -> None: ...
    def __iter__(self) -> Page: ...
    def __next__(self) -> PageContent: ...
    def next(self) -> PageContent: ...
    def parse(self, json_obj: Mapping[str, object]) -> Page: ...
    def get(
        self,
        endpoint: str,
        params: dict[str, object] | None = None,
    ) -> Page: ...

@dataclass
class More:
    api_path: str
    title: str

    @classmethod
    def parse(cls, json_obj: Mapping[str, object]) -> More | None: ...

class PageCategory:
    type: str | None
    title: str | None
    description: str | None
    session: Session
    request: Requests
    item_types: dict[str, Callable[[Mapping[str, object]], TidalItem]]
    _more: More | None

    def __init__(self, session: Session) -> None: ...
    def parse(self, json_obj: Mapping[str, object]) -> AllCategories: ...
    def show_more(self) -> Page | None: ...

class PageCategoryV2:
    type: str | None
    module_id: str | None
    title: str | None
    subtitle: str | None
    description: str | None
    category_type: str
    session: Session
    request: Requests
    item_types: dict[str, Callable[[Mapping[str, object]], TidalItem]]
    _more: More | None
    _type_map: dict[str, type[PageCategoryV2]]

    def __init__(self, session: Session) -> None: ...
    @classmethod
    def register_subclass(
        cls,
        category_type: str,
    ) -> Callable[
        [type[PageCategoryV2]],
        type[PageCategoryV2],
    ]: ...
    def parse_item(
        self,
        list_item: Mapping[str, object],
    ) -> PageCategoryV2: ...
    def _parse_base(self, list_item: Mapping[str, object]) -> None: ...
    def parse(self, json_obj: Mapping[str, object]) -> PageCategoryV2: ...
    def view_all(self) -> Page | None: ...

class SimpleList(PageCategoryV2):
    items: list[TidalItem]

    def __init__(self, session: Session) -> None: ...
    def parse(self, json_obj: Mapping[str, object]) -> SimpleList: ...
    def get_item(self, json_obj: Mapping[str, object]) -> TidalItem | None: ...

class ShortcutList(SimpleList): ...
class HorizontalList(SimpleList): ...
class HorizontalListWithContext(HorizontalList): ...

class TrackList(PageCategoryV2):
    items: list[Track]

    def __init__(self, session: Session) -> None: ...
    def parse(self, json_obj: Mapping[str, object]) -> TrackList: ...

class FeaturedItems(PageCategory):
    items: list[PageItem] | None

    def __init__(self, session: Session) -> None: ...
    def parse(self, json_obj: Mapping[str, object]) -> FeaturedItems: ...

class PageLinks(PageCategory):
    items: list[PageLink] | None

    def parse(self, json_obj: Mapping[str, object]) -> PageLinks: ...

class ItemList(PageCategory):
    items: list[TidalItem] | None

    def parse(self, json_obj: Mapping[str, object]) -> ItemList: ...

class PageLink:
    title: str
    icon: str | None
    image_id: str | None
    api_path: str
    session: Session
    request: Requests

    def __init__(
        self,
        session: Session,
        json_obj: Mapping[str, object],
    ) -> None: ...
    def get(self) -> Page: ...

class PageItem:
    header: str
    short_header: str
    short_sub_header: str
    image_id: str
    type: str
    artifact_id: str
    text: str
    featured: bool
    session: Session
    request: Requests

    def __init__(
        self,
        session: Session,
        json_obj: Mapping[str, object],
    ) -> None: ...
    def get(
        self,
    ) -> Album | Artist | Playlist | Track | UserPlaylist | Video: ...

class TextBlock:
    text: str
    icon: str
    items: list[str] | None
    session: Session

    def __init__(self, session: Session) -> None: ...
    def parse(self, json_obj: Mapping[str, object]) -> TextBlock: ...

class LinkList(PageCategory):
    items: list[Mapping[str, object]] | None
    title: str | None
    description: str | None

    def parse(self, json_obj: Mapping[str, object]) -> LinkList: ...

class ItemHeader:
    items: list[TidalItem] | None

    def __init__(self, item: TidalItem) -> None: ...
