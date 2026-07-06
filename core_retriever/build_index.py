import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from core_retriever.chunk_core import chunk_core, sha256_file


DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def build_core_index(core_path, out_dir, model_name=DEFAULT_MODEL, model_loader=None):
    core = Path(core_path)
    if not core.exists():
        raise FileNotFoundError(f"BOIS Core file does not exist: {core}")

    output = Path(out_dir)
    output.mkdir(parents=True, exist_ok=True)

    chunks = chunk_core(core)
    model = _load_model(model_name, model_loader=model_loader)
    embeddings = model.encode(
        [chunk["text"] for chunk in chunks],
        normalize_embeddings=True,
    )
    embeddings = np.asarray(embeddings, dtype=np.float32)

    chunks_path = output / "core_chunks.json"
    embeddings_path = output / "core_embeddings.npy"
    manifest_path = output / "manifest.json"

    chunks_path.write_text(
        json.dumps(chunks, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    np.save(embeddings_path, embeddings)

    manifest = {
        "source_path": str(core),
        "source_sha256": sha256_file(core),
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "model_name": model_name,
        "chunks_count": len(chunks),
        "embedding_shape": list(embeddings.shape),
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build a local BOIS Core semantic index.")
    parser.add_argument("--core", required=True, help="Path to external BOIS Core machine JSON.")
    parser.add_argument("--out", required=True, help="Output directory for index files.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="SentenceTransformer model name.")
    args = parser.parse_args(argv)

    try:
        manifest = build_core_index(args.core, args.out, model_name=args.model)
    except Exception as exc:
        raise SystemExit(f"Failed to build BOIS Core index: {exc}") from exc

    print(
        "BOIS Core index built: "
        f"{manifest['chunks_count']} chunks, "
        f"shape={manifest['embedding_shape']}, "
        f"source={manifest['source_path']}"
    )


def _load_model(model_name, model_loader=None):
    if model_loader:
        return model_loader(model_name)

    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name)


if __name__ == "__main__":
    main()
