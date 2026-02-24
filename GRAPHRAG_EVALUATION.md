# GraphRAG & Graph Ranking: Evaluation of Approaches

> **Purpose:** Comprehensive evaluation of graph-based enhancements proposed for the NASA Patent Matching Tool. Documents why the GCP Spanner GraphRAG reference architecture is not suitable, and why a lightweight in-process approach is the correct path.

---

## Table of Contents

1. [Context: What We Have Today](#1-context-what-we-have-today)
2. [What Was Proposed](#2-what-was-proposed)
3. [Evaluation: GCP Spanner GraphRAG Architecture](#3-evaluation-gcp-spanner-graphrag-architecture)
4. [Evaluation: Full Microsoft-Style GraphRAG](#4-evaluation-full-microsoft-style-graphrag)
5. [Evaluation: Third-Party Graph Databases](#5-evaluation-third-party-graph-databases)
6. [Why These Approaches Don't Fit](#6-why-these-approaches-dont-fit)
7. [What Would Actually Help](#7-what-would-actually-help)
8. [Decision Matrix](#8-decision-matrix)

---

## 1. Context: What We Have Today

### Current Pipeline (Single Query Architecture)

```
User enters patent number
  -> BigQuery VECTOR_SEARCH (cosine distance on 64-dim embeddings)
  -> Single DataFrame with all results + metadata
     -> Results table (pure cosine order)
     -> Network graph visualization (pyvis, citation edges)
     -> Assignee/Inventor/CPC charts
     -> Gemini 2.5 Flash summary (top 5 abstracts)
```

**Key characteristics:**
- **1 BigQuery call** for all similarity matching
- **1 Gemini call** for AI summary
- **0 embedding generation** at query time (pre-computed by Google)
- **0 reranking** — results ordered purely by cosine distance
- **Total latency:** 3-8 seconds
- **Monthly cost:** ~$10-50
- **GCP services used:** BigQuery, Vertex AI (Gemini), Cloud Run

### Data Already Available in BigQuery

The `us_patents_indexed` table already contains:

| Column | Type | Graph Relevance |
|--------|------|-----------------|
| `embedding_v1` | ARRAY<FLOAT64> (64-dim) | Vector similarity (already used) |
| `citation` | ARRAY<STRUCT> | Backward citations (patents THIS cites) |
| `cited_by` | ARRAY<STRUCT> | Forward citations (patents that cite THIS) |
| `parent` | ARRAY<STRUCT> | Parent applications (patent family) |
| `child` | ARRAY<STRUCT> | Child applications (patent family) |
| `assignee_harmonized` | ARRAY<STRUCT> | Companies (entity nodes) |
| `inventor_harmonized` | ARRAY<STRUCT> | Inventors (entity nodes) |
| `cpc` | ARRAY<STRUCT> | Technology classification codes |
| `top_terms` | ARRAY<STRUCT> | Extracted keywords |

**We already have a natural knowledge graph.** Patents are nodes. Citations, family relationships, shared assignees, shared inventors, and shared CPC codes are edges. This graph exists explicitly in the structured data — it does not need to be extracted from unstructured text.

---

## 2. What Was Proposed

### Proposal A: Personalized PageRank (Professor's Suggestion)

Add graph ranking using Personalized PageRank (PPR) to score patents by structural importance in the citation network, seeded from the query patent. Color graph nodes by PPR rank. Provide dual ranking (text similarity + graph importance).

### Proposal B: GCP Spanner GraphRAG Reference Architecture

Use Google's reference architecture for GraphRAG on Spanner:
- **Reference:** https://docs.cloud.google.com/architecture/gen-ai-graphrag-spanner
- Spanner Graph for knowledge graph + vector storage
- Vertex AI for embeddings, LLM, and Agent Engine orchestration
- Cloud Run Functions for data ingestion
- Pub/Sub for event-driven processing
- Full ingestion pipeline: documents -> entity extraction -> knowledge graph -> community detection -> summaries

### Proposal C: Full Microsoft-Style GraphRAG

Offline preprocessing pipeline that extracts entities from patent text, builds a knowledge graph, runs community detection (Leiden algorithm), pre-generates community summaries, and uses those summaries at query time for richer LLM context.

---

## 3. Evaluation: GCP Spanner GraphRAG Architecture

### What It's Designed For

The Spanner GraphRAG reference architecture solves: **"I have unstructured documents (PDFs, reports, articles) and need to build a knowledge graph from scratch to enable graph-aware retrieval."**

Its ingestion pipeline:
1. Upload documents to Cloud Storage
2. Pub/Sub triggers Cloud Run Function
3. Function uses Gemini + LangChain to extract entities and relationships from raw text
4. Text converted to vector embeddings via Vertex AI
5. Graph nodes, edges, and embeddings stored in Spanner Graph
6. At query time: vector search + graph traversal + ranking + LLM summary

### Why It Doesn't Fit Our Problem

#### 3.1 We Don't Need Entity Extraction

The most expensive and complex part of this architecture is the ingestion pipeline that uses an LLM to extract entities and relationships from unstructured text. **Our data is already structured.**

| What Spanner GraphRAG extracts via LLM | What we already have in BigQuery |
|---|---|
| "Company X is mentioned in this document" | `assignee_harmonized` array with company names |
| "Person Y is associated with this work" | `inventor_harmonized` array with inventor names |
| "Document A references Document B" | `citation` and `cited_by` arrays with patent numbers |
| "This document is about Topic Z" | `cpc` classification codes and `top_terms` |
| "Document A is a derivative of Document C" | `parent` and `child` arrays |

Using an LLM to extract what already exists as structured fields is redundant and introduces extraction errors.

#### 3.2 We Don't Need Spanner

Spanner Graph is a globally distributed, strongly consistent database designed for multi-region, high-write-throughput workloads. Our application:

- Has **one region** (us-central1)
- Has **zero writes** at query time (read-only search)
- Has **quarterly batch updates** (not continuous ingestion)
- Already has all data in **BigQuery** with a vector index

Migrating to Spanner would mean:
- Duplicating data from BigQuery to Spanner
- Paying for Spanner nodes (~$0.90/node-hour minimum = ~$650/month minimum)
- Managing a second database
- Losing BigQuery's native `VECTOR_SEARCH` which already works

#### 3.3 We Don't Need the Event-Driven Pipeline

The reference architecture uses Pub/Sub + Cloud Run Functions for event-driven document ingestion. Our data pipeline is:

```sql
-- Quarterly scheduled query in BigQuery
MERGE INTO us_patents_indexed
USING (SELECT ... FROM patents-public-data) AS source
ON target.publication_number = source.publication_number
WHEN NOT MATCHED THEN INSERT (...)
```

One scheduled SQL query. No event-driven architecture needed.

#### 3.4 Cost Comparison

| Component | Spanner GraphRAG | Our Current System |
|-----------|-----------------|-------------------|
| Database | Spanner (~$650+/mo) | BigQuery (~$10-20/mo) |
| Ingestion | Cloud Run Functions + Pub/Sub (~$20-50/mo) | Scheduled BigQuery query (~$1/quarter) |
| LLM for entity extraction | Gemini calls per document (~varies) | Not needed (data is structured) |
| LLM for summaries | Gemini (~$0.001/query) | Gemini (~$0.001/query) |
| Embeddings | Vertex AI Embeddings API | Pre-computed (free) |
| Agent Engine | Vertex AI Agent Engine (~$50+/mo) | Not needed |
| **Monthly total** | **~$750-1,000+** | **~$10-50** |

**15-100x cost increase for capabilities we don't need.**

#### 3.5 Latency Impact

| Step | Spanner GraphRAG | Our Current System |
|------|-----------------|-------------------|
| Vector search | Spanner vector query (~2-4s) | BigQuery VECTOR_SEARCH (~2-5s) |
| Graph traversal | Spanner GQL (~1-3s) | Not applicable (currently) |
| Ranking API | Vertex AI Search (~1-2s) | Not applicable (cosine order) |
| LLM summary | Gemini (~2-3s) | Gemini (~2-3s) |
| **Total** | **~6-12s** | **~3-8s** |

No latency improvement. Potentially worse due to multi-service hops.

---

## 4. Evaluation: Full Microsoft-Style GraphRAG

### What It Entails

1. **Offline pipeline:** Process all patents through entity extraction, build a knowledge graph, run Leiden community detection, pre-generate community summaries
2. **Storage:** Maintain the knowledge graph + community summaries in a graph database or indexed store
3. **Query time:** Identify relevant communities, pull summaries, feed to LLM

### Why It Doesn't Fit

#### 4.1 Scale of Preprocessing

Our table has millions of US patents. Running entity extraction + community detection on millions of documents is a substantial batch processing job that would need to be repeated quarterly when new patents are added. This is the kind of pipeline that took the legacy system hours on a GPU VM — exactly what we eliminated by moving to BigQuery.

#### 4.2 Our Graph Already Exists

Microsoft GraphRAG builds knowledge graphs from unstructured text because the documents don't have explicit relationships. Patents do. The citation graph, family relationships, assignee overlaps, and CPC classification hierarchy are all explicit structured data. Building a second knowledge graph on top of data that is already a knowledge graph adds complexity without new information.

#### 4.3 Community Detection is Interesting but Heavy

Running Leiden or Louvain community detection on the patent citation graph could identify technology clusters. However:

- It requires the full graph in memory or a graph database
- Results need to be pre-computed and stored
- Communities change as new patents are added (quarterly recomputation)
- For a capstone project with a defined scope, this is a significant infrastructure addition

---

## 5. Evaluation: Third-Party Graph Databases

### Options Considered

| Tool | Integration | Cost | Fit |
|------|------------|------|-----|
| **Neo4j (AuraDB)** | Native graph, Cypher queries, has PageRank | ~$65+/mo (AuraDB Pro) | Over-engineered for our subgraph |
| **PuppyGraph** | Sits on top of BigQuery, Gremlin/openCypher | Enterprise pricing | Adds a service layer we don't need |
| **Amazon Neptune** | AWS graph database | Wrong cloud provider | Not applicable |
| **TigerGraph** | Enterprise graph analytics | Enterprise pricing | Massive overkill |

### Why They Don't Fit

Our graph operation is: **run Personalized PageRank on a subgraph of 100-500 nodes at query time.** This takes milliseconds in NetworkX (a Python library). Adding a dedicated graph database for this operation is like buying a forklift to move a chair.

If we were running PageRank on the **entire** patent citation graph (millions of nodes) at query time, a graph database would make sense. But we're not — we're running it on a small subgraph extracted from our BigQuery results.

---

## 6. Why These Approaches Don't Fit

### The Core Mismatch

All three heavy approaches (Spanner GraphRAG, Microsoft GraphRAG, dedicated graph DB) solve the problem of **"I need to build and manage a knowledge graph."** Our problem is: **"I already have a knowledge graph in BigQuery and want to run one graph algorithm on a small subgraph at query time."**

```
Their problem:  Unstructured docs -> Extract entities -> Build graph -> Query graph
Our problem:    Structured patent data -> Already a graph -> Run PPR on subgraph
```

### Summary Table

| Approach | Solves Our Problem? | New GCP Services | Monthly Cost Delta | Implementation Time | Maintenance Burden |
|----------|-------------------|-----------------|-------------------|--------------------|--------------------|
| Spanner GraphRAG | No — solves a different problem entirely | Spanner, Pub/Sub, Cloud Run Functions, Agent Engine | +$700-950/mo | 4-8 weeks | High (multi-service) |
| Microsoft GraphRAG | Partially — community detection is useful, but pipeline is heavy | Depends on implementation | +$200-500/mo | 6-12 weeks | High (batch pipeline) |
| Neo4j / Graph DB | Overkill — subgraph is too small to justify | External service | +$65-200/mo | 2-4 weeks | Medium |
| **NetworkX in-process** | **Yes — directly solves the PPR requirement** | **None** | **+$0** | **1-2 weeks** | **None (pip dependency)** |

---

## 7. What Would Actually Help

See **[GRAPH_RANKING_PROPOSAL.md](./GRAPH_RANKING_PROPOSAL.md)** for the recommended implementation approach.

**Preview:** NetworkX PPR in the existing Python process + enriched Gemini prompt with graph context. Zero new GCP services, zero new infrastructure, zero additional monthly cost.

---

## 8. Decision Matrix

### Evaluation Criteria (Weighted)

| Criterion | Weight | Spanner GraphRAG | Microsoft GraphRAG | Graph DB (Neo4j) | NetworkX In-Process |
|-----------|--------|-----------------|-------------------|------------------|-------------------|
| Solves the stated problem | 25% | 2/10 | 5/10 | 7/10 | **9/10** |
| Implementation effort | 20% | 2/10 | 2/10 | 5/10 | **9/10** |
| Operational cost | 15% | 1/10 | 3/10 | 5/10 | **10/10** |
| Maintenance burden | 15% | 2/10 | 3/10 | 5/10 | **9/10** |
| Latency impact | 10% | 4/10 | 5/10 | 6/10 | **8/10** |
| Architectural simplicity | 10% | 2/10 | 3/10 | 5/10 | **9/10** |
| Capstone scope feasibility | 5% | 1/10 | 2/10 | 6/10 | **10/10** |
| **Weighted Score** | **100%** | **2.3** | **3.5** | **5.6** | **9.2** |

### Verdict

**NetworkX in-process is the correct approach.** It directly solves the professor's requirement (Personalized PageRank + graph-colored nodes), uses existing data, adds zero infrastructure, and can be implemented in 1-2 weeks.

The GCP Spanner GraphRAG architecture is designed for a fundamentally different problem (building knowledge graphs from unstructured documents) and would add ~$700+/month in costs for capabilities we already have natively in our BigQuery data.
