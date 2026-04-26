import logging
import os
import time

import streamlit as st

from utils.config import get_project

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GCP_PROJECT = get_project()
VERTEX_LOCATION = os.getenv("VERTEX_AI_LOCATION", "us-central1")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


@st.cache_resource
def _get_model():
    import vertexai
    from vertexai.generative_models import GenerativeModel

    vertexai.init(project=GCP_PROJECT, location=VERTEX_LOCATION)
    return GenerativeModel(GEMINI_MODEL)


DEFAULT_PROMPT = """You are a patent analyst at NASA's Technology Transfer Office.

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


GRAPH_AWARE_PROMPT = """You are a senior patent analyst at NASA's Technology Transfer \
Office, helping Technology Transfer Officers identify licensing and collaboration \
opportunities.

A user searched for patent {query_pub}:
Title: {query_title}
Abstract: {query_abstract}

Below are the top results ranked by a blend of text similarity (cosine distance \
on embeddings) and citation graph importance (Personalized PageRank seeded from \
the query patent). Higher PPR scores mean the patent is more structurally central \
in the citation network — it is cited by or cites many other relevant patents.

{results_json}

Using ALL the data above — including citation relationships, shared assignees, \
and structurally important patents from the citation network — write a structured \
analysis with these sections:

## Technology Landscape
Summarize the technical space this patent operates in. Describe how the technology \
has evolved based on the citation relationships (which patents are foundational \
and which are derivative).

## Key Players
Identify the key companies and inventors. If an assignee holds multiple patents \
in the results, note their portfolio concentration. Distinguish between companies \
that own foundational IP vs. those with derivative/incremental patents.

## Citation Network Patterns
Analyze the citation structure: identify clusters of patents that cite each other, \
highlight any patent that is cited by many results (a "hub" patent), and note \
patents discovered through citation network analysis rather than text similarity.

## Licensing & Collaboration Opportunities
Provide specific, actionable recommendations for NASA. If a patent is structurally \
foundational (high PPR, cited by many results), flag its assignee as a priority \
licensing target. Suggest whether NASA should pursue the foundational IP holder \
or individual derivative patent owners. Reference specific patent numbers.

Keep the analysis concise (4-6 paragraphs total across all sections). Use plain \
professional language. Avoid legal jargon. Every recommendation should reference \
a specific patent number or assignee name."""


@st.cache_data(ttl=3600, show_spinner=False)
def generate_summary(
    query_pub: str,
    query_title: str,
    query_abstract: str,
    results_json: str,
    prompt_template: str | None = None,
) -> str:
    model = _get_model()

    template = prompt_template if prompt_template else DEFAULT_PROMPT
    prompt = template.format(
        query_pub=query_pub,
        query_title=query_title,
        query_abstract=query_abstract,
        results_json=results_json,
    )

    logger.info(
        "Gemini request: model=%s, prompt_length=%d chars",
        GEMINI_MODEL, len(prompt),
    )

    try:
        t0 = time.time()
        response = model.generate_content(prompt)
        elapsed = time.time() - t0
        logger.info("Gemini response: %d chars in %.2fs", len(response.text), elapsed)
        return response.text
    except Exception as e:
        logger.error("Gemini generation failed: %s", e)
        return f"Summary generation failed: {e}"


def build_results_text(results_df) -> str:
    lines: list[str] = []
    top = results_df.head(5)
    for i, (_, r) in enumerate(top.iterrows(), 1):
        lines.append(f"""Result {i}: {r['publication_number']}
Title: {r['title_text']}
Assignee: {r.get('primary_assignee', 'N/A')}
Abstract: {r['abstract_text'][:500]}
Similarity: {r['similarity']:.2%}
---""")
    return "\n".join(lines)


def build_results_text_with_graph(
    results_df,
    ppr_scores: dict[str, float],
    citation_edges: list[tuple[str, str, str]],
    expanded_df=None,
) -> str:
    """Build enriched results text with graph context for Gemini prompt.

    Includes text similarity, PPR scores, citation relationships, shared
    assignees, and structurally important patents from expansion.
    """
    lines: list[str] = []
    top = results_df.head(5)
    for i, (_, r) in enumerate(top.iterrows(), 1):
        pub = r["publication_number"]
        sim = r.get("similarity", 0)
        ppr = ppr_scores.get(pub, 0)
        blended = r.get("blended_score", sim)
        lines.append(f"""Result {i}: {pub}
Title: {r['title_text']}
Assignee: {r.get('primary_assignee', 'N/A')}
Abstract: {r['abstract_text'][:500]}
Text Similarity: {sim:.2%} | Graph Importance (PPR): {ppr:.4f} | Blended: {blended:.2%}
---""")

    # Citation relationships (capped at 20)
    if citation_edges:
        lines.append("\nCitation relationships between results:")
        result_pubs = set(results_df["publication_number"].tolist())
        shown = 0
        for src, tgt, etype in citation_edges:
            if src in result_pubs and tgt in result_pubs:
                lines.append(f"  {src} --[{etype}]--> {tgt}")
                shown += 1
                if shown >= 20:
                    break

    # Shared assignees
    assignee_counts: dict[str, int] = {}
    for _, r in results_df.head(10).iterrows():
        a = r.get("primary_assignee")
        if a and a != "N/A":
            assignee_counts[a] = assignee_counts.get(a, 0) + 1
    shared = {k: v for k, v in assignee_counts.items() if v > 1}
    if shared:
        lines.append("\nShared assignees:")
        for assignee, count in sorted(shared.items(), key=lambda x: -x[1]):
            lines.append(f"  {assignee}: {count} patents")

    # Structurally important from expansion
    if expanded_df is not None and not expanded_df.empty and ppr_scores:
        expanded_with_ppr = []
        for _, r in expanded_df.iterrows():
            pub = r["publication_number"]
            score = ppr_scores.get(pub, 0)
            if score > 0:
                expanded_with_ppr.append((pub, r.get("title_text", ""), score))
        expanded_with_ppr.sort(key=lambda x: -x[2])
        if expanded_with_ppr:
            lines.append(
                "\nStructurally important patents discovered via citation network:"
            )
            for pub, title, score in expanded_with_ppr[:3]:
                lines.append(f"  {pub}: {title} (PPR: {score:.4f})")

    return "\n".join(lines)
