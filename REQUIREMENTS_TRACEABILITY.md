# Requirements Traceability Matrix

> Maps every stakeholder, professor, and proposal requirement to its implementation in code. Updated with the PPR graph ranking feature.

---

## 1. Stakeholder Requirements (Dennis / NASA TTO Partner Meeting)

These requirements come from the partner meeting with Dennis, documented in `BIGQUERY_QUERIES.md`.

| ID | Requirement | Source Quote | Status | Implementation | Notes |
|----|-------------|-------------|--------|----------------|-------|
| S-1 | US patents only | "just stay at the US" | Done | `bigquery_client.py` — `WHERE base.country_code = 'US'` in table creation query | Filter applied at data layer |
| S-2 | 20-year rolling window | "only needs to go back like 20 years" | Done | `bigquery_client.py` — `WHERE base.filing_date >= 20060101` in table creation query | Quarterly update preserves this filter |
| S-3 | Top 10 assignees by hit count | Partner meeting requirement | Done | `app/utils/charts.py:create_assignee_chart()` renders Plotly bar chart from `assignee_harmonized` array | Displayed in Analytics section |
| S-4 | Top 10 lead innovators (inventors) | Partner meeting requirement | Done | `app/utils/charts.py:create_inventor_chart()` renders Plotly bar chart from `inventor_harmonized` array | Displayed in Analytics section |
| S-5 | CPC technology area distribution | Partner meeting requirement | Done | `app/utils/charts.py:create_cpc_chart()` renders CPC section distribution | Displayed in Analytics section |
| S-6 | Quarterly database updates | "just update the database with newly issued patents" | Done | `BIGQUERY_QUERIES.md` section 6 — `MERGE INTO` scheduled query inserts new patents without rebuilding | Incremental upsert, no full rebuild |
| S-7 | AI-generated summary of results | Dennis wants actionable insights for licensing | Done | `app/utils/gemini_client.py:generate_summary()` calls Gemini 2.5 Pro with graph-aware prompt | Graph-aware prompt produces structured analysis with licensing recommendations |
| S-8 | Interactive citation network graph | Visualize patent relationships | Done | `app/utils/graph.py:build_network_html()` builds pyvis directed graph with citation/family edges | Nodes colored by score, sized by importance |
| S-9 | Downloadable results | Export search results for offline review | Done | `app/app.py:492-507` — ZIP download with CSV, AI summary text, and network graph HTML | Single download button |
| S-10 | Patent number as search input | Dennis searches by publication number | Done | `app/app.py:59-63` — text input in sidebar form | Validated and stripped before query |

---

## 2. Professor's Requirements (Graph Ranking)

From the professor's suggestion documented in `GRAPHRAG_EVALUATION.md` section 2 and `GRAPH_RANKING_PROPOSAL.md`.

| ID | Requirement | Status | Implementation | Notes |
|----|-------------|--------|----------------|-------|
| P-1 | Add Personalized PageRank as a ranking signal | Done | `app/utils/graph_ranking.py:compute_ppr()` — NetworkX PPR seeded from query patent with alpha=0.85 | Falls back to empty dict if no edges or convergence fails |
| P-2 | Color graph nodes by PPR rank | Done | `app/utils/graph.py:build_network_html()` — `score_column` param accepts `ppr_score` or `blended_score` | 6-tier color gradient via `_score_color()` |
| P-3 | Dual ranking (text similarity + graph importance) | Done | `app/utils/graph_ranking.py:blend_scores()` — `blended = 0.6 * cosine + 0.4 * ppr_normalized` | Alpha=0.6 default, configurable |
| P-4 | Use existing structured citation data (not entity extraction) | Done | `app/utils/graph_ranking.py:build_citation_graph()` uses `citation`, `cited_by`, `parent`, `child` arrays from BigQuery | Zero LLM calls for graph construction |
| P-5 | In-process computation (no new GCP services) | Done | `networkx` pip dependency only — PPR computed in Cloud Run process | Zero new infrastructure, zero additional monthly cost |
| P-6 | Graceful degradation to cosine-only on failure | Done | `app/app.py:175-201` — `try/except` around entire PPR pipeline; `ppr_available` flag gates all graph features | System never gets worse than pure cosine |

---

## 3. Proposal Section 7 — Graph-Aware Gemini Prompt Requirements

From `GRAPH_RANKING_PROPOSAL.md` section 7.

