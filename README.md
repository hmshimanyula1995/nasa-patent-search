# NASA Patent Similarity Search Tool

A semantic patent search tool built for NASA's Technology Transfer Office (TTO). Enter a US patent number and get back ranked similar patents, an AI-generated competitive landscape analysis, interactive charts, and a citation network graph.

**Purdue University MSAI Capstone -- Team E (Spring 2026)**

## How It Works

```
User enters patent number (e.g., 8410469)
    |
    v
Patent Number Normalization (resolves plain numbers, commas, prefixes)
    |
    v
BigQuery Vector Search (cosine distance on 64-dim pre-computed embeddings)
    |
    v
Citation Expansion (1-hop neighbors from citation/cited_by/parent/child arrays)
    |
    v
Graph Construction + Personalized PageRank (NetworkX)
    |
    v
Score Blending (60% text similarity + 40% graph importance)
    |
    v
Gemini AI Summary + Plotly Charts + Pyvis Network Graph
    |
    v
Streamlit UI with print/PDF export support
```

## Features

- **Semantic search** -- finds patents by meaning, not just keywords, using Google's pre-computed 64-dimensional embeddings
- **Graph ranking** -- Personalized PageRank on the citation network surfaces structurally important patents that pure text search would miss
- **Flexible input** -- accepts patent numbers in any format: `US-8410469-B2`, `8410469`, `8,410,469`, `US8410469`
- **AI analysis** -- Gemini produces a structured 4-section report covering technology landscape, key players, citation patterns, and licensing opportunities
- **Interactive network graph** -- drag-and-drop patent relationship visualization with color-coded similarity tiers
- **Analytics charts** -- top assignees, top inventors, and CPC technology distribution
- **Print/PDF ready** -- `Ctrl+P` produces a clean landscape layout with full-width tables and stacked charts
- **Download package** -- ZIP file with CSV results, AI summary text, and standalone network graph HTML

## Architecture

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

**No GPU required.** Embeddings are pre-computed by Google in the public `patents-public-data` dataset. The previous system required a 104GB RAM VM -- this serverless approach eliminated that entirely.

## Project Structure

```
app/
  app.py                      # Main Streamlit application
  requirements.txt            # Python dependencies
  Dockerfile                  # Cloud Run container
  .streamlit/config.toml      # Theme + server config
  utils/
    __init__.py
    bigquery_client.py         # BigQuery queries, patent normalization
    gemini_client.py           # Gemini API client + prompt templates
    graph_ranking.py           # PageRank computation + score blending
    graph.py                   # Pyvis network graph generation
    charts.py                  # Plotly chart generation
    styles.py                  # NASA light theme CSS + print styles
```

## Quick Start

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

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `GOOGLE_CLOUD_PROJECT` | `grad-589-588` | GCP project for BigQuery + Vertex AI |
| `BIGQUERY_DATASET` | `patent_research` | BigQuery dataset name |
| `BIGQUERY_TABLE` | `us_patents_indexed` | BigQuery table name |
| `VERTEX_AI_LOCATION` | `us-central1` | Vertex AI endpoint region |
| `GEMINI_MODEL` | `gemini-2.5-pro` | Gemini model ID |

## Performance

| Stage | Cold | Cached |
|-------|------|--------|
| Patent normalization | 0.3-0.5s | -- |
| BigQuery vector search | 3.4s | 171ms |
| Citation expansion | 0.5s | cached |
| PageRank (in-process) | <100ms | -- |
| Gemini summarization | 2-3s | cached |
| Charts + graph | <500ms | -- |
| **Total** | **~7-9s** | **~1s** |

Results are cached for 1 hour. Repeated searches for the same patent return in under 1 second.

## Cost

- **Per-query (cold):** ~$0.32 (BigQuery bytes scanned)
- **Monthly hosting (Cloud Run):** ~$35-40 with min-instances 0
- **Previous system:** $800-1,200/month on a 104GB RAM VM with 2-5 minute query times

## Documentation

| Document | Description |
|----------|-------------|
| [`POC_REFERENCE.md`](POC_REFERENCE.md) | Detailed technical reference covering every component, code snippets, and design decisions |
| [`DEPLOYMENT.md`](DEPLOYMENT.md) | Full deployment guide including production setup with IAP, service accounts, and data maintenance |
| [`REQUIREMENTS_TRACEABILITY.md`](REQUIREMENTS_TRACEABILITY.md) | Maps NASA TTO requirements to implementation |
| [`GRAPH_RANKING_PROPOSAL.md`](GRAPH_RANKING_PROPOSAL.md) | Design document for the PageRank integration |
| [`GRAPHRAG_EVALUATION.md`](GRAPHRAG_EVALUATION.md) | Evaluation of graph-based RAG approaches |

## Dependencies

```
streamlit>=1.38.0                # UI framework
google-cloud-bigquery>=3.25.0    # BigQuery client
google-cloud-aiplatform>=1.60.0  # Vertex AI / Gemini
db-dtypes>=1.2.0                 # BigQuery date/time types
pandas>=2.2.0                    # DataFrames
plotly>=5.22.0                   # Charts
pyvis>=0.3.2                     # Network graph
networkx>=3.3                    # PageRank
```

## License

Internal project -- Purdue University / NASA Technology Transfer Office.
