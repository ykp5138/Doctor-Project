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
SAPBERT_CLS_DIR = "indexes_sapbert_cls"

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
        self.embeddings = np.load(embeddings_path).astype("float32")
        if self.embeddings.ndim != 2 or not self.embeddings.size:
            raise RuntimeError("ICD index must contain a nonempty two-dimensional vector matrix")
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
        from icd_embeddings import embedding_config_from_metadata, load_embedding_model
        self.embedding_config = embedding_config_from_metadata(raw, self.embeddings.shape[1])
        self.model = load_embedding_model(
            self.embedding_config, device=os.getenv("ICD_EMBEDDING_DEVICE") or None,
            local_files_only=os.getenv("ICD_LOCAL_MODELS_ONLY", "").lower() in ("1", "true"),
        )
        if len(self.metadata) != self.embeddings.shape[0] or not np.isfinite(self.embeddings).all():
            raise RuntimeError("ICD index metadata and vectors do not match")

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

    def retrieve_for_concepts(self, concepts, top_k=8, max_candidates=25):
        return _retrieve_concepts([("single", self)], concepts, top_k, max_candidates)


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

    def retrieve_for_concepts(self, concepts, top_k=8, max_candidates=25):
        return _retrieve_concepts([("minilm", self.minilm), ("sapbert", self.sapbert)],
                                  concepts, top_k, max_candidates)


def _clinical_queries(concepts):
    # Confirmed diagnosis concepts lead candidate budgeting. They remain model
    # candidates only, not automatic diagnoses or automatic code suggestions.
    keys = ("diagnoses_mentioned", "symptoms", "medications_discussed", "procedures_ordered",
            "history_relevant", "vitals_exam_findings")
    result = []
    for key in keys:
        for term in concepts.get(key, []) or []:
            if isinstance(term, str) and term.strip():
                query = expand_query_term(term) if key in ("medications_discussed", "procedures_ordered") else term
                result.append((key, term.strip(), query))
    return result


def _description_key(text):
    return " ".join(re.findall(r"\w+", text.casefold()))


def _exact_diagnosis_map(metadata):
    """Anchor names and inclusion terms from the installed ICD-10-CM data.

    Parenthesized nonessential modifiers in inclusion terms can be omitted in
    spoken names. These matches affect candidate priority only, never selection.
    """
    import simple_icd_10_cm as cm
    from icd10_utils import is_complete_code
    result = {}
    for item in metadata:
        if not is_complete_code(item["code"]):
            continue
        terms = [item["description"]]
        terms.extend(cm.get_includes(item["code"]))
        terms.extend(cm.get_inclusion_term(item["code"]))
        seen = set()
        for term in terms:
            for spelling in (term, re.sub(r"\([^)]*\)", "", term)):
                key = _description_key(spelling)
                if key and key not in seen:
                    result.setdefault(key, []).append({**item, "matched_alias": term})
                    seen.add(key)
    return result


def _retrieve_concepts(models, concepts, top_k, max_candidates):
    from icd10_utils import is_complete_code
    queries = _clinical_queries(concepts)
    metadata = models[0][1].metadata
    owner = models[0][1]
    if not hasattr(owner, "_exact_description_map"):
        owner._exact_description_map = _exact_diagnosis_map(metadata)
    exact = owner._exact_description_map
    pools, details = [], {}
    for category, term, query in queries:
        scores, local = {}, {}
        for source, retriever in models:
            # Fuse ranks within each query instead of globally ranking unrelated
            # symptom lists against each other and evicting diagnosis candidates.
            for rank, item in enumerate(retriever.retrieve([query], top_k=top_k * 2), 1):
                code = item["code"]
                if not is_complete_code(code):
                    continue
                scores[code] = scores.get(code, 0) + 1 / (60 + rank)
                entry = local.setdefault(code, {**item, "sources": [], "exact_diagnosis": False})
                entry["sources"].append(source)
        if category == "diagnoses_mentioned":
            for item in exact.get(_description_key(term), []):
                if is_complete_code(item["code"]):
                    local[item["code"]] = {**item, "score": 1.0, "matched_query": term,
                                            "sources": ["exact"], "exact_diagnosis": True}
                    scores[item["code"]] = 1.0
        ordered = sorted(local, key=lambda code: (-int(local[code]["exact_diagnosis"]), -scores[code], code))[:top_k]
        pools.append(ordered)
        for code in ordered:
            context = {"category": category, "text": term}
            if code not in details:
                details[code] = {**local[code], "matched_concepts": [context], "rrf_score": scores[code]}
            elif context not in details[code]["matched_concepts"]:
                details[code]["matched_concepts"].append(context)
    chosen = []
    # Reserve first-round coverage for every concept before spending the budget
    # on lower-ranked alternatives from one concept.
    for rank in range(top_k):
        for pool in pools:
            if rank < len(pool) and pool[rank] not in chosen:
                chosen.append(pool[rank])
                if len(chosen) >= max_candidates:
                    return [details[code] for code in chosen]
    return [details[code] for code in chosen]


_RETRIEVER = None


def _sapbert_index_dir():
    override = os.getenv("ICD_SAPBERT_INDEX_DIR")
    if override:
        return override
    if os.getenv("ICD_SELECTOR_MODE", "enhanced").strip().lower() == "legacy" or os.getenv("ICD_RETRIEVAL_MODE", "enhanced").strip().lower() == "legacy":
        return SAPBERT_DIR
    new_index = os.path.join(BASE_DIR, SAPBERT_CLS_DIR)
    if all(os.path.isfile(os.path.join(new_index, filename))
           for filename in ("icd10_embeddings.npy", "icd10_metadata.json")):
        return SAPBERT_CLS_DIR
    return SAPBERT_DIR


def get_retriever():
    global _RETRIEVER
    if _RETRIEVER is None:
        if ACTIVE_INDEX_DIR == "hybrid":
            sapbert_dir = _sapbert_index_dir()
            print(f"[icd-retrieval] SapBERT index: {sapbert_dir}")
            _RETRIEVER = HybridRetriever(sapbert_dir=sapbert_dir)
        else:
            _RETRIEVER = ICD10Retriever(ACTIVE_INDEX_DIR)
    return _RETRIEVER
