from collections import Counter
import pandas as pd
import plotly.graph_objects as go


COLORS = [
    "#00D4FF", "#7C3AED", "#10B981", "#F59E0B", "#EF4444",
    "#EC4899", "#8B5CF6", "#06B6D4", "#84CC16", "#F97316",
]

GRID = "rgba(255,255,255,0.04)"
ZEROLINE = "rgba(255,255,255,0.06)"

DARK_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#E4E4E7", family="Inter, system-ui, sans-serif", size=12),
    margin=dict(l=10, r=10, t=40, b=10),
    hoverlabel=dict(
        bgcolor="#1E1E2E",
        font_size=12,
        font_family="Inter",
        bordercolor="rgba(255,255,255,0.1)",
    ),
    legend=dict(
        bgcolor="rgba(0,0,0,0)",
        font=dict(size=11),
    ),
)

CPC_LABELS = {
    "A": "Human Necessities",
    "B": "Operations / Transport",
    "C": "Chemistry / Metallurgy",
    "D": "Textiles / Paper",
    "E": "Fixed Constructions",
    "F": "Mechanical Engineering",
    "G": "Physics",
    "H": "Electricity",
    "Y": "Emerging Tech",
}


def _to_list(val) -> list:
    if val is None:
        return []
    if isinstance(val, list):
        return val
    try:
        return list(val)
    except (TypeError, ValueError):
        return []


def _extract_names(results_df: pd.DataFrame, column: str) -> list[str]:
    names = []
    for _, row in results_df.iterrows():
        items = _to_list(row.get(column))
        for item in items:
            if isinstance(item, dict):
                name = item.get("name", "")
                if name:
                    names.append(name)
    return names


def create_assignee_chart(results_df: pd.DataFrame, top_n: int = 10) -> go.Figure:
    names = _extract_names(results_df, "assignee_harmonized")
    counts = Counter(names).most_common(top_n)

    if not counts:
        return _empty_chart("No assignee data available")

    labels, values = zip(*reversed(counts))

    fig = go.Figure(go.Bar(
        x=list(values),
        y=list(labels),
        orientation="h",
        marker=dict(
            color=list(values),
            colorscale=[[0, "#0066FF"], [1, "#00D4FF"]],
            line=dict(width=0),
            cornerradius=4,
        ),
        hovertemplate="<b>%{y}</b><br>Patents: %{x}<extra></extra>",
    ))

    fig.update_layout(
        **DARK_LAYOUT,
        title=dict(text="Top Assignees", font=dict(size=14, color="#FAFAFA")),
        height=350,
        yaxis=dict(gridcolor=GRID, zerolinecolor=ZEROLINE, tickfont=dict(size=11)),
        xaxis=dict(gridcolor=GRID, zerolinecolor=ZEROLINE, title="Patent Count"),
    )
    return fig


def create_inventor_chart(results_df: pd.DataFrame, top_n: int = 10) -> go.Figure:
    names = _extract_names(results_df, "inventor_harmonized")
    counts = Counter(names).most_common(top_n)

    if not counts:
        return _empty_chart("No inventor data available")

    labels, values = zip(*reversed(counts))

    fig = go.Figure(go.Bar(
        x=list(values),
        y=list(labels),
        orientation="h",
        marker=dict(
            color=list(values),
            colorscale=[[0, "#7C3AED"], [1, "#C084FC"]],
            line=dict(width=0),
            cornerradius=4,
        ),
        hovertemplate="<b>%{y}</b><br>Patents: %{x}<extra></extra>",
    ))

    fig.update_layout(
        **DARK_LAYOUT,
        title=dict(text="Top Inventors", font=dict(size=14, color="#FAFAFA")),
        height=350,
        yaxis=dict(gridcolor=GRID, zerolinecolor=ZEROLINE, tickfont=dict(size=11)),
        xaxis=dict(gridcolor=GRID, zerolinecolor=ZEROLINE, title="Patent Count"),
    )
    return fig


def create_cpc_chart(results_df: pd.DataFrame) -> go.Figure:
    letters = []
    for _, row in results_df.iterrows():
        cpc = _to_list(row.get("cpc"))
        for entry in cpc:
            if isinstance(entry, dict):
                code = entry.get("code", "")
                if code and code[0].isalpha():
                    letters.append(code[0].upper())

    counts = Counter(letters).most_common()

    if not counts:
        return _empty_chart("No CPC data available")

    labels = [f"{l} - {CPC_LABELS.get(l, l)}" for l, _ in counts]
    values = [v for _, v in counts]
    bar_colors = [COLORS[i % len(COLORS)] for i in range(len(counts))]

    fig = go.Figure(go.Bar(
        x=labels,
        y=values,
        marker=dict(color=bar_colors, line=dict(width=0), cornerradius=4),
        hovertemplate="<b>%{x}</b><br>Count: %{y}<extra></extra>",
    ))

    fig.update_layout(
        **DARK_LAYOUT,
        title=dict(text="Technology Distribution (CPC)", font=dict(size=14, color="#FAFAFA")),
        height=350,
        xaxis=dict(gridcolor=GRID, zerolinecolor=ZEROLINE, tickangle=-30, tickfont=dict(size=10)),
        yaxis=dict(gridcolor=GRID, zerolinecolor=ZEROLINE, title="Count"),
    )
    return fig


def _empty_chart(message: str) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        **DARK_LAYOUT,
        height=350,
        annotations=[dict(
            text=message,
            xref="paper", yref="paper",
            x=0.5, y=0.5,
            showarrow=False,
            font=dict(size=14, color="#71717A"),
        )],
    )
    return fig
