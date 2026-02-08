# Deployment Guide: NASA Patent Matching Tool

## Performance Baseline (Measured)

| Metric | Cold Query | Cached Query |
|--------|-----------|-------------|
| BigQuery vector search | 3.4s | 171ms |
| Data scanned | 51.7 GB | 0 bytes |
| Cost per query | ~$0.32 | $0.00 |
| Vector index usage | FULLY_USED | CACHE_HIT |
| Gemini summarization | ~2-3s | cached 1hr |
| **End-to-end (search + summary)** | **~6s** | **~1s** |

For comparison, the old system took 2-5 minutes per search.

---

## Option 1: Quick Deploy for Teammates (Cloud Run)

This gets the app live in ~5 minutes. Anyone with the URL can access it.

### Prerequisites

- `gcloud` CLI installed and authenticated
- Docker (or let Cloud Build handle it)
- Access to `grad-589-588` project

### Steps

```bash
cd app/

# Build and deploy in one command (Cloud Build + Cloud Run)
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

This will:
1. Build the Docker image using Cloud Build
2. Push it to Google Container Registry
3. Deploy to Cloud Run
4. Return a public URL like `https://nasa-patent-search-xxxxx-uc.a.run.app`

Share that URL with your team. Done.

### Cost Estimate (Teammate Testing)

| Resource | Monthly Cost |
|----------|-------------|
| Cloud Run (min-instances=0) | $0 when idle, ~$5-10 with light use |
| BigQuery queries (~100 searches) | ~$32 |
| Gemini API (~100 calls) | ~$0.02 |
| **Total** | **~$35-40/month** |

---

## Option 2: Production Deploy for NASA

NASA would have their own GCP project. The app connects to BigQuery and Vertex AI, so we need to either replicate the data or grant cross-project access.

### Architecture

```
NASA GCP Project
├── Cloud Run (hosts the Streamlit app)
├── BigQuery (copy of us_patents_indexed table)
├── Vertex AI (Gemini API access)
├── IAP (Identity-Aware Proxy for authentication)
├── Cloud Scheduler (quarterly data refresh)
└── Cloud Monitoring (alerts, dashboards)
```

### Step 1: Replicate Data to NASA Project

```bash
# Copy the patent table to NASA's project
bq cp \
  grad-589-588:patent_research.us_patents_indexed \
  NASA_PROJECT_ID:patent_research.us_patents_indexed

# Recreate the vector index in NASA's project
bq query --project_id=NASA_PROJECT_ID --use_legacy_sql=false '
CREATE VECTOR INDEX patent_embedding_index
ON `NASA_PROJECT_ID.patent_research.us_patents_indexed`(embedding_v1)
OPTIONS(
    index_type = "IVF",
    distance_type = "COSINE",
    ivf_options = "{\"num_lists\": 1000}"
);
'
```

### Step 2: Deploy with Authentication (IAP)

Identity-Aware Proxy (IAP) restricts access to authorized NASA users only. No custom auth code needed.

```bash
# Deploy WITHOUT --allow-unauthenticated
gcloud run deploy nasa-patent-search \
  --source . \
  --project NASA_PROJECT_ID \
  --region us-central1 \
  --no-allow-unauthenticated \
  --memory 1Gi \
  --cpu 1 \
  --port 8080 \
  --min-instances 1 \
  --max-instances 10 \
  --set-env-vars "GOOGLE_CLOUD_PROJECT=NASA_PROJECT_ID,BIGQUERY_DATASET=patent_research,BIGQUERY_TABLE=us_patents_indexed,VERTEX_AI_LOCATION=us-central1,GEMINI_MODEL=gemini-2.5-flash"
```

Then enable IAP:

```bash
# Enable IAP on the Cloud Run service
gcloud iap web enable \
  --resource-type=cloud-run \
  --service=nasa-patent-search \
  --project=NASA_PROJECT_ID

# Grant access to specific NASA users/groups
gcloud iap web add-iam-policy-binding \
  --resource-type=cloud-run \
  --service=nasa-patent-search \
  --member="group:tto-team@nasa.gov" \
  --role="roles/iap.httpsResourceAccessor" \
  --project=NASA_PROJECT_ID

# Or grant to individual users
gcloud iap web add-iam-policy-binding \
  --resource-type=cloud-run \
  --service=nasa-patent-search \
  --member="user:dennis@nasa.gov" \
  --role="roles/iap.httpsResourceAccessor" \
  --project=NASA_PROJECT_ID
```

Users will see a Google sign-in page before reaching the app. Only authorized accounts get through. Zero code changes needed in the app.

### Step 3: Custom Domain (Optional)

```bash
# Map a custom domain
gcloud run domain-mappings create \
  --service nasa-patent-search \
  --domain patents.nasa-tto.gov \
  --region us-central1 \
  --project NASA_PROJECT_ID
```

Then add the DNS records Google provides to NASA's domain registrar.

---

## Authentication Options Summary

| Method | Effort | Best For |
|--------|--------|----------|
| `--allow-unauthenticated` | None | Teammate POC, demos |
| **IAP (Identity-Aware Proxy)** | Low (CLI only) | **NASA production** |
| Cloud Run + OAuth proxy | Medium | Custom login flow |
| Streamlit auth (st.login) | Medium | Built-in user management |

**Recommendation for NASA: IAP.** It uses Google Workspace / Cloud Identity accounts. NASA employees sign in with their Google account. No code changes. Managed by GCP IAM policies.

