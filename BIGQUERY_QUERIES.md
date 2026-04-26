# BigQuery Queries Reference

> All queries used to build and validate the NASA Patent Matching Tool data layer. Run these in order.
>
> **Canonical deploy path:** the `MERGE` and table creation queries used during a NASA handover are also documented in [`MIGRATION.md`](MIGRATION.md), parameterized by `NASA_PROJECT_ID`. This file uses the literal `grad-589-588` project ID and is intended as the team-internal reference. If the two ever drift, MIGRATION.md is the source of truth.

---

## 1. Schema Exploration

**Purpose:** Verify what columns exist in the public patent tables before building our own.

```sql
SELECT *
FROM `patents-public-data.patents.publications`
LIMIT 1;
```

**What we learned:** The `patents-public-data.patents.publications` table contains all bibliographic data: `publication_number`, `application_number`, `filing_date`, `publication_date`, `grant_date`, `assignee_harmonized`, `inventor_harmonized`, `citation` (backward), `parent`, `child`, `cpc`, and more.

The `patents-public-data.google_patents_research.publications` table contains research-grade fields: `title` (already English-extracted), `abstract` (already English-extracted), `embedding_v1` (pre-calculated 64-dim vector), `cited_by` (forward citations), and `top_terms`.

---

## 2. Initial Table Creation (First Attempt)

**Purpose:** Create our indexed patent table by JOINing the two public tables. This was our first pass.

```sql
CREATE OR REPLACE TABLE `grad-589-588.patent_research.us_patents_indexed` AS
SELECT
    base.publication_number,
    base.filing_date,
    res.title,
    res.abstract,
    res.embedding_v1,
    res.cited_by,
    res.top_terms,
    base.assignee_harmonized[SAFE_OFFSET(0)].name AS primary_assignee,
    base.inventor_harmonized[SAFE_OFFSET(0)].name AS primary_inventor
FROM `patents-public-data.patents.publications` AS base
INNER JOIN `patents-public-data.google_patents_research.publications` AS res
    ON base.publication_number = res.publication_number
WHERE base.country_code = 'US'
    AND res.embedding_v1 IS NOT NULL
    AND base.filing_date >= 20060101;
```

**What it solved:** Got us a working table with embeddings for vector search.

**What was missing:** Only extracted the first assignee/inventor (not the full list). No backward citations, no parent/child connections, no CPC codes, no application number, no publication/grant dates. Not enough for production.

---

## 3. Production Table Creation (Final)

**Purpose:** Complete table with every field needed to satisfy all of Dennis's requirements from the partner meeting.

```sql
CREATE OR REPLACE TABLE `grad-589-588.patent_research.us_patents_indexed` AS
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
WHERE base.country_code = 'US'
    AND res.embedding_v1 IS NOT NULL
    AND base.filing_date >= 20060101;
```

**What each field covers:**

| Field | Source Table | Why We Need It |
|-------|-------------|----------------|
| `publication_number` | publications | Patent identifier, primary key for searches |
| `application_number` | publications | Alternative search key (some patents searched by application number) |
| `filing_date` | publications | 20-year window filter, timeline display |
| `publication_date` | publications | When the patent went public, timeline display |
| `grant_date` | publications | When the patent was granted (null for applications) |
| `title` | research | Display, Gemini summarization input (pre-extracted English) |
| `abstract` | research | Display, Gemini summarization input (pre-extracted English) |
| `embedding_v1` | research | 64-dim vector for BigQuery Vector Search |
| `cited_by` | research | Forward citations: "patents that cite THIS patent" |
| `citation` | publications | Backward citations: "patents THIS patent cites" |
| `parent` | publications | Parent applications (continuations, divisionals) |
| `child` | publications | Child applications |
| `assignee_harmonized` | publications | Full assignee array for "top 10 assignees" charts |
| `inventor_harmonized` | publications | Full inventor array for "top 10 inventors" charts |
| `primary_assignee` | publications | First assignee for quick display (no array parsing needed) |
| `primary_inventor` | publications | First inventor for quick display |
| `cpc` | publications | CPC codes for technology area distribution charts |
| `top_terms` | research | Keywords for word clouds and topic analysis |

