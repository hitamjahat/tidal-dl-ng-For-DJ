"""Monkey-patch for mpegdash to handle non-integer AdaptationSet attributes.

TIDAL recently started returning MPD manifests with string values like "main"
for the AdaptationSet ``id`` and ``group`` attributes, which mpegdash expects
to be integers. This causes a ``ValueError``: invalid literal for int() with
base 10: 'main'.

This patch modifies the ``parse_attr_value`` function to gracefully handle
non-integer values for attributes that are expected to be integers.
"""

import logging
import re
from typing import Any
from xml.dom.minidom import Element

from mpegdash import utils as mpegdash_utils

logger = logging.getLogger(__name__)

# Type alias for the value_type parameter accepted by mpegdash.
ValueType = type | list[type]

# Module-level flag tracking whether the patch has been applied.
_patch_state: dict[str, bool] = {"applied": False}


def _safe_int(value: str) -> int | None:
    """Safely convert a value to int, returning None on failure.

    Args:
        value: The string value to convert.

    Returns:
        int | None: The integer value, or None if conversion fails.
    """
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _convert_list(attr_val: str, value_type: list[type]) -> list[str]:
    """Convert a comma/space separated string to a list of values.

    Args:
        attr_val: The raw attribute string value.
        value_type: The list-wrapped target type for each element.

    Returns:
        list[str]: The converted list, or string elements on failure.
    """
    attr_type: type = value_type[0] if value_type else str
    try:
        return [attr_type(elem) for elem in re.split(r"[, ]", attr_val)]
    except (ValueError, TypeError):
        return [str(elem) for elem in re.split(r"[, ]", attr_val)]


def _convert_single(
    attr_name: str,
    attr_val: str,
    value_type: type,
) -> Any | None:
    """Convert a single attribute value to the target type.

    Args:
        attr_name: The attribute name (used for logging).
        attr_val: The raw attribute string value.
        value_type: The target type to convert to.

    Returns:
        Any | None: The converted value, or None on failure.
    """
    if value_type is int:
        if (result := _safe_int(attr_val)) is None:
            logger.debug(
                "mpegdash: Could not convert '%s'='%s' to int, using None",
                attr_name,
                attr_val,
            )
        return result
    try:
        return value_type(attr_val)
    except (ValueError, TypeError):
        logger.debug(
            "mpegdash: Could not convert '%s'='%s' to %s, using None",
            attr_name,
            attr_val,
            value_type.__name__,
        )
        return None


def patched_parse_attr_value(
    xmlnode: Element,
    attr_name: str,
    value_type: ValueType,
) -> Any | None:
    """Patched version of mpegdash parse_attr_value.

    Args:
        xmlnode: The XML node to read the attribute from.
        attr_name: The attribute name to read.
        value_type: The target type or list of types to convert to.

    Returns:
        Any | None: The converted value, or None if not present/failed.
    """
    if attr_name not in xmlnode.attributes:
        return None

    attr_node: Any = xmlnode.attributes[attr_name]
    node_value: str | None = attr_node.nodeValue
    attr_val: str = node_value if node_value is not None else ""

    if isinstance(value_type, list):
        return _convert_list(attr_val, value_type)

    return _convert_single(attr_name, attr_val, value_type)


def apply_mpegdash_patch() -> None:
    """Apply a monkey-patch to mpegdash for string values in integer fields.

    This patches the ``parse_attr_value`` function in ``mpegdash.utils`` to
    gracefully handle non-integer values (like "main") for attributes that
    are expected to be integers.
    """
    if _patch_state["applied"]:
        return

    try:
        mpegdash_utils.parse_attr_value = patched_parse_attr_value
        _patch_state["applied"] = True
        logger.debug("mpegdash patch applied successfully")

    except ImportError:
        logger.warning("Could not import mpegdash, patch not applied")
    except Exception:
        logger.exception("Failed to apply mpegdash patch")
