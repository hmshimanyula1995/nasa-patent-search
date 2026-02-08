#!pip install -q sentence-transformers tqdm pyarrow

import torch
import pandas as pd
import numpy as np
import ast
import glob
import os
from tqdm import tqdm
from sentence_transformers import SentenceTransformer

#Edit these paths below as needed
parquet_path = r"E:\us_patents_parquets\us_patent_parquets"
output_dir = r"E:\us_patents_parquets\USPatentLocalEmbeddings"
os.makedirs(output_dir, exist_ok=True)

device = "cuda" if torch.cuda.is_available() else "cpu"
model_name = "all-MiniLM-L6-v2"
embed_model = SentenceTransformer(model_name, device=device)

batch_size = 512

def extract_text(cell, lang="en"):
    if cell is None or (isinstance(cell, float) and pd.isna(cell)):
        return ""
    if isinstance(cell, np.ndarray):
        cell = cell.tolist()
    if isinstance(cell, str):
        cell = cell.strip()
        if cell in ("", "[]", "nan"):
            return ""
        try:
            cell = ast.literal_eval(cell)
        except Exception:
            return cell
    if isinstance(cell, list):
        if not cell:
            return ""
        for entry in cell:
            if isinstance(entry, dict) and entry.get("language") == lang:
                return entry.get("text", "")
        if isinstance(cell[0], dict):
            return cell[0].get("text", "")
        return str(cell[0])
    if isinstance(cell, dict):
        if cell.get("language") == lang:
            return cell.get("text", "")
        return cell.get("text", "")
    return str(cell)

files = sorted(glob.glob(f"{parquet_path}/*.parquet"))
print(f"Found {len(files)} parquet files")

for i, file in enumerate(tqdm(files, desc="Processing files")):
    try:
        df = pd.read_parquet(file)

        # Use existing 'title_en' and 'abstract_en' if they exist (for the erroring files)
        if "title_en" in df.columns:
            # If the data is already pre-extracted, use it directly
            title_col = df["title_en"]
        elif "title_localized" in df.columns:
            # If the localized column exists, extract the English text
            title_col = df["title_localized"].apply(lambda x: extract_text(x, "en"))
        else:
            # Fallback for completely missing columns
            title_col = pd.Series([""] * len(df))

        df["title_en"] = title_col

        # Apply the same logic to the abstract
        if "abstract_en" in df.columns:
            abstract_col = df["abstract_en"]
        elif "abstract_localized" in df.columns:
            abstract_col = df["abstract_localized"].apply(lambda x: extract_text(x, "en"))
        else:
            abstract_col = pd.Series([""] * len(df))

        df["abstract_en"] = abstract_col

        # Ensure the columns are strings and handle NaNs for embedding
        df["title_en"] = df["title_en"].fillna("").astype(str)
        df["abstract_en"] = df["abstract_en"].fillna("").astype(str)

        texts = (df["title_en"] + ". " + df["abstract_en"]).tolist()

        with torch.inference_mode():
            embeddings = embed_model.encode(
                texts,
                batch_size=batch_size,
                convert_to_tensor=True,
                device=device,
                show_progress_bar=True
            )

        out_path = os.path.join(output_dir, f"embeddings_{i:05d}.pt")
        torch.save(embeddings, out_path)

        del df, texts, embeddings
        torch.cuda.empty_cache()

    except Exception as e:
        print(f"Error processing {file}: {e}")