**Filters applied:**
- `country_code = 'US'` - US patents only (Dennis confirmed: "just stay at the US")
- `embedding_v1 IS NOT NULL` - only patents with pre-calculated embeddings (required for vector search)
- `filing_date >= 20060101` - rolling 20-year window (Dennis: "only needs to go back like 20 years")

---

## 4. Vector Search Index Creation

**Purpose:** Create an IVF index on the embedding column so BigQuery can perform fast approximate nearest neighbor searches instead of brute-force scanning every row.

```sql
CREATE VECTOR INDEX patent_embedding_index
ON `grad-589-588.patent_research.us_patents_indexed`(embedding_v1)
OPTIONS(
    index_type = 'IVF',
    distance_type = 'COSINE',
    ivf_options = '{"num_lists": 1000}'
);
```

**Check index build status:**

```sql
SELECT *
FROM `grad-589-588.patent_research.INFORMATION_SCHEMA.VECTOR_INDEXES`
WHERE table_name = 'us_patents_indexed';
```

Wait for `coverage_percentage` to reach 100% before running search queries. Index creation can take several minutes depending on table size.

**Why these options:**

### Distance Type: `COSINE`

| Option | What It Measures | When To Use |
|--------|-----------------|-------------|
| `COSINE` | Angle between vectors (direction) | Text embeddings where meaning = direction. This is ours. |
| `EUCLIDEAN` | Straight-line distance (magnitude matters) | Image features, spatial data. Wrong for text. |
| `DOT_PRODUCT` | Requires pre-normalized vectors | Adds unnecessary complexity for no benefit here. |

Google's `embedding_v1` vectors encode semantic meaning as direction, not magnitude. Two patents about "catheter blood sampling" point in similar directions regardless of abstract length. COSINE captures that. EUCLIDEAN would penalize patents with different vector magnitudes even if they're about the same topic.

### Index Type: `IVF`

