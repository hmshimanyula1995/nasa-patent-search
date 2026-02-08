1.	Create an updated joined table in Google BigQuery using the script found in create_joined_BQ_table.docx. This script will pull columns from the Google Patents Publications dataset and the USPTO Publications dataset, filter for English-language abstracts, and create a new table in BigQuery.
    a.	Optional: Add a filter based on publication_date, filing_date, grant_date, or priority_date from the table `patents-public-data.patents.publications`(USPTO data) to only include patents published since the last update.

2.	Once the table is created, export as Parquet files to Google Cloud Storage bucket, folder titled ‘Joined-Parquets’.

3.	Create embeddings from the joined parquets, using the script titled “create_pt_embeddings_batched.py”
    a.	Minimum system requirements: 1x NVIDIA T4 GPU, 16 vCPUs, 104 GB RAM
    b.	System dependencies: torch, pandas, os, sentence-transformers, google-cloud-storage, google-cloud-bigquery, pyarrow
