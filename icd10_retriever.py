"""
Semantic retrieval over the ICD-10-CM code database.

Loads the embeddings + metadata produced by build_icd_index.py and serves
top-k cosine-similarity lookups via a FAISS inner-product index. Use the
module-level get_retriever() singleton so the model and index load once per
process rather than per request.
"""
import json
import os
import re

import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Which index the live retriever uses:
#   "indexes"          -> MiniLM only (legacy)
#   "indexes_sapbert"  -> SapBERT only
#   "hybrid"           -> query both and merge (production default)
ACTIVE_INDEX_DIR = "hybrid"
MINILM_DIR = "indexes"
SAPBERT_DIR = "indexes_sapbert"

# Fallback embedding model for legacy list-shape metadata (the original MiniLM
# index stored no model_name); newer indexes record their model in the metadata.
DEFAULT_MODEL_NAME = "all-MiniLM-L6-v2"


# --- Query-side expansion for drug/procedure terms (Round 1) ---------------------
# SapBERT misses long-term-use Z-codes for bare drug names; MiniLM catches them
# only when the query carries the use-concept phrase. So we CONCAT the original
# term with a class-level use phrase (measured: concat beats expand-only, which
# regressed DOACs). Diagnoses already retrieve well RAW and are NOT expanded.
_ANTICOAG = "long term current use of anticoagulant"
_ANTIPLATELET = "long term current use of antiplatelet antithrombotic"
_HYPOGLYCEMIC = "long term current use of oral hypoglycemic"
_INSULIN = "long term current use of insulin"
_STEROID = "long term current use of systemic steroids"
_IMMUNOSUPP = "long term current use of immunosuppressant"
_IMMUNOMOD = "long term current use of immunomodulator"
_RETINOID = "long term current use of oral retinoid"
_CALCINEURIN = "long term current use of calcineurin inhibitor"
_ADULT_EXAM = "encounter for general adult medical examination"

DRUG_EXPANSIONS = {
    # anticoagulants
    "warfarin": _ANTICOAG, "apixaban": _ANTICOAG, "rivaroxaban": _ANTICOAG,
    "dabigatran": _ANTICOAG, "edoxaban": _ANTICOAG,
    # antiplatelets
    "clopidogrel": _ANTIPLATELET, "aspirin": _ANTIPLATELET, "ticagrelor": _ANTIPLATELET,
    "prasugrel": _ANTIPLATELET,
    # oral hypoglycemics
    "metformin": _HYPOGLYCEMIC, "glipizide": _HYPOGLYCEMIC, "glimepiride": _HYPOGLYCEMIC,
    "sitagliptin": _HYPOGLYCEMIC,
    # insulin
    "insulin": _INSULIN,
    # systemic steroids
    "prednisone": _STEROID, "prednisolone": _STEROID, "methylprednisolone": _STEROID,
    # immunosuppressants
    "methotrexate": _IMMUNOSUPP, "azathioprine": _IMMUNOSUPP, "mycophenolate": _IMMUNOSUPP,
    "cyclosporine": _IMMUNOSUPP,
    # immunomodulators / biologics
    "adalimumab": _IMMUNOMOD, "etanercept": _IMMUNOMOD, "ustekinumab": _IMMUNOMOD,
    "secukinumab": _IMMUNOMOD, "dupilumab": _IMMUNOMOD,
    # retinoids
    "isotretinoin": _RETINOID, "acitretin": _RETINOID,
    # calcineurin inhibitors
    "tacrolimus": _CALCINEURIN, "pimecrolimus": _CALCINEURIN,
    # procedures / wellness encounters
    "annual physical": _ADULT_EXAM, "yearly checkup": _ADULT_EXAM,
    "wellness exam": _ADULT_EXAM, "routine physical": _ADULT_EXAM,
}

