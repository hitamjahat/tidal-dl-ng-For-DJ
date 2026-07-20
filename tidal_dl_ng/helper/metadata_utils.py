"""Utilities for extracting and formatting metadata from TIDAL objects."""

from contextlib import suppress
from typing import cast


def _convert_list_to_str(value: list[object] | tuple[object, ...]) -> str:
    """Convert list/tuple to comma-separated string.

    Args:
        value: The list or tuple to convert.

    Returns:
        str: Comma-separated string, or em-dash if empty.
    """
    if not value:
        return "—"
    with suppress(Exception):
        return ", ".join([str(x) for x in value])
    return str(value)


def _convert_dict_to_str(value: dict[str, object]) -> str:
    """Extract meaningful string from dict.

    Args:
        value: The dictionary to convert.

    Returns:
        str: A meaningful string representation of the dict.
    """
    if name := value.get("name"):
        return str(name)
    for key in ("label", "title", "genre", "name"):
        if val := value.get(key):
            return str(val)
    with suppress(Exception):
        if vals := [str(v) for v in value.values() if v is not None]:
            return ", ".join(vals)
    return str(value)


def safe_str(value: object) -> str:
    """Convert a potentially non-str value into a safe string for display.

    Args:
        value: The value to convert.

    Returns:
        str: Safe string representation, '—' for None/empty.
    """
    with suppress(Exception):
        if value is None:
            return "—"
        if isinstance(value, str):
            return value if value != "" else "—"
        if isinstance(value, list | tuple):
            seq = cast("list[object] | tuple[object, ...]", value)
            return _convert_list_to_str(seq)
        if isinstance(value, dict):
            dict_value = cast("dict[str, object]", value)
            return _convert_dict_to_str(dict_value)
        return str(value)
    return "—"


def _find_in_dict_container(
    container: dict[str, object],
    names: tuple[str, ...],
) -> object | None:
    """Search for names in a dict container.

    Args:
        container: The dictionary to search in.
        names: The keys to look for.

    Returns:
        object | None: The first matching value, or None.
    """
    for name in names:
        if name in container and container[name] is not None:
            return container[name]
    # Fuzzy key match
    keys: list[str] = list(container.keys())
    for name in names:
        for key in keys:
            if name.lower() in key.lower():
                return container[key]
    return None


def _fuzzy_scan_attrs(
    obj: object,
    names: tuple[str, ...],
) -> object | None:
    """Fuzzy scan object attributes for matching names.

    Args:
        obj: The object to inspect.
        names: The attribute name fragments to search for.

    Returns:
        object | None: The first matching attribute value, or None.
    """
    with suppress(Exception):
        for key in dir(obj):
            key_lower = key.lower()
            for name in names:
                if name.lower() in key_lower:
                    with suppress(Exception):
                        if (val := getattr(obj, key)) is not None:
                            return val
    return None


def find_attr(obj: object, *names: str) -> object | None:
    """Attempt to find an attribute or data key from an object.

    Args:
        obj: The object to inspect.
        *names: Attribute/key names to search for.

    Returns:
        object | None: The found value or None.
    """
    # Direct attributes
    for name in names:
        with suppress(Exception):
            if hasattr(obj, name) and (val := getattr(obj, name)) is not None:
                return val

    # Inspect common dict-like internals
    for container_name in ("_data", "data", "__dict__"):
        with suppress(Exception):
            container = getattr(obj, container_name, None)
            if isinstance(container, dict):
                dict_container = cast("dict[str, object]", container)
                if (
                    result := _find_in_dict_container(
                        dict_container,
                        names,
                    )
                ) is not None:
                    return result

    # Fuzzy scan of attributes
    return _fuzzy_scan_attrs(obj, names)