| Option | How It Works | Speed | Accuracy | Best For |
|--------|-------------|-------|----------|----------|
| `IVF` | Divides vectors into clusters, searches nearby clusters only | Fast | Tunable | Predictable, tunable behavior. Our choice. |
| `TREE_AH` | Tree + asymmetric hashing (Google's ScaNN) | Faster on very large/high-dim data | High | Very high dimensionality (256+, 768+) |
| No index | Brute-force scan of every row | Slowest | Perfect (100%) | Small tables only |

Our embeddings are 64-dimensional. At this dimensionality, IVF is efficient and gives direct control over speed vs accuracy. TREE_AH's advantages appear at higher dimensions (256+). IVF is the right call.

### num_lists: `1000`

Controls how many clusters the index creates. At query time, only nearest clusters are searched.

- **More clusters** = faster search, might miss relevant results
- **Fewer clusters** = slower search, more accurate

Rule of thumb: `sqrt(N)` to `4 * sqrt(N)` where N = row count.

For ~4 million US patents: `sqrt(4,000,000) = ~2,000`. Valid range: **1,000 to 8,000**.

We chose 1,000 (conservative end) because Dennis makes business decisions based on these results. He reaches out to companies saying "we see you have a portfolio in this space." Missing a relevant patent matters more than shaving 200ms off a query that already runs in seconds.

**Tuning reference (if needed later):**

| Setting | Behavior |
|---------|----------|
| `"num_lists": 500` | More accurate, slightly slower |
| `"num_lists": 1000` | Balanced (current choice) |
| `"num_lists": 2000` | Faster, slightly less accurate |

At our scale, the difference is marginal. We're coming from a system that took minutes. All of these return in seconds.

---

## 5. Test Queries

### 5a. Basic Vector Search

**Purpose:** Verify that vector search works and returns sensible results. Replace the publication number with any patent in your table.

```sql
SELECT
    base.publication_number,
    base.title,
    base.primary_assignee,
    base.primary_inventor,
    base.filing_date,
    distance
FROM VECTOR_SEARCH(
    TABLE `grad-589-588.patent_research.us_patents_indexed`,
    'embedding_v1',
    (
        SELECT embedding_v1
        FROM `grad-589-588.patent_research.us_patents_indexed`
        WHERE publication_number = 'US-2007156035-A1'
    ),
    top_k => 10,
    distance_type => 'COSINE'
)
ORDER BY distance;
```

**What to check:** The first result should be the query patent itself (distance = 0). The remaining results should be semantically related. For the catheter patent `US-2007156035-A1`, you should see other medical device / IV catheter / blood sampling patents.

**Verified result (Feb 2026):**

| # | publication_number | title | primary_assignee | distance |
|---|---|---|---|---|
| 1 | US-2007156035-A1 | Catheter operable to deliver IV fluids... | SALUS CORP D B A ICP MEDICAL | 0.0 |
| 2 | US-2007219438-A1 | Catheter operable to deliver iv fluids... | SALUS CORP D B A ICP MEDICAL | 0.0027 |
| 3 | US-8348844-B2 | Automated blood sampler and analyzer | KUNJAN KISLAYA | 0.132 |
| 4 | US-2010137778-A1 | Automated Blood Sampler and Analyzer | KUNJAN KISLAYA | 0.137 |
| 5 | US-2023225645-A1 | Cannula sensing system | CHASE ARNOLD | 0.143 |
| 6 | US-2012016213-A1 | Blood test strip and an intravenous catheter system | BURKHOLZ JONATHAN KARL | 0.146 |
| 7 | US-8747333-B2 | Blood test strip and an intravenous catheter system | BURKHOLZ JONATHAN KARL | 0.149 |
| 8 | US-8383044-B2 | Blood sampling device | BECTON DICKINSON CO | 0.149 |
| 9 | US-2009018483-A1 | Infrared Sample Chamber | WALKER STEPHEN D | 0.153 |
| 10 | US-2011009717-A1 | Blood sampling device | BECTON DICKINSON CO | 0.154 |

Result #1 is the query patent itself (distance 0). Result #2 is a continuation filing by the same assignee/inventor (distance ~0). Results #3-10 are all semantically related medical device / blood sampling patents. Becton Dickinson (major medical device company) appears twice. Search quality confirmed.

### 5b. Full Results With All Fields

**Purpose:** Verify every field comes back correctly in a search result.

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
        WHERE publication_number = 'US-2007156035-A1'
    ),
    top_k => 20,
    distance_type => 'COSINE'
)
ORDER BY distance;
```

**What to check:**
- `assignee_harmonized` returns an array (not null, not empty for most results)
- `inventor_harmonized` returns an array
- `cited_by` and `citation` return arrays (may be empty for some patents)
- `cpc` returns classification codes
- `abstract` is English text (not localized JSON)
- `distance` values make sense (lower = more similar)

### 5c. Top 10 Assignees Chart Data

**Purpose:** Verify we can generate the "top 10 assignees by hit count" chart that Dennis asked for.

```sql
WITH search_results AS (
    SELECT base.assignee_harmonized, distance
    FROM VECTOR_SEARCH(
        TABLE `grad-589-588.patent_research.us_patents_indexed`,
        'embedding_v1',
        (
            SELECT embedding_v1
            FROM `grad-589-588.patent_research.us_patents_indexed`
            WHERE publication_number = 'US-2007156035-A1'
        ),
        top_k => 100,
        distance_type => 'COSINE'
    )
)
SELECT
    assignee.name AS assignee_name,
    COUNT(*) AS patent_count
FROM search_results,
    UNNEST(assignee_harmonized) AS assignee
WHERE assignee.name IS NOT NULL AND assignee.name != ''
GROUP BY assignee_name
ORDER BY patent_count DESC
LIMIT 10;
```

**What to check:** Returns company/organization names with counts. For a medical device patent, you should see medical companies like Becton Dickinson, Medtronic, Abbott, etc.

### 5d. Top 10 Inventors Chart Data

**Purpose:** Verify we can generate the "top 10 lead innovators" chart that Dennis asked for.

```sql
WITH search_results AS (
    SELECT base.inventor_harmonized, distance
    FROM VECTOR_SEARCH(
        TABLE `grad-589-588.patent_research.us_patents_indexed`,
        'embedding_v1',
        (
            SELECT embedding_v1
            FROM `grad-589-588.patent_research.us_patents_indexed`
            WHERE publication_number = 'US-2007156035-A1'
        ),
        top_k => 100,
        distance_type => 'COSINE'
    )
)
SELECT
    inventor.name AS inventor_name,
    COUNT(*) AS patent_count
FROM search_results,
    UNNEST(inventor_harmonized) AS inventor
