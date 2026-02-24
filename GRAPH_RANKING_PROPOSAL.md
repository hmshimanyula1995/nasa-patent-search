# Graph Ranking Proposal: Personalized PageRank + Graph-Aware AI Summary

> **Purpose:** Detailed implementation proposal for adding graph-based ranking and graph-aware LLM context to the NASA Patent Matching Tool. This is the recommended approach following the evaluation in [GRAPHRAG_EVALUATION.md](./GRAPHRAG_EVALUATION.md).

---

## Table of Contents

1. [Problem Statement](#1-problem-statement)
2. [Current System Gaps](#2-current-system-gaps)
3. [Proposed Solution](#3-proposed-solution)
4. [Architecture Changes](#4-architecture-changes)
5. [Implementation Plan](#5-implementation-plan)
6. [Scoring & Ranking Strategy](#6-scoring--ranking-strategy)
7. [Graph-Aware Gemini Prompt](#7-graph-aware-gemini-prompt)
8. [UI Changes](#8-ui-changes)
9. [Scenario Analysis](#9-scenario-analysis)
10. [Performance Impact](#10-performance-impact)
11. [Risk Assessment](#11-risk-assessment)
12. [Why This Approach Over Alternatives](#12-why-this-approach-over-alternatives)
13. [Stakeholder Questions](#13-stakeholder-questions)
14. [Implementation Timeline](#14-implementation-timeline)

---

## 1. Problem Statement

The current system ranks patents **only by textual similarity** (cosine distance on embeddings). This misses patents that are structurally important in the citation network but may not have similar abstracts.

**Example scenario:** A foundational 2008 patent started an entire subfield. Every patent in the top-20 results cites it directly or indirectly. But because its abstract uses different terminology than the query patent, it ranks #18 by cosine similarity. A Technology Transfer Officer would want this patent surfaced prominently — it's the root of the innovation tree — but the current system buries it.

**The professor's suggestion:** Add Personalized PageRank to use the citation graph structure as a second ranking signal, and color graph nodes by their graph rank.

---

## 2. Current System Gaps

### Gap 1: Ranking is One-Dimensional

```
Current: Patent A (93% similar) > Patent B (91% similar) > Patent C (89% similar)
```

This ranking ignores:
- Patent C is cited by 12 of the 20 results (structurally central)
- Patent B has zero citations to/from any other result (isolated)
- Patent A and Patent D share the same assignee and CPC codes (cluster signal)

### Gap 2: The Network Graph is Decorative

The pyvis network graph shows citation edges between results, but it doesn't influence ranking or scoring. Users see the connections visually but the system doesn't use them analytically. Nodes are colored by cosine similarity, not by structural importance.

### Gap 3: Gemini Sees Abstracts in Isolation

The current Gemini prompt feeds 5 abstracts with no structural context:

```
Result 1: US-XXXX  Title: ...  Abstract: ...  Similarity: 94%
Result 2: US-YYYY  Title: ...  Abstract: ...  Similarity: 91%
...
```

Gemini doesn't know:
- Which patents cite which
- Which are foundational vs derivative
- Which companies are competing in the same space
- What sub-clusters exist in the results

---

## 3. Proposed Solution

### Three Changes, One Pipeline

```
1. CITATION EXPANSION   — Fetch 1-hop citation neighbors beyond top-k results
2. PERSONALIZED PAGERANK — Run PPR on expanded subgraph using NetworkX
3. GRAPH-AWARE PROMPT    — Enrich the Gemini prompt with graph context
```

### What Each Change Does

| Change | Purpose | Improves |
|--------|---------|----------|
| Citation expansion | Bring in structurally important patents that cosine missed | Result completeness |
| Personalized PageRank | Rank patents by structural importance seeded from query patent | Ranking quality |
| Graph-aware Gemini prompt | Give the LLM citation structure, clusters, PPR scores | AI summary quality |

### What Stays the Same

- BigQuery `VECTOR_SEARCH` remains the primary retrieval method
- Cosine similarity remains a ranking signal (not replaced, augmented)
- Same GCP services (BigQuery, Vertex AI, Cloud Run)
- Same Streamlit UI framework
- Same data table (`us_patents_indexed`)

---

## 4. Architecture Changes

### Current Architecture (1 Query)

```
User input
  -> BigQuery VECTOR_SEARCH (top-k by cosine)
  -> DataFrame
  -> Gemini summary (top 5 abstracts)
  -> Render
```

### Proposed Architecture (2 Queries + In-Process PPR)

```
User input
  -> Step 1: BigQuery VECTOR_SEARCH (top-k by cosine)         [existing]
  -> Step 2: BigQuery citation expansion (1-hop neighbors)     [NEW]
  -> Step 3: NetworkX PPR on expanded subgraph                 [NEW]
  -> Step 4: Blend scores (cosine + PPR)                       [NEW]
  -> Step 5: Gemini summary (graph-aware prompt)               [MODIFIED]
  -> Render (nodes colored by PPR rank)                        [MODIFIED]
```

### New Dependencies

| Dependency | Type | Size | Purpose |
|------------|------|------|---------|
| `networkx` | pip package | ~3 MB | Personalized PageRank computation |

That's it. One pip dependency. No new GCP services.

### Query Flow Diagram

```
┌─────────────────────────────────────────────────────────┐
│                    BigQuery                              │
│                                                         │
│  Query 1: VECTOR_SEARCH                                 │
│  ┌──────────────────────────────────────────────┐       │
│  │ Input: patent_number, top_k                   │       │
│  │ Output: top-k patents + all metadata          │       │
│  │ Signal: cosine similarity (embeddings)        │       │
│  └──────────────────────┬───────────────────────┘       │
│                         │                                │
│  Query 2: CITATION EXPANSION                             │
│  ┌──────────────────────┴───────────────────────┐       │
│  │ Input: all patent numbers from citation/       │       │
│  │        cited_by arrays of top-k results        │       │
│  │ Output: neighboring patents not in top-k       │       │
│  │ Signal: graph structure (citations)            │       │
│  └──────────────────────┬───────────────────────┘       │
│                         │                                │
└─────────────────────────┼───────────────────────────────┘
                          │
┌─────────────────────────┼───────────────────────────────┐
│              Python (Cloud Run)                          │
│                         │                                │
│  Step 3: BUILD GRAPH + PPR                               │
│  ┌──────────────────────┴───────────────────────┐       │
│  │ • Combine top-k results + expanded neighbors  │       │
│  │ • Build NetworkX DiGraph (nodes + edges)      │       │
│  │ • Run nx.pagerank(personalization={query: 1}) │       │
│  │ • Output: PPR score per patent                │       │
│  └──────────────────────┬───────────────────────┘       │
│                         │                                │
│  Step 4: BLEND SCORES                                    │
│  ┌──────────────────────┴───────────────────────┐       │
│  │ • combined = α × cosine + (1-α) × ppr_norm   │       │
│  │ • Patents from expansion: ppr_score only      │       │
│  │ • Sort by combined score                      │       │
│  └──────────────────────┬───────────────────────┘       │
│                         │                                │
│  Step 5: GRAPH-AWARE GEMINI PROMPT                       │
│  ┌──────────────────────┴───────────────────────┐       │
│  │ • Abstracts + citation links + PPR scores     │       │
│  │ • Cluster information + shared assignees      │       │
│  │ • Send to Gemini 2.5 Flash                    │       │
│  └──────────────────────────────────────────────┘       │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## 5. Implementation Plan

### File Changes

| File | Change | Type |
|------|--------|------|
| `app/utils/bigquery_client.py` | Add citation expansion query | Modify |
| `app/utils/graph_ranking.py` | New file: NetworkX PPR computation + score blending | Create |
| `app/utils/gemini_client.py` | Enrich prompt with graph context | Modify |
| `app/utils/graph.py` | Color nodes by PPR rank (not just cosine) | Modify |
| `app/app.py` | Integrate new pipeline steps, add ranking toggle | Modify |
| `app/requirements.txt` | Add `networkx` | Modify |

### Step-by-Step Implementation

#### Step 1: Citation Expansion Query (`bigquery_client.py`)

Add a second query that fetches patents referenced in the citation/cited_by/parent/child arrays of the top-k results but not already in the result set:

```sql
SELECT
    publication_number,
    title,
    abstract,
    primary_assignee,
    primary_inventor,
    citation,
    cited_by,
    parent,
    child,
    cpc
FROM `grad-589-588.patent_research.us_patents_indexed`
WHERE publication_number IN UNNEST(@neighbor_ids)
```

Where `@neighbor_ids` is the list of patent numbers extracted from the citation arrays of the top-k results, minus patents already in the top-k.

#### Step 2: Graph Construction + PPR (`graph_ranking.py`)

```python
import networkx as nx
import pandas as pd
from typing import Dict, Tuple


def build_citation_graph(
    results_df: pd.DataFrame,
    expanded_df: pd.DataFrame,
    query_patent: str,
) -> nx.DiGraph:
    """Build a directed graph from citation relationships."""
    G = nx.DiGraph()

    # Combine both DataFrames
    all_patents = pd.concat([results_df, expanded_df], ignore_index=True)
    patent_set = set(all_patents["publication_number"].tolist())

    # Add nodes
    for _, row in all_patents.iterrows():
        G.add_node(row["publication_number"])

    # Add citation edges (only between patents in our set)
    for _, row in all_patents.iterrows():
        pub = row["publication_number"]

        # Forward citations (this patent cites others)
        if row.get("citation"):
            for cite in row["citation"]:
                cited_pub = cite.get("publication_number", "")
                if cited_pub in patent_set:
                    G.add_edge(pub, cited_pub, type="cites")

        # Backward citations (others cite this patent)
        if row.get("cited_by"):
            for cite in row["cited_by"]:
                citing_pub = cite.get("publication_number", "")
                if citing_pub in patent_set:
                    G.add_edge(citing_pub, pub, type="cited_by")

        # Family relationships
        if row.get("parent"):
            for p in row["parent"]:
                parent_pub = p.get("publication_number", "")
                if parent_pub in patent_set:
                    G.add_edge(pub, parent_pub, type="parent")

        if row.get("child"):
            for c in row["child"]:
                child_pub = c.get("publication_number", "")
                if child_pub in patent_set:
                    G.add_edge(pub, child_pub, type="child")

    return G


def compute_ppr(
    G: nx.DiGraph,
    query_patent: str,
    alpha: float = 0.85,
) -> Dict[str, float]:
    """Run Personalized PageRank seeded from the query patent."""
    if query_patent not in G:
        return {}

    personalization = {node: 0.0 for node in G.nodes()}
    personalization[query_patent] = 1.0

    ppr_scores = nx.pagerank(
        G,
        alpha=alpha,
        personalization=personalization,
        max_iter=100,
        tol=1e-06,
    )

    return ppr_scores


def normalize_scores(scores: Dict[str, float]) -> Dict[str, float]:
    """Normalize scores to 0-1 range."""
    if not scores:
        return {}
    max_score = max(scores.values())
    min_score = min(scores.values())
    spread = max_score - min_score
    if spread == 0:
        return {k: 1.0 for k in scores}
    return {k: (v - min_score) / spread for k, v in scores.items()}


def blend_scores(
    results_df: pd.DataFrame,
    ppr_scores: Dict[str, float],
    alpha: float = 0.6,
) -> pd.DataFrame:
    """
    Blend cosine similarity with PPR scores.

    alpha: weight for cosine similarity (1-alpha for PPR)
    Default 0.6 = 60% text similarity, 40% graph importance
    """
    ppr_normalized = normalize_scores(ppr_scores)

    df = results_df.copy()
    df["ppr_score"] = df["publication_number"].map(ppr_normalized).fillna(0.0)
    df["ppr_pct"] = (df["ppr_score"] * 100).clip(0, 100)

    # Blended score (only for patents that have both signals)
    has_similarity = df["similarity"].notna()
    df["blended_score"] = 0.0
    df.loc[has_similarity, "blended_score"] = (
        alpha * df.loc[has_similarity, "similarity"]
        + (1 - alpha) * df.loc[has_similarity, "ppr_score"]
    )

    # Patents from citation expansion (no cosine score) use PPR only
    df.loc[~has_similarity, "blended_score"] = df.loc[~has_similarity, "ppr_score"]

    return df
```

#### Step 3: Graph-Aware Gemini Prompt (`gemini_client.py`)

Modify `build_results_text` to include citation structure:

```python
def build_results_text_with_graph(
    results_df: pd.DataFrame,
    ppr_scores: dict,
    citation_edges: list,
) -> str:
    """Build LLM context that includes graph structure."""
    lines = []

    # Top 5 results with PPR scores
    top = results_df.head(5)
    for i, (_, r) in enumerate(top.iterrows(), 1):
        ppr = ppr_scores.get(r["publication_number"], 0)
        lines.append(f"""Result {i}: {r['publication_number']}
Title: {r['title_text']}
Assignee: {r.get('primary_assignee', 'N/A')}
Abstract: {r['abstract_text'][:500]}
Text Similarity: {r['similarity']:.2%}
Graph Importance (PPR): {ppr:.4f}
---""")

    # Citation relationships between results
    if citation_edges:
        lines.append("\nCitation Relationships Between Results:")
        for src, tgt, edge_type in citation_edges[:20]:  # Cap at 20
            lines.append(f"  - {src} {edge_type} {tgt}")

    # Shared assignees
    assignee_counts = {}
    for _, r in results_df.head(10).iterrows():
        a = r.get("primary_assignee", "")
        if a:
            assignee_counts[a] = assignee_counts.get(a, 0) + 1
    shared = {k: v for k, v in assignee_counts.items() if v > 1}
    if shared:
        lines.append("\nAssignees With Multiple Patents in Results:")
        for assignee, count in sorted(shared.items(), key=lambda x: -x[1]):
            lines.append(f"  - {assignee}: {count} patents")

    return "\n".join(lines)
```

#### Step 4: Node Coloring by PPR (`graph.py`)

Modify node color function to use PPR rank:

```python
def _ppr_color(ppr_score: float) -> str:
    """Color node by Personalized PageRank score (normalized 0-1)."""
    if ppr_score >= 0.8:
        return "#0B3D91"  # NASA blue (highest importance)
    if ppr_score >= 0.6:
        return "#105BD8"  # Medium-high importance
    if ppr_score >= 0.4:
        return "#4773AA"  # Medium importance
    if ppr_score >= 0.2:
        return "#FF9D1E"  # Lower importance
    return "#AEB0B5"      # Low importance (gray)
```

#### Step 5: Orchestration (`app.py`)

```python
# After existing vector search
results_df = search_patents(pn, tk)

# NEW: Citation expansion
neighbor_ids = extract_citation_neighbors(results_df)
expanded_df = fetch_patents_by_ids(neighbor_ids)

# NEW: Build graph + PPR
G = build_citation_graph(results_df, expanded_df, pn)
ppr_scores = compute_ppr(G, pn)

# NEW: Blend scores
results_with_scores = blend_scores(results_df, ppr_scores, alpha=0.6)

# MODIFIED: Graph-aware Gemini prompt
citation_edges = [(u, v, d["type"]) for u, v, d in G.edges(data=True)]
results_text = build_results_text_with_graph(
    results_with_scores, ppr_scores, citation_edges
)
ai_summary = generate_summary(
    query_pub=query_patent["publication_number"],
    query_title=query_patent["title_text"],
    query_abstract=query_patent["abstract_text"][:800],
    results_json=results_text,
)
```

---

## 6. Scoring & Ranking Strategy

### The Two Signals

| Signal | Source | What It Captures | Strengths | Blind Spots |
|--------|--------|-----------------|-----------|-------------|
| **Cosine Similarity** | BigQuery embeddings | Textual/semantic similarity | Finds patents about the same topic regardless of citation links | Misses foundational patents with different terminology |
| **PPR Score** | NetworkX on citation graph | Structural importance seeded from query patent | Finds influential and central patents in the citation neighborhood | Ignores content — a highly-cited patent about a different topic could score high |

### Blending Formula

```
blended_score = α × cosine_similarity_normalized + (1 - α) × ppr_score_normalized
```

### Alpha Selection

| Alpha | Behavior | Best For |
|-------|----------|----------|
| **1.0** | Pure cosine (current system behavior) | Prior art search (find patents that say the same thing) |
| **0.7** | Heavy text, light graph | General similarity search with mild structural boost |
| **0.6** | Balanced toward text | Default recommendation — surfaces structural outliers without destroying text ranking |
| **0.5** | Equal weight | Exploratory landscape analysis |
| **0.3** | Heavy graph, light text | Finding foundational/influential patents in the space |
| **0.0** | Pure PPR | Citation network analysis only |

**Default recommendation: α = 0.6**

This preserves the text-similarity ranking users expect while giving a meaningful boost to structurally important patents. A patent at 89% cosine but high PPR can overtake a patent at 91% cosine but zero graph connections.

### Handling Patents from Citation Expansion

Patents pulled in through citation expansion have no cosine similarity score (they weren't returned by vector search). Options:

| Approach | Pros | Cons |
|----------|------|------|
| **A: Show separately** — list expansion patents in a "Structurally Important" section below main results | Clear separation, no confusion | Two lists might confuse users |
| **B: Mark with badge** — include in main list with a "Graph Discovery" badge, ranked by PPR only | Single unified list | Mixed ranking signals could be confusing |
| **C: Omit from main list** — only show expansion patents in the network graph, sized by PPR | Simplest UI change | Users might miss important patents |

**Recommendation: Option A** — separate section. Clean, honest, no mixed signals.

---

## 7. Graph-Aware Gemini Prompt

### Current Prompt (Text Only)

```
You are a patent analyst at NASA's Technology Transfer Office.

A user searched for patent US-XXXX:
Title: ...
Abstract: ...

The following are the top 5 most semantically similar patents found:
[5 abstracts with similarity scores]

Write a brief analysis...
```

### Proposed Prompt (Graph-Aware)

```
You are a patent analyst at NASA's Technology Transfer Office.

A user searched for patent US-XXXX:
Title: ...
Abstract: ...

The following are the top 5 most relevant patents found (ranked by blended
text-similarity + citation-graph-importance score):

Result 1: US-AAAA
Title: ...
Assignee: Boeing
Abstract: ...
Text Similarity: 94%
Graph Importance (PPR): 0.0312 (Rank #3 in citation network)
---
Result 2: US-BBBB
...

Citation Relationships Between Results:
  - US-AAAA cites US-CCCC
  - US-BBBB cites US-AAAA and US-DDDD
  - US-CCCC is cited by 8 patents in the result set (foundational)

Assignees With Multiple Patents in Results:
  - Boeing: 4 patents
  - Lockheed Martin: 3 patents
  - NASA: 2 patents

Structurally Important Patents (discovered via citation network, not text similarity):
  - US-FFFF (PPR: 0.089) — cited by 12 results, foundational patent in this space

Write a brief (3-5 paragraph) analysis that:
1. Summarizes what technical space this patent operates in
2. Identifies the key companies and inventors active in this space
3. Highlights structural patterns: which patents are foundational, which are
   derivative, and how the citation network clusters
4. Notes any patents discovered through citation analysis (not text similarity)
   that may represent foundational IP or collaboration opportunities
5. Suggests potential licensing or collaboration opportunities for NASA

Write in plain professional language. Focus on actionable insights.
```

### Expected Improvement

| Aspect | Current Summary | Graph-Aware Summary |
|--------|----------------|-------------------|
| Technology landscape | Generic topic description | Describes technology evolution (foundational -> derivative) |
| Key players | Lists assignees from abstracts | Identifies which companies own foundational vs recent patents |
| Patterns | "Several patents share similar approaches" | "Boeing's 4 patents form a citation cluster, all derived from Lockheed's foundational US-CCCC" |
| Recommendations | Generic "potential for collaboration" | "NASA should consider licensing US-CCCC (foundational, cited by 12 results) rather than individual derivative patents" |

---

## 8. UI Changes

### Network Graph (Modified)

**Current:** Nodes colored by cosine similarity (green = high, gray = low)

**Proposed:** Add toggle for node coloring:
- **"Text Similarity"** — current behavior (cosine-based colors)
- **"Graph Importance"** — nodes colored by PPR score, sized by PPR rank

Node size scales with PPR score — structurally important patents appear larger.

### Results Table (Modified)

Add columns:
- **PPR Score** — graph importance percentage
- **Blended Rank** — combined ranking position

### New Section: "Structurally Important Patents"

Below the main results table, show patents discovered through citation expansion that weren't in the original vector search results. These are patents that are structurally central in the citation network around the query patent.

### Ranking Toggle

Add a simple control:
- **"Text Similarity"** — sort by cosine (current behavior)
- **"Graph Importance"** — sort by PPR score
- **"Blended" (default)** — sort by combined score

---

## 9. Scenario Analysis

### Scenario 1: Query Patent Has Rich Citation Network

**Situation:** User searches for a well-cited patent in a mature field (e.g., lithium-ion battery technology). The top-20 results have dense cross-citations.

**Current behavior:** Results ranked purely by abstract similarity. Foundational patents with older/different terminology rank low.

**With PPR:** Foundational patents get boosted because many results cite them. The citation expansion pulls in seminal patents not in the top-20 by cosine. Gemini summary identifies the innovation lineage.

**Impact: High.** PPR adds significant value.

### Scenario 2: Query Patent is Isolated (Few Citations)

**Situation:** User searches for a very recent patent (filed 2024) with few or zero citations in the database.

**Current behavior:** Works fine — cosine similarity finds textually similar patents.

**With PPR:** Citation expansion returns few or no neighbors. PPR graph is sparse. PPR scores are mostly uniform (no structural signal). Blended score effectively falls back to cosine similarity.

**Impact: Neutral.** PPR doesn't hurt, just doesn't add much. System degrades gracefully.

### Scenario 3: Query Patent Spans Multiple Technical Domains

**Situation:** A patent covers both hardware (sensor design) and software (data processing algorithm). Cosine results split between hardware and software patents that don't cite each other.

**Current behavior:** Mixed results with no clustering signal.

**With PPR:** The two clusters (hardware vs software) are structurally disconnected in the citation graph. PPR naturally ranks each cluster's internal patents higher than cross-cluster outliers. Gemini summary can identify the two distinct clusters because citation edges are included in the prompt.

**Impact: Medium.** PPR provides clustering signal that cosine alone cannot.

### Scenario 4: Assignee Dominance

**Situation:** A single company (e.g., Boeing) holds 15 of the top-20 results by cosine similarity.

**Current behavior:** Results dominated by one assignee's patents.

**With PPR:** If Boeing's patents are heavily self-citing (common for large portfolios), PPR may further concentrate scores within Boeing's cluster. However, citation expansion might surface a competitor's foundational patent that Boeing's entire portfolio builds upon.

**Impact: Medium.** PPR doesn't solve assignee dominance but may surface the competitor's foundational work.

### Scenario 5: Very Small Result Set

**Situation:** User requests only 5 results (small top-k). Citation expansion adds another 10-20 neighbors.

**Current behavior:** 5 results displayed.

**With PPR:** Small initial set means fewer citation edges to start with. Expansion is critical here — without it, PPR on 5 nodes is meaningless. With expansion to ~20-25 nodes, PPR becomes viable but less robust than with larger sets.

**Impact: Low-Medium.** Recommend minimum top-k of 20 when graph ranking is enabled.

### Scenario 6: Patent Not in Citation Network

**Situation:** A very old patent (pre-2006) or very obscure patent with zero entries in citation/cited_by arrays.

**Current behavior:** Works fine for cosine search.

**With PPR:** Empty citation arrays → no expansion → no graph to run PPR on → system falls back to pure cosine ranking automatically.

**Impact: None.** Graceful degradation, identical to current behavior.

---

## 10. Performance Impact

### Latency Breakdown

| Step | Current | Proposed | Delta |
|------|---------|----------|-------|
| BigQuery VECTOR_SEARCH | 2-5s | 2-5s | +0s |
| Citation expansion query | — | 1-3s | +1-3s |
| Build NetworkX graph | — | <50ms | +50ms |
| Compute PPR | — | <100ms | +100ms |
| Blend scores | — | <10ms | +10ms |
| Build graph-aware prompt | — | <10ms | +10ms |
| Gemini summary | 2-3s | 2-3s | +0s |
| **Total** | **3-8s** | **5-11s** | **+2-3s** |

### Optimization: Run Expansion in Parallel with Gemini

```python
# Current: sequential
results_df = search_patents(pn, tk)
ai_summary = generate_summary(...)  # waits for this

# Proposed: parallel where possible
results_df = search_patents(pn, tk)

# These can run in parallel:
# Thread 1: Citation expansion + PPR
# Thread 2: Initial Gemini summary (can be updated later)
# Thread 3: Chart generation (already parallel)
```

With parallelization, the additional latency can be reduced to ~1-2s.

### Memory Impact

| Component | Memory |
|-----------|--------|
| NetworkX graph (500 nodes, 2000 edges) | ~5-10 MB |
| PPR score dictionary (500 entries) | <1 MB |
| Expanded DataFrame (100-300 rows) | ~2-5 MB |
| **Total additional** | **~10-15 MB per request** |

Negligible on Cloud Run (which has 256MB+ RAM per instance).

### BigQuery Cost Impact

| Query | Estimated Bytes Scanned | Cost |
|-------|------------------------|------|
| VECTOR_SEARCH (existing) | ~50-200 MB | ~$0.00025-0.001 |
| Citation expansion | ~10-50 MB | ~$0.00005-0.00025 |
| **Per search total** | ~60-250 MB | ~$0.0003-0.00125 |

Negligible cost increase (~$0.0001 per search).

---

## 11. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Citation expansion query is slow on highly-cited patents | Medium | Medium (adds 3-5s) | Cap neighbor_ids at 500 patents; timeout after 5s and fall back to cosine-only |
| PPR scores are uniform (no structural signal) | Low | Low | Detect low variance in PPR scores; if PPR max/min ratio < 2, hide PPR column and use cosine only |
| Blended ranking confuses users | Medium | Medium | Default to cosine view; PPR/blended as opt-in toggle |
| NetworkX computation fails on edge cases | Low | Low | Wrap in try/except; fall back to cosine-only ranking |
| Citation arrays contain patents not in our table | High | None | Filter to only patents in `us_patents_indexed`; ignore external references |
| Expanded patents lack cosine similarity score | Certain | Low | Display in separate "Structurally Important" section with clear labeling |

### Graceful Degradation

Every new component has a fallback to current behavior:

```
If citation expansion fails → skip PPR, use cosine only
If PPR computation fails   → skip blending, use cosine only
If graph-aware prompt fails → fall back to current simple prompt
If expanded_df is empty     → no structural section, normal results
```

The system never gets worse than it is today.

---

## 12. Why This Approach Over Alternatives

### vs. GCP Spanner GraphRAG

| Dimension | Spanner GraphRAG | This Proposal |
|-----------|-----------------|---------------|
| New GCP services | 4+ (Spanner, Pub/Sub, Cloud Run Functions, Agent Engine) | 0 |
| Monthly cost increase | +$700-950 | +$0.10-0.50 |
| Implementation time | 4-8 weeks | 1-2 weeks |
| Solves the problem | No (designed for unstructured → graph extraction) | Yes (directly adds PPR + graph-aware LLM) |

### vs. Full Microsoft GraphRAG

| Dimension | Microsoft GraphRAG | This Proposal |
|-----------|-------------------|---------------|
| Preprocessing pipeline | Offline batch: entity extraction + community detection on millions of patents | None — uses existing structured data |
| Infrastructure | Graph database + batch compute | NetworkX in existing Cloud Run |
| Quarterly maintenance | Rerun full pipeline on new patents | Automatic (new patents have citation data natively) |
| Better summaries? | Yes (community summaries are very good) | Partially (graph-aware prompt is simpler but still a major improvement) |

### vs. Neo4j / Graph Database

| Dimension | Neo4j | This Proposal |
|-----------|-------|---------------|
| Cost | $65-200+/mo | $0 |
| Operational overhead | Manage a database | None (in-process computation) |
| Performance benefit | Better for full-graph queries | Unnecessary for 100-500 node subgraph |
| PageRank quality | Slightly better (native optimized) | Equivalent for our subgraph size |

### Bottom Line

This proposal is the **minimum viable architecture change** that delivers the professor's requirement. It adds graph ranking, graph-colored nodes, and graph-aware AI summaries without new services, without new infrastructure, and without new ongoing costs. Every component degrades gracefully to current behavior on failure.

---

## 13. Stakeholder Questions

Before implementing, the following questions should be answered by NASA Technology Transfer Officers (the end users):

### Question 1: Discovery Intent

**"When you search for a patent, are you primarily looking for patents that describe the same technology, or patents that are most influential/foundational in that technology's citation network?"**

- If "same technology" → cosine is sufficient, PPR is nice-to-have
- If "influential/foundational" → PPR is critical
- If "both" → blended score is the right default

### Question 2: Citation Chain Usage

**"Do you currently follow citation chains manually (clicking through references in Google Patents or USPTO) to find foundational work?"**

- If yes → PPR automates exactly what they're doing by hand (strong justification)
- If no → PPR is a new capability they may not know they need (requires education)

### Question 3: Ranking Preference

**"Would you prefer a single ranked list, or the ability to toggle between 'text similarity' and 'graph importance' views?"**

- Single list → use blended score as default, no toggle needed
- Toggle → build the UI control, let users explore both dimensions

### Question 4: Structural Discovery

**"Would it be valuable to see patents that aren't textually similar but are heavily cited by patents that are? (e.g., a foundational patent from 2008 that every recent patent in the space builds on)"**

- If yes → citation expansion + "Structurally Important" section is valuable
- If no → skip citation expansion, just run PPR on the existing top-k results

---

## 14. Implementation Timeline

### Phase 1: Core PPR (Week 1)

| Task | Estimated Effort |
|------|-----------------|
| Add `networkx` to requirements.txt | 5 min |
| Write citation expansion query in `bigquery_client.py` | 2-3 hours |
| Create `graph_ranking.py` (build graph, PPR, normalize, blend) | 3-4 hours |
| Integrate into `app.py` pipeline | 2-3 hours |
| Add PPR score column to results table | 1 hour |
| Add graceful degradation (try/except fallbacks) | 1-2 hours |
| Testing + edge cases | 3-4 hours |

### Phase 2: Graph-Aware Gemini (Week 1-2)

| Task | Estimated Effort |
|------|-----------------|
| Modify `build_results_text` to include graph context | 2-3 hours |
| Update Gemini prompt template | 1-2 hours |
| Test summary quality with/without graph context | 2-3 hours |

### Phase 3: UI Enhancements (Week 2)

| Task | Estimated Effort |
|------|-----------------|
| Modify `graph.py` to color nodes by PPR score | 2-3 hours |
| Scale node size by PPR rank | 1-2 hours |
| Add ranking toggle (Text / Graph / Blended) | 3-4 hours |
| Add "Structurally Important Patents" section | 2-3 hours |
| UI polish + testing | 2-3 hours |

### Total Estimated Effort: 25-35 hours (1-2 weeks)
