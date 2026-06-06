"""
One-time build of a semantic search index over the full ICD-10-CM code database.

Embeds every code (with its description and parent category) using
all-MiniLM-L6-v2 and writes two artifacts consumed by icd10_retriever.py:

    indexes/icd10_embeddings.npy  — float32 matrix, shape (N, 384), L2-normalized
    indexes/icd10_metadata.json   — list of {code, description, text} in row order

Usage:
    python build_icd_index.py          # builds if missing, else exits
    python build_icd_index.py --force  # rebuilds even if artifacts exist
"""
import json
import os
import sys
import time

import numpy as np
from sentence_transformers import SentenceTransformer
import simple_icd_10_cm as cm

MODEL_NAME = "all-MiniLM-L6-v2"
INDEX_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "indexes")
EMBEDDINGS_PATH = os.path.join(INDEX_DIR, "icd10_embeddings.npy")
METADATA_PATH = os.path.join(INDEX_DIR, "icd10_metadata.json")
BATCH_SIZE = 256


def build_text(code: str, description: str) -> str:
    """Build the embedding text for a code, enriching with the parent category when available."""
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
        print(f"Index already exists:\n  {EMBEDDINGS_PATH}\n  {METADATA_PATH}")
        print("Pass --force to rebuild.")
        return

    start = time.time()

    print(f"Loading model '{MODEL_NAME}'...")
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
        json.dump(metadata, f)

    elapsed = time.time() - start
    print(f"\nDone. Embedded {len(metadata)} codes -> shape {embeddings.shape}")
    print(f"Saved:\n  {EMBEDDINGS_PATH}\n  {METADATA_PATH}")
    print(f"Total elapsed: {elapsed:.1f}s")


if __name__ == "__main__":
    main()
