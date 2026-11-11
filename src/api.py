"""STEP 5 — REST API with FastAPI.

Run:  uvicorn src.api:app --reload
Open: http://localhost:8000/docs   (interactive Swagger UI, try /ask there)
"""
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from src.generate import answer
from src.retrieve import get_retriever


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_retriever()  # load models once at startup, not on the first request
    yield


app = FastAPI(title="Uni & Behörden Assistant", version="0.2.0", lifespan=lifespan)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=1000)


class Source(BaseModel):
    n: int
    source: str
    page: int
    snippet: str


class AskResponse(BaseModel):
    answer: str
    found: bool = Field(..., description="False when the assistant refused because the documents don't cover it")
    reason: str
    sources: list[Source]
    faithfulness: dict | None = Field(None, description="Judge verdict when FAITHFULNESS_CHECK is report/enforce")
    latency_ms: int


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest):
    start = time.perf_counter()
    try:
        result = answer(req.question)
    except Exception as e:  # e.g. LLM API down or wrong key
        raise HTTPException(status_code=502, detail=f"LLM error: {e}")
    return AskResponse(**result, latency_ms=int((time.perf_counter() - start) * 1000))
