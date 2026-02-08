"""
Batch processor for patent embeddings - runs as a standalone script
Can be run from terminal and keeps running even if browser closes
"""

import torch
import pandas as pd
import json
import os
from sentence_transformers import SentenceTransformer
from google.cloud import storage, bigquery
import logging
import sys

# Setup logging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('batch_embeddings.log'),  # Save to file
        logging.StreamHandler()  # Also print to console
    ]
)
logger = logging.getLogger(__name__)

os.environ['PYTORCH_CUDA_ALLOC_CONF'] = 'expandable_segments:True'

# Configuration
SOURCE_PROJECT_NAME = 'patent-comparer' # Update to match your project name
SOURCE_BUCKET_NAME = 'capstone_patent_bucket' # Update to match your bucket name
SOURCE_FOLDER_NAME = 'us_patent_parquets' # Should match the parquet file folder

DESTINATION_PROJECT_NAME = 'patent-comparer' # Can be same or different than source
DESTINATION_BUCKET_NAME = 'new_capstone_embeddings' # Can be same or different than source
DESTINATION_FOLDER_NAME = 'us_patent_embeddings'
PROGRESS_FILE_NAME = 'last_batch_processed.txt'

TOTAL_BATCHES = 500
BATCH_SIZE = 1  # Files per batch
DEVICE = "cuda"
EMBED_MODEL_NAME = "all-MiniLM-L6-v2"

def get_last_processed_batch():
    storage_client = storage.Client(project=DESTINATION_PROJECT_NAME)
    bucket = storage_client.bucket(DESTINATION_BUCKET_NAME)
    try:
        blob = bucket.blob(PROGRESS_FILE_NAME)
        if blob.exists():
            content = blob.download_as_text()
            return int(content.strip())
    except Exception as e:
        logger.error(f"Could not read progress file: {e}")
    return -1 # Start from batch 0 if no progress or error

def save_progress(batch_num):
    storage_client = storage.Client(project=DESTINATION_PROJECT_NAME)
    bucket = storage_client.bucket(DESTINATION_BUCKET_NAME)
    try:
        blob = bucket.blob(PROGRESS_FILE_NAME)
        blob.upload_from_string(str(batch_num))
        logger.info(f"Progress saved: processed up to batch {batch_num}")
    except Exception as e:
        logger.error(f"Could not save progress file: {e}")

def get_all_parquet_files():
    """List all parquet files in GCS folder"""
    logger.info("Fetching list of parquet files from GCS...")
    client = storage.Client(project=SOURCE_PROJECT_NAME)
    bucket = client.bucket(SOURCE_BUCKET_NAME)
    blobs = bucket.list_blobs(prefix=f'{SOURCE_FOLDER_NAME}/')
    parquet_files = [f'gs://{SOURCE_BUCKET_NAME}/{blob.name}' for blob in blobs if blob.name.endswith('.parquet')]
    logger.info(f"Found {len(parquet_files)} parquet files in {SOURCE_PROJECT_NAME}")
    return sorted(parquet_files)

