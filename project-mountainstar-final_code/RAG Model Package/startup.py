""" Start-up script to load the FAISS and metadata offset indices"""

import pandas as pd
import os
import faiss
import gcsfs
import time


# paths
parquet_path = "gs://capstone_patent_bucket/us_patent_parquets"
FAISS_INDEX_PATH = "gs://capstone_patent_bucket/faiss_index/localsnippetUSPatent/ivfflatnprobe16NLIST1024.faiss"
METADATA_OFFSETS_PATH = "gs://capstone_patent_bucket/faiss_index/localsnippetUSPatent/ivfflat_metadata_offsets.csv" # New cache file
# NEW: Path for the Patent ID to Global Index Map (CHANGED TO .parquet for speed)
PATENT_ID_MAP_PATH = "gs://capstone_patent_bucket/faiss_index/localsnippetUSPatent/patent_id_map.parquet"
# Local cache for FAISS index (shared across runs/processes)
FAISS_CACHE_DIR = os.path.join("faiss_index_cache")
FAISS_LOCAL_INDEX_PATH = os.path.join(
    FAISS_CACHE_DIR,
    "localsnippetUSPatent_ivfflatnprobe16NLIST1024.faiss"
)
os.makedirs(FAISS_CACHE_DIR, exist_ok=True)


# --- Shared state (will be populated by load_indices()) ---
index = None
metadata_offsets = None
offset = None
patent_id_map = None
_loaded = False  # Track whether indices have been loaded

def load_faiss_index(index_path, fs):
    """
    Loads the FAISS IndexIVFFlat via a local cache on disk, using GCS only if needed.

    - Uses FAISS_LOCAL_INDEX_PATH as a shared cache file.
    - Uses a .lock file so multiple processes do not download at the same time.
    """
    print(f"\n--- Attempting to load FAISS index from cache for {index_path} ---")

    local_path = FAISS_LOCAL_INDEX_PATH
    lock_path = local_path + ".lock"

    # Fast path: index already cached locally
    if os.path.exists(local_path):
        try:
            loaded_index = faiss.read_index(local_path)
            print(
                f"FAISS index loaded successfully from cache: "
                f"{local_path} ({loaded_index.ntotal} vectors)."
            )
            return loaded_index
        except Exception as e:
            print(
                f"Error reading local FAISS index at {local_path}: {e}. "
                "Will try to refresh from GCS."
            )

    # Try to become the "builder" that downloads the index
    we_are_builder = False
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
        we_are_builder = True
    except FileExistsError:
        we_are_builder = False

    if we_are_builder:
        try:
            # Validate that the remote file exists in GCS
            path_parts = index_path.replace("gs://", "").split("/", 1)
            if len(path_parts) < 2 or not fs.exists(path_parts[0] + "/" + path_parts[1]):
                print("FAISS index file not found in GCS. Will rebuild.")
                return None

            print(f"Downloading FAISS index from {index_path} to {local_path} ...")
            fs.get(index_path, local_path)

            loaded_index = faiss.read_index(local_path)
            print(
                f"FAISS index loaded successfully from GCS into cache "
                f"({loaded_index.ntotal} vectors)."
            )
            return loaded_index

        except Exception as e:
            print(f"ERROR loading FAISS index from GCS: {e}. Need to rebuild.")
            if os.path.exists(local_path):
                try:
                    os.remove(local_path)
                except OSError:
                    pass
            return None
        finally:
            # Always remove the lock, even if something failed
            try:
                os.remove(lock_path)
            except FileNotFoundError:
                pass
    else:
        # We are a waiter: another process is downloading the index
        print("[FAISS] Another process is downloading the index. Waiting for cache...")
        for _ in range(60):  # wait up to ~120 seconds
            if not os.path.exists(lock_path) and os.path.exists(local_path):
                break
            time.sleep(2)

        if not os.path.exists(local_path):
            print("FAISS index cache not found after waiting. Need to rebuild.")
            return None

        try:
            loaded_index = faiss.read_index(local_path)
            print(
                f"FAISS index loaded successfully from cache after wait: "
                f"{local_path} ({loaded_index.ntotal} vectors)."
            )
            return loaded_index
        except Exception as e:
            print(
                f"ERROR reading FAISS index from cache after wait: {e}. "
                "Need to rebuild."
            )
            return None



def load_offsets(gcs_parquet_path, gcs_offset_path, fs):
    """Tries to load pre-calculated offsets from GCS; calculates and saves them if not found."""
    print(f"\n--- Attempting to load metadata offsets from {gcs_offset_path} ---")
    
    try:
        offsets_df = pd.read_csv(gcs_offset_path, storage_options={'fs': fs})
        loaded_offsets = list(offsets_df.itertuples(index=False, name=None))
        loaded_offset = loaded_offsets[-1][2] if loaded_offsets else 0
        
        print(f"Offsets loaded successfully from GCS. Total records: {loaded_offset:,}")
        return loaded_offsets, loaded_offset
        
    except Exception as e:
        print(f"Error loading offset file: {e}. Need to rebuild.")
        return None, None


def load_patent_id_map(gcs_parquet_path, gcs_map_path, fs):
    """Tries to load pre-calculated patent ID map from GCS; calculates and saves them if not found."""
    print(f"\n--- Attempting to load Patent ID Map from {gcs_map_path} ---")
    
    try:
        map_df = pd.read_parquet(gcs_map_path, storage_options={'fs': fs})
        patent_id_to_global_index = pd.Series(
            map_df.global_index.values, 
            index=map_df.patent_id
        ).to_dict()
        
        print(f"Patent ID Map loaded successfully from GCS. Total IDs: {len(patent_id_to_global_index):,}")
        return patent_id_to_global_index
        
    except Exception as e:
        path_parts = gcs_map_path.replace("gs://", "").split("/", 1)
        if len(path_parts) < 2 or not fs.exists(path_parts[0] + '/' + path_parts[1]):
            print(f"Patent ID Map file not found. Need to recalculate.")
        else:
            print(f"Error loading Patent ID Map file: {e}. Need to recalculate as a fallback.")
        return None

def load_indices():
    """Main function to load all indices. Call this from app.py."""
    global index, metadata_offsets, offset, patent_id_map, _loaded
    
    # Skip if already loaded
    if _loaded:
        print("Indices already loaded, skipping...")
        return index, metadata_offsets, offset, patent_id_map
    
    fs = gcsfs.GCSFileSystem()
    
    try:
        index = load_faiss_index(FAISS_INDEX_PATH, fs)
        if index is None:
            raise RuntimeError("Failed to load FAISS index")
        print(f"✓ FAISS index loaded with {index.ntotal} vectors")
            
        metadata_offsets, offset = load_offsets(parquet_path, METADATA_OFFSETS_PATH, fs)
        if metadata_offsets is None:
            raise RuntimeError("Failed to load metadata offsets")
        print(f"✓ Metadata offsets loaded: {offset:,} records")
            
        patent_id_map = load_patent_id_map(parquet_path, PATENT_ID_MAP_PATH, fs)
        if patent_id_map is None:
            raise RuntimeError("Failed to load patent ID map")
        print(f"✓ Patent ID map loaded: {len(patent_id_map):,} IDs")
        
        print("\n✓ All indices loaded successfully from GCS.")
        _loaded = True
        return index, metadata_offsets, offset, patent_id_map
        
    except Exception as e:
        print(f"ERROR: Failed to load indices: {e}")
        index = None
        metadata_offsets = None
        offset = None
        patent_id_map = None
        return None, None, None, None


# Only run if executed directly (for testing)
if __name__ == "__main__":
    pass













