from xml.dom.minidom import Element

def parse_attr_value[T](
    xmlnode: Element,
    attr_name: str,
    value_type: type[T] | list[type[T]],
) -> T | None: ...
def parse_child_nodes[T](
    xmlnode: Element,
    tag_name: str,
    node_type: type[T] | str,
) -> list[T] | None: ...
def parse_node_value[T](
    xmlnode: Element,
    value_type: type[T],
) -> T | None: ...
def write_child_node(
    xmlnode: Element,
    tag_name: str,
    node: object | list[object] | None,
) -> None: ...
