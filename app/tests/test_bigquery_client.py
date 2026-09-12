"""Tests for utils.bigquery_client that do not need a BigQuery connection."""
import numpy as np
import pandas as pd
import pytest

from utils import bigquery_client as bq


def _arr(*pubs):
    return np.array([{"publication_number": p} for p in pubs], dtype=object)


def test_extract_citation_neighbors_reads_numpy_array_cells():
    # Regression: BigQuery returns REPEATED columns as numpy arrays. The old
    # isinstance(raw, list) check silently dropped every neighbor.
    df = pd.DataFrame(
        {
            "publication_number": ["US-1-A1"],
            "citation": [_arr("US-2-A1")],
            "cited_by": [_arr("US-3-A1")],
            "parent": [None],
            "child": [np.array([], dtype=object)],
        }
    )
    assert sorted(bq.extract_citation_neighbors(df)) == ["US-2-A1", "US-3-A1"]


def test_extract_citation_neighbors_excludes_patents_already_in_results():
    df = pd.DataFrame(
        {
            "publication_number": ["US-1-A1", "US-2-A1"],
            "citation": [_arr("US-2-A1", "US-9-A1"), _arr("US-1-A1")],
            "cited_by": [None, None],
            "parent": [None, None],
            "child": [None, None],
        }
    )
    assert bq.extract_citation_neighbors(df) == ["US-9-A1"]


def test_extract_citation_neighbors_caps_at_max_neighbors():
    df = pd.DataFrame(
        {
            "publication_number": ["US-1-A1"],
            "citation": [_arr(*[f"US-{i}-A1" for i in range(100, 110)])],
            "cited_by": [None],
            "parent": [None],
            "child": [None],
        }
    )
    assert len(bq.extract_citation_neighbors(df, max_neighbors=3)) == 3


def test_extract_citation_neighbors_returns_empty_when_no_arrays():
    df = pd.DataFrame(
        {"publication_number": ["US-1-A1"], "citation": [None], "cited_by": [None],
         "parent": [None], "child": [None]}
    )
    assert bq.extract_citation_neighbors(df) == []


@pytest.mark.parametrize(
    "value, expected",
    [(20240115, "2024-01-15"), (None, "N/A"), (float("nan"), "N/A"), (pd.NA, "N/A"), (0, "N/A"), (2024, "2024")],
)
def test_format_date(value, expected):
    assert bq.format_date(value) == expected


@pytest.mark.parametrize(
    "value, expected",
    [({"value": "Title"}, "Title"), ({}, ""), (None, ""), ("plain", "plain"), (12, "12")],
)
def test_extract_struct_value(value, expected):
    assert bq.extract_struct_value(value) == expected


class _FakeJob:
    def __init__(self, rows):
        self._rows = rows

    def result(self):
        return self._rows


class _FakeClient:
    """Answers normalize lookups from a fixed table without touching BigQuery."""

    def __init__(self, known):
        self.known = known
        self.queries = []

    def query(self, sql, job_config=None):
        number = job_config.query_parameters[0].value
        self.queries.append(sql)
        if "CONCAT('US-', @number, '-B1')" in sql:
            hits = [p for p in self.known if p in {f"US-{number}-B1", f"US-{number}-B2", f"US-{number}-A1"}]
        elif "LIKE CONCAT" in sql:
            hits = [p for p in self.known if p.startswith(f"US-{number}")]
        else:
            hits = [p for p, app in self.known.items() if app == number]
        return _FakeJob([{"publication_number": p} for p in hits[:1]])


@pytest.fixture
def fake_client(monkeypatch):
    client = _FakeClient({"US-8410469-B2": "US-13/123456", "US-2007156035-A1": "US-11/999"})
    monkeypatch.setattr(bq, "_get_client", lambda: client)
    return client


def test_normalize_returns_full_publication_number_without_querying(fake_client):
    assert bq.normalize_patent_number(" us-8410469-b2 ") == "US-8410469-B2"
    assert fake_client.queries == []


def test_normalize_resolves_plain_grant_number_with_commas(fake_client):
    assert bq.normalize_patent_number("8,410,469") == "US-8410469-B2"


def test_normalize_strips_us_prefix(fake_client):
    assert bq.normalize_patent_number("US8410469") == "US-8410469-B2"


def test_normalize_falls_back_to_like_match_for_unusual_suffix(fake_client):
    fake_client.known["US-5551212-C1"] = "US-14/1"
    assert bq.normalize_patent_number("5551212") == "US-5551212-C1"
    assert len(fake_client.queries) == 2


def test_normalize_falls_back_to_application_number(fake_client):
    fake_client.known["US-7-B1"] = "12345"
    assert bq.normalize_patent_number("12345") == "US-7-B1"
    assert len(fake_client.queries) == 3


def test_normalize_rejects_non_numeric_input_without_querying(fake_client):
    assert bq.normalize_patent_number("not a patent") is None
    assert fake_client.queries == []


def test_normalize_returns_none_for_empty_input(fake_client):
    assert bq.normalize_patent_number("   ") is None


def test_normalize_returns_none_when_nothing_matches(fake_client):
    assert bq.normalize_patent_number("99999999") is None