| ID | Requirement | Status | Implementation | Notes |
|----|-------------|--------|----------------|-------|
| PR-1 | Include PPR scores alongside similarity in prompt | Done | `gemini_client.py:build_results_text_with_graph()` line 144 — `Text Similarity: {sim:.2%} \| Graph Importance (PPR): {ppr:.4f} \| Blended: {blended:.2%}` | Raw PPR float + blended percentage |
| PR-2 | Include citation relationships between results | Done | `gemini_client.py:build_results_text_with_graph()` lines 148-157 — citation edges formatted as `src --[type]--> tgt`, capped at 20 | Only edges where both endpoints are in result set |
| PR-3 | Include shared assignee data | Done | `gemini_client.py:build_results_text_with_graph()` lines 160-169 — assignee counts from top 10 results, filtered to those with >1 patent | Sorted by count descending |
| PR-4 | Include structurally important patents from expansion | Done | `gemini_client.py:build_results_text_with_graph()` lines 172-185 — top 3 expanded patents by PPR score | Only shown if expanded_df is non-empty |
| PR-5 | Ask Gemini to identify foundational vs derivative patents | Done | `gemini_client.py:GRAPH_AWARE_PROMPT` — "Technology Landscape" section: "which patents are foundational and which are derivative" | Structured section header |
| PR-6 | Ask Gemini to note citation-network-discovered patents | Done | `gemini_client.py:GRAPH_AWARE_PROMPT` — "Citation Network Patterns" section: "note patents discovered through citation network analysis" | Explicit instruction |
| PR-7 | Ask Gemini to suggest licensing opportunities | Done | `gemini_client.py:GRAPH_AWARE_PROMPT` — "Licensing & Collaboration Opportunities" section with specific logic: "If structurally foundational, flag assignee as priority target" | References specific patent numbers |
| PR-8 | Explain PPR scores in the prompt | Done | `gemini_client.py:GRAPH_AWARE_PROMPT` — "Higher PPR scores mean the patent is more structurally central in the citation network" | In-prompt interpretation for the LLM |
| PR-9 | Structured output sections (not essay prose) | Done | `gemini_client.py:GRAPH_AWARE_PROMPT` — 4 markdown headers: Technology Landscape, Key Players, Citation Network Patterns, Licensing & Collaboration Opportunities | Concise 4-6 paragraph cap |
| PR-10 | Cluster analysis in prompt | Done | `gemini_client.py:GRAPH_AWARE_PROMPT` — "identify clusters of patents that cite each other" | In Citation Network Patterns section |
| PR-11 | Technology evolution narrative | Done | `gemini_client.py:GRAPH_AWARE_PROMPT` — "Describe how the technology has evolved based on the citation relationships" | In Technology Landscape section |
| PR-12 | Actionable specificity requirement | Done | `gemini_client.py:GRAPH_AWARE_PROMPT` — "Every recommendation should reference a specific patent number or assignee name" | Closing instruction |

---

## 4. Proposal Section 8 — UI Requirements

From `GRAPH_RANKING_PROPOSAL.md` section 8.

| ID | Requirement | Status | Implementation | Notes |
|----|-------------|--------|----------------|-------|
| UI-1 | Ranking toggle (Text Similarity / Graph Importance / Blended) | Done | `app/app.py:112-117` — `st.radio` with 3 options, default "Blended" | Controls sort column and node coloring |
| UI-2 | PPR score column in results table | Done | `app/app.py:388-400` — `ppr_pct` ProgressColumn when `ppr_available` is True | Labeled "Graph (PPR)" |
| UI-3 | Blended score column in results table | Done | `app/app.py:395-400` — `blended_pct` ProgressColumn | Labeled "Blended" |
| UI-4 | "Structurally Important Patents" section below main results | Done | `app/app.py:415-457` — separate dataframe for expanded patents sorted by `ppr_pct` descending, top 10 | Triangle-shaped nodes in graph distinguish these |
| UI-5 | Node sizing by score | Done | `app/utils/graph.py:134` — `node_size = 18 + int(score * 32)` | Higher scores = larger nodes |
| UI-6 | Toggle controls node coloring source | Done | `app/app.py:226-237` — `score_col` set based on `ranking_mode`; passed to `build_network_html()` as `score_column` | Seamless switching between all 3 modes |
| UI-7 | Citation Network metric card | Done | `app/app.py:285-286` — `m5.metric("Citation Network", f"+{expanded_count}")` | Shows count of expanded patents |
| UI-8 | Graph legend in sidebar | Done | `app/app.py:83-109` — edge colors, node score tiers, node shapes (dot vs triangle) | Matches actual rendering |

---

## 5. Proposal Section 13 — Stakeholder Questions Status

From `GRAPH_RANKING_PROPOSAL.md` section 13. These are questions the proposal recommended asking stakeholders before implementation.

