# Deploying to a New GCP Project

This guide is for the team taking ownership of the NASA Patent Similarity
Search application. It describes everything required to spin the
application up in a fresh Google Cloud project from scratch and operate it
through GitHub Actions.

The application has no project-specific code. All Google Cloud identifiers
are read from environment variables at runtime, and the Cloud Run deploy is
performed by a GitHub Actions workflow. The workflow authenticates to GCP
through Workload Identity Federation, so no service account JSON keys are
ever stored in GitHub or on a developer machine.

The setup work below splits cleanly into three phases:

- **Phase A: GCP setup** (done once by a NASA Cloud admin). Enables APIs,
  creates service accounts, configures Workload Identity Federation,
  loads the patent table, and creates the Scheduled Query that performs
  the recurring data refresh.
- **Phase B: GitHub setup** (done once by a NASA repository admin).
  Stores the GCP identifiers as GitHub Variables and the WIF references as
  GitHub Secrets so the workflows can authenticate.
- **Phase C: Deploy and operate**. Click "Run workflow" in the GitHub
  Actions tab. Subsequent deploys are the same one click.

> Estimated time end to end: about 90 minutes the first time, mostly the
> BigQuery table copy or rebuild running in the background. Subsequent
> deploys are around three minutes each.

---

## Phase A: GCP setup

### A1. Prerequisites

- A GCP project where the application will run. The project ID is referred
  to below as `NASA_PROJECT_ID`.
- A user account with `roles/owner` (or a combination including IAM admin
  and BigQuery admin) on `NASA_PROJECT_ID` for the initial setup.
- The `gcloud` CLI installed locally, or use Cloud Shell.

```bash
export NASA_PROJECT_ID="your-project-id-here"
export REGION="us-central1"
export GITHUB_ORG="your-github-org"
export GITHUB_REPO="nasa-patent-search"

gcloud config set project "$NASA_PROJECT_ID"
```

### A2. Enable required APIs

```bash
gcloud services enable \
  bigquery.googleapis.com \
  bigquerydatatransfer.googleapis.com \
  aiplatform.googleapis.com \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  iamcredentials.googleapis.com \
  sts.googleapis.com \
  --project="$NASA_PROJECT_ID"
```

`iamcredentials` and `sts` are required for the OIDC token exchange used by
Workload Identity Federation. The rest are for the application's own
runtime needs.

### A3. Create the runtime service account

The Cloud Run service runs as a dedicated runtime service account with
only the permissions the application needs at request time.

```bash
gcloud iam service-accounts create patent-search-sa \
  --display-name="Patent Search Runtime" \
  --project="$NASA_PROJECT_ID"

export RUNTIME_SA="patent-search-sa@${NASA_PROJECT_ID}.iam.gserviceaccount.com"

gcloud projects add-iam-policy-binding "$NASA_PROJECT_ID" \
  --member="serviceAccount:$RUNTIME_SA" --role="roles/bigquery.dataViewer"
gcloud projects add-iam-policy-binding "$NASA_PROJECT_ID" \
  --member="serviceAccount:$RUNTIME_SA" --role="roles/bigquery.jobUser"
gcloud projects add-iam-policy-binding "$NASA_PROJECT_ID" \
  --member="serviceAccount:$RUNTIME_SA" --role="roles/aiplatform.user"
gcloud projects add-iam-policy-binding "$NASA_PROJECT_ID" \
  --member="serviceAccount:$RUNTIME_SA" --role="roles/bigquerydatatransfer.user"
```

The last role lets the in-app "Refresh Patent Data" button trigger the
Scheduled Query manually. The button is disabled if the role is missing.

### A4. Create the deploy service account

A separate service account is impersonated by the GitHub Actions workflow
to perform the Cloud Run deploy. Keeping deploy and runtime identities
distinct is standard production practice.

