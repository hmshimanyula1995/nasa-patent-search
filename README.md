# NASA Patent Similarity Search Tool

A semantic patent search tool built for NASA's Technology Transfer Office (TTO). Enter a US patent number and get back semantically similar patents ranked by a blend of text similarity and citation graph importance, along with an AI-generated analysis, interactive charts, and a network graph.

**Purdue University MSAI Capstone -- Team E (Spring 2026)**

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Project Structure](#2-project-structure)
3. [Quick Start](#3-quick-start)
4. [Patent Number Normalization](#4-patent-number-normalization)
5. [Data Layer -- BigQuery Vector Search](#5-data-layer----bigquery-vector-search)
6. [Citation Expansion Pipeline](#6-citation-expansion-pipeline)
7. [Graph Ranking -- Personalized PageRank](#7-graph-ranking----personalized-pagerank)
8. [Score Blending](#8-score-blending)
9. [LLM Integration -- Gemini Summarization](#9-llm-integration----gemini-summarization)
10. [Network Graph Visualization](#10-network-graph-visualization)
11. [Analytics Charts](#11-analytics-charts)
12. [Frontend -- Streamlit Application](#12-frontend----streamlit-application)
13. [Print / PDF Export Styles](#13-print--pdf-export-styles)
14. [Caching Strategy](#14-caching-strategy)
15. [Error Handling and Graceful Degradation](#15-error-handling-and-graceful-degradation)
16. [Observability -- Structured Logging](#16-observability----structured-logging)
17. [Deployment](#17-deployment)
18. [Data Schema](#18-data-schema)
19. [Environment Variables](#19-environment-variables)
20. [Performance](#20-performance)
21. [Dependencies](#21-dependencies)

---

## 1. System Overview

The tool lets NASA Technology Transfer Officers enter a US patent number and get back semantically similar patents ranked by a blend of text similarity and citation graph importance, along with an AI-generated analysis, interactive charts, and a network graph.

**Pipeline:**

```
User Input (patent number, top-K)
    |
    v
Patent Number Normalization (plain grant #, commas, US prefix -> publication_number)
    |
    v
BigQuery VECTOR_SEARCH (cosine distance on 64-dim embeddings)
    |
    v
Citation Expansion (fetch 1-hop neighbors from citation arrays)
    |
    v
Graph Construction + Personalized PageRank (NetworkX)
    |
    v
Score Blending (60% cosine + 40% PPR)
    |
    v
Parallel:
  - Gemini Summarization (graph-aware prompt, top 5 results)
  - Plotly Charts (assignees, inventors, CPC distribution)
  - Pyvis Network Graph (interactive HTML)
    |
    v
Streamlit Rendering + ZIP Download + Print/PDF Export
```

**GCP services used:** BigQuery (vector search + data storage), Vertex AI / Gemini (summarization), Cloud Run (hosting).

**No GPU required.** Embeddings are pre-computed by Google in the public `patents-public-data` dataset and stored in BigQuery. The old system used a 104GB RAM VM to generate embeddings at query time -- this approach eliminated that entirely.

**Key features:**

- **Semantic search** -- finds patents by meaning, not just keywords, using Google's pre-computed 64-dimensional embeddings
- **Graph ranking** -- Personalized PageRank on the citation network surfaces structurally important patents that pure text search would miss
- **Flexible input** -- accepts patent numbers in any format: `US-8410469-B2`, `8410469`, `8,410,469`, `US8410469`
- **AI analysis** -- Gemini produces a structured 4-section report covering technology landscape, key players, citation patterns, and licensing opportunities
- **Interactive network graph** -- drag-and-drop patent relationship visualization with color-coded similarity tiers
- **Analytics charts** -- top assignees, top inventors, and CPC technology distribution
- **Print/PDF ready** -- `Ctrl+P` produces a clean landscape layout with full-width tables and stacked charts
- **Download package** -- ZIP file with CSV results, AI summary text, and standalone network graph HTML

**Architecture:**

| Component | Technology |
|-----------|------------|
| Frontend | Streamlit |
| Vector search | BigQuery `VECTOR_SEARCH` (cosine, 64-dim) |
| Graph ranking | NetworkX (Personalized PageRank) |
| AI summarization | Vertex AI / Gemini 2.5 |
| Charts | Plotly |
| Network graph | Pyvis |
| Hosting | Google Cloud Run |
| Data storage | BigQuery |

---

## 2. Project Structure

```
app/
  app.py                      # Main Streamlit application (557 lines)
  requirements.txt            # Python dependencies
  Dockerfile                  # Cloud Run container
  .streamlit/config.toml      # Theme + server config
  utils/
    __init__.py
    bigquery_client.py         # BigQuery queries, data retrieval, patent normalization (292 lines)
    gemini_client.py           # Gemini API client + prompt templates (202 lines)
    graph_ranking.py           # PageRank computation + score blending (202 lines)
    graph.py                   # Pyvis network graph generation (254 lines)
    charts.py                  # Plotly chart generation (180 lines)
    styles.py                  # NASA light theme CSS + print styles (565 lines)
```

Total application code is approximately 2,250 lines of Python.

---

## 3. Quick Start

### Prerequisites

- Python 3.11+
- Google Cloud SDK (`gcloud`) with access to project `grad-589-588`
- Application Default Credentials configured

### Run Locally

```bash
# Authenticate with GCP
gcloud auth application-default login

# Install dependencies
cd app/
pip install -r requirements.txt

# Run
streamlit run app.py
```

The app will open at `http://localhost:8501`.

### Deploy to Cloud Run

```bash
cd app/
gcloud run deploy nasa-patent-search \
  --source . \
  --project grad-589-588 \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 1Gi \
  --cpu 1 \
  --port 8080 \
  --min-instances 0 \
  --max-instances 3 \
  --set-env-vars "GOOGLE_CLOUD_PROJECT=grad-589-588,BIGQUERY_DATASET=patent_research,BIGQUERY_TABLE=us_patents_indexed,VERTEX_AI_LOCATION=us-central1,GEMINI_MODEL=gemini-2.5-flash"
```

Cloud Build handles the Docker build. Cloud Run serves the container. This single command does everything.

**Redeploying after code changes:**

```bash
cd app/
gcloud run deploy nasa-patent-search --source . --project grad-589-588 --region us-central1
```

Zero-downtime rolling update.

**For production (NASA):** Use `--no-allow-unauthenticated` and enable Identity-Aware Proxy (IAP). See `DEPLOYMENT.md` for the full production deployment guide including IAP setup, service accounts, custom domains, and quarterly data maintenance.

---

## 4. Patent Number Normalization

**File:** `app/utils/bigquery_client.py`

**Problem:** Users enter patent numbers in many formats -- plain grant numbers (`8410469`), with commas (`8,410,469`), with US prefix (`US8410469`), or the full publication format (`US-8410469-B2`). The BigQuery table keys on `publication_number` (e.g., `US-8410469-B2`), so we need to resolve user input to that format before searching.

**Approach:** A 3-step lookup cascade in `normalize_patent_number()`:

1. **Already formatted?** If input matches `XX-NNNN-XN` regex, return as-is.
2. **Clean the input:** Strip commas, spaces, leading "US" prefix.
3. **BigQuery lookup cascade:**
   - Try exact suffix match: `US-{number}-B1`, `US-{number}-B2`, `US-{number}-A1`
   - Try LIKE pattern: `US-{number}%` (catches unusual suffixes like `-A2`, `-B3`)
   - Try application number lookup: match against `application_number` column

```python
def normalize_patent_number(raw_input: str) -> str | None:
    cleaned = raw_input.strip().replace(",", "").replace(" ", "")

    # Already in publication_number format
    if _PUB_NUMBER_RE.match(cleaned):
        return cleaned

    # Strip leading "US" prefix
    number = re.sub(r"^US", "", cleaned, flags=re.IGNORECASE)

    if not number.isdigit():
        return None

    # Step 1: exact suffix match (B1, B2, A1)
    # Step 2: LIKE pattern match
    # Step 3: application_number lookup
    # Returns first match or None
```

**Key details:**
- Each BigQuery lookup is parameterized (`@number`) to prevent injection.
- The function returns `None` if no match is found, which triggers an error message in the UI suggesting the full publication format.
- When the input is normalized (e.g., `8410469` -> `US-8410469-B2`), the UI shows the resolution: "Resolved `8410469` → `US-8410469-B2`".
- Commas are stripped immediately (`8,410,469` -> `8410469`), so all four test patents work with or without commas.

---

## 5. Data Layer -- BigQuery Vector Search

**File:** `app/utils/bigquery_client.py`

**Problem:** Given a patent number, find the top-K most similar US patents by embedding distance.

**Approach:** BigQuery's built-in `VECTOR_SEARCH` function runs cosine-distance search on pre-computed 64-dimensional embeddings. The embeddings come from Google's `patents-public-data.google_patents_research.publications` table and were merged into our indexed table.

**Primary query:**

```sql
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
    TABLE `grad-589-588.patent_research.us_patents_indexed`,
    'embedding_v1',
    (
        SELECT embedding_v1
        FROM `grad-589-588.patent_research.us_patents_indexed`
        WHERE publication_number = @patent_number
    ),
    top_k => @top_k,
    distance_type => 'COSINE'
)
ORDER BY distance
```

The query returns all metadata in a single round trip. No joins needed because we denormalized everything (citations, assignees, inventors, CPC codes) into struct/array columns during the initial data merge.

**Key implementation details:**

- Table reference is parameterized via environment variables (`GOOGLE_CLOUD_PROJECT`, `BIGQUERY_DATASET`, `BIGQUERY_TABLE`).
- Query parameters use BigQuery's `@param` syntax to prevent injection.
- The BigQuery client is instantiated once via `@st.cache_resource` and reused.
- Results are cached for 1 hour via `@st.cache_data(ttl=3600)`.

**Post-processing:**

```python
# Title and abstract come as struct {value: "..."} from BigQuery
df["title_text"] = df["title"].apply(extract_struct_value)
df["abstract_text"] = df["abstract"].apply(extract_struct_value)

# Dates are stored as integers (e.g., 20240115)
df["filed"] = df["filing_date"].apply(format_date)  # -> "2024-01-15"

# Cosine similarity = 1 - cosine distance
df["similarity"] = 1 - df["distance"]
df["similarity_pct"] = (df["similarity"] * 100).clip(0, 100)
```

---

## 6. Citation Expansion Pipeline

**File:** `app/utils/bigquery_client.py`

**Problem:** The vector search only returns patents that are textually similar. Patents that are structurally important (heavily cited, foundational IP) might not show up in a pure embedding search.

**Approach:** After the initial search, extract all unique patent IDs from the citation arrays (`citation`, `cited_by`, `parent`, `child`) of the results. Fetch their metadata from BigQuery. This gives us a 1-hop citation neighborhood to feed into PageRank.

**Extraction logic:**

```python
def extract_citation_neighbors(results_df, max_neighbors=500):
    existing = set(results_df["publication_number"].tolist())
    neighbors = set()

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
```

The cap at 500 is deliberate: BigQuery charges per bytes scanned, and a 500-element `IN UNNEST(...)` clause keeps costs and latency reasonable.

**Fetch query:**

```sql
SELECT
    publication_number, title, abstract,
    primary_assignee, primary_inventor,
    assignee_harmonized, inventor_harmonized,
    citation, cited_by, parent, child,
    cpc, filing_date, publication_date, grant_date, top_terms
FROM `grad-589-588.patent_research.us_patents_indexed`
WHERE publication_number IN UNNEST(@neighbor_ids)
```

The function `fetch_citation_neighbors` takes a tuple (for hashability with Streamlit's cache) and returns a DataFrame with the same post-processing as the main search.

---

## 7. Graph Ranking -- Personalized PageRank

**File:** `app/utils/graph_ranking.py`

**Problem:** Text similarity alone misses structurally important patents. A patent might have low embedding distance but be cited by 50 other results -- that structural signal matters for licensing decisions.

**Approach:** Build a directed citation graph from all search results plus expanded neighbors, then run Personalized PageRank (PPR) seeded from the query patent. PPR scores tell us which patents are most reachable from the query patent through citation chains.

**Graph construction:**

```python
def build_citation_graph(results_df, expanded_df, query_patent):
    G = nx.DiGraph()

    # Combine search results + expanded patents
    all_dfs = [results_df]
    if expanded_df is not None and not expanded_df.empty:
        all_dfs.append(expanded_df)
    combined = pd.concat(all_dfs, ignore_index=True)

    node_set = set(combined["publication_number"].tolist())
    node_set.add(query_patent)

    for pub in node_set:
        G.add_node(pub)

    # Directed edges from citation arrays
    for _, row in combined.iterrows():
        pub = row["publication_number"]

        # This patent cites X -> edge from pub to X
        for cited in _extract_pub_numbers(row.get("citation")):
            if cited in node_set and cited != pub:
                G.add_edge(pub, cited, edge_type="cites")

        # X cites this patent -> edge from X to pub
        for citing in _extract_pub_numbers(row.get("cited_by")):
            if citing in node_set and citing != pub:
                G.add_edge(citing, pub, edge_type="cited_by")

        # Parent/child family relationships
        for parent in _extract_pub_numbers(row.get("parent")):
            if parent in node_set and parent != pub:
                G.add_edge(parent, pub, edge_type="parent")

        for child in _extract_pub_numbers(row.get("child")):
            if child in node_set and child != pub:
                G.add_edge(pub, child, edge_type="child")

    return G
```

Only edges where both endpoints exist in the node set are added. Self-citations are excluded.

**PageRank computation:**

```python
def compute_ppr(G, query_patent, alpha=0.85):
    if G.number_of_edges() == 0:
        return {}

    if query_patent not in G:
        G.add_node(query_patent)

    # 100% teleport probability to query patent
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
        return scores
    except nx.PowerIterationFailedConvergence:
        return {}
```

`alpha=0.85` means at each step there's a 15% chance of teleporting back to the query patent. This ensures scores are anchored to the query rather than converging to generic hubs in the patent corpus.

If the graph has no edges (isolated patent with no citations) or PageRank fails to converge, the function returns an empty dict and the system falls back to cosine-only ranking.

---

## 8. Score Blending

**File:** `app/utils/graph_ranking.py`

**Problem:** We have two ranking signals -- cosine similarity (text) and PPR (graph structure). Need to combine them into a single ranking.

**Approach:**

```python
def blend_scores(results_df, ppr_scores, alpha=0.6):
    df = results_df.copy()

    normalized = normalize_scores(ppr_scores)  # min-max to [0, 1]

    df["ppr_raw"] = df["publication_number"].map(lambda pn: ppr_scores.get(pn, 0.0))
    df["ppr_score"] = df["publication_number"].map(lambda pn: normalized.get(pn, 0.0))
    df["ppr_pct"] = (df["ppr_score"] * 100).clip(0, 100)

    cosine = df["similarity"].fillna(0.0)
    ppr = df["ppr_score"].fillna(0.0)
    df["blended_score"] = alpha * cosine + (1 - alpha) * ppr
    df["blended_pct"] = (df["blended_score"] * 100).clip(0, 100)

    return df
```

Formula: `blended = 0.6 * cosine_similarity + 0.4 * ppr_normalized`

The PPR scores are min-max normalized to [0, 1] before blending so they're on the same scale as cosine similarity. If all PPR scores are equal (degenerate graph), they all normalize to 1.0.

The UI provides three ranking modes that users can toggle:
- **Blended** (default): `blended_score`
- **Text Similarity**: `similarity` (pure cosine)
- **Graph Importance**: `ppr_score` (pure PPR)

This toggle also controls which score is used for graph node coloring and sizing.

---

## 9. LLM Integration -- Gemini Summarization

**File:** `app/utils/gemini_client.py`

**Problem:** Raw patent data is dense. Technology Transfer Officers need a human-readable summary of the competitive landscape, key players, and licensing opportunities.

**Approach:** Feed the top 5 results (plus graph context if available) into Gemini with a structured prompt. Two prompt templates exist:

1. **Default prompt** -- text similarity only, 3-5 paragraph free-form analysis.
2. **Graph-aware prompt** (production) -- includes PPR scores, citation edges, shared assignees. Produces a 4-section structured output:
   - Technology Landscape
   - Key Players
   - Citation Network Patterns
   - Licensing & Collaboration Opportunities

**Model initialization:**

```python
GCP_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", "grad-589-588")
VERTEX_LOCATION = os.getenv("VERTEX_AI_LOCATION", "us-central1")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-pro")

@st.cache_resource
def _get_model():
    import vertexai
    from vertexai.generative_models import GenerativeModel
    vertexai.init(project=GCP_PROJECT, location=VERTEX_LOCATION)
    return GenerativeModel(GEMINI_MODEL)
```

The model is lazy-loaded and cached for the process lifetime.

**Building the graph-aware context:**

```python
def build_results_text_with_graph(results_df, ppr_scores, citation_edges, expanded_df):
    lines = []

    # Top 5 results with all three scores
    for i, (_, r) in enumerate(results_df.head(5).iterrows(), 1):
        pub = r["publication_number"]
        lines.append(f"""Result {i}: {pub}
Title: {r['title_text']}
Assignee: {r.get('primary_assignee', 'N/A')}
Abstract: {r['abstract_text'][:500]}
Text Similarity: {sim:.2%} | Graph Importance (PPR): {ppr:.4f} | Blended: {blended:.2%}
---""")

    # Citation edges between results (max 20)
    if citation_edges:
        lines.append("\nCitation relationships between results:")
        for src, tgt, etype in citation_edges:
            lines.append(f"  {src} --[{etype}]--> {tgt}")

    # Shared assignees (companies with 2+ patents in results)
    # ... aggregation logic ...

    # Structurally important patents from expansion (top 3 by PPR)
    # ... expansion logic ...

    return "\n".join(lines)
```

This gives Gemini enough context to reason about the citation network structure, not just text similarity. The prompt explicitly asks it to reference specific patent numbers and assignees -- which makes the output actionable for licensing decisions.

**Caching:** The summary is cached for 1 hour per unique combination of query patent + top 5 results.

---

## 10. Network Graph Visualization

**File:** `app/utils/graph.py`

**Problem:** Visualize patent relationships interactively so users can see citation chains, identify clusters, and understand the structural layout.

**Approach:** Build a Pyvis network graph from the patent data. Nodes represent patents, edges represent relationships (similarity, citations, parent/child). The graph is exported as self-contained HTML and embedded in Streamlit.

**Node types:**

| Type | Shape | Size | Color |
|------|-------|------|-------|
| Query patent | dot | 45px (fixed) | NASA blue (#0B3D91) |
| Search result | dot | 18-50px (score-based) | 6-tier gradient |
| Expanded patent | triangle | 18-50px (PPR-based) | 6-tier gradient |

**Score-based color tiers (accessible, avoids red-green adjacency):**

```python
def _score_color(score):
    pct = score * 100
    if pct >= 95: return "#1a7431"  # Dark green
    if pct >= 90: return "#2E8540"  # Green
    if pct >= 85: return "#4A90D9"  # Blue
    if pct >= 80: return "#F0C419"  # Yellow
    if pct >= 75: return "#FF9D1E"  # Orange
    return "#DD361C"                # Red
```

**3-channel accessibility:** Every patent's relevance is encoded in color + node size + numeric label. This means the information is accessible even for color-blind users.

**Edge types:**

| Relationship | Color | Style | Width |
|-------------|-------|-------|-------|
| Similar (query to result) | Blue (#105BD8) | Solid | 1 + score * 2 |
| Cites | Slate blue (#4773AA) | Dashed | 1 |
| Cited by | Light slate (#8BA6CA) | Dashed | 1 |
| Parent | Orange (#FF9D1E) | Solid | 1.5 |
| Child | Red (#DD361C) | Solid | 1.5 |

**Physics engine configuration:**

```python
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
    }
}"""
```

ForceAtlas2Based was chosen because it handles directed graphs well and produces readable layouts for 20-100 nodes. The gravitational constant of -120 provides enough repulsion to avoid overlap without scattering nodes too far.

**Citation edge caps:** Citations are capped at 10 per direction per patent, parents/children at 5. This prevents a single heavily-cited patent from creating hundreds of edges and making the graph unreadable.

---

## 11. Analytics Charts

**File:** `app/utils/charts.py`

**Problem:** Provide aggregate analytics across the search results -- who are the top assignees, inventors, and what technology areas are represented.

**Approach:** Three Plotly charts, each following the same pattern:

1. **Top 10 Assignees** -- horizontal bar chart (blue gradient)
2. **Top 10 Inventors** -- horizontal bar chart (green gradient)
3. **CPC Technology Distribution** -- vertical bar chart (multi-color)

**Data extraction from nested structs:**

```python
def _extract_names(results_df, column):
    names = []
    for _, row in results_df.iterrows():
        items = _to_list(row.get(column))
        for item in items:
            if isinstance(item, dict):
                name = item.get("name", "")
                if name:
                    names.append(name)
    return names
```

BigQuery returns `assignee_harmonized` and `inventor_harmonized` as arrays of structs like `[{name: "Google LLC", country: "US"}, ...]`. The extraction function handles the nested structure and flattens it to a list of names, which is then counted with `collections.Counter`.

**CPC distribution parsing:**

```python
for _, row in results_df.iterrows():
    cpc = _to_list(row.get("cpc"))
    for entry in cpc:
        if isinstance(entry, dict):
            code = entry.get("code", "")
            if code and code[0].isalpha():
                letters.append(code[0].upper())
```

CPC codes like `H04L63/10` are reduced to their section letter (`H`). Each section maps to a human-readable label (e.g., `H - Electricity`). This gives a quick view of which technology domains the similar patents span.

All charts share a common `BASE_LAYOUT` for consistent styling and use NASA brand colors.

---

## 12. Frontend -- Streamlit Application

**File:** `app/app.py`

**Problem:** Present all the backend outputs in a clean, navigable interface.

**Layout:**

```
Sidebar
  - NASA logo + branding
  - Search form (patent number input + top-K slider)
  - Graph legend (edge colors, node tiers, node shapes)
  - Ranking mode toggle (Blended / Text Similarity / Graph Importance)

Main Content
  - Header banner
  - Status indicator (collapsible progress with normalization feedback)
  - Metrics row (5 cards: Results, Assignees, Inventors, Avg Similarity, Citation Network)
  - Query patent card (metadata + abstract + top terms)
  - AI Analysis (expandable Gemini output)
  - Similar Patents table (sortable, with progress bars for scores)
  - Structurally Important Patents table (if PPR available)
  - Analytics charts (2-column: assignees + inventors, full-width: CPC)
  - Patent Network graph (interactive HTML embed)
  - Download ZIP button
  - Footer
```

**Search flow with normalization:**

The search pipeline starts with a normalization step before querying BigQuery. The status indicator shows intermediate feedback like "Resolving patent number..." and "Resolved `8410469` → `US-8410469-B2`" so the user understands the lookup.

```python
with st.status("Analyzing patents...", expanded=True) as status:
    normalized = normalize_patent_number(pn)
    if normalized is None:
        status.update(label="Patent not found", state="error")
        st.stop()

    if normalized != pn:
        st.write(f"Resolved `{pn}` → `{normalized}`")
    pn = normalized

    results_df = search_patents(pn, tk)
    # ... rest of pipeline
```

**Session state management:**

```python
if submitted and patent_number:
    st.session_state["patent_number"] = patent_number.strip()
    st.session_state["top_k"] = top_k
```

The search form uses `st.form` to batch the patent number and top-K into a single submission. The patent number input accepts multiple formats (e.g., `US-2007156035-A1`, `8410469`, `8,410,469`) with help text explaining this. Values persist in session state across Streamlit reruns.

**Results table with conditional columns:**

```python
base_cols = [
    "publication_number", "title_text", "primary_assignee",
    "primary_inventor", "filed", "similarity_pct",
]

if ppr_available:
    base_cols.extend(["ppr_pct", "blended_pct"])
```

When PPR is available, the table shows three score columns (Similarity, Graph/PPR, Blended) with progress bars. When PPR fails, it shows only Similarity.

**Download packaging:**

```python
buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
    zf.writestr("search_results.csv", csv_data)
    zf.writestr("ai_summary.txt", ai_summary)
    zf.writestr("network_graph.html", graph_html)
```

The ZIP contains three files: the results table as CSV, the AI summary as plain text, and the network graph as a standalone HTML file that can be opened in any browser.

---

## 13. Print / PDF Export Styles

**File:** `app/utils/styles.py`

**Problem:** When users print the page or save as PDF (Ctrl+P / Cmd+P), data tables and charts on the right side are clipped. Streamlit's sidebar takes horizontal space, the `max-width: 1400px` overflows the print page, and `overflow: hidden` on dataframes clips columns.

**Approach:** A `@media print` CSS block at the end of the stylesheet that restructures the layout for paper output.

**Print rules:**

| Rule | Purpose |
|------|---------|
| `@page { size: landscape; margin: 0.5in }` | Landscape orientation for wide tables and charts |
| Hide sidebar, form, download button, iframe | Remove interactive-only elements |
| `.block-container { max-width: 100% }` | Remove 1400px cap, fill full page width |
| `overflow: visible` on dataframes/expanders | Fix right-side column clipping |
| `flex-direction: column` on horizontal blocks | Stack 2-column chart layout vertically |
| `box-shadow: none` on cards/metrics | Remove decorative shadows (saves ink) |
| `break-inside: avoid` on patent cards | Prevent cards from splitting across pages |
| `print-color-adjust: exact` on badges/tags | Force background colors to print |
| Hide footer | Remove footer from print output |

**Key decisions:**
- **Landscape orientation:** Charts and data tables are wide, landscape gives the most usable space.
- **Hide network graph (iframe):** The vis.js interactive canvas typically renders as blank in print. The network graph HTML is included in the download ZIP as an alternative.
- **Hide sidebar:** Contains the search form and legend which aren't useful on a printed report.
- **Stack columns:** Forces the 2-column chart layout into single column so each chart gets the full page width.

Users can also download the complete results as a ZIP (CSV + AI summary + network graph HTML) for sharing.

---

## 14. Caching Strategy

Three levels of caching are used:

| What | Decorator | TTL | Scope |
|------|-----------|-----|-------|
| BigQuery client | `@st.cache_resource` | Process lifetime | Shared across all users |
| Gemini model | `@st.cache_resource` | Process lifetime | Shared across all users |
| Search results | `@st.cache_data(ttl=3600)` | 1 hour | Per (patent_number, top_k) |
| Citation neighbors | `@st.cache_data(ttl=3600)` | 1 hour | Per neighbor_ids tuple |
| AI summary | `@st.cache_data(ttl=3600)` | 1 hour | Per (query_pub, results_text) |

`@st.cache_resource` is used for expensive-to-create objects that should be shared (clients, model handles). `@st.cache_data` is used for function return values that are specific to inputs but can be reused for repeated searches.

The 1-hour TTL means the first search for a given patent takes ~7-9 seconds. Subsequent searches for the same patent within the hour return in under 1 second.

---

## 15. Error Handling and Graceful Degradation

The system is designed so that no failure makes it worse than a basic cosine similarity search.

| Failure | What Happens |
|---------|-------------|
| Patent number normalization fails | Error with suggestion to use full publication format, execution stops |
| Patent not found in BigQuery | Error message displayed, execution stops |
| Citation expansion fails | PPR pipeline is skipped, cosine-only ranking |
| PPR computation fails (no edges, no convergence) | Returns empty scores, cosine-only ranking |
| No expanded neighbors found | "Structurally Important" section is hidden |
| Gemini call fails | Error message shown in summary section |
| BigQuery vector index unavailable | Query degrades to full table scan (slower but still works) |

Implementation pattern:

```python
ppr_available = False
try:
    neighbor_ids = extract_citation_neighbors(results_df)
    if neighbor_ids:
        expanded_df = fetch_citation_neighbors(tuple(neighbor_ids))

    G = build_citation_graph(results_df, expanded_df, pn)
    ppr_scores = compute_ppr(G, pn)

    if ppr_scores:
        search_results = blend_scores(search_results, ppr_scores)
        citation_edges = get_citation_edges(G, result_pubs)
        ppr_available = True
except Exception:
    ppr_available = False
    expanded_df = None
```

The `ppr_available` flag controls all downstream behavior: which Gemini prompt to use, which table columns to show, whether to display the Structurally Important section, and which score column drives graph node colors.

---

## 16. Observability -- Structured Logging

**Files:** All modules (`app.py`, `bigquery_client.py`, `gemini_client.py`, `graph_ranking.py`)

**Problem:** When something fails in production (Cloud Run), we need to understand what happened without being able to reproduce the issue locally.

**Approach:** Python's `logging` module is configured at `INFO` level across all modules. Every significant operation logs its inputs, outputs, and elapsed time.

**What gets logged:**

| Event | Level | Example |
|-------|-------|---------|
| Search initiated | INFO | `Search initiated: input='8410469', top_k=20` |
| Patent normalization | INFO | `Normalized '8410469' -> 'US-8410469-B2'` |
| Normalization failure | WARNING | `Could not resolve '999' to any publication_number` |
| Vector search timing | INFO | `Vector search completed: 15 rows in 3.41s` |
| Citation neighbor fetch | INFO | `Fetching 127 citation neighbors` |
| Graph construction | INFO | `Citation graph built: 42 nodes, 89 edges` |
| PPR computation | INFO | `PPR computed: 42 scores, top 3: [('US-...', '0.142')]` |
| PPR fallback | INFO/ERROR | `PPR skipped: graph has no edges` or `PPR pipeline failed` |
| Gemini request | INFO | `Gemini request: model=gemini-2.5-flash, prompt_length=4521 chars` |
| Gemini response | INFO | `Gemini response: 1823 chars in 2.31s` |
| Total pipeline | INFO | `Analysis complete: 15 results, ppr=True, total=6.82s` |

On Cloud Run, these logs are automatically collected by Cloud Logging and can be viewed in the GCP Console under Logging > Logs Explorer. Filter by `resource.type="cloud_run_revision"` and `resource.labels.service_name="nasa-patent-search"`.

---

## 17. Deployment

**Container:** `python:3.11-slim` base image. The Dockerfile is minimal:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8080/_stcore/health || exit 1
ENTRYPOINT ["streamlit", "run", "app.py", \
    "--server.port=8080", "--server.address=0.0.0.0"]
```

**Deploy command (for team testing):**

```bash
cd app/
gcloud run deploy nasa-patent-search \
  --source . \
  --project grad-589-588 \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 1Gi \
  --cpu 1 \
  --port 8080 \
  --min-instances 0 \
  --max-instances 3 \
  --set-env-vars "GOOGLE_CLOUD_PROJECT=grad-589-588,BIGQUERY_DATASET=patent_research,BIGQUERY_TABLE=us_patents_indexed,VERTEX_AI_LOCATION=us-central1,GEMINI_MODEL=gemini-2.5-flash"
```

Cloud Build handles the Docker build. Cloud Run serves the container. No CI/CD pipeline -- this single command does everything.

**For production (NASA):** Use `--no-allow-unauthenticated` and enable Identity-Aware Proxy (IAP). See `DEPLOYMENT.md` for the full production deployment guide including IAP setup, service accounts, custom domains, and quarterly data maintenance.

**Redeploying after code changes:**

```bash
cd app/
gcloud run deploy nasa-patent-search --source . --project grad-589-588 --region us-central1
```

Zero-downtime rolling update.

---

## 18. Data Schema

**Table:** `grad-589-588.patent_research.us_patents_indexed`

| Column | Type | Notes |
|--------|------|-------|
| `publication_number` | STRING | Primary key (e.g., `US-2007156035-A1`) |
| `application_number` | STRING | Alternative identifier |
| `filing_date` | INTEGER | YYYYMMDD format |
| `publication_date` | INTEGER | YYYYMMDD format |
| `grant_date` | INTEGER | YYYYMMDD, null for applications |
| `title` | STRUCT | `{value: "..."}` |
| `abstract` | STRUCT | `{value: "..."}` |
| `embedding_v1` | ARRAY\<FLOAT64\> | 64-dimensional vector (pre-computed by Google) |
| `primary_assignee` | STRING | First company name |
| `primary_inventor` | STRING | First inventor name |
| `assignee_harmonized` | ARRAY\<STRUCT\> | `[{name: "...", country: "..."}]` |
| `inventor_harmonized` | ARRAY\<STRUCT\> | `[{name: "...", country: "..."}]` |
| `citation` | ARRAY\<STRUCT\> | Patents this one cites `[{publication_number: "..."}]` |
| `cited_by` | ARRAY\<STRUCT\> | Patents that cite this one |
| `parent` | ARRAY\<STRUCT\> | Parent applications |
| `child` | ARRAY\<STRUCT\> | Child applications |
| `cpc` | ARRAY\<STRUCT\> | CPC classification codes `[{code: "H04L63/10"}]` |
| `top_terms` | ARRAY\<STRUCT\> | Extracted keywords `[{value: "neural network"}]` |

**Data source:** Merged from two Google public datasets:
- `patents-public-data.patents.publications` -- core patent metadata + citations
- `patents-public-data.google_patents_research.publications` -- embeddings, top_terms, cited_by

**Filters applied during merge:** US patents only (`country_code = 'US'`), filed after 2006 (`filing_date >= 20060101`), embedding exists (`embedding_v1 IS NOT NULL`).

**Vector index:** BigQuery automatically creates a ScaNN-based index on `embedding_v1` for the `VECTOR_SEARCH` function. The index type is IVF with cosine distance.

---

## 19. Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `GOOGLE_CLOUD_PROJECT` | `grad-589-588` | GCP project for BigQuery + Vertex AI |
| `BIGQUERY_DATASET` | `patent_research` | BigQuery dataset name |
| `BIGQUERY_TABLE` | `us_patents_indexed` | BigQuery table name |
| `VERTEX_AI_LOCATION` | `us-central1` | Vertex AI endpoint region |
| `GEMINI_MODEL` | `gemini-2.5-pro` | Gemini model ID (deployed with `gemini-2.5-flash` for lower cost/latency) |

No secrets are hardcoded. Authentication uses Application Default Credentials (ADC) -- on Cloud Run, the service account is attached automatically. Locally, run `gcloud auth application-default login`.

---

## 20. Performance

| Stage | Cold | Cached |
|-------|------|--------|
| Patent normalization | 0.3-0.5s | N/A (only when input needs resolving) |
| BigQuery vector search | 3.4s | 171ms |
| Citation expansion query | 0.5s | cached |
| PPR computation (in-process) | <100ms | N/A |
| Gemini summarization | 2-3s | cached |
| Charts + graph build | <500ms | N/A |
| **Total end-to-end** | **~7-9s** | **~1s** |

**Query cost:** ~$0.32 per cold search (51.7 GB scanned for vector search + ~10 GB for citation expansion). Cached searches cost nothing.

**Comparison to previous system:** The old architecture (Fall 2025) used a 104GB RAM VM running at $800-1,200/month with 2-5 minute query times. This serverless approach costs $35-40/month with 7-9 second queries.

---

## 21. Dependencies

```
streamlit>=1.38.0                # UI framework
google-cloud-bigquery>=3.25.0    # BigQuery client
google-cloud-aiplatform>=1.60.0  # Vertex AI + Gemini
db-dtypes>=1.2.0                 # BigQuery date/time types
pandas>=2.2.0                    # DataFrames
plotly>=5.22.0                   # Chart rendering
pyvis>=0.3.2                     # Network graph HTML export
networkx>=3.3                    # PageRank computation
```

Install: `pip install -r requirements.txt`

Run locally: `streamlit run app/app.py`

Requires `gcloud auth application-default login` for local BigQuery/Vertex AI access.

---

## Additional Documentation

| Document | Description |
|----------|-------------|
| [`DEPLOYMENT.md`](DEPLOYMENT.md) | Full deployment guide including production setup with IAP, service accounts, and data maintenance |
| [`REQUIREMENTS_TRACEABILITY.md`](REQUIREMENTS_TRACEABILITY.md) | Maps NASA TTO requirements to implementation |
| [`GRAPH_RANKING_PROPOSAL.md`](GRAPH_RANKING_PROPOSAL.md) | Design document for the PageRank integration |
| [`GRAPHRAG_EVALUATION.md`](GRAPHRAG_EVALUATION.md) | Evaluation of graph-based RAG approaches |

## License

Internal project -- Purdue University / NASA Technology Transfer Office.
