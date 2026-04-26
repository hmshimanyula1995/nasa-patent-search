import os
import tempfile
import pandas as pd
from pyvis.network import Network


EDGE_COLORS = {
    "similar": "#105BD8",
    "cites": "#4773AA",
    "cited_by": "#8BA6CA",
    "parent": "#FF9D1E",
    "child": "#DD361C",
}

PHYSICS_OPTIONS = """{
    "physics": {
        "forceAtlas2Based": {
            "gravitationalConstant": -120,
            "springLength": 200,
            "springConstant": 0.01,
            "damping": 0.4
        },
        "solver": "forceAtlas2Based",
        "stabilization": {"iterations": 80}
    },
    "interaction": {
        "hover": true,
        "tooltipDelay": 150,
        "zoomView": true,
        "dragView": true
    },
    "edges": {
        "smooth": {"type": "continuous"},
        "width": 1.5
    }
}"""


def _to_list(val) -> list:
    if val is None:
        return []
    if isinstance(val, list):
        return val
    try:
        return list(val)
    except (TypeError, ValueError):
        return []


def _score_color(score: float) -> str:
    """6-tier accessible color gradient for patent relevance scores.

    Uses colors that avoid pure red-green adjacency for color-blind users.
    Score is expected in [0, 1] range.
    """
    pct = score * 100
    if pct >= 95:
        return "#1a7431"  # Dark green – highest
    if pct >= 90:
        return "#2E8540"  # Green – high
    if pct >= 85:
        return "#4A90D9"  # Baby blue – good
    if pct >= 80:
        return "#F0C419"  # Yellow – moderate
    if pct >= 75:
        return "#FF9D1E"  # Orange – lower
    return "#DD361C"      # Red – low