```bash
gcloud iam service-accounts create patent-search-deployer \
  --display-name="Patent Search Deployer (CI)" \
  --project="$NASA_PROJECT_ID"

export DEPLOY_SA="patent-search-deployer@${NASA_PROJECT_ID}.iam.gserviceaccount.com"

# Deploy and update Cloud Run services
gcloud projects add-iam-policy-binding "$NASA_PROJECT_ID" \
  --member="serviceAccount:$DEPLOY_SA" --role="roles/run.admin"

# Required so the deployer can attach the runtime service account to Cloud Run
gcloud iam service-accounts add-iam-policy-binding "$RUNTIME_SA" \
  --member="serviceAccount:$DEPLOY_SA" \
  --role="roles/iam.serviceAccountUser" \
  --project="$NASA_PROJECT_ID"

# Submit Cloud Build jobs (used by `gcloud run deploy --source`)
gcloud projects add-iam-policy-binding "$NASA_PROJECT_ID" \
  --member="serviceAccount:$DEPLOY_SA" --role="roles/cloudbuild.builds.editor"

# Push the built image to Artifact Registry
gcloud projects add-iam-policy-binding "$NASA_PROJECT_ID" \
  --member="serviceAccount:$DEPLOY_SA" --role="roles/artifactregistry.writer"

# Cloud Build needs to write its own logs and stage source
gcloud projects add-iam-policy-binding "$NASA_PROJECT_ID" \
  --member="serviceAccount:$DEPLOY_SA" --role="roles/logging.logWriter"
gcloud projects add-iam-policy-binding "$NASA_PROJECT_ID" \
  --member="serviceAccount:$DEPLOY_SA" --role="roles/storage.objectAdmin"

# So the refresh-data workflow can start manual runs of the Scheduled Query
gcloud projects add-iam-policy-binding "$NASA_PROJECT_ID" \
  --member="serviceAccount:$DEPLOY_SA" --role="roles/bigquerydatatransfer.user"
gcloud projects add-iam-policy-binding "$NASA_PROJECT_ID" \
  --member="serviceAccount:$DEPLOY_SA" --role="roles/bigquery.jobUser"
```

### A5. Configure Workload Identity Federation

This is the keyless authentication setup. GitHub's OIDC token is exchanged
for short-lived credentials that impersonate the deploy service account.
No JSON keys are created, downloaded, or stored.

```bash
# Create a Workload Identity Pool
gcloud iam workload-identity-pools create github-pool \
  --location="global" \
  --display-name="GitHub Actions Pool" \
  --project="$NASA_PROJECT_ID"

# Capture the pool's full resource name
export WIF_POOL_NAME="$(gcloud iam workload-identity-pools describe github-pool \
  --location=global \
  --project="$NASA_PROJECT_ID" \
  --format='value(name)')"

# Add GitHub as an OIDC provider, restricted to a single repository
gcloud iam workload-identity-pools providers create-oidc github-provider \
  --location="global" \
  --workload-identity-pool="github-pool" \
  --display-name="GitHub Actions OIDC" \
  --attribute-mapping="google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.repository=assertion.repository,attribute.repository_owner=assertion.repository_owner" \
  --attribute-condition="assertion.repository_owner == '${GITHUB_ORG}'" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --project="$NASA_PROJECT_ID"

# Allow GitHub Actions runs from the specific repo to impersonate the deploy SA
gcloud iam service-accounts add-iam-policy-binding "$DEPLOY_SA" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/${WIF_POOL_NAME}/attribute.repository/${GITHUB_ORG}/${GITHUB_REPO}" \
  --project="$NASA_PROJECT_ID"

# Capture the provider resource name. Save this; you'll paste it into GitHub.
gcloud iam workload-identity-pools providers describe github-provider \
  --location=global \
  --workload-identity-pool=github-pool \
  --project="$NASA_PROJECT_ID" \
  --format='value(name)'
```

The final command prints something like
`projects/123456789/locations/global/workloadIdentityPools/github-pool/providers/github-provider`.
That value goes into GitHub as the `WIF_PROVIDER` secret.

> **GitHub Enterprise Server:** if NASA runs GHES rather than github.com,
> the `--issuer-uri` is the Actions OIDC URL of the NASA GHES instance,
> not `token.actions.githubusercontent.com`. Confirm with the GHES admin.

### A6. Create the patent table

The application reads from a single BigQuery table. There are two ways to
populate it.

#### Option A: Copy the existing table from the source project

If the team handing off the project still has the populated table, copy it
directly. Server-side copy of the 50 GB table runs in a few minutes.

```bash
bq mk --dataset --project_id="$NASA_PROJECT_ID" patent_research

bq cp \
  grad-589-588:patent_research.us_patents_indexed \
  "$NASA_PROJECT_ID:patent_research.us_patents_indexed"
```

The vector index does not survive a copy; recreate it once the copy
finishes:

```bash
bq query --project_id="$NASA_PROJECT_ID" --use_legacy_sql=false '
CREATE VECTOR INDEX patent_embedding_index
ON `'"$NASA_PROJECT_ID"'.patent_research.us_patents_indexed`(embedding_v1)
OPTIONS(
    index_type = "IVF",
    distance_type = "COSINE",
    ivf_options = "{\"num_lists\": 1000}"
);'
```

#### Option B: Rebuild from the public Google Patents dataset

