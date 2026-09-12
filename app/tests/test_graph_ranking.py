"""Tests for utils.graph_ranking using BigQuery-shaped numpy array cells."""
import numpy as np
import pandas as pd
import pytest

from utils import graph_ranking as gr


def _arr(*pubs):
    return np.array([{"publication_number": p} for p in pubs], dtype=object)


@pytest.fixture
def results():
    return pd.DataFrame(
        {
            "publication_number": ["US-1-A1", "US-2-A1", "US-3-A1"],
            "similarity": [1.0, 0.8, 0.6],
            "citation": [_arr("US-2-A1", "US-9-A1"), _arr("US-3-A1"), None],
            "cited_by": [None, _arr("US-1-A1"), None],
            "parent": [None, None, _arr("US-2-A1")],
            "child": [_arr("US-1-A1"), None, None],
        }
    )


def test_build_citation_graph_adds_edges_only_between_known_nodes(results):
    G = gr.build_citation_graph(results, None, "US-1-A1")
    assert set(G.nodes()) == {"US-1-A1", "US-2-A1", "US-3-A1"}
    assert G.has_edge("US-1-A1", "US-2-A1")
    assert G.has_edge("US-2-A1", "US-3-A1")  # from row 2's citation and row 3's parent
    assert not G.has_node("US-9-A1")
    assert not G.has_edge("US-1-A1", "US-1-A1")


def test_build_citation_graph_includes_expanded_patents(results):
    expanded = pd.DataFrame(
        {"publication_number": ["US-9-A1"], "citation": [None], "cited_by": [_arr("US-1-A1")],
         "parent": [None], "child": [None]}
    )
    G = gr.build_citation_graph(results, expanded, "US-1-A1")
    assert G.has_edge("US-1-A1", "US-9-A1")
    assert G.edges["US-1-A1", "US-9-A1"]["edge_type"] in {"cites", "cited_by"}


def test_compute_ppr_returns_empty_without_edges():
    G = gr.build_citation_graph(
        pd.DataFrame({"publication_number": ["US-1-A1"], "citation": [None], "cited_by": [None],
                      "parent": [None], "child": [None]}), None, "US-1-A1")
    assert gr.compute_ppr(G, "US-1-A1") == {}


def test_compute_ppr_returns_empty_when_query_has_no_outgoing_edges():
    # Seen on real data: many patents cite only patents that are not in the
    # index, so the query node has in-edges but no out-edges. Personalized
    # PageRank then keeps all mass on the query (score 1.0) and every other
    # node gets floating-point residue, which the UI would show as 0.0%
    # "structurally important" patents. Treat that as "no PPR available".
    df = pd.DataFrame(
        {
            "publication_number": ["US-1-A1", "US-2-A1", "US-3-A1"],
            "citation": [_arr("US-99-A1"), _arr("US-1-A1"), _arr("US-2-A1")],
            "cited_by": [None, None, None],
            "parent": [None, None, None],
            "child": [None, None, None],
        }
    )
    G = gr.build_citation_graph(df, None, "US-1-A1")
    assert G.number_of_edges() == 2 and G.out_degree("US-1-A1") == 0
    assert gr.compute_ppr(G, "US-1-A1") == {}


def test_compute_ppr_seeds_from_query_patent(results):
    G = gr.build_citation_graph(results, None, "US-1-A1")
    scores = gr.compute_ppr(G, "US-1-A1")
    assert set(scores) == {"US-1-A1", "US-2-A1", "US-3-A1"}
    assert scores["US-1-A1"] == max(scores.values())
    assert abs(sum(scores.values()) - 1.0) < 1e-6


def test_normalize_scores_min_max_and_constant_case():
    assert gr.normalize_scores({"a": 1.0, "b": 3.0}) == {"a": 0.0, "b": 1.0}
    assert gr.normalize_scores({"a": 2.0, "b": 2.0}) == {"a": 1.0, "b": 1.0}
    assert gr.normalize_scores({}) == {}


def test_blend_scores_weights_cosine_and_normalized_ppr(results):
    out = gr.blend_scores(results, {"US-1-A1": 0.5, "US-2-A1": 0.3, "US-3-A1": 0.1})
    row = out.set_index("publication_number").loc["US-2-A1"]
    assert row["ppr_raw"] == 0.3
    assert row["ppr_score"] == pytest.approx(0.5)
    assert row["blended_score"] == pytest.approx(0.6 * 0.8 + 0.4 * 0.5)
    assert row["blended_pct"] == pytest.approx(100 * (0.6 * 0.8 + 0.4 * 0.5))


def test_get_citation_edges_filters_to_patent_set(results):
    G = gr.build_citation_graph(results, None, "US-1-A1")
    edges = gr.get_citation_edges(G, {"US-1-A1", "US-2-A1"})
    assert [(u, v) for u, v, _ in edges] == [("US-1-A1", "US-2-A1")]
    assert all(u != "US-3-A1" and v != "US-3-A1" for u, v, _ in edges)
