"""Headless end-to-end tests of app.py with fake BigQuery and Gemini clients.

Synthetic result rows are built with pyarrow and converted the same way
google-cloud-bigquery's to_dataframe() converts them, so cells have the real
production shapes: dict structs, numpy object arrays, nullable Int64 dates.
"""
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pytest
from streamlit.testing.v1 import AppTest

from utils import bigquery_client as bq
from utils import gemini_client as gc
from utils import refresh

APP = str(Path(__file__).resolve().parents[1] / "app.py")

PUB_STRUCT = pa.list_(pa.struct([("publication_number", pa.string())]))
NAME_STRUCT = pa.list_(pa.struct([("name", pa.string())]))
VALUE_STRUCT = pa.struct([("value", pa.string())])


def _pubs(*p):
    return [{"publication_number": x} for x in p]


def _names(*n):
    return [{"name": x} for x in n]


def _patents(rows, with_distance):
    fields = [
        ("publication_number", pa.string()), ("application_number", pa.string()),
        ("title", VALUE_STRUCT), ("abstract", VALUE_STRUCT),
        ("primary_assignee", pa.string()), ("primary_inventor", pa.string()),
        ("assignee_harmonized", NAME_STRUCT), ("inventor_harmonized", NAME_STRUCT),
        ("filing_date", pa.int64()), ("publication_date", pa.int64()), ("grant_date", pa.int64()),
        ("cited_by", PUB_STRUCT), ("citation", PUB_STRUCT), ("parent", PUB_STRUCT), ("child", PUB_STRUCT),
        ("cpc", pa.list_(pa.struct([("code", pa.string())]))),
        ("top_terms", pa.list_(pa.struct([("value", pa.string())]))),
    ]
    if with_distance:
        fields.append(("distance", pa.float64()))
    table = pa.Table.from_pylist(rows, schema=pa.schema(fields))
    return table.to_pandas(
        integer_object_nulls=True,
        types_mapper=lambda t: pd.Int64Dtype() if pa.types.is_int64(t) else None,
    )


def _row(pub, **kw):
    base = dict(
        publication_number=pub, application_number=f"APP-{pub}",
        title={"value": f"Title {pub}"}, abstract={"value": f"Abstract {pub}"},
        primary_assignee="ACME Corp", primary_inventor="Ada Lovelace",
        assignee_harmonized=_names("ACME Corp"), inventor_harmonized=_names("Ada Lovelace"),
        filing_date=20200101, publication_date=20210101, grant_date=0,
        cited_by=[], citation=[], parent=[], child=[],
        cpc=[{"code": "G06F"}], top_terms=[{"value": "rocket"}, {"value": "fuel"}],
    )
    base.update(kw)
    return base


RESULTS = _patents(
    [
        _row("US-1-A1", distance=0.0, citation=_pubs("US-2-A1", "US-10-A1"), child=_pubs("US-11-A1")),
        _row("US-2-A1", distance=0.05, cited_by=_pubs("US-1-A1"), citation=_pubs("US-3-A1"),
             primary_assignee="Globex", assignee_harmonized=_names("Globex")),
        _row("US-3-A1", distance=0.2, parent=_pubs("US-10-A1"), grant_date=20220202),
        _row("US-4-A1", distance=0.4, cpc=[{"code": "H04L"}]),
    ],
    with_distance=True,
)

NEIGHBORS = _patents(
    [
        _row("US-10-A1", cited_by=_pubs("US-1-A1"), child=_pubs("US-3-A1")),
        _row("US-11-A1", parent=_pubs("US-1-A1")),
    ],
    with_distance=False,
)


class _Job:
    def __init__(self, df=None, rows=()):
        self._df, self._rows = df, list(rows)

    def to_dataframe(self):
        return self._df.copy()

    def result(self):
        return self._rows


class _FakeBigQuery:
    def __init__(self):
        self.sql = []

    def query(self, sql, job_config=None):
        self.sql.append(sql)
        if "VECTOR_SEARCH" in sql:
            return _Job(df=RESULTS)
        if "IN UNNEST(@neighbor_ids)" in sql:
            ids = set(job_config.query_parameters[0].values)
            return _Job(df=NEIGHBORS[NEIGHBORS["publication_number"].isin(ids)])
        number = job_config.query_parameters[0].value
        return _Job(rows=[{"publication_number": "US-1-A1"}] if number == "1" else [])


class _Chunk:
    def __init__(self, text):
        self.text = text


class _FakeGenAI:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.models = self

    def generate_content_stream(self, *, model, contents, config=None):
        return iter([_Chunk("## Technology Landscape\n"), _Chunk("Fake analysis body.")])


