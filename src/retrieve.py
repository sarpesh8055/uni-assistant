"""STEP 3 — Hybrid retrieval: combine semantic + keyword search with Reciprocal Rank Fusion.

Try it:  python -m src.retrieve "Wie oft darf ich eine Prüfung wiederholen?"
"""
import pickle
import sys
from functools import lru_cache

from src.config import BM25_FILE, EMBED_MODEL, EMBEDDINGS_FILE, RETRIEVAL_MODE, TOP_K
from src.index import load_chunks, tokenize


def rrf_fuse(rankings: list[list[int]], rrf_k: int = 60) -> dict[int, float]:
    """Reciprocal Rank Fusion: score = sum(1 / (rrf_k + rank)) over all rankings.

    Simple, needs no score normalisation, and is what many production systems use.
    """
    fused: dict[int, float] = {}
    for ranking in rankings:
        for rank, idx in enumerate(ranking):
            fused[idx] = fused.get(idx, 0.0) + 1.0 / (rrf_k + rank + 1)
    return fused


class HybridRetriever:
    def __init__(self):
        import numpy as np
        from sentence_transformers import SentenceTransformer

        self.np = np
        self.chunks = load_chunks()
        self.emb = np.load(EMBEDDINGS_FILE)
        with open(BM25_FILE, "rb") as f:
            self.bm25 = pickle.load(f)
        self.model = SentenceTransformer(EMBED_MODEL)

    def dense_scores(self, query: str):
        q = self.model.encode(f"query: {query}", normalize_embeddings=True)
        return self.emb @ q   # cosine similarity, because both sides are normalised

    def search(self, query: str, k: int = TOP_K, mode: str = RETRIEVAL_MODE) -> list[dict]:
        """Return the top-k chunks. Every hit carries `dense_score` (cosine similarity),
        which generate.py uses to decide whether the documents cover the question at all."""
        np = self.np
        n = max(k * 4, 20)
        dense = self.dense_scores(query)
        rankings = []
        if mode in ("hybrid", "dense"):
            rankings.append(list(np.argsort(-dense)[:n]))
        if mode in ("hybrid", "sparse"):
            sparse = self.bm25.get_scores(tokenize(query))
            rankings.append([i for i in np.argsort(-sparse)[:n] if sparse[i] > 0])
        if not rankings:
            raise ValueError(f"unknown retrieval mode: {mode!r}")
        fused = rrf_fuse(rankings)
        best = sorted(fused, key=fused.get, reverse=True)[:k]
        return [
            {**self.chunks[i], "score": round(fused[i], 4), "dense_score": round(float(dense[i]), 4)}
            for i in best
        ]


@lru_cache(maxsize=1)
def get_retriever() -> HybridRetriever:
    return HybridRetriever()


if __name__ == "__main__":
    query = " ".join(sys.argv[1:]) or "How many times can I retake an exam?"
    for hit in get_retriever().search(query):
        print(f"\n[rrf {hit['score']} | cos {hit['dense_score']}] {hit['source']} p.{hit['page']} ({hit['lang']})")
        print(hit["text"][:300].replace("\n", " "), "...")
