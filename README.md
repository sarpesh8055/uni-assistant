# 🎓 Uni & Behörden Assistant

A multilingual (German/English) RAG assistant that answers questions about German university
regulations and administrative documents, **with source citations**.

**Stack:** Python · PyMuPDF · sentence-transformers (multilingual-e5) · BM25 · hybrid search (RRF) · OpenAI-compatible LLM / Ollama · FastAPI · Streamlit · Docker

```
PDFs ──► ingest.py ──► chunks.jsonl ──► index.py ──► embeddings + BM25
                                                          │
 question ──► retrieve.py (hybrid search) ◄───────────────┘
                  │
                  ▼
            generate.py (LLM + citations) ──► api.py (FastAPI) ──► ui.py (Streamlit)
                  │
            eval/run_eval.py (Hit@k, MRR)
```

---

## Step-by-step guide

### Step 0 — Setup (15 min)

```bash
cd uni-assistant
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # then open .env and add your API key
```

**No API key?** Use a free local model:
install [Ollama](https://ollama.com), run `ollama pull llama3.1`, and use "Option B" in `.env`.

Create a GitHub repo now and commit after every step. A clean commit history looks good to employers.

### Step 1 — Collect documents (`src/download.py`)

```bash
python -m src.download
```
This downloads 11 public PDFs from Paderborn University (Electrical Systems Engineering master, v3) into `data/raw/`:
general and special examination provisions (official German versions **and** English translations), the
September 2024 amendment, the module handbook, transition rules v2 → v3, and PAUL guides.
The PDFs are not committed to git; the script makes the corpus reproducible.

👉 *Learn:* the German original and the English reading version are **not identical**. The English one already
includes the 2024 amendment. Real document collections have versions, and your assistant has to cite the right one.

### Step 2 — Ingest (`src/ingest.py`)

```bash
python -m src.ingest
```
Open `data/processed/chunks.jsonl` and **read some chunks**. Are they clean? Do any sentences get cut in half?
👉 *Learn:* why chunk size and overlap matter, and why metadata (source, page, language) matters for citations.

### Step 3 — Index (`src/index.py`)

```bash
python -m src.index
```
👉 *Learn:* dense embeddings (meaning) vs. BM25 (exact keywords like "§ 12" or "ECTS"). Read why
e5 models need the `query:` / `passage:` prefixes.

### Step 4 — Retrieve (`src/retrieve.py`)

```bash
python -m src.retrieve "Wie oft darf ich eine Prüfung wiederholen?"
python -m src.retrieve "How often can I retake an exam?"
```
Do both languages find the same chunks? That's multilingual retrieval working.
👉 *Learn:* Reciprocal Rank Fusion, a simple way to merge two rankings.

### Step 5 — Generate answers (`src/generate.py`)

```bash
python -m src.generate "What do I need for re-registration?"
```
Then ask something that is **not** in your documents. It should say "I couldn't find this".
Hallucination control has three layers, cheapest first:
1. **Retrieval gate**: if no chunk is similar enough (`MIN_DENSE_SCORE`), refuse *without calling the LLM*.
2. **Prompt**: answer only from the numbered sources, or reply `NOT_FOUND`.
3. **Citation check**: an answer that cites no valid source is rejected. Only sources the answer actually cites are returned, each with its page and a snippet.

👉 *Learn:* grounding, citations and hallucination control.

### Step 6 — API + UI (`src/api.py`, `src/ui.py`)

```bash
uvicorn src.api:app --reload        # terminal 1 → open http://localhost:8000/docs
streamlit run src/ui.py             # terminal 2
```
👉 *Learn:* REST APIs, Pydantic validation and separating backend from frontend.

### Step 7 — Evaluate (`eval/run_eval.py`) ⭐ most important

1. Edit `eval/questions.jsonl`. Write **30–50 real questions**. For each one, note the PDF **and page** that contains the answer.
   Make ~20% of them **unanswerable** (`"expected_source": null`). They test whether the assistant refuses honestly.
2. Run `python -m eval.run_eval` (free, no LLM). You get:
   - **Hit@5 doc / Hit@5 page / MRR**: does retrieval find the right document, and the right page?
   - **Abstention**: the best similarity score for answerable vs. unanswerable questions. Set `MIN_DENSE_SCORE` in `.env` to a value between the two groups.
3. Run `python -m eval.run_eval --answers` for the full pipeline (uses the LLM): refusal rate, false-refusal rate and citation accuracy.
4. Run experiments, changing **one thing at a time**. Each run prints its README row:
   ```bash
   python -m eval.run_eval --name baseline
   python -m eval.run_eval --mode dense  --name dense-only
   python -m eval.run_eval --mode sparse --name bm25-only
   CHUNK_SIZE=500 python -m src.ingest && python -m src.index && python -m eval.run_eval --name chunk-500
   ```
   | Experiment | Hit@5 doc | Hit@5 page | MRR | Refuses unanswerable | False refusals |
   |---|---|---|---|---|---|
   | Baseline (800 chars, e5-small, hybrid, gate 0.83) | 97% | 92% | 0.842 | 43% | 0% |
   | Dense only (no BM25) | 95% | 79% | 0.834 | – | – |
   | BM25 only | 97% | 79% | 0.752 | – | – |
   | Chunk size 500 | | | | | |
   | `intfloat/multilingual-e5-base` | | | | | |
   | + Reranker `mmarco-mMiniLMv2-L12` (small, multilingual) | 100% | 89% | 0.857 | 43% | 0% |
   | + Reranker `bge-reranker-v2-m3` (568M params) | not run: out of memory on a 4 GB RAM laptop | | | | |

   First rows measured on 11 Uni Paderborn ESE v3 PDFs and 45 questions (38 answerable, 7 unanswerable), retrieval only.
   Reranker takeaway: the small reranker finds the right *document* more often but the right *page* less often,
   and adds several seconds per question on CPU, so it stays **off** by default (`RERANKER=` in `.env`).
   The large one needs ~2.3 GB for the weights alone; measure it on a machine with more RAM
   (e.g. Google Colab) before deciding.

   End-to-end with the LLM (`--answers`, Groq `openai/gpt-oss-120b`):

   | Run | Refuses unanswerable | False refusals | Citation accuracy | Wrong-language answers |
   |---|---|---|---|---|
   | First run | 100% | 37% | 96% | several |
   | + citation-format fix, explicit answer language, precedence rule in prompt | 100% | 8% | 91% | 0 |

   The first run's 37% false refusals were mostly a bug: the model cites as `【1】`, the parser only accepted `[1]`.
   Remaining errors (6 of 45): 3 false refusals; "thesis language" is a retrieval miss (the special-provisions page
   is not in the top 5, so the model follows the general rule); "thesis length" had the right page at rank 3 but the
   model used the general provisions' 900-hour workload instead of "120 pages"; "time until thesis grade" was
   answered with an inference the sources don't state. Next steps: reranker, and an answer-faithfulness check.

   Faithfulness judge (`python -m eval.judge_saved eval/results/faithfulness-llm.json`, judge `gpt-oss-20b`):

   | Judged answers | Supported | Flagged | Flags that were justified | False refusals if enforced |
   |---|---|---|---|---|
   | 35 | 89% | 4 | 3 of 4 (incl. both wrong thesis answers) | 18% (vs. 8% without) |

   Decision: `FAITHFULNESS_CHECK=report`. The UI shows a "partly unverified" warning instead of refusing,
   because enforcing would block correct answers too. Lessons:
   - A first run flagged 17/35 answers. Cause: a bug of mine (the judge saw the cited sources renumbered,
     so `[5]` pointed at nothing). Measuring in report mode before enforcing caught it.
   - LLM-as-judge measures **faithfulness, not correctness**: it misses answers that quote the wrong rule
     ("grades within ten weeks" is a real sentence, but about credit transfer). Hand-written labels catch those.
   - Groq free tier: 200k tokens/day per model, about 60-70 answers/day with `gpt-oss-120b`.
     The judge runs on a different model so it has its own quota.

   Paste this table into your README. **It's the strongest part of your portfolio.**

Unit tests (no models or API key needed): `pip install -r requirements-dev.txt && pytest`.

### Step 8 — Level up (weeks 4–6)

Do these in order. Each one is a resume bullet:

1. **Reranker.** After hybrid search, re-score the top 20 with `CrossEncoder("BAAI/bge-reranker-v2-m3")` from sentence-transformers and keep the top 5. Measure the change in Step 7.
2. **Answer evaluation.** Use [RAGAS](https://docs.ragas.io) to score *faithfulness* and *answer relevancy*, not only retrieval.
3. **Agent with tools.** Use [LangGraph](https://langchain-ai.github.io/langgraph/) and give the LLM tools: `search_documents`, `calculate_deadline(date, days)`, `draft_email(to, topic)`. Learn tool/function calling.
4. **Observability.** Add [Langfuse](https://langfuse.com) (free tier) to trace every request: retrieved chunks, latency and token cost.
5. **Vector DB.** Replace the numpy index with Qdrant (`docker run -p 6333:6333 qdrant/qdrant`).
6. **Docker.** After building the index, run `docker compose up --build` (API on :8000, UI on :8501).
7. **CI.** `.github/workflows/ci.yml` already runs the unit tests. Extend it to run `python -m eval.run_eval --min-hit 0.8`, so CI fails if retrieval quality drops.
8. **Deploy.** Put it on Hugging Face Spaces or Render, and record a 2-minute demo video for LinkedIn.

---

## Interview questions you should be able to answer after this project

- Why hybrid search instead of only embeddings?
- How did you choose chunk size? (Answer with your eval table!)
- How do you stop the model from hallucinating?
- How would you scale this to 1 million documents?
- What does your system cost per 1,000 questions?
