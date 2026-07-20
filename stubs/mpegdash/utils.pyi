"""Type stubs for the mpegdash.utils module.

Provides type information for the functions used by the monkey-patch
in tidal_dl_ng.helper.mpegdash_patch.
"""

from xml.dom.minidom import Element

def parse_attr_value(
    xmlnode: Element,
    attr_name: str,
    value_type: type | list[type],
) -> object | None:
    """Parse an attribute value from an XML node."""
    ...

def parse_child_nodes(
    xmlnode: Element,
    tag_name: str,
    node_type: type | str,
) -> list[object] | None:
    """Parse child nodes from an XML node."""
    ...

def parse_node_value(
    xmlnode: Element,
    value_type: type,
) -> object | None:
    """Parse the node value from an XML node."""
    ...

def write_child_node(
    xmlnode: Element,
    tag_name: str,
    node: object | list[object] | None,
) -> None:
    """Write a child node to an XML node."""
    ...
