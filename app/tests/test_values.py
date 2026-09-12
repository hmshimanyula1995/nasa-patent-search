"""Tests for utils.values: coercion of BigQuery array/struct cells.

BigQuery's to_dataframe() hands REPEATED columns to pandas as numpy object
arrays, not Python lists. Every consumer must treat both the same way.
"""
import math

import numpy as np

from utils.values import extract_pub_numbers, to_list


def test_to_list_returns_empty_for_none():
    assert to_list(None) == []


def test_to_list_passes_lists_through_unchanged():
    items = [{"a": 1}, {"b": 2}]
    assert to_list(items) is items


def test_to_list_converts_numpy_object_array_to_list():
    arr = np.array([{"a": 1}, {"b": 2}], dtype=object)
    assert to_list(arr) == [{"a": 1}, {"b": 2}]


def test_to_list_converts_empty_numpy_array_to_empty_list():
    assert to_list(np.array([], dtype=object)) == []


def test_to_list_returns_empty_for_scalar_number():
    assert to_list(42) == []


def test_to_list_returns_empty_for_nan_cell():
    assert to_list(math.nan) == []


def test_to_list_does_not_split_a_string_into_characters():
    assert to_list("US-1-A1") == []


def test_extract_pub_numbers_reads_struct_array():
    arr = np.array(
        [{"publication_number": "US-1-A1"}, {"publication_number": ""}, {"other": 1}],
        dtype=object,
    )
    assert extract_pub_numbers(arr) == ["US-1-A1"]


def test_extract_pub_numbers_reads_plain_string_items():
    assert extract_pub_numbers(["US-1-A1", "", None]) == ["US-1-A1"]


def test_extract_pub_numbers_returns_empty_for_none():
    assert extract_pub_numbers(None) == []
