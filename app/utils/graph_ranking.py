"""Personalized PageRank graph ranking for patent citation networks.

Builds a directed citation graph from search results + expanded neighbors,
computes Personalized PageRank seeded from the query patent, and blends
PPR scores with cosine similarity for a combined ranking signal.
"""

import logging

import networkx as nx
import pandas as pd

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _extract_pub_numbers(array_field: list | None) -> list[str]:
    """Extract publication_number strings from BQ struct arrays."""
    if array_field is None:
        return []
    if not isinstance(array_field, list):
        try:
            array_field = list(array_field)
        except (TypeError, ValueError):
            return []
    pubs: list[str] = []
    for item in array_field:
        if isinstance(item, dict):
            pub = item.get("publication_number", "")
            if pub:
                pubs.append(pub)
        elif isinstance(item, str) and item:
            pubs.append(item)
    return pubs


def build_citation_graph(
    results_df: pd.DataFrame,
    expanded_df: pd.DataFrame | None,
    query_patent: str,
) -> nx.DiGraph:
    """Build a directed citation graph from results + expanded patents.

    Nodes = all patents in results_df + expanded_df.
    Edges = citation/cited_by/parent/child relationships where BOTH
    endpoints exist in the node set. Self-citations are excluded.
    """
    G = nx.DiGraph()

    # Collect all patent rows
    all_dfs = [results_df]
    if expanded_df is not None and not expanded_df.empty:
        all_dfs.append(expanded_df)
    combined = pd.concat(all_dfs, ignore_index=True)

    node_set = set(combined["publication_number"].tolist())
    node_set.add(query_patent)

    # Add all nodes
    for pub in node_set:
        G.add_node(pub)

    # Add directed edges from citation arrays
    for _, row in combined.iterrows():
        pub = row["publication_number"]

        # This patent cites others -> edge from pub to cited
        for cited in _extract_pub_numbers(row.get("citation")):
            if cited in node_set and cited != pub:
                G.add_edge(pub, cited, edge_type="cites")

        # This patent is cited by others -> edge from citing to pub
        for citing in _extract_pub_numbers(row.get("cited_by")):
            if citing in node_set and citing != pub:
                G.add_edge(citing, pub, edge_type="cited_by")

        # Parent -> child relationship
        for parent in _extract_pub_numbers(row.get("parent")):
            if parent in node_set and parent != pub:
                G.add_edge(parent, pub, edge_type="parent")

        for child in _extract_pub_numbers(row.get("child")):
            if child in node_set and child != pub:
                G.add_edge(pub, child, edge_type="child")

    logger.info(
        "Citation graph built: %d nodes, %d edges",
        G.number_of_nodes(), G.number_of_edges(),
    )
    return G


def compute_ppr(
    G: nx.DiGraph,
    query_patent: str,
    alpha: float = 0.85,
) -> dict[str, float]:
    """Compute Personalized PageRank seeded from the query patent.

    Args:
        G: Citation graph.
        query_patent: Patent to seed teleport probability from.
        alpha: Damping factor (0.85 = 15% teleport back to query).

    Returns:
        Dict mapping patent -> raw PPR score. Empty if graph has no edges.
    """
    if G.number_of_edges() == 0:
        logger.info("PPR skipped: graph has no edges")
        return {}

    if query_patent not in G:
        G.add_node(query_patent)

    personalization = {node: 0.0 for node in G.nodes()}
    personalization[query_patent] = 1.0

    try:
        scores = nx.pagerank(
            G,
            alpha=alpha,
            personalization=personalization,
            max_iter=100,
            tol=1e-06,
        )
        top_3 = sorted(scores.items(), key=lambda x: -x[1])[:3]
        logger.info(
            "PPR computed: %d scores, top 3: %s",
            len(scores),
            [(pub, f"{s:.6f}") for pub, s in top_3],
        )
        return scores
    except nx.PowerIterationFailedConvergence:
        logger.warning("PPR failed to converge after 100 iterations")
        return {}


def normalize_scores(scores: dict[str, float]) -> dict[str, float]:
    """Min-max normalize scores to [0, 1] range.

    If all scores are equal, returns all 1.0.
    """
    if not scores:
        return {}

    values = list(scores.values())
    min_val = min(values)
    max_val = max(values)

    if max_val == min_val:
        return {k: 1.0 for k in scores}

    spread = max_val - min_val
    return {k: (v - min_val) / spread for k, v in scores.items()}


def blend_scores(
    results_df: pd.DataFrame,
    ppr_scores: dict[str, float],
    alpha: float = 0.6,
) -> pd.DataFrame:
    """Blend cosine similarity with PPR scores.

    blended = alpha * cosine_similarity + (1 - alpha) * ppr_normalized

    Adds columns: ppr_raw, ppr_score, ppr_pct, blended_score, blended_pct.
    """
    df = results_df.copy()

    normalized = normalize_scores(ppr_scores)

    df["ppr_raw"] = df["publication_number"].map(
        lambda pn: ppr_scores.get(pn, 0.0)
    )
    df["ppr_score"] = df["publication_number"].map(
        lambda pn: normalized.get(pn, 0.0)
    )
    df["ppr_pct"] = (df["ppr_score"] * 100).clip(0, 100)

    cosine = df["similarity"].fillna(0.0)
    ppr = df["ppr_score"].fillna(0.0)
    df["blended_score"] = alpha * cosine + (1 - alpha) * ppr
    df["blended_pct"] = (df["blended_score"] * 100).clip(0, 100)

    return df


def get_citation_edges(
    G: nx.DiGraph,
    patent_set: set[str],
) -> list[tuple[str, str, str]]:
    """Extract (source, target, edge_type) tuples for patents in the set.

    Only returns edges where both endpoints are in patent_set.
    Used to feed citation context into Gemini prompts.
    """
    edges: list[tuple[str, str, str]] = []
    for u, v, data in G.edges(data=True):
        if u in patent_set and v in patent_set:
            edge_type = data.get("edge_type", "cites")
            edges.append((u, v, edge_type))
    return edges
