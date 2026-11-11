"""STEP 3 — Hybrid retrieval: combine semantic + keyword search with Reciprocal Rank Fusion.

Try it:  python -m src.retrieve "Wie oft darf ich eine Prüfung wiederholen?"
"""
import pickle
import sys
from functools import lru_cache

from src.config import (BM25_FILE, EMBED_MODEL, EMBEDDINGS_FILE, RERANK_CANDIDATES, RERANKER,
                        RETRIEVAL_MODE, TOP_K)
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


def join_overlapping(prev: str, cur: str) -> str:
    """Glue two neighbouring chunks, dropping the text they share (the chunk overlap)."""
    for k in range(min(len(prev), len(cur)), 19, -1):   # < 20 chars shared is a coincidence, not overlap
        if prev.endswith(cur[:k]):
            return prev + cur[k:]
    return f"{prev}\n\n{cur}"


def with_previous_chunk(chunks: list[dict], i: int) -> str:
    """The chunk text preceded by the chunk before it on the same page.

    A rule and its exception can land in different chunks; a chunk starting
    "three. Deviating from this, ..." never says *what* is three. Showing the LLM
    the previous chunk restores that context without changing retrieval or the
    page that gets cited."""
    cur = chunks[i]
    if i > 0 and chunks[i - 1]["source"] == cur["source"] and chunks[i - 1]["page"] == cur["page"]:
        return join_overlapping(chunks[i - 1]["text"], cur["text"])
    return cur["text"]


class HybridRetriever:
    def __init__(self, reranker: str = RERANKER):
        import numpy as np
        from sentence_transformers import SentenceTransformer

        self.np = np
        self.chunks = load_chunks()
        self.emb = np.load(EMBEDDINGS_FILE)
        with open(BM25_FILE, "rb") as f:
            self.bm25 = pickle.load(f)
        self.model = SentenceTransformer(EMBED_MODEL)
        self.reranker_name = reranker
        self._reranker = None

    def rerank(self, query: str, idxs: list[int]) -> list[int]:
        """Cross-encoder: reads question and chunk TOGETHER, so it judges relevance much better
        than comparing two separate embeddings. Too slow for the whole corpus, fine for 20 candidates."""
        if self._reranker is None:
            from sentence_transformers import CrossEncoder

            self._reranker = CrossEncoder(self.reranker_name, max_length=512)
        scores = self._reranker.predict([(query, self.chunks[i]["text"]) for i in idxs])
        return [i for _, i in sorted(zip(scores, idxs), key=lambda t: -t[0])]

    def dense_scores(self, query: str):
        q = self.model.encode(f"query: {query}", normalize_embeddings=True)
        return self.emb @ q   # cosine similarity, because both sides are normalised

    def search(self, query: str, k: int = TOP_K, mode: str = RETRIEVAL_MODE, rerank: bool | None = None) -> list[dict]:
        """Return the top-k chunks. Every hit carries `dense_score` (cosine similarity),
        which generate.py uses to decide whether the documents cover the question at all,
        and `context`: its text with the preceding chunk of the same page, which is what the LLM sees."""
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
        ranked = sorted(fused, key=fused.get, reverse=True)
        use_rerank = bool(self.reranker_name) if rerank is None else rerank
        if use_rerank:
            best = self.rerank(query, ranked[:RERANK_CANDIDATES])[:k]
        else:
            best = ranked[:k]
        return [
            {**self.chunks[i], "context": with_previous_chunk(self.chunks, i),
             "score": round(fused[i], 4), "dense_score": round(float(dense[i]), 4)}
            for i in best
        ]


@lru_cache(maxsize=2)
def get_retriever(reranker: str = RERANKER) -> HybridRetriever:
    return HybridRetriever(reranker)


if __name__ == "__main__":
    query = " ".join(sys.argv[1:]) or "How many times can I retake an exam?"
    for hit in get_retriever().search(query):
        print(f"\n[rrf {hit['score']} | cos {hit['dense_score']}] {hit['source']} p.{hit['page']} ({hit['lang']})")
        print(hit["text"][:300].replace("\n", " "), "...")
