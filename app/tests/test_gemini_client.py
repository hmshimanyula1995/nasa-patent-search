"""Tests for utils.gemini_client against a fake Google Gen AI client.

The real client is never constructed: google.genai.Client is replaced for the
duration of each test, and the Streamlit resource cache is cleared so the fake
from one test cannot leak into the next.
"""
import logging

import pandas as pd
import pytest

from utils import gemini_client as gc


class _Chunk:
    def __init__(self, text):
        self.text = text


class _FakeModels:
    def __init__(self, chunks, error=None):
        self.chunks = chunks
        self.error = error
        self.calls = []

    def generate_content_stream(self, *, model, contents):
        self.calls.append(("stream", model, contents))
        if self.error:
            raise self.error
        return iter(self.chunks)

    def generate_content(self, *, model, contents):
        self.calls.append(("sync", model, contents))
        if self.error:
            raise self.error
        return _Chunk("".join(c.text or "" for c in self.chunks))


class _FakeClient:
    instances: list = []
    chunks: list = []
    error = None

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.models = _FakeModels(self.chunks, self.error)
        _FakeClient.instances.append(self)


@pytest.fixture
def fake_genai(monkeypatch):
    _FakeClient.instances = []
    _FakeClient.chunks = [_Chunk("Hello"), _Chunk(None), _Chunk(""), _Chunk(" world")]
    _FakeClient.error = None
    monkeypatch.setattr("google.genai.Client", _FakeClient)
    gc._get_client.clear()
    gc.generate_summary.clear()
    yield _FakeClient
    gc._get_client.clear()
    gc.generate_summary.clear()


def _stream(**overrides):
    kwargs = dict(query_pub="US-1-A1", query_title="T", query_abstract="A", results_json="RESULTS")
    kwargs.update(overrides)
    return list(gc.stream_summary(**kwargs))


def test_stream_summary_targets_vertex_ai_with_configured_project_and_region(fake_genai):
    _stream()
    assert len(fake_genai.instances) == 1
    assert fake_genai.instances[0].kwargs == {
        "enterprise": True, "project": "test-project", "location": "test-region",
    }


def test_stream_summary_yields_only_non_empty_chunks(fake_genai):
    assert _stream() == ["Hello", " world"]


def test_stream_summary_sends_configured_model_and_rendered_prompt(fake_genai):
    _stream(results_json="THE RESULTS")
    kind, model, contents = fake_genai.instances[0].models.calls[0]
    assert kind == "stream"
    assert model == "gemini-test-model"
    assert "US-1-A1" in contents and "THE RESULTS" in contents


def test_stream_summary_uses_supplied_prompt_template(fake_genai):
    _stream(prompt_template="custom {query_pub} {results_json}")
    _, _, contents = fake_genai.instances[0].models.calls[0]
    assert contents == "custom US-1-A1 RESULTS"


def test_stream_summary_reuses_one_client_across_calls(fake_genai):
    _stream()
    _stream()
    assert len(fake_genai.instances) == 1


def test_stream_summary_hides_raw_error_and_logs_it(fake_genai, caplog):
    fake_genai.error = RuntimeError("403 permission denied on projects/secret")
    with caplog.at_level(logging.ERROR, logger="utils.gemini_client"):
        chunks = _stream()
    assert chunks == [gc.SUMMARY_UNAVAILABLE_MESSAGE]
    assert "projects/secret" not in chunks[0]
    assert "projects/secret" in caplog.text


def test_stream_summary_hides_client_construction_error(fake_genai, monkeypatch):
    def _boom(**kwargs):
        raise RuntimeError("could not load credentials for projects/secret")
    monkeypatch.setattr("google.genai.Client", _boom)
    assert _stream() == [gc.SUMMARY_UNAVAILABLE_MESSAGE]


def test_stream_summary_reports_unavailable_when_gemini_returns_no_text(fake_genai, caplog):
    # A safety-blocked or empty response has candidates without text parts:
    # google-genai returns None from .text instead of raising.
    fake_genai.chunks = [_Chunk(None), _Chunk("")]
    with caplog.at_level(logging.WARNING, logger="utils.gemini_client"):
        chunks = _stream()
    assert chunks == [gc.SUMMARY_UNAVAILABLE_MESSAGE]
    assert "no text" in caplog.text.lower()


def test_generate_summary_reports_unavailable_when_gemini_returns_no_text(fake_genai):
    fake_genai.chunks = [_Chunk(None)]
    assert gc.generate_summary("US-1-A1", "T", "A", "R") == gc.SUMMARY_UNAVAILABLE_MESSAGE


def test_generate_summary_returns_full_text(fake_genai):
    assert gc.generate_summary("US-1-A1", "T", "A", "R") == "Hello world"
    assert fake_genai.instances[0].models.calls[0][0] == "sync"


def test_generate_summary_hides_raw_error(fake_genai):
    fake_genai.error = RuntimeError("quota exceeded for projects/secret")
    assert gc.generate_summary("US-1-A1", "T", "A", "R") == gc.SUMMARY_UNAVAILABLE_MESSAGE


def _results_df():
    return pd.DataFrame(
        {
            "publication_number": ["US-1-A1", "US-2-A1", "US-3-A1"],
            "title_text": ["One", "Two", "Three"],
            "abstract_text": ["a" * 600, "b", "c"],
            "primary_assignee": ["ACME", "ACME", "N/A"],
            "similarity": [0.9, 0.8, 0.7],
            "blended_score": [0.85, 0.75, 0.6],
        }
    )


def test_build_results_text_truncates_abstract_and_formats_similarity():
    text = gc.build_results_text(_results_df())
    assert "Result 1: US-1-A1" in text
    assert "a" * 500 in text and "a" * 501 not in text
    assert "Similarity: 90.00%" in text


def test_build_results_text_with_graph_lists_edges_and_shared_assignees():
    text = gc.build_results_text_with_graph(
        _results_df(),
        ppr_scores={"US-1-A1": 0.5, "US-2-A1": 0.25, "US-99-A1": 0.1},
        citation_edges=[("US-1-A1", "US-2-A1", "cites"), ("US-1-A1", "US-77-A1", "cites")],
        expanded_df=pd.DataFrame({"publication_number": ["US-99-A1"], "title_text": ["Ninety-nine"]}),
    )
    assert "US-1-A1 --[cites]--> US-2-A1" in text
    assert "US-77-A1" not in text
    assert "ACME: 2 patents" in text
    assert "US-99-A1: Ninety-nine (PPR: 0.1000)" in text
    assert "Graph Importance (PPR): 0.5000" in text