If the source project is unavailable, rebuild from `patents-public-data`.
The MERGE filters US patents from 2006 onward (about 12 million rows) and
takes the embedding column from the public dataset. Embedding coverage is
100% on US patents, so no rows are dropped because of missing embeddings.
Patents filed before 2006 are intentionally excluded.

```bash
bq mk --dataset --project_id="$NASA_PROJECT_ID" patent_research

bq query --project_id="$NASA_PROJECT_ID" --use_legacy_sql=false '
CREATE TABLE `'"$NASA_PROJECT_ID"'.patent_research.us_patents_indexed` AS
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
    AND base.filing_date >= 20060101;'
```

Then create the vector index (same command as Option A).

### A7. Create the Scheduled Query that performs the refresh

The application does not run the patent refresh itself. A BigQuery
Scheduled Query holds the refresh SQL and is the only thing that performs
the refresh. It runs automatically on a quarterly cron and can be
triggered ad-hoc from three places: the BigQuery console, the in-app
"Refresh Patent Data" button on the Cloud Run service, and the
`refresh-data` GitHub Actions workflow.

Quarterly is the default; adjust `--schedule` to change cadence (the
syntax is the BigQuery Data Transfer schedule grammar: `every quarter`,
`every 30 days`, `every monday 09:00`).

```bash
bq query --project_id="$NASA_PROJECT_ID" --use_legacy_sql=false \
  --schedule="every quarter" \
  --display_name="Patent Data Quarterly Refresh" '
MERGE `'"$NASA_PROJECT_ID"'.patent_research.us_patents_indexed` AS target
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
        target.child = source.child;'
```

After the command runs, look up the resource name of the new Scheduled
Query:

```bash
bq ls --transfer_config --transfer_location="$REGION" --project_id="$NASA_PROJECT_ID"
```

The output includes a `name` like
`projects/12345/locations/us-central1/transferConfigs/abc-uuid`. Save it.
This goes into GitHub as the `REFRESH_TRANSFER_CONFIG` variable and is
also the value passed to the Cloud Run service at runtime.

---

## Phase B: GitHub setup

In the repository's GitHub UI, navigate to **Settings > Secrets and
variables > Actions**.

### B1. GitHub Repository Variables

Variables tab. These are not secret; they are visible to anyone with
repository read access, which is fine because they are GCP identifiers,
not credentials.

| Variable | Example value |
| --- | --- |
| `GCP_PROJECT_ID` | `nasa-patent-search-prod` |
| `GCP_REGION` | `us-central1` |
| `RUNTIME_SERVICE_ACCOUNT` | `patent-search-sa@nasa-patent-search-prod.iam.gserviceaccount.com` |
| `BIGQUERY_DATASET` | `patent_research` |
| `BIGQUERY_TABLE` | `us_patents_indexed` |
| `GEMINI_MODEL` | `gemini-2.5-flash` |
| `REFRESH_TRANSFER_CONFIG` | `projects/12345/locations/us-central1/transferConfigs/abc-uuid` |

### B2. GitHub Repository Secrets

Secrets tab. These are encrypted at rest in GitHub and masked in workflow
logs.

| Secret | Value |
| --- | --- |
| `WIF_PROVIDER` | The full provider resource name printed at the end of step A5, e.g. `projects/123456789/locations/global/workloadIdentityPools/github-pool/providers/github-provider` |
| `WIF_SERVICE_ACCOUNT` | The deploy SA email, e.g. `patent-search-deployer@nasa-patent-search-prod.iam.gserviceaccount.com` |

These two values together let GitHub Actions authenticate without any
JSON key files.

---

## Phase C: Deploy and operate

### C1. Run the deploy workflow

Navigate to the **Actions** tab in the GitHub repository, select the
**Deploy to Cloud Run** workflow, and click **Run workflow** on the `main`
branch. The workflow:

1. Authenticates to GCP via Workload Identity Federation (no key file).
2. Builds the application container with Cloud Build using `app/`.
3. Deploys it to Cloud Run with the runtime service account attached and
   all environment variables set from the GitHub Variables.
4. Prints the public service URL on the last step's log line.

A typical run finishes in about three minutes. Subsequent deploys are
identical: click Run workflow again.

### C2. Verify the deployment

1. Open the Cloud Run URL printed by the workflow.
2. Search for `US-2007156035-A1`. The first result should be the patent
   itself with similarity 100%, followed by other catheter and
   blood-sampling patents. This is the canonical demo patent because its
   neighbors are documented in `BIGQUERY_QUERIES.md`.
3. Open the sidebar. The **Patent Data Refresh** panel shows the last
   refresh time. If the Scheduled Query has run at least once, the panel
   shows the date; otherwise it shows "No previous refresh run is on
   record."