| ID | Question | Answer / Status | Impact on Implementation |
|----|----------|-----------------|-------------------------|
| Q-1 | Discovery intent: "same technology" vs "foundational/influential"? | Assumed "both" — implemented blended ranking as default | Alpha=0.6 balances text and graph; toggle allows pure cosine or pure PPR |
| Q-2 | Do users follow citation chains manually? | Not yet asked — PPR automates this regardless | PPR provides the value whether they do it manually or not |
| Q-3 | Single ranked list or toggle? | Implemented toggle (3 modes) | Users can choose their preferred view |
| Q-4 | Value of structurally important non-similar patents? | Assumed yes — implemented "Structurally Important Patents" section | Separate section below main results with clear labeling |

---

## 6. Accessibility Requirements

From `app/utils/graph.py` and the proposal's accessibility considerations.

| ID | Requirement | Status | Implementation | Notes |
|----|-------------|--------|----------------|-------|
| A-1 | 6-tier color gradient (not binary red/green) | Done | `graph.py:_score_color()` — 6 tiers: #1a7431, #2E8540, #4A90D9, #F0C419, #FF9D1E, #DD361C | Avoids pure red-green adjacency |
| A-2 | 3-channel redundancy: color + size + numeric label | Done | `graph.py:build_network_html()` — node color from `_score_color()`, size from `18 + int(score * 32)`, label includes `{score_pct}%` | Any single channel is sufficient |
| A-3 | Shape differentiation for expansion patents | Done | `graph.py:build_network_html()` — search results are `shape="dot"`, expanded patents are `shape="triangle"` | Additional visual channel beyond color |
| A-4 | Hover tooltips with full context | Done | `graph.py:build_network_html()` — `title` param includes patent number, title, assignee, and score | Accessible via mouse hover |

---

## 7. Graceful Degradation Requirements

From `GRAPH_RANKING_PROPOSAL.md` section 11 (Risk Assessment).

| ID | Failure Scenario | Fallback Behavior | Implementation |
|----|-----------------|-------------------|----------------|
| GD-1 | Citation expansion query fails | Skip PPR, use cosine-only ranking | `app.py:198-201` — `except Exception: ppr_available = False` |
| GD-2 | PPR computation fails (no convergence) | Return empty scores, use cosine-only | `graph_ranking.py:117` — `except PowerIterationFailedConvergence: return {}` |
| GD-3 | Graph has no edges (isolated patent) | PPR returns empty dict, cosine-only | `graph_ranking.py:99` — `if G.number_of_edges() == 0: return {}` |
| GD-4 | No expanded neighbors found | No structural section shown, normal results | `app.py:178-179` — `if neighbor_ids:` guard; empty `expanded_df` skips structural section |
| GD-5 | Graph-aware Gemini prompt fails | Never happens — prompt is just a string template; if Gemini itself fails, error message returned | `gemini_client.py:105-106` — `except Exception as e: return f"Summary generation failed: {e}"` |
| GD-6 | PPR scores are uniform (no structural signal) | PPR column shows 100% for all; blended still works because cosine breaks ties | `graph_ranking.py:133-134` — `if max_val == min_val: return {k: 1.0 for k in scores}` |

---

## 8. Model & Prompt Configuration

| ID | Configuration | Value | Rationale |
|----|--------------|-------|-----------|
| C-1 | Gemini model | `gemini-2.5-pro` (default, env-overridable via `GEMINI_MODEL`) | Better structured reasoning for 4-section analysis; same API, no code changes |
| C-2 | PPR damping factor (alpha) | 0.85 | Standard PageRank value; 15% teleport back to query patent |
| C-3 | Blending alpha (cosine weight) | 0.6 | 60% text similarity, 40% graph importance; preserves user expectations while surfacing structural outliers |
| C-4 | Citation expansion cap | 500 patents | Prevents oversized BigQuery queries on highly-cited patents |
| C-5 | Citation edges in prompt | Capped at 20 | Keeps prompt token count manageable |
| C-6 | Expanded patents in prompt | Top 3 by PPR | Most structurally important only |

---

## File Index

All files involved in the implementation:

| File | Role |
|------|------|
| `app/app.py` | Main Streamlit application — orchestrates pipeline, renders UI |
| `app/utils/bigquery_client.py` | BigQuery queries — vector search + citation expansion |
| `app/utils/gemini_client.py` | Gemini API client — prompts + summary generation |
| `app/utils/graph_ranking.py` | PPR computation — graph construction, PageRank, score blending |
| `app/utils/graph.py` | Network visualization — pyvis graph with accessible coloring |
| `app/utils/charts.py` | Plotly charts — assignee, inventor, CPC distributions |
| `app/utils/styles.py` | CSS — NASA light theme styling |
| `app/requirements.txt` | Python dependencies (includes `networkx`) |
