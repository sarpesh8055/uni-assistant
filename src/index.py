"""STEP 2 — Indexing: build a vector index (embeddings) AND a keyword index (BM25).

Run:  python -m src.index
"""
import json
import pickle
import re

from src.config import BM25_FILE, CHUNKS_FILE, EMBED_MODEL, EMBEDDINGS_FILE


def tokenize(text: str) -> list[str]:
    # keep "§" as its own token so queries like "§ 12" match exactly
    return re.findall(r"§|\w+", text.lower())


def load_chunks() -> list[dict]:
    with open(CHUNKS_FILE, encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def main():
    # heavy imports live here so the rest of the package (and the tests) stay light
    import numpy as np
    from rank_bm25 import BM25Okapi
    from sentence_transformers import SentenceTransformer

    chunks = load_chunks()
    texts = [c["text"] for c in chunks]
    print(f"Indexing {len(texts)} chunks...")

    # 1) Dense / semantic index. e5 models expect the "passage: " prefix.
    model = SentenceTransformer(EMBED_MODEL)
    emb = model.encode(
        [f"passage: {t}" for t in texts],
        batch_size=32,
        show_progress_bar=True,
        normalize_embeddings=True,   # so dot product == cosine similarity
    )
    np.save(EMBEDDINGS_FILE, emb.astype(np.float32))

    # 2) Sparse / keyword index. Catches exact terms like "§ 12" or "ECTS".
    bm25 = BM25Okapi([tokenize(t) for t in texts])
    with open(BM25_FILE, "wb") as f:
        pickle.dump(bm25, f)

    print(f"✓ embeddings {emb.shape} -> {EMBEDDINGS_FILE}")
    print(f"✓ BM25 index -> {BM25_FILE}")


if __name__ == "__main__":
    main()