def process_batch(parquet_files_batch, embed_model, bq_client, batch_num):
    """Process a batch of parquet files"""
    try:
        logger.info(f"Loading {len(parquet_files_batch)} files...")
        df_batch = pd.concat([pd.read_parquet(file) for file in parquet_files_batch], ignore_index=True)
        logger.info(f"Loaded {len(df_batch):,} rows")

        # Extract Patent IDs
        patent_ids = df_batch[["publication_number", "application_number"]].to_dict('records')
        logger.info(f"Extracted {len(patent_ids):,} patent IDs")

        # Extract titles
        patent_titles = df_batch["title_en"].tolist()

        # Extract abstracts text
        patent_abstracts = df_batch["abstract_en"].tolist()

        # Combine titles with abstracts
        patent_texts = [f"{title} {abstract}" for title, abstract in zip(patent_titles, patent_abstracts)]


        logger.info(f"Creating embeddings for {len(df_batch):,} patents...")
       
        # Process embeddings in chunks to avoid memory crashes
        chunk_size = 750000
        all_embeddings = []
        num_chunks = (len(patent_texts) + chunk_size - 1) // chunk_size
        
        for chunk_idx in range(num_chunks):
            start_idx = chunk_idx * chunk_size
            end_idx = min(start_idx + chunk_size, len(patent_texts))
            chunk = patent_texts[start_idx:end_idx]
            
            logger.info(f"Processing chunk {chunk_idx + 1}/{num_chunks} ({len(chunk)} texts)...")
    
            # Create embeddings
            with torch.inference_mode():
                embeddings = embed_model.encode(
                    chunk,
                    batch_size=1024,
                    convert_to_tensor=True,
                    device="cuda",
                    show_progress_bar=True
                )
        
            all_embeddings.append(embeddings)
            logger.info(f"Chunk {chunk_idx + 1} complete")
        
        # Concatenate all chunks
        logger.info("Concatenating embeddings...")
        embeddings = torch.cat(all_embeddings)
        logger.info(f"All embeddings created: shape {embeddings.shape}")

        # Verify lengths match
        if len(embeddings) != len(patent_ids):
            raise ValueError(f"Mismatch: {len(embeddings)} embeddings but {len(patent_ids)} patent IDs!")
        
        # Save batch as .pt file
        batch_file = f'batch_{batch_num}_data.pt'
        logger.info(f"Saving {len(embeddings):,} embeddings and patent IDs to {batch_file}")

        batch_data = {
            'patent_ids' : patent_ids,
            'embeddings' : embeddings
        }
        torch.save(batch_data, batch_file)
        logger.info(f"Saved batch data to {batch_file}")

        # Upload embeddings to GCS
        logger.info(f"Uploading {batch_file} to GCS...")
        try:
            storage_client = storage.Client(project=DESTINATION_PROJECT_NAME)
            bucket = storage_client.bucket(DESTINATION_BUCKET_NAME)

            # Upload single file
            blob = bucket.blob(f"{DESTINATION_FOLDER_NAME}/{batch_file}")
            blob.upload_from_filename(batch_file)
            logger.info(f"✓ Successfully uploaded {batch_file} to gs://{DESTINATION_BUCKET_NAME}/{DESTINATION_FOLDER_NAME}/{batch_file}")
            
            #Delete local file after successful upload
            try:
                os.remove(batch_file)
                logger.info(f"✓ Deleted local copy of {batch_file} to free disk space")
            except FileNotFoundError:
                logger.warning(f"Local file {batch_file} not found for deletion")
        except Exception as e:
            logger.error(f"Upload failed: {e}")
            raise
        return len(df_batch)
        
    except Exception as e:
        logger.error(f"Error processing batch: {e}")
        raise

def main():
    
    logger.info("="*70)
    logger.info(f"Source: {SOURCE_PROJECT_NAME} / {SOURCE_BUCKET_NAME}")
    logger.info(f"Destination: {DESTINATION_PROJECT_NAME} / {DESTINATION_BUCKET_NAME}")
    logger.info("="*70)
    
    # Initialize
    embed_model = SentenceTransformer(EMBED_MODEL_NAME, device=DEVICE)
    bq_client = bigquery.Client(project=SOURCE_PROJECT_NAME)
    
    # Get files
    parquet_files = get_all_parquet_files()
    
    # Process in batches
    total_batches = (len(parquet_files) + BATCH_SIZE - 1) // BATCH_SIZE
    total_embeddings_created = 0

    start_batch = get_last_processed_batch() + 1

    logger.info(f"START BATCH: Starting with batch {start_batch}")
    
    for batch_num in range(start_batch, total_batches):
        start_idx = batch_num * BATCH_SIZE
        end_idx = start_idx + BATCH_SIZE
        batch = parquet_files[start_idx:end_idx]
        
        logger.info(f"\n{'='*70}")
        logger.info(f"BATCH {batch_num} / {total_batches}")
        logger.info(f"{'='*70}")
        
        try:
            embeddings_created = process_batch(batch, embed_model, bq_client, batch_num)
            total_embeddings_created += embeddings_created
            logger.info(f"Batch {batch_num + 1} complete")
        except Exception as e:
            logger.error(f"Failed on batch {batch_num + 1}. Stopping.")
            sys.exit(1)
        save_progress(batch_num)

    logger.info(f"Successfully created embeddings for {total_embeddings_created:,} patents and uploaded to GCS.")

if __name__ == "__main__":
    main()
