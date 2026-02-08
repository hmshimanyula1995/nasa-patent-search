import os
import streamlit as st

GCP_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", "grad-589-588")
VERTEX_LOCATION = os.getenv("VERTEX_AI_LOCATION", "us-central1")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


@st.cache_resource
def _get_model():
    import vertexai
    from vertexai.generative_models import GenerativeModel

    vertexai.init(project=GCP_PROJECT, location=VERTEX_LOCATION)
    return GenerativeModel(GEMINI_MODEL)


@st.cache_data(ttl=3600, show_spinner=False)
def generate_summary(
    query_pub: str,
    query_title: str,
    query_abstract: str,
    results_json: str,
) -> str:
    model = _get_model()

    prompt = f"""You are a patent analyst at NASA's Technology Transfer Office.

A user searched for patent {query_pub}:
Title: {query_title}
Abstract: {query_abstract}

The following are the top 5 most semantically similar patents found:

{results_json}

Write a brief (3-5 paragraph) analysis that:
1. Summarizes what technical space this patent operates in
2. Identifies the key companies and inventors active in this space
3. Highlights any notable patterns (e.g., multiple patents from the same assignee,
   clustering of filing dates, convergence of approaches)
4. Suggests potential licensing or collaboration opportunities for NASA

Write in plain professional language. Avoid legal jargon. Focus on actionable insights
that a Technology Transfer Officer could use to identify potential licensees."""

    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Summary generation failed: {e}"


def build_results_text(results_df) -> str:
    lines = []
    top = results_df.head(5)
    for i, (_, r) in enumerate(top.iterrows(), 1):
        lines.append(f"""Result {i}: {r['publication_number']}
Title: {r['title_text']}
Assignee: {r.get('primary_assignee', 'N/A')}
Abstract: {r['abstract_text'][:500]}
Similarity: {r['similarity']:.2%}
---""")
    return "\n".join(lines)