@pytest.fixture
def fakes(monkeypatch):
    bigquery = _FakeBigQuery()
    monkeypatch.setattr(bq, "_get_client", lambda: bigquery)
    monkeypatch.setattr("google.genai.Client", _FakeGenAI)
    monkeypatch.delenv("REFRESH_TRANSFER_CONFIG", raising=False)
    for cached in (bq.search_patents, bq.fetch_citation_neighbors, gc._get_client, refresh.get_last_refresh):
        cached.clear()
    yield bigquery
    for cached in (bq.search_patents, bq.fetch_citation_neighbors, gc._get_client, refresh.get_last_refresh):
        cached.clear()


def _run_landing():
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    return at


def _run_search(text):
    at = _run_landing()
    at.sidebar.text_input[0].input(text)
    at.sidebar.button[0].click()
    at.run()
    return at


def _all_markdown(at):
    return "\n".join(m.value for m in at.markdown)


def test_landing_page_renders_without_exceptions(fakes):
    at = _run_landing()
    assert not at.exception
    assert "Search NASA's Patent Database" in _all_markdown(at)
    assert "Manual refresh is not available" in " ".join(c.value for c in at.caption)


def test_search_renders_full_results_page_from_bigquery_shaped_rows(fakes):
    at = _run_search("US-1-A1")
    assert not at.exception, at.exception[0].value
    assert [m.label for m in at.metric] == [
        "Results", "Unique Assignees", "Unique Inventors", "Avg Similarity", "Citation Network",
    ]
    assert at.metric[0].value == "3"
    assert at.metric[4].value == "+2"
    assert len(at.dataframe) == 2
    assert "Structurally Important Patents" in _all_markdown(at)
    assert "Fake analysis body." in _all_markdown(at)
    assert "rocket" in _all_markdown(at)
    assert [e.label for e in at.expander] == ["AI Analysis (Gemini)"]


def test_structural_table_hides_rows_that_would_display_as_zero(fakes, monkeypatch):
    # Nodes unreachable from the seed get floating-point residue from the
    # power iteration. They must not appear as "structurally important" at 0.0%.
    from utils import graph_ranking as gr
    real = gr.compute_ppr

    def residue(G, query, alpha=0.85, undirected=False):
        scores = real(G, query, alpha, undirected)
        for pub in ("US-10-A1", "US-11-A1"):
            if pub in scores:
                scores[pub] = 1e-9
        return scores

    monkeypatch.setattr(gr, "compute_ppr", residue)  # app.py re-imports it on every run
    at = _run_search("US-1-A1")
    assert not at.exception, at.exception[0].value
    assert "Structurally Important Patents" not in _all_markdown(at)
    assert len(at.dataframe) == 1


def test_search_expands_citation_neighbors_through_bigquery(fakes):
    _run_search("US-1-A1")
    assert any("IN UNNEST(@neighbor_ids)" in s for s in fakes.sql)


def test_search_normalizes_plain_grant_number(fakes):
    at = _run_search("1")
    assert not at.exception
    assert any("Resolved `1` → `US-1-A1`" in w.value for w in at.markdown)


def test_unknown_patent_shows_friendly_error_and_stops(fakes):
    at = _run_search("99")
    assert not at.exception
    assert any("not found in the indexed database" in e.value for e in at.error)
    assert at.metric == []


def test_sidebar_has_undirected_graph_toggle_defaulting_off(fakes):
    at = _run_landing()
    toggles = at.sidebar.toggle
    assert [t.label for t in toggles] == ["Undirected citation graph"]
    assert toggles[0].value is False


def test_undirected_toggle_changes_ranking_and_is_shown_in_results_header(fakes):
    at = _run_search("US-1-A1")
    assert "Undirected citation graph" not in _all_markdown(at)
    at.sidebar.toggle[0].set_value(True)
    at.run()
    assert not at.exception, at.exception[0].value
    assert "Undirected citation graph" in _all_markdown(at)
    assert at.metric[4].label == "Citation Network"


def test_app_uses_no_deprecated_streamlit_width_flag():
    assert "use_container_width" not in Path(APP).read_text()


def test_network_graph_is_rendered_with_st_iframe(fakes):
    # st.components.v1.html is scheduled for removal; st.iframe is the
    # replacement and embeds an HTML string directly.
    assert "components.html" not in Path(APP).read_text()
    at = _run_search("US-1-A1")
    assert not at.exception
    frames = at.get("iframe")
    assert len(frames) == 1
    assert "US-2-A1" in frames[0].proto.srcdoc
