"""Central settings so every script uses the same paths and models.

Most values can be overridden with environment variables, which makes eval
experiments a one-liner, e.g.  CHUNK_SIZE=500 python -m src.ingest
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Windows consoles default to cp1252 and crash on "✓", "§" or "ü" in print(). Force UTF-8.
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
CHUNKS_FILE = PROCESSED_DIR / "chunks.jsonl"
EMBEDDINGS_FILE = PROCESSED_DIR / "embeddings.npy"
BM25_FILE = PROCESSED_DIR / "bm25.pkl"

EMBED_MODEL = os.getenv("EMBED_MODEL", "intfloat/multilingual-e5-small")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
# The faithfulness judge can use a different (smaller, separately rate-limited) model.
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "") or LLM_MODEL

CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", 800))       # characters per chunk
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", 150))  # characters shared between neighbouring chunks
TOP_K = int(os.getenv("TOP_K", 5))                    # chunks given to the LLM
RETRIEVAL_MODE = os.getenv("RETRIEVAL_MODE", "hybrid")  # hybrid | dense | sparse

# Optional cross-encoder reranker: re-scores the top RERANK_CANDIDATES fused hits and keeps TOP_K.
# Empty = off. Multilingual options: BAAI/bge-reranker-v2-m3 (best, ~2 GB, slow on CPU),
# cross-encoder/mmarco-mMiniLMv2-L12-H384-v1 (small, fast).
RERANKER = os.getenv("RERANKER", "")
RERANK_CANDIDATES = int(os.getenv("RERANK_CANDIDATES", 20))

# Abstention gate: if the best chunk's cosine similarity to the question is below
# this, we answer "I couldn't find this" WITHOUT calling the LLM. e5 scores are
# compressed (unrelated text often scores ~0.7), so tune this on your eval set:
# run `python -m eval.run_eval` and look at the "abstention" section.
MIN_DENSE_SCORE = float(os.getenv("MIN_DENSE_SCORE", 0.83))

# Faithfulness check: a second LLM call ("judge") verifies that every claim in the answer is backed by
# the sources it cites. off | report (attach verdict) | enforce (refuse unsupported answers).
# Costs one extra LLM call per answered question.
FAITHFULNESS_CHECK = os.getenv("FAITHFULNESS_CHECK", "off")