BRAND_TO_GENERIC = {
    "coumadin": "warfarin", "eliquis": "apixaban", "xarelto": "rivaroxaban",
    "pradaxa": "dabigatran", "plavix": "clopidogrel", "brilinta": "ticagrelor",
    "humira": "adalimumab", "enbrel": "etanercept", "stelara": "ustekinumab",
    "cosentyx": "secukinumab", "dupixent": "dupilumab", "accutane": "isotretinoin",
    "protopic": "tacrolimus", "elidel": "pimecrolimus",
}


def _contains_whole_key(words: list, key: str) -> bool:
    """True if the multi-word `key` appears as a contiguous whole-word run in `words`."""
    kw = key.split()
    n = len(kw)
    return any(words[i:i + n] == kw for i in range(len(words) - n + 1))


def expand_query_term(term: str) -> str:
    """
    Expand a drug/procedure term to include its class use-phrase (CONCAT: original
    token + phrase). Resolves brand names to generics first. Returns the term
    unchanged if nothing matches.

    Matching: case-insensitive EXACT whole-term match first; if none, whole-word
    containment (so "warfarin 5mg daily" / "takes aspirin" / "patient on Coumadin"
    still expand) — matched on word boundaries via tokenization so "insulin" can't
    match inside another word.
    """
    low = term.strip().lower()

    # 1. Exact whole-term match (brand -> generic, or generic directly).
    generic = BRAND_TO_GENERIC.get(low)
    if generic is None and low in DRUG_EXPANSIONS:
        generic = low

    # 2. Whole-word containment fallback. Prefer longer (multi-word) keys first.
    if generic is None:
        words = re.findall(r"[a-z0-9]+", low)
        for key in sorted(BRAND_TO_GENERIC, key=lambda k: -len(k.split())):
            if _contains_whole_key(words, key):
                generic = BRAND_TO_GENERIC[key]
                break
        if generic is None:
            for key in sorted(DRUG_EXPANSIONS, key=lambda k: -len(k.split())):
                if _contains_whole_key(words, key):
                    generic = key
                    break

    if generic is None:
        return term  # not a known drug/procedure -> leave RAW

    phrase = DRUG_EXPANSIONS.get(generic)
    return f"{term} {phrase}" if phrase else term


class ICD10Retriever:
    def __init__(self, index_dir: str = "indexes"):
        # Accept either a bare directory name (resolved against the project dir)
        # or an absolute path.
        if not os.path.isabs(index_dir):
            index_dir = os.path.join(BASE_DIR, index_dir)
        embeddings_path = os.path.join(index_dir, "icd10_embeddings.npy")
        metadata_path = os.path.join(index_dir, "icd10_metadata.json")

        if not os.path.exists(embeddings_path) or not os.path.exists(metadata_path):
            raise RuntimeError(
                f"ICD-10 semantic index not found in '{index_dir}'. Build it first: "
                "\"python build_icd_index_sapbert.py\" (SapBERT) or "
                "\"python build_icd_index.py\" (MiniLM)."
            )

        # Imported here so a missing faiss/sentence-transformers install surfaces
        # only when retrieval is actually used, not at module import time.
        import faiss
        from sentence_transformers import SentenceTransformer

        self.embeddings = np.load(embeddings_path).astype("float32")
        with open(metadata_path, "r", encoding="utf-8") as f:
            raw = json.load(f)

        # New shape: {"model_name": ..., "codes": [...]}. Legacy shape: a bare list.
        if isinstance(raw, dict):
            self.metadata = raw.get("codes", [])
            self.model_name = raw.get("model_name", DEFAULT_MODEL_NAME)
        else:
            self.metadata = raw
            self.model_name = DEFAULT_MODEL_NAME

        # Load whichever embedding model matches the index (dim must agree).
        self.model = SentenceTransformer(self.model_name)

        # Inner product on L2-normalized vectors == cosine similarity.
        dim = self.embeddings.shape[1]
        self.index = faiss.IndexFlatIP(dim)
        self.index.add(self.embeddings)

    def retrieve(self, queries: list[str], top_k: int = 10) -> list[dict]:
        queries = [q for q in queries if isinstance(q, str) and q.strip()]
        if not queries:
            return []

        query_vecs = self.model.encode(
            queries,
            normalize_embeddings=True,
            convert_to_numpy=True,
        ).astype("float32")

        scores, indices = self.index.search(query_vecs, top_k)

        # Deduplicate across queries: keep the highest score per code and record
        # which query surfaced it.
        best: dict[str, dict] = {}
        for qi, query in enumerate(queries):
            for score, row in zip(scores[qi], indices[qi]):
                if row < 0:  # FAISS pads with -1 when fewer than top_k results
                    continue
                meta = self.metadata[row]
                code = meta["code"]
                fscore = float(score)
                existing = best.get(code)
                if existing is None or fscore > existing["score"]:
                    best[code] = {
                        "code": code,
                        "description": meta["description"],
                        "score": fscore,
                        "matched_query": query,
                    }

        return sorted(best.values(), key=lambda d: d["score"], reverse=True)


