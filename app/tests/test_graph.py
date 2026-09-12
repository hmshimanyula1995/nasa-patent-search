"""Tests for utils.graph network HTML generation."""
import numpy as np
import pandas as pd
import pytest

from utils import graph


def _arr(*pubs):
    return np.array([{"publication_number": p} for p in pubs], dtype=object)


def _results():
    return pd.DataFrame(
        {
            "publication_number": ["US-1-A1", "US-2-A1", "US-3-A1"],
            "title_text": ["Query", "Two", "Three"],
            "primary_assignee": ["ACME", "Globex", None],
            "similarity": [1.0, 0.96, 0.7],
            "citation": [_arr("US-2-A1", "US-77-A1"), None, None],
            "cited_by": [None, None, _arr("US-1-A1")],
            "parent": [None, _arr("US-3-A1"), None],
            "child": [None, None, None],
        }
    )


@pytest.mark.parametrize(
    "score, color",
    [(0.96, "#1a7431"), (0.92, "#2E8540"), (0.86, "#4A90D9"), (0.81, "#F0C419"), (0.76, "#FF9D1E"), (0.2, "#DD361C")],
)
def test_score_color_tiers(score, color):
    assert graph._score_color(score) == color


def test_build_network_html_contains_all_nodes_and_query_styling():
    html = graph.build_network_html(_results(), "US-1-A1")
    assert "US-2-A1" in html and "US-3-A1" in html
    assert "QUERY: US-1-A1" in html
    assert "US-77-A1" not in html


def test_build_network_html_adds_expanded_nodes_as_triangles():
    expanded = pd.DataFrame(
        {"publication_number": ["US-9-A1"], "title_text": ["Nine"], "primary_assignee": ["X"],
         "ppr_score": [0.5], "citation": [_arr("US-1-A1")], "cited_by": [None], "parent": [None], "child": [None]}
    )
    html = graph.build_network_html(_results(), "US-1-A1", expanded_df=expanded)
    assert "US-9-A1 (Citation Network)" in html
    assert '"shape": "triangle"' in html


def test_build_network_html_handles_missing_score_column():
    html = graph.build_network_html(_results(), "US-1-A1", score_column="blended_score")
    assert "US-2-A1" in html


def test_build_network_html_leaves_no_temp_file(tmp_path, monkeypatch):
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    import tempfile
    tempfile.tempdir = None
    graph.build_network_html(_results(), "US-1-A1")
    assert list(tmp_path.glob("patent_graph_*")) == []
