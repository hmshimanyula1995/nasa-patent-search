import os
import streamlit as st
import pandas as pd
from google.cloud import bigquery


PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", "grad-589-588")
DATASET = os.getenv("BIGQUERY_DATASET", "patent_research")
TABLE = os.getenv("BIGQUERY_TABLE", "us_patents_indexed")

FULL_TABLE = f"`{PROJECT}.{DATASET}.{TABLE}`"

VECTOR_SEARCH_QUERY = f"""
SELECT
    base.publication_number,
    base.application_number,
    base.title,
    base.abstract,
    base.primary_assignee,
    base.primary_inventor,
    base.assignee_harmonized,
    base.inventor_harmonized,
    base.filing_date,
    base.publication_date,
    base.grant_date,
    base.cited_by,
    base.citation,
    base.parent,
    base.child,
    base.cpc,
    base.top_terms,
    distance
FROM VECTOR_SEARCH(
    TABLE {FULL_TABLE},
    'embedding_v1',
    (
        SELECT embedding_v1
        FROM {FULL_TABLE}
        WHERE publication_number = @patent_number
    ),
    top_k => @top_k,
    distance_type => 'COSINE'
)
ORDER BY distance
"""

CITATION_EXPANSION_QUERY = f"""
SELECT
    publication_number, title, abstract,
    primary_assignee, primary_inventor,
    assignee_harmonized, inventor_harmonized,
    citation, cited_by, parent, child,
    cpc, filing_date, publication_date, grant_date, top_terms
FROM {FULL_TABLE}
WHERE publication_number IN UNNEST(@neighbor_ids)
"""


def format_date(date_int) -> str:
    if not date_int or pd.isna(date_int):
        return "N/A"
    s = str(int(date_int))
    if len(s) == 8:
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return s


def extract_struct_value(val) -> str:
    if isinstance(val, dict):
        return val.get("value", "")
    if val is None:
        return ""
    return str(val)


@st.cache_resource
def _get_client() -> bigquery.Client:
    return bigquery.Client(project=PROJECT)


@st.cache_data(ttl=3600, show_spinner=False)
def search_patents(patent_number: str, top_k: int = 20) -> pd.DataFrame:
    client = _get_client()

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("patent_number", "STRING", patent_number),
            bigquery.ScalarQueryParameter("top_k", "INT64", top_k),
        ]
    )

    df = client.query(VECTOR_SEARCH_QUERY, job_config=job_config).to_dataframe()

    if df.empty:
        return df

    df["title_text"] = df["title"].apply(extract_struct_value)
    df["abstract_text"] = df["abstract"].apply(extract_struct_value)

    df["filed"] = df["filing_date"].apply(format_date)
    df["published"] = df["publication_date"].apply(format_date)
    df["granted"] = df["grant_date"].apply(format_date)

    df["similarity"] = 1 - df["distance"]
    df["similarity_pct"] = (df["similarity"] * 100).clip(0, 100)

    return df


def extract_citation_neighbors(
    results_df: pd.DataFrame,
    max_neighbors: int = 500,
) -> list[str]:
    """Extract unique patent IDs from citation arrays not already in results.

    Iterates citation/cited_by/parent/child arrays from all result rows,
    collects unique publication_numbers not in the results set, and caps
    at max_neighbors to avoid oversized queries.
    """
    existing = set(results_df["publication_number"].tolist())
    neighbors: set[str] = set()

    for _, row in results_df.iterrows():
        for col in ("citation", "cited_by", "parent", "child"):
            raw = row.get(col)
            if raw is None:
                continue
            items = raw if isinstance(raw, list) else []
            for item in items:
                pub = ""
                if isinstance(item, dict):
                    pub = item.get("publication_number", "")
                elif isinstance(item, str):
                    pub = item
                if pub and pub not in existing:
                    neighbors.add(pub)
                    if len(neighbors) >= max_neighbors:
                        return list(neighbors)

    return list(neighbors)


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_citation_neighbors(neighbor_ids: tuple[str, ...]) -> pd.DataFrame:
    """Fetch patent metadata for citation-expanded neighbors from BigQuery.

    Args:
        neighbor_ids: Tuple of publication_number strings (tuple for hashability).

    Returns:
        DataFrame with patent metadata. No similarity/distance columns.
        Empty DataFrame on failure.
    """
    if not neighbor_ids:
        return pd.DataFrame()

    client = _get_client()

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ArrayQueryParameter("neighbor_ids", "STRING", list(neighbor_ids)),
        ]
    )

    try:
        df = client.query(CITATION_EXPANSION_QUERY, job_config=job_config).to_dataframe()
    except Exception:
        return pd.DataFrame()

    if df.empty:
        return df

    df["title_text"] = df["title"].apply(extract_struct_value)
    df["abstract_text"] = df["abstract"].apply(extract_struct_value)
    df["filed"] = df["filing_date"].apply(format_date)
    df["published"] = df["publication_date"].apply(format_date)
    df["granted"] = df["grant_date"].apply(format_date)

    return df