4. If `REFRESH_TRANSFER_CONFIG` is set and the last refresh is older than
   seven days, click **Refresh Patent Data Now**. A toast confirms the job
   started. Reload the page after a few minutes; the timestamp should
   advance.

### C3. Three ways to trigger a manual data refresh

All three trigger the same Scheduled Query and produce the same outcome.

1. **In-app button**: sidebar of the Cloud Run service. Subject to a
   seven-day cooldown to prevent accidental cost. Anyone with access to
   the application URL can use it.
2. **GitHub Actions workflow**: **Refresh Patent Data** in the Actions
   tab. Requires typing `REFRESH` in the confirmation input. Useful when
   admins want to refresh from outside the application.
3. **BigQuery console**: Scheduled Queries page. Open the entry, click
   **Run now**.

The cron schedule on the Scheduled Query (quarterly by default) runs
automatically and is independent of all three manual triggers.

---

## Environment variable reference

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `GOOGLE_CLOUD_PROJECT` | Yes | metadata server | GCP project ID. Falls back to Application Default Credentials if unset. |
| `BIGQUERY_DATASET` | No | `patent_research` | Dataset holding the patent table. |
| `BIGQUERY_TABLE` | No | `us_patents_indexed` | The patent table itself. |
| `VERTEX_AI_LOCATION` | No | `us-central1` | Region for Vertex AI / Gemini calls. |
| `GEMINI_MODEL` | No | `gemini-2.5-flash` | Gemini model id. Stay on 2.5 until 3.x is GA. |
| `REFRESH_TRANSFER_CONFIG` | No | unset | Resource name of the Scheduled Query. The in-app refresh button is hidden when this is unset. |

Copy `app/.env.example` for a local template. The deploy workflow sets
all of these from GitHub Variables, so a local `.env` is only useful for
local development.

---

## Operational notes

**Refresh cadence and cost.** The Scheduled Query runs every quarter by
default. Each run scans the public source datasets and costs a few dollars
on BigQuery on-demand pricing. The in-app manual refresh enforces a
seven-day cooldown so the button cannot be spammed; the cron job is not
subject to the cooldown.

**Measured performance and cost (from the team's `grad-589-588` deployment).**

| Metric | Cold query | Cached query |
| --- | --- | --- |
| BigQuery vector search | 3.4s | 171ms |
| Data scanned | 51.7 GB | 0 bytes |
| Cost per query | ~$0.32 | $0.00 |
| Vector index usage | FULLY_USED | CACHE_HIT |
| Gemini summarization | ~2-3s | cached 1hr |
| **End-to-end (search + summary)** | **~6s** | **~1s** |

| Cost line item | Estimate at NASA production volume |
| --- | --- |
| Cloud Run (min-instances=1, moderate traffic) | $15-30 / month |
| BigQuery storage (~50 GB) | $1 / month |
| BigQuery queries (~500 searches / month) | ~$160 / month |
| Vertex AI / Gemini (~500 calls / month) | ~$0.10 / month |
| Quarterly refresh runs | a few dollars per run |
| **Total** | **~$175-190 / month** |

For comparison, the legacy 104 GB-RAM-VM system cost approximately
$800-1200 / month always-on with 2-5 minute query times. The current
serverless architecture is roughly an order of magnitude cheaper at
production volume and orders of magnitude faster.

**Vector index maintenance.** The vector index updates automatically as
rows are added or modified, so no separate rebuild step is required after
each refresh.

**Failure alerting.** BigQuery Scheduled Queries can be configured to send
an email on failure from the Scheduled Queries UI in the BigQuery console.
Enable this on the created config so failures are not silent.

**Data freshness banner.** The application shows a top-of-page banner if
the last refresh is more than 90 days old. If the banner persists after a
successful refresh, the run state may be `FAILED` rather than `SUCCEEDED`;
check the Scheduled Query history.

**Authentication.** This guide deploys with `--allow-unauthenticated` so
NASA IT can validate the application end to end. Wiring NASA Launchpad
SSO or Identity-Aware Proxy is a separate workstream.

**Gemini model version.** `gemini-2.5-flash` is GA and covered by the
Vertex AI ATO. Gemini 3.x is preview-only as of April 2026 and should not
be used in production until Google announces GA. Once 3.x is GA, switch by
updating the `GEMINI_MODEL` GitHub Variable and re-running the deploy
workflow.

**Continuous deployment.** The deploy workflow currently runs on
`workflow_dispatch` only (manual trigger). When NASA is ready, add
`push: branches: [main]` to enable continuous deployment and consider
gating with a GitHub Environment that requires reviewer approval before
production deploys proceed.
