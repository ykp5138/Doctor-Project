"""Build a separate SapBERT CLS index from ICD-10-CM descriptions.

Writes indexes_sapbert_cls/icd10_embeddings.npy and icd10_metadata.json.
Metadata records pooling, input format, model revision, dimensions, and code-set
provenance so queries use the same representation. Original indexes/ and
indexes_sapbert/ remain available for comparisons and rollback.

Usage: python build_icd_index_sapbert.py [--local-files-only] [--device cuda]
Use --force only to rebuild the separate output index.
"""
import json
import os
import time
import argparse

import numpy as np
import simple_icd_10_cm as cm
from icd_embeddings import make_embedding_config, load_embedding_model, code_set_provenance

MODEL_NAME = "cambridgeltl/SapBERT-from-PubMedBERT-fulltext"
INDEX_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "indexes_sapbert_cls")
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
    parser = argparse.ArgumentParser(description="Build a separate versioned SapBERT index; existing legacy vectors are preserved.")
    parser.add_argument("--output-dir", default=INDEX_DIR)
    parser.add_argument("--pooling", choices=("cls", "legacy_auto"), default="cls")
    parser.add_argument("--text-format", choices=("description", "code_description_parent"), default="description")
    parser.add_argument("--max-seq-length", type=int, default=128)
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    parser.add_argument("--device", default=None)
    parser.add_argument("--revision", default=None)
    parser.add_argument("--local-files-only", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    index_dir = os.path.abspath(args.output_dir)
    project_dir = os.path.dirname(os.path.abspath(__file__))
    protected = {os.path.normcase(os.path.realpath(os.path.join(project_dir, directory)))
                 for directory in ("indexes", "indexes_sapbert")}
    if os.path.normcase(os.path.realpath(index_dir)) in protected:
        raise ValueError("Use a separate output directory; both working legacy indexes are protected.")
    embeddings_path = os.path.join(index_dir, "icd10_embeddings.npy")
    metadata_path = os.path.join(index_dir, "icd10_metadata.json")

    if os.path.exists(embeddings_path) and os.path.exists(metadata_path) and not args.force:
        print(f"SapBERT index already exists:\n  {embeddings_path}\n  {metadata_path}")
        print("Pass --force to rebuild.")
        return

    start = time.time()

    print(f"Loading model '{MODEL_NAME}' (~440MB, downloads on first use)...")
    config = make_embedding_config(MODEL_NAME, pooling=args.pooling, text_format=args.text_format,
                                   max_seq_length=args.max_seq_length, revision=args.revision)
    model = load_embedding_model(config, device=args.device, local_files_only=args.local_files_only)
    config["dimension"] = model.get_sentence_embedding_dimension()
    if not config["revision"]:
        config["revision"] = getattr(model[0].auto_model.config, "_commit_hash", None)
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
        text = description if args.text_format == "description" else build_text(code, description)
        metadata.append({"code": code, "description": description, "text": text})
        texts.append(text)

    print(f"Embedding {len(texts)} codes (batch_size={args.batch_size}, pooling={args.pooling})...")
    embeddings = model.encode(
        texts,
        batch_size=args.batch_size,
        show_progress_bar=True,
        normalize_embeddings=True,
        convert_to_numpy=True,
    ).astype("float32")

    if embeddings.shape != (len(metadata), config["dimension"]) or not np.isfinite(embeddings).all():
        raise ValueError("Invalid generated embedding matrix; index was not saved")
    if not np.allclose(np.linalg.norm(embeddings, axis=1), 1, atol=1e-4):
        raise ValueError("Generated embeddings are not normalized; index was not saved")
    os.makedirs(index_dir, exist_ok=True)
    with open(embeddings_path + ".tmp", "wb") as f:
        np.save(f, embeddings)
    with open(metadata_path + ".tmp", "w", encoding="utf-8") as f:
        json.dump({"schema_version": 2, "model_name": MODEL_NAME, "embedding_config": config,
                   "code_set": code_set_provenance(), "codes": metadata}, f)
    os.replace(embeddings_path + ".tmp", embeddings_path)
    os.replace(metadata_path + ".tmp", metadata_path)

    elapsed = time.time() - start
    print(f"\nDone. Embedded {len(metadata)} codes -> shape {embeddings.shape} (no synonym enrichment)")
    print(f"Saved:\n  {embeddings_path}\n  {metadata_path}")
    print(f"Total elapsed: {elapsed:.1f}s")


if __name__ == "__main__":
    main()
