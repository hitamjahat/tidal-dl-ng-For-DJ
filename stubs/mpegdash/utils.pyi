from typing import TypeVar
from xml.dom.minidom import Element

_T = TypeVar("_T")

def parse_attr_value(
    xmlnode: Element,
    attr_name: str,
    value_type: type[_T] | list[type[_T]],
) -> _T | None: ...
def parse_child_nodes(
    xmlnode: Element,
    tag_name: str,
    node_type: type[_T] | str,
) -> list[_T] | None: ...
def parse_node_value(
    xmlnode: Element,
    value_type: type[_T],
) -> _T | None: ...
def write_child_node(
    xmlnode: Element,
    tag_name: str,
    node: object | list[object] | None,
) -> None: ...
