"""Versioned embedding configuration shared by index building and retrieval."""
import hashlib
import importlib.metadata
from pathlib import Path

SAPBERT_MODEL = "cambridgeltl/SapBERT-from-PubMedBERT-fulltext"


def make_embedding_config(model_name, pooling="legacy_auto", text_format="code_description_parent",
                          max_seq_length=None, revision=None, dimension=None):
    if pooling not in ("legacy_auto", "cls"):
        raise ValueError("Unsupported embedding pooling configuration")
    if text_format not in ("description", "code_description_parent"):
        raise ValueError("Unsupported embedding text format")
    if max_seq_length is not None and (type(max_seq_length) is not int or max_seq_length < 1):
        raise ValueError("max_seq_length must be a positive integer")
    return dict(model_name=model_name, pooling=pooling, text_format=text_format,
                max_seq_length=max_seq_length, revision=revision, dimension=dimension,
                normalized=True)


def embedding_config_from_metadata(metadata, embedding_dimension=None):
    if isinstance(metadata, dict) and metadata.get("embedding_config"):
        config = make_embedding_config(**{key: value for key, value in metadata["embedding_config"].items()
                                         if key in ("model_name", "pooling", "text_format", "max_seq_length", "revision", "dimension")})
    else:
        name = metadata.get("model_name", "all-MiniLM-L6-v2") if isinstance(metadata, dict) else "all-MiniLM-L6-v2"
        config = make_embedding_config(name)
    if embedding_dimension is not None and config.get("dimension") not in (None, embedding_dimension):
        raise ValueError("Index dimension does not match its embedding configuration")
    if embedding_dimension is not None:
        config["dimension"] = embedding_dimension
    return config


def load_embedding_model(config, device=None, local_files_only=False):
    from sentence_transformers import SentenceTransformer, models
    model_path = config["model_name"]
    if local_files_only and not Path(model_path).exists():
        from huggingface_hub import snapshot_download
        repo_id = model_path if "/" in model_path else "sentence-transformers/" + model_path
        model_path = snapshot_download(repo_id, revision=config.get("revision"), local_files_only=True)
    options = dict(local_files_only=local_files_only)
    if config.get("revision"):
        options["revision"] = config["revision"]
    if config["pooling"] == "cls":
        # SapBERT's published representation is the final-layer CLS token.
        transformer = models.Transformer(model_path, model_args=dict(options),
                                         tokenizer_args=dict(options), config_args=dict(options),
                                         max_seq_length=config.get("max_seq_length") or 128)
        pooling = models.Pooling(transformer.get_word_embedding_dimension(),
                                 pooling_mode_cls_token=True, pooling_mode_mean_tokens=False,
                                 pooling_mode_max_tokens=False)
        model = SentenceTransformer(modules=[transformer, pooling], device=device)
    else:
        # Old vectors must keep their original loader/pooling. Never reinterpret
        # a legacy mean-pooled index as a new CLS index.
        model = SentenceTransformer(model_path, device=device, **options)
        if config.get("max_seq_length"):
            model.max_seq_length = config["max_seq_length"]
    expected = config.get("dimension")
    if expected is not None and model.get_sentence_embedding_dimension() != expected:
        raise ValueError("Loaded embedding model has a different dimension from the index")
    return model


def code_set_provenance():
    import simple_icd_10_cm as cm
    root = Path(cm.__file__).parent
    sources = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix in (".xml", ".txt") and "202" in path.name:
            sources.append(dict(filename=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    return {"package": "simple_icd_10_cm", "package_version": importlib.metadata.version("simple_icd_10_cm"),
            "source_files": sources}
