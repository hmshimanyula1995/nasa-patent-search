"""Tests for utils.charts with BigQuery-shaped numpy array cells."""
import numpy as np
import pandas as pd

from utils import charts


def _names(*names):
    return np.array([{"name": n} for n in names], dtype=object)


def _df():
    return pd.DataFrame(
        {
            "assignee_harmonized": [_names("ACME", "Globex"), _names("ACME"), None],
            "inventor_harmonized": [_names("Ada"), np.array([], dtype=object), _names("Ada", "Bob")],
            "cpc": [
                np.array([{"code": "G06F"}, {"code": "H04L"}], dtype=object),
                np.array([{"code": "g06n"}, {"code": "1234"}], dtype=object),
                None,
            ],
        }
    )


def test_assignee_chart_counts_names_from_numpy_arrays():
    fig = charts.create_assignee_chart(_df())
    bar = fig.data[0]
    assert dict(zip(bar.y, bar.x)) == {"ACME": 2, "Globex": 1}
    assert fig.layout.title.text == "Top Assignees"


def test_inventor_chart_respects_top_n():
    fig = charts.create_inventor_chart(_df(), top_n=1)
    assert list(fig.data[0].y) == ["Ada"]


def test_cpc_chart_groups_by_section_letter_and_skips_non_alpha():
    fig = charts.create_cpc_chart(_df())
    labels = list(fig.data[0].x)
    assert labels[0] == "G - Physics"
    assert list(fig.data[0].y) == [2, 1]
    assert all(not label.startswith("1") for label in labels)


def test_charts_render_placeholder_when_no_data():
    empty = pd.DataFrame({"assignee_harmonized": [None], "inventor_harmonized": [None], "cpc": [None]})
    for fn, msg in [
        (charts.create_assignee_chart, "No assignee data available"),
        (charts.create_inventor_chart, "No inventor data available"),
        (charts.create_cpc_chart, "No CPC data available"),
    ]:
        fig = fn(empty)
        assert fig.data == ()
        assert fig.layout.annotations[0].text == msg
