"""
Build a medical-domain semantic search index over the full ICD-10-CM database
using SapBERT (cambridgeltl/SapBERT-from-PubMedBERT-fulltext), which is pretrained
on UMLS entity-linking pairs and handles drug names / clinical terminology far
better than MiniLM.

Writes, into indexes_sapbert/ (separate from the MiniLM indexes/ so the original
stays intact as a fallback):

    indexes_sapbert/icd10_embeddings.npy  — float32 matrix, shape (N, 768), L2-normalized
    indexes_sapbert/icd10_metadata.json   — {"model_name": "...", "codes": [{code, description, text}, ...]}

The model_name is stored in the metadata so icd10_retriever.py loads the matching
model automatically (MiniLM=384-dim vs SapBERT=768-dim are not interchangeable).

Usage:
    python build_icd_index_sapbert.py          # builds if missing, else exits
    python build_icd_index_sapbert.py --force  # rebuilds even if artifacts exist
"""
import json
import os
import sys
import time

import numpy as np
from sentence_transformers import SentenceTransformer
import simple_icd_10_cm as cm

MODEL_NAME = "cambridgeltl/SapBERT-from-PubMedBERT-fulltext"
INDEX_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "indexes_sapbert")
EMBEDDINGS_PATH = os.path.join(INDEX_DIR, "icd10_embeddings.npy")
METADATA_PATH = os.path.join(INDEX_DIR, "icd10_metadata.json")
BATCH_SIZE = 128  # smaller than MiniLM's 256 — SapBERT is a larger model


def build_text(code: str, description: str) -> str:
    """Build the embedding text for a code, enriching with the parent category when available.
    Same format as the MiniLM builder — no synonym dictionary (testing SapBERT in isolation)."""
    text = f"{code}: {description}"
    try:
        parent = cm.get_parent(code)
        if parent:
            parent_desc = cm.get_description(parent)
            if parent_desc:
                text = f"{code}: {description} (category: {parent_desc})"
    except Exception:
        pass  # Silent fall-back to the simple form
    return text


def main():
    force = "--force" in sys.argv[1:]

    if os.path.exists(EMBEDDINGS_PATH) and os.path.exists(METADATA_PATH) and not force:
        print(f"SapBERT index already exists:\n  {EMBEDDINGS_PATH}\n  {METADATA_PATH}")
        print("Pass --force to rebuild.")
        return

    start = time.time()

    print(f"Loading model '{MODEL_NAME}' (~440MB, downloads on first use)...")
    model = SentenceTransformer(MODEL_NAME)
    print(f"Model loaded on device: {model.device}")

    print("Loading ICD-10-CM codes...")
    codes = cm.get_all_codes(with_dots=True)

    metadata = []
    texts = []
    for code in codes:
        try:
            description = cm.get_description(code)
        except Exception:
            continue  # Skip anything without a resolvable description
        if not description:
            continue
        text = build_text(code, description)
        metadata.append({"code": code, "description": description, "text": text})
        texts.append(text)

    print(f"Embedding {len(texts)} codes (batch_size={BATCH_SIZE})...")
    embeddings = model.encode(
        texts,
        batch_size=BATCH_SIZE,
        show_progress_bar=True,
        normalize_embeddings=True,
        convert_to_numpy=True,
    ).astype("float32")

    os.makedirs(INDEX_DIR, exist_ok=True)
    np.save(EMBEDDINGS_PATH, embeddings)
    with open(METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump({"model_name": MODEL_NAME, "codes": metadata}, f)

    elapsed = time.time() - start
    print(f"\nDone. Embedded {len(metadata)} codes -> shape {embeddings.shape} (no synonym enrichment)")
    print(f"Saved:\n  {EMBEDDINGS_PATH}\n  {METADATA_PATH}")
    print(f"Total elapsed: {elapsed:.1f}s")


if __name__ == "__main__":
    main()