---

## Service Account Permissions

The Cloud Run service needs a service account with these roles:

```bash
# Create a dedicated service account
gcloud iam service-accounts create patent-search-sa \
  --display-name="Patent Search App" \
  --project=NASA_PROJECT_ID

SA_EMAIL="patent-search-sa@NASA_PROJECT_ID.iam.gserviceaccount.com"

# Grant BigQuery access
gcloud projects add-iam-policy-binding NASA_PROJECT_ID \
  --member="serviceAccount:$SA_EMAIL" \
  --role="roles/bigquery.dataViewer"

gcloud projects add-iam-policy-binding NASA_PROJECT_ID \
  --member="serviceAccount:$SA_EMAIL" \
  --role="roles/bigquery.jobUser"

# Grant Vertex AI access
gcloud projects add-iam-policy-binding NASA_PROJECT_ID \
  --member="serviceAccount:$SA_EMAIL" \
  --role="roles/aiplatform.user"

# Deploy with this service account
gcloud run services update nasa-patent-search \
  --service-account=$SA_EMAIL \
  --project=NASA_PROJECT_ID \
  --region=us-central1
```

---

## Quarterly Data Maintenance

The patent database needs quarterly updates. Set up a scheduled BigQuery MERGE:

### Step 1: Create the Scheduled Query

```bash
bq query --project_id=NASA_PROJECT_ID --use_legacy_sql=false \
  --schedule="every quarter" \
  --display_name="Patent Data Quarterly Refresh" '
MERGE `NASA_PROJECT_ID.patent_research.us_patents_indexed` AS target
USING (
    SELECT
        base.publication_number,
        base.application_number,
        base.filing_date,
        base.publication_date,
        base.grant_date,
        res.title,
        res.abstract,
        res.embedding_v1,
        res.cited_by,
        base.citation,
        base.parent,
        base.child,
        base.assignee_harmonized,
        base.inventor_harmonized,
        base.assignee_harmonized[SAFE_OFFSET(0)].name AS primary_assignee,
        base.inventor_harmonized[SAFE_OFFSET(0)].name AS primary_inventor,
        base.cpc,
        res.top_terms
    FROM `patents-public-data.patents.publications` AS base
    INNER JOIN `patents-public-data.google_patents_research.publications` AS res
        ON base.publication_number = res.publication_number
    WHERE base.country_code = "US"
        AND res.embedding_v1 IS NOT NULL
        AND base.filing_date >= 20060101
) AS source
ON target.publication_number = source.publication_number
WHEN NOT MATCHED THEN
    INSERT ROW
WHEN MATCHED THEN
    UPDATE SET
        target.cited_by = source.cited_by,
        target.citation = source.citation,
        target.parent = source.parent,
        target.child = source.child;
'
```

### Step 2: Set Up Monitoring Alerts

```bash
# Alert if Cloud Run error rate exceeds 5%
gcloud monitoring policies create \
  --notification-channels=CHANNEL_ID \
  --display-name="Patent Search Error Rate" \
  --condition-display-name="High Error Rate" \
  --condition-filter='resource.type="cloud_run_revision" AND metric.type="run.googleapis.com/request_count" AND metric.labels.response_code_class!="2xx"'

# Alert if BigQuery scheduled query fails
gcloud monitoring policies create \
  --notification-channels=CHANNEL_ID \
  --display-name="Patent Data Refresh Failed" \
  --condition-display-name="Scheduled Query Failure" \
  --condition-filter='resource.type="bigquery_resource" AND severity>=ERROR'
```

---

## Maintenance Checklist

### Automatic (No Action Needed)
- Cloud Run scales to zero when idle (no cost)
- Cloud Run auto-scales on traffic spikes
- BigQuery query cache handles repeated searches
- Vector index is maintained by BigQuery automatically
- SSL/TLS certificates are managed by Cloud Run

### Quarterly
- Scheduled MERGE query runs automatically
- Verify new patents were added: check row count before/after
- Vector index auto-rebuilds after data changes (may take minutes)

### As Needed
- Update Gemini model version if Google deprecates current one
- Monitor BigQuery costs in billing dashboard
- Review IAP access list when NASA team members change
- Update app code: rebuild and redeploy with `gcloud run deploy`

### Redeploying After Code Changes

```bash
cd app/
gcloud run deploy nasa-patent-search \
  --source . \
  --project NASA_PROJECT_ID \
  --region us-central1
```

That is it. Cloud Build rebuilds the Docker image and Cloud Run performs a rolling update with zero downtime.

---

## Cost Estimate: NASA Production

| Resource | Monthly Estimate |
|----------|-----------------|
| Cloud Run (min-instances=1, moderate traffic) | $15-30 |
| BigQuery storage (us_patents_indexed, ~50GB) | $1 |
| BigQuery queries (~500 searches/month) | ~$160 |
| Gemini API (~500 calls/month) | ~$0.10 |
| IAP | Free |
| Cloud Scheduler | Free tier |
| **Total** | **~$175-190/month** |

Compared to the old system: 104GB RAM VM running 24/7 = ~$800-1200/month.

---

## Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `GOOGLE_CLOUD_PROJECT` | `grad-589-588` | GCP project ID |
| `BIGQUERY_DATASET` | `patent_research` | BigQuery dataset name |
| `BIGQUERY_TABLE` | `us_patents_indexed` | BigQuery table name |
| `VERTEX_AI_LOCATION` | `us-central1` | Vertex AI region |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model ID |