class HybridRetriever:
    """
    Queries the MiniLM and SapBERT indexes and merges the candidates.

    MiniLM covers long-term-use / encounter Z-codes well (e.g. aspirin -> Z79.82,
    annual physical -> Z00.00); SapBERT is far stronger on clinical/dermatology
    terminology (e.g. psoriasis -> L40, basal cell carcinoma -> C44). Merging keeps
    both strengths. Each merged candidate carries a "source" field: minilm / sapbert / both.
    """

    def __init__(self, minilm_dir: str = MINILM_DIR, sapbert_dir: str = SAPBERT_DIR):
        self.minilm = ICD10Retriever(minilm_dir)
        self.sapbert = ICD10Retriever(sapbert_dir)

    # Reciprocal Rank Fusion constant (standard default). Larger k flattens the
    # contribution of top ranks; 60 is the widely-used value.
    RRF_K = 60

    def retrieve(self, queries: list[str], top_k: int = 10) -> list[dict]:
        per_model = {"minilm": self.minilm.retrieve(queries, top_k),
                     "sapbert": self.sapbert.retrieve(queries, top_k)}

        rrf: dict[str, float] = {}        # fusion score (ranking)
        cosine: dict[str, float] = {}     # max raw cosine per code (display + 0.7 warning)
        info: dict[str, dict] = {}        # description + matched_query from the best cosine hit
        sources: dict[str, set] = {}

        for src, items in per_model.items():
            for rank, it in enumerate(items, start=1):  # 1-based rank within THIS model
                code = it["code"]
                # RRF: a code in both lists sums both 1/(k+rank) contributions, so
                # cross-model agreement ranks higher. Scale-invariant — raw score
                # magnitudes can no longer evict the other model's candidates.
                rrf[code] = rrf.get(code, 0.0) + 1.0 / (self.RRF_K + rank)
                sources.setdefault(code, set()).add(src)
                if code not in cosine or it["score"] > cosine[code]:
                    cosine[code] = it["score"]
                    info[code] = {"description": it["description"], "matched_query": it["matched_query"]}

        merged = []
        for code, rscore in rrf.items():
            srcs = sources[code]
            merged.append({
                "code": code,
                "description": info[code]["description"],
                "score": cosine[code],        # cosine kept for display + empty-result warning
                "rrf_score": rscore,          # fusion score used for ordering
                "matched_query": info[code]["matched_query"],
                "source": "both" if len(srcs) == 2 else next(iter(srcs)),
            })

        return sorted(merged, key=lambda d: d["rrf_score"], reverse=True)


_RETRIEVER = None


def get_retriever():
    global _RETRIEVER
    if _RETRIEVER is None:
        if ACTIVE_INDEX_DIR == "hybrid":
            _RETRIEVER = HybridRetriever()
        else:
            _RETRIEVER = ICD10Retriever(ACTIVE_INDEX_DIR)
    return _RETRIEVER