def _scan_dict_recursive(
    container: dict[str, object],
    key_substrings: list[str],
) -> object | None:
    """Recursively scan a dict for keys matching any substring.

    Args:
        container: The dictionary to scan.
        key_substrings: Substrings to match against keys.

    Returns:
        object | None: The first matching value, or None.
    """
    for key, val in container.items():
        key_lower = str(key).lower()
        for sub in key_substrings:
            if sub.lower() in key_lower and val is not None:
                return val
        # recurse into nested structures
        if isinstance(val, dict):
            dict_val = cast("dict[str, object]", val)
            if (
                found := _scan_dict_recursive(
                    dict_val,
                    key_substrings,
                )
            ) is not None:
                return found
        if isinstance(val, list | tuple):
            seq = cast("list[object] | tuple[object, ...]", val)
            for item in seq:
                if isinstance(item, dict):
                    dict_item = cast("dict[str, object]", item)
                    if (
                        found := _scan_dict_recursive(
                            dict_item,
                            key_substrings,
                        )
                    ) is not None:
                        return found
    return None


def search_in_data(
    obj: object,
    key_substrings: list[str],
) -> object | None:
    """Recursively search dict-like internals for matching keys.

    Args:
        obj: The object to search.
        key_substrings: List of key substrings to search for.

    Returns:
        object | None: The first matching value found, or None.
    """
    # check common containers
    for container_name in ("_data", "data", "__dict__"):
        with suppress(Exception):
            container = getattr(obj, container_name, None)
            if isinstance(container, dict):
                dict_container = cast("dict[str, object]", container)
                if (
                    found := _scan_dict_recursive(
                        dict_container,
                        key_substrings,
                    )
                ) is not None:
                    return found

    # as last resort, try obj.__dict__ if available
    with suppress(Exception):
        data = getattr(obj, "__dict__", None)
        if isinstance(data, dict):
            dict_data = cast("dict[str, object]", data)
            return _scan_dict_recursive(dict_data, key_substrings)

    return None


def _extract_name_from_dict(
    item: dict[str, object],
    match_types: tuple[str, ...] | None,
) -> str | None:
    """Extract name from a dict if it matches type filters.

    Args:
        item: The dictionary to extract from.
        match_types: Optional tuple of role types to filter by.

    Returns:
        str | None: The extracted name, or None.
    """
    if "name" not in item or not item["name"]:
        return None
    if match_types:
        type_val = (
            item.get("type") or item.get("role") or item.get("credit_type")
        )
        if type_val and any(mt in str(type_val).lower() for mt in match_types):
            return str(item["name"])
        return None
    return str(item["name"])


def _get_item_name(item: object) -> str | None:
    """Extract a name from an item using all available strategies.

    Args:
        item: The item to extract a name from.

    Returns:
        str | None: The extracted name, or None.
    """
    if item is None:
        return None
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        dict_item = cast("dict[str, object]", item)
        for key in ("name", "artist", "person"):
            if val := dict_item.get(key):
                return str(val)
        return None
    result: str | None = None
    if nm := getattr(item, "name", None) or getattr(item, "title", None):
        result = str(nm)
    else:
        with suppress(Exception):
            result = str(item)
    return result


def extract_names_from_mixed(
    value: object,
    match_types: tuple[str, ...] | None = None,
) -> list[str]:
    """Normalize various credit-like structures into a list of names.

    Accepts lists of dicts, dicts, strings, or objects. If match_types is
    provided, only include entries where the type/role matches one of them.

    Args:
        value: The value to extract names from.
        match_types: Optional tuple of role types to filter by.

    Returns:
        list[str]: List of extracted names.
    """
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        dict_value = cast("dict[str, object]", value)
        if name := _extract_name_from_dict(dict_value, match_types):
            return [name]
        return [str(v) for v in dict_value.values() if v is not None]
    if isinstance(value, list | tuple):
        seq = cast("list[object] | tuple[object, ...]", value)
        items = tuple(seq)
        return _extract_names_from_items(items, match_types)
    return []


def _extract_names_from_items(
    items: tuple[object, ...],
    match_types: tuple[str, ...] | None,
) -> list[str]:
    """Extract names from a sequence of mixed items.

    Args:
        items: The items to extract names from.
        match_types: Optional tuple of role types to filter by.

    Returns:
        list[str]: List of extracted names.
    """
    names: list[str] = []
    for item in items:
        if isinstance(item, dict):
            dict_item = cast("dict[str, object]", item)
            if name := _extract_name_from_dict(dict_item, match_types):
                names.append(name)
        elif name := _get_item_name(item):
            names.append(name)
    return names
