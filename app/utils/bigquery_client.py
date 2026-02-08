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
