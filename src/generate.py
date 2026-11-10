"""STEP 4 — Answer generation with citations, and "I couldn't find this" when sources are missing.

Try it:  python -m src.generate "What documents do I need for re-registration?"

Hallucination control happens in three layers, cheapest first:
  1. Retrieval gate  — if no chunk is similar enough to the question, refuse
                       without calling the LLM at all (no cost, no risk).
  2. Prompt          — the LLM must answer only from the numbered sources and
                       reply with the token NOT_FOUND if they don't contain it.
  3. Citation check  — an answer that cites no valid source is treated as
                       ungrounded and replaced by the refusal message.
"""
import json
import re
import sys
from functools import lru_cache

from src.config import FAITHFULNESS_CHECK, LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, MIN_DENSE_SCORE
from src.ingest import guess_language

NOT_FOUND_TOKEN = "NOT_FOUND"
NOT_FOUND_MESSAGE = {
    "en": "I couldn't find this in the documents.",
    "de": "Dazu habe ich in den Dokumenten nichts gefunden.",
}

SYSTEM_PROMPT = f"""You are an assistant for international students in Germany.
Answer ONLY using the numbered sources provided. Rules:
- Every factual sentence must cite its source inline, like [1] or [2][3].
- If the sources do not contain the answer, reply with exactly: {NOT_FOUND_TOKEN}
  Do not guess and do not use outside knowledge.
- Answer in the language requested in the user message, even if the sources are in another language.
- Rules can conflict. Programme-specific "special provisions" (Besondere Bestimmungen) override the
  "general provisions" (Allgemeine Bestimmungen), and a later amendment (Änderung) overrides the text it amends.
  When this applies, give the overriding rule.
- Give concrete numbers, deadlines and limits when the sources contain them.
- Be concise and practical (at most 5 sentences)."""

LANGUAGE_NAME = {"en": "English", "de": "German"}


@lru_cache(maxsize=1)
def get_client():
    from openai import OpenAI

    return OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY)


def build_context(hits: list[dict]) -> str:
    """Numbered source list. A hit may carry its own number "n" (used by the judge, which sees
    only the cited sources but must keep the numbers the answer refers to)."""
    return "\n\n".join(
        f"[{h.get('n', i)}] ({h['source']}, page {h['page']})\n{h['text']}" for i, h in enumerate(hits, 1)
    )


def normalize_citations(text: str) -> str:
    """Models write citations in different styles: [1], [1, 2], 【1】, 【1†L3-L5】, (Source 1).
    Rewrite them all to the canonical [1][2] form so they can be parsed and shown consistently."""
    def canon(m):
        nums = re.findall(r"\d+", m.group(1))
        return "".join(f"[{n}]" for n in nums)

    text = re.sub(r"【\s*(\d+(?:\s*,\s*\d+)*)[^】]*】", canon, text)          # 【1】 or 【1†L3】
    text = re.sub(r"\[\s*(\d+(?:\s*[,;]\s*\d+)+)\s*\]", canon, text)         # [1, 2]
    text = re.sub(r"\((?:source|sources|quelle|quellen)\s+(\d+(?:\s*,\s*\d+)*)\)", canon, text, flags=re.I)
    return text


def cited_numbers(text: str, n_sources: int) -> list[int]:
    """Source numbers the answer actually cites, in order of first use, ignoring invalid ones."""
    seen: list[int] = []
    for m in re.findall(r"\[(\d+)\]", normalize_citations(text)):
        i = int(m)
        if 1 <= i <= n_sources and i not in seen:
            seen.append(i)
    return seen


JUDGE_PROMPT = """You check answers of a document assistant for faithfulness.
You get numbered SOURCES and an ANSWER that cites them like [1].
For every claim in the ANSWER, decide whether the cited sources state it (directly or as a clear paraphrase).
Claims that add information not in the sources, or draw conclusions the sources do not state, are UNSUPPORTED.
Wording, language (German/English) and formatting differences are fine.
Reply with JSON only: {"supported": true|false, "unsupported_claims": ["..."]}"""