def build_network_html(
    results_df: pd.DataFrame,
    query_patent: str,
    score_column: str = "similarity",
    expanded_df: pd.DataFrame | None = None,
    expanded_score_column: str = "ppr_score",
) -> str:
    """Build an interactive network graph with accessible 3-channel scoring.

    Args:
        results_df: Search results with score columns.
        query_patent: The query patent publication number.
        score_column: Column in results_df to drive color/size (default: similarity).
        expanded_df: Citation-expanded patents (rendered as triangles).
        expanded_score_column: Score column for expanded patents.
    """
    net = Network(
        height="550px",
        width="100%",
        bgcolor="#F6F8FC",
        font_color="#323A45",
        directed=True,
        select_menu=False,
        filter_menu=False,
    )
    net.set_options(PHYSICS_OPTIONS)

    # Track all node IDs for edge filtering
    result_pubs = set(results_df["publication_number"].tolist())
    expanded_pubs: set[str] = set()
    if expanded_df is not None and not expanded_df.empty:
        expanded_pubs = set(expanded_df["publication_number"].tolist())
    all_pubs = result_pubs | expanded_pubs

    # Query patent node
    query_row = results_df[results_df["publication_number"] == query_patent]
    query_title = ""
    if not query_row.empty:
        query_title = query_row.iloc[0].get("title_text", "")

    net.add_node(
        query_patent,
        label=query_patent,
        title=f"QUERY: {query_patent}\n{query_title}",
        color={"background": "#0B3D91", "border": "#061F4A"},
        size=45,
        font={"size": 12, "color": "#212121"},
        shape="dot",
        borderWidth=3,
    )

    # Result patent nodes — 3 accessibility channels: color + size + numeric label
    for _, row in results_df.iterrows():
        pub = row["publication_number"]
        if pub == query_patent:
            continue

        score = row.get(score_column, row.get("similarity", 0))
        score = max(0.0, min(1.0, float(score))) if pd.notna(score) else 0.0
        score_pct = int(score * 100)

        title_text = row.get("title_text", "")
        assignee = row.get("primary_assignee", "N/A")
        node_color = _score_color(score)
        node_size = 18 + int(score * 32)

        net.add_node(
            pub,
            label=f"{pub}\n{score_pct}%",
            title=f"{pub}\n{title_text}\nAssignee: {assignee}\nScore: {score_pct}%",
            color={"background": node_color, "border": "#DCE4EF"},
            size=node_size,
            font={"size": 10, "color": "#5B616B"},
            shape="dot",
            borderWidth=1,
        )

        net.add_edge(
            query_patent,
            pub,
            color={"color": EDGE_COLORS["similar"], "opacity": 0.4},
            width=1 + score * 2,
            title=f"Score: {score_pct}%",
        )

    # Expanded patent nodes — triangles to distinguish from search results
    if expanded_df is not None and not expanded_df.empty:
        for _, row in expanded_df.iterrows():
            pub = row["publication_number"]
            if pub == query_patent or pub in result_pubs:
                continue

            score = row.get(expanded_score_column, 0)
            score = max(0.0, min(1.0, float(score))) if pd.notna(score) else 0.0
            score_pct = int(score * 100)

            title_text = row.get("title_text", "")
            assignee = row.get("primary_assignee", "N/A")
            node_color = _score_color(score)
            node_size = 18 + int(score * 32)

            net.add_node(
                pub,
                label=f"{pub}\n{score_pct}%",
                title=(
                    f"{pub} (Citation Network)\n{title_text}"
                    f"\nAssignee: {assignee}\nPPR: {score_pct}%"
                ),
                color={"background": node_color, "border": "#DCE4EF"},
                size=node_size,
                font={"size": 9, "color": "#5B616B"},
                shape="triangle",
                borderWidth=1,
            )

    # Citation edges — iterate all DataFrames
    all_dfs = [results_df]
    if expanded_df is not None and not expanded_df.empty:
        all_dfs.append(expanded_df)

    for source_df in all_dfs:
        for _, row in source_df.iterrows():
            pub = row["publication_number"]

            citations = _to_list(row.get("citation"))
            if citations:
                for cite in citations[:10]:
                    if isinstance(cite, dict):
                        cited_pub = cite.get("publication_number", "")
                        if cited_pub and cited_pub in all_pubs and cited_pub != pub:
                            net.add_edge(
                                pub, cited_pub,
                                color={"color": EDGE_COLORS["cites"], "opacity": 0.3},
                                width=1,
                                title="Cites",
                                dashes=True,
                            )

            cited_by = _to_list(row.get("cited_by"))
            if cited_by:
                for cite in cited_by[:10]:
                    if isinstance(cite, dict):
                        citing_pub = cite.get("publication_number", "")
                        if citing_pub and citing_pub in all_pubs and citing_pub != pub:
                            net.add_edge(
                                citing_pub, pub,
                                color={"color": EDGE_COLORS["cited_by"], "opacity": 0.3},
                                width=1,
                                title="Cited by",
                                dashes=True,
                            )

            parents = _to_list(row.get("parent"))
            if parents:
                for parent in parents[:5]:
                    if isinstance(parent, dict):
                        parent_pub = parent.get("publication_number", "")
                        if parent_pub and parent_pub in all_pubs and parent_pub != pub:
                            net.add_edge(
                                parent_pub, pub,
                                color={"color": EDGE_COLORS["parent"], "opacity": 0.4},
                                width=1.5,
                                title="Parent",
                            )

            children = _to_list(row.get("child"))
            if children:
                for child in children[:5]:
                    if isinstance(child, dict):
                        child_pub = child.get("publication_number", "")
                        if child_pub and child_pub in all_pubs and child_pub != pub:
                            net.add_edge(
                                pub, child_pub,
                                color={"color": EDGE_COLORS["child"], "opacity": 0.4},
                                width=1.5,
                                title="Child",
                            )

    # Per-render unique tempfile so concurrent Streamlit sessions on the same
    # Cloud Run instance do not overwrite or unlink each other's graph file.
    fd, path = tempfile.mkstemp(prefix="patent_graph_", suffix=".html")
    os.close(fd)
    try:
        net.save_graph(path)
        with open(path, "r") as f:
            html = f.read()
    finally:
        if os.path.exists(path):
            os.unlink(path)

    return html
