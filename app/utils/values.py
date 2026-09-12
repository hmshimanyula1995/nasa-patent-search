"""Coercion helpers for values that come back from BigQuery.

BigQuery's ``to_dataframe()`` converts REPEATED columns through pyarrow, so a
cell holding an ARRAY<STRUCT> arrives as a numpy object array of dicts rather
than a Python list. Scalar NULLs arrive as None or NaN. Every module that walks
citation, assignee, CPC or top_terms arrays must go through these helpers so
the behavior stays identical regardless of the pandas or pyarrow version.
"""
from __future__ import annotations

import math
from typing import Any


def to_list(value: Any) -> list:
    """Return ``value`` as a Python list, or ``[]`` when it is not an array.

    Accepts lists, tuples and numpy arrays. Returns ``[]`` for None, NaN,
    numbers and strings, so a scalar cell is never iterated by accident.
    """
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, (str, bytes)):
        return []
    if isinstance(value, float) and math.isnan(value):
        return []
    try:
        return list(value)
    except (TypeError, ValueError):
        return []


def extract_pub_numbers(array_field: Any) -> list[str]:
    """Extract non-empty publication_number strings from a BigQuery struct array.

    Items may be dicts with a ``publication_number`` key or bare strings.
    """
    pubs: list[str] = []
    for item in to_list(array_field):
        if isinstance(item, dict):
            pub = item.get("publication_number", "")
            if pub:
                pubs.append(pub)
        elif isinstance(item, str) and item:
            pubs.append(item)
    return pubs