def call_judge(answer_text: str, hits: list[dict]) -> str:
    response = get_client().chat.completions.create(
        model=LLM_MODEL,
        temperature=0,
        messages=[
            {"role": "system", "content": JUDGE_PROMPT},
            {"role": "user", "content": f"SOURCES:\n{build_context(hits)}\n\nANSWER:\n{answer_text}"},
        ],
    )
    return (response.choices[0].message.content or "").strip()


def parse_verdict(raw: str) -> dict:
    """Robust JSON extraction: models sometimes wrap JSON in prose or code fences.
    If the verdict can't be parsed we don't know, so we report supported=None (not a pass)."""
    m = re.search(r"\{.*\}", raw, re.S)
    try:
        data = json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        data = {}
    supported = data.get("supported")
    return {
        "supported": supported if isinstance(supported, bool) else None,
        "unsupported_claims": [str(c) for c in data.get("unsupported_claims", []) if c][:5],
    }


def check_faithfulness(answer_text: str, cited_hits: list[dict], judge=call_judge) -> dict:
    return parse_verdict(judge(answer_text, cited_hits))


def not_found(question: str, reason: str) -> dict:
    return {
        "answer": NOT_FOUND_MESSAGE[guess_language(question)],
        "found": False,
        "reason": reason,
        "sources": [],
    }


def call_llm(question: str, hits: list[dict]) -> str:
    response = get_client().chat.completions.create(
        model=LLM_MODEL,
        temperature=0,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": (
                f"Sources:\n{build_context(hits)}\n\nQuestion: {question}\n\n"
                f"Answer in {LANGUAGE_NAME[guess_language(question)]}."
            )},
        ],
    )
    return (response.choices[0].message.content or "").strip()


def answer(question: str, retriever=None, llm=call_llm, min_score: float = MIN_DENSE_SCORE,
           verify: str = FAITHFULNESS_CHECK, judge=call_judge) -> dict:
    """`retriever`, `llm` and `judge` are injectable so the logic can be unit-tested without models.

    verify: "off"     - no faithfulness check
            "report"  - run the judge and attach its verdict, but still return the answer
            "enforce" - refuse if the judge finds unsupported claims
    """
    if retriever is None:
        from src.retrieve import get_retriever

        retriever = get_retriever()

    hits = retriever.search(question)
    best = max((h.get("dense_score", 0.0) for h in hits), default=0.0)
    if not hits or best < min_score:
        return not_found(question, reason=f"retrieval_gate (best cosine {best:.3f} < {min_score})")

    text = normalize_citations(llm(question, hits))
    if NOT_FOUND_TOKEN in text:
        return not_found(question, reason="llm_not_found")

    cited = cited_numbers(text, len(hits))
    if not cited:
        return not_found(question, reason="no_citations")

    verdict = None
    if verify in ("report", "enforce"):
        # the judge only sees the sources the answer cites: a claim must be backed by ITS citation
        verdict = check_faithfulness(text, [{**hits[i - 1], "n": i} for i in cited], judge=judge)
        if verify == "enforce" and verdict["supported"] is False:
            return {**not_found(question, reason="unfaithful"), "faithfulness": verdict}

    return {
        "answer": text,
        "found": True,
        "reason": "answered",
        "sources": [
            {
                "n": i,
                "source": hits[i - 1]["source"],
                "page": hits[i - 1]["page"],
                "snippet": hits[i - 1]["text"][:300],
            }
            for i in cited
        ],
        **({"faithfulness": verdict} if verdict else {}),
    }


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or "How many times can I retake an exam?"
    result = answer(q)
    print(result["answer"], f"\n({result['reason']})\n")
    for s in result["sources"]:
        print(f"  [{s['n']}] {s['source']} p.{s['page']}")
