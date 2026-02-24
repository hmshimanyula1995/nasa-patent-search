import logging
import os
import re
import time

import pandas as pd
import streamlit as st
from google.cloud import bigquery

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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


_PUB_NUMBER_RE = re.compile(r"^[A-Z]{2}-\d+-[A-Z]\d$")

NORMALIZE_QUERY = f"""
SELECT publication_number
FROM {FULL_TABLE}
WHERE publication_number IN (
    CONCAT('US-', @number, '-B1'),
    CONCAT('US-', @number, '-B2'),
    CONCAT('US-', @number, '-A1')
)
LIMIT 1
"""

NORMALIZE_LIKE_QUERY = f"""
SELECT publication_number
FROM {FULL_TABLE}
WHERE publication_number LIKE CONCAT('US-', @number, '%')
LIMIT 1
"""

NORMALIZE_APP_QUERY = f"""
SELECT publication_number
FROM {FULL_TABLE}
WHERE application_number = @number
LIMIT 1
"""


def normalize_patent_number(raw_input: str) -> str | None:
    """Convert user input to the publication_number format used in BigQuery.

    Accepts:
      - Full format: US-8410469-B2 (returned as-is)
      - Plain grant number: 8410469 or 8,410,469
      - Prefixed: US8410469

    Returns the matched publication_number or None if not found.
    """
    cleaned = raw_input.strip().replace(",", "").replace(" ", "")
    if not cleaned:
        return None

    # Already in publication_number format (e.g., US-8410469-B2)
    if _PUB_NUMBER_RE.match(cleaned):
        logger.info("Input '%s' already in publication_number format", cleaned)
        return cleaned

    # Strip leading "US" prefix if present (e.g., US8410469 -> 8410469)
    number = re.sub(r"^US", "", cleaned, flags=re.IGNORECASE)

    # Must be numeric at this point
    if not number.isdigit():
        logger.warning("Input '%s' is not a valid patent number after cleaning", raw_input)
        return None

    logger.info("Normalizing plain number '%s' — looking up in BigQuery", number)
    client = _get_client()

    # Step 1: Try exact match with common suffixes (B1, B2, A1)
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("number", "STRING", number),
        ]
    )
    t0 = time.time()
    rows = list(client.query(NORMALIZE_QUERY, job_config=job_config).result())
    elapsed = time.time() - t0

    if rows:
        pub = rows[0]["publication_number"]
        logger.info("Resolved '%s' -> '%s' via exact suffix match (%.2fs)", number, pub, elapsed)
        return pub

    # Step 2: Try LIKE pattern (catches unusual suffixes)
    t0 = time.time()
    rows = list(client.query(NORMALIZE_LIKE_QUERY, job_config=job_config).result())
    elapsed = time.time() - t0

    if rows:
        pub = rows[0]["publication_number"]
        logger.info("Resolved '%s' -> '%s' via LIKE match (%.2fs)", number, pub, elapsed)
        return pub

    # Step 3: Try application_number lookup
    t0 = time.time()
    rows = list(client.query(NORMALIZE_APP_QUERY, job_config=job_config).result())
    elapsed = time.time() - t0

    if rows:
        pub = rows[0]["publication_number"]
        logger.info("Resolved '%s' -> '%s' via application_number (%.2fs)", number, pub, elapsed)
        return pub

    logger.warning("Could not resolve '%s' to any publication_number", number)
    return None


@st.cache_data(ttl=3600, show_spinner=False)
def search_patents(patent_number: str, top_k: int = 20) -> pd.DataFrame:
    logger.info("search_patents called: patent_number='%s', top_k=%d", patent_number, top_k)
    client = _get_client()

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("patent_number", "STRING", patent_number),
            bigquery.ScalarQueryParameter("top_k", "INT64", top_k),
        ]
    )

    t0 = time.time()
    df = client.query(VECTOR_SEARCH_QUERY, job_config=job_config).to_dataframe()
    elapsed = time.time() - t0
    logger.info("Vector search completed: %d rows in %.2fs", len(df), elapsed)

    if df.empty:
        logger.warning("No results for patent_number='%s'", patent_number)
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

    logger.info("Fetching %d citation neighbors", len(neighbor_ids))
    client = _get_client()

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ArrayQueryParameter("neighbor_ids", "STRING", list(neighbor_ids)),
        ]
    )

    try:
        t0 = time.time()
        df = client.query(CITATION_EXPANSION_QUERY, job_config=job_config).to_dataframe()
        elapsed = time.time() - t0
        logger.info("Citation neighbor fetch: %d rows in %.2fs", len(df), elapsed)
    except Exception as exc:
        logger.error("Citation neighbor fetch failed: %s", exc)
        return pd.DataFrame()

    if df.empty:
        return df

    df["title_text"] = df["title"].apply(extract_struct_value)
    df["abstract_text"] = df["abstract"].apply(extract_struct_value)
    df["filed"] = df["filing_date"].apply(format_date)
    df["published"] = df["publication_date"].apply(format_date)
    df["granted"] = df["grant_date"].apply(format_date)

    return df
