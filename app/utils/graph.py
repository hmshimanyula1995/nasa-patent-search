import os
import tempfile
import pandas as pd
from pyvis.network import Network


EDGE_COLORS = {
    "similar": "#00D4FF",
    "cites": "#3B82F6",
    "cited_by": "#60A5FA",
    "parent": "#F59E0B",
    "child": "#EF4444",
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


def _similarity_color(similarity: float) -> str:
    if similarity >= 0.8:
        return "#10B981"
    if similarity >= 0.6:
        return "#84CC16"
    if similarity >= 0.4:
        return "#F59E0B"
    return "#71717A"


def build_network_html(results_df: pd.DataFrame, query_patent: str) -> str:
    net = Network(
        height="550px",
        width="100%",
        bgcolor="#0E1117",
        font_color="#E4E4E7",
        directed=True,
        select_menu=False,
        filter_menu=False,
    )
    net.set_options(PHYSICS_OPTIONS)

    result_pubs = set(results_df["publication_number"].tolist())

    query_row = results_df[results_df["publication_number"] == query_patent]
    query_title = ""
    if not query_row.empty:
        query_title = query_row.iloc[0].get("title_text", "")

    net.add_node(
        query_patent,
        label=query_patent,
        title=f"QUERY: {query_patent}\n{query_title}",
        color={"background": "#00D4FF", "border": "#0066FF"},
        size=45,
        font={"size": 12, "color": "#FAFAFA"},
        shape="dot",
        borderWidth=3,
    )

    for _, row in results_df.iterrows():
        pub = row["publication_number"]
        if pub == query_patent:
            continue

        similarity = row.get("similarity", 0)
        title = row.get("title_text", "")
        assignee = row.get("primary_assignee", "N/A")
        node_color = _similarity_color(similarity)
        node_size = 15 + int(max(0, similarity) * 25)

        net.add_node(
            pub,
            label=pub,
            title=f"{pub}\n{title}\nAssignee: {assignee}\nSimilarity: {similarity:.1%}",
            color={"background": node_color, "border": "rgba(255,255,255,0.15)"},
            size=node_size,
            font={"size": 10, "color": "#A1A1AA"},
            shape="dot",
            borderWidth=1,
        )

        net.add_edge(
            query_patent,
            pub,
            color={"color": EDGE_COLORS["similar"], "opacity": 0.4},
            width=1 + similarity * 2,
            title=f"Similarity: {similarity:.1%}",
        )

    for _, row in results_df.iterrows():
        pub = row["publication_number"]

        citations = _to_list(row.get("citation"))
        if citations:
            for cite in citations[:10]:
                if isinstance(cite, dict):
                    cited_pub = cite.get("publication_number", "")
                    if cited_pub and cited_pub in result_pubs and cited_pub != pub:
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
                    if citing_pub and citing_pub in result_pubs and citing_pub != pub:
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
                    if parent_pub and parent_pub in result_pubs and parent_pub != pub:
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
                    if child_pub and child_pub in result_pubs and child_pub != pub:
                        net.add_edge(
                            pub, child_pub,
                            color={"color": EDGE_COLORS["child"], "opacity": 0.4},
                            width=1.5,
                            title="Child",
                        )

    path = os.path.join(tempfile.gettempdir(), "patent_graph.html")
    net.save_graph(path)
    with open(path, "r") as f:
        html = f.read()
    os.unlink(path)

    return html