WHERE inventor.name IS NOT NULL AND inventor.name != ''
GROUP BY inventor_name
ORDER BY patent_count DESC
LIMIT 10;
```

**What to check:** Returns inventor names with counts. Names should be real people, not empty strings or garbage data.

**Verified result (Feb 2026):**

| # | inventor_name | patent_count |
|---|---|---|
| 1 | WILKINSON BRADLEY M | 29 |
| 2 | MARCHIARULLO DANIEL J | 25 |
| 3 | ROTHENBERG ASHLEY RACHEL | 13 |
| 4 | GELFAND CRAIG A | 12 |
| 5 | FLETCHER GARY D | 12 |
| 6 | SAMSOONDAR JAMES | 9 |
| 7 | BURKHOLZ JONATHAN KARL | 8 |
| 8 | HOANG MINH QUANG | 6 |
| 9 | DAVIS BRYAN G | 6 |
| 10 | MA YIPING | 6 |

Real inventor names with meaningful counts. Davis Bryan G (from Becton Dickinson in the basic search results) shows up here too with 6 patents. Data is consistent across queries.

### 5e. CPC Technology Distribution

**Purpose:** Verify CPC code data for technology area charts.

```sql
WITH search_results AS (
    SELECT base.cpc, distance
    FROM VECTOR_SEARCH(
        TABLE `grad-589-588.patent_research.us_patents_indexed`,
        'embedding_v1',
        (
            SELECT embedding_v1
            FROM `grad-589-588.patent_research.us_patents_indexed`
            WHERE publication_number = 'US-2007156035-A1'
        ),
        top_k => 100,
        distance_type => 'COSINE'
    )
)
SELECT
    SUBSTR(cpc_entry.code, 1, 1) AS cpc_section,
    COUNT(*) AS count
FROM search_results,
    UNNEST(cpc) AS cpc_entry
WHERE cpc_entry.code IS NOT NULL
GROUP BY cpc_section
ORDER BY count DESC;
```

**What to check:** Returns single-letter CPC sections (A-H, Y) with counts. For a medical device patent, section A (Human Necessities) should be dominant.

### 5f. Citation Network Data (Starburst Graph)

**Purpose:** Verify we have the citation data needed to build the interactive network graph.

```sql
WITH search_results AS (
    SELECT
        base.publication_number,
        base.title,
        base.cited_by,
        base.citation,
        base.parent,
        base.child,
        distance
    FROM VECTOR_SEARCH(
        TABLE `grad-589-588.patent_research.us_patents_indexed`,
        'embedding_v1',
        (
            SELECT embedding_v1
            FROM `grad-589-588.patent_research.us_patents_indexed`
            WHERE publication_number = 'US-2007156035-A1'
        ),
        top_k => 10,
        distance_type => 'COSINE'
    )
)
SELECT
    publication_number,
    title,
    ARRAY_LENGTH(cited_by) AS forward_citation_count,
    ARRAY_LENGTH(citation) AS backward_citation_count,
    ARRAY_LENGTH(parent) AS parent_count,
    ARRAY_LENGTH(child) AS child_count,
    distance
FROM search_results
ORDER BY distance;
```

**What to check:** At least some results should have non-zero citation counts. This data feeds the starburst network graph.

---

## 6. Quarterly Update Query (Scheduled)

**Purpose:** Add newly filed patents to the table without rebuilding from scratch. Schedule this in BigQuery as a recurring query every 3 months.

```sql
MERGE `grad-589-588.patent_research.us_patents_indexed` AS target
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
    WHERE base.country_code = 'US'
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
```

**What it does:** Inserts patents that don't already exist in the table, and refreshes the citation/family arrays on existing patents (because forward citations grow over time as later patents reference earlier ones). This is the "incremental upsert" Dennis asked for ("just update the database with newly issued patents").

**Scheduling:** Set this up as a BigQuery Scheduled Query to run quarterly (every 3 months). Dennis confirmed: "quarterly is fine." The application's in-app refresh button and `.github/workflows/refresh-data.yml` both trigger this same Scheduled Query rather than running the SQL directly, so all three refresh paths produce identical results.

---

## Query Execution Order

| Step | Query | Run When |
|------|-------|----------|
| 1 | Schema exploration | Once (already done) |
| 2 | Production table creation | Once (initial setup) |
| 3 | Vector index creation | Once (after table is created) |
| 4 | Test queries 5a-5f | Once (verify everything works) |
| 5 | Quarterly update (MERGE) | Every 3 months (scheduled) |
