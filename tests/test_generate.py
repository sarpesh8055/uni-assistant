from src.generate import NOT_FOUND_MESSAGE, answer, cited_numbers

HITS = [
    {"source": "po.pdf", "page": 12, "text": "Eine Prüfung kann zweimal wiederholt werden.", "dense_score": 0.88},
    {"source": "visa.pdf", "page": 3, "text": "Students may work 140 full days per year.", "dense_score": 0.84},
]


class FakeRetriever:
    def __init__(self, hits):
        self.hits = hits

    def search(self, q):
        return self.hits


def must_not_be_called(q, hits):
    raise AssertionError("LLM should not be called")


def test_cited_numbers_ignores_out_of_range_and_duplicates():
    assert cited_numbers("A [2]. B [1][2]. C [7].", n_sources=2) == [2, 1]


def test_retrieval_gate_refuses_without_calling_llm():
    low = [{**h, "dense_score": 0.6} for h in HITS]
    r = answer("Wie hoch ist die Miete?", retriever=FakeRetriever(low), llm=must_not_be_called, min_score=0.8)
    assert r["found"] is False and r["sources"] == []
    assert r["answer"] == NOT_FOUND_MESSAGE["de"]
    assert r["reason"].startswith("retrieval_gate")


def test_empty_retrieval_refuses():
    r = answer("anything at all?", retriever=FakeRetriever([]), llm=must_not_be_called)
    assert r["found"] is False


def test_llm_not_found_token_becomes_localized_refusal():
    r = answer("What is the pool opening time?", retriever=FakeRetriever(HITS),
               llm=lambda q, h: "NOT_FOUND", min_score=0.8)
    assert r == {"answer": NOT_FOUND_MESSAGE["en"], "found": False, "reason": "llm_not_found", "sources": []}


def test_answer_without_citations_is_rejected():
    r = answer("How often can I retake an exam?", retriever=FakeRetriever(HITS),
               llm=lambda q, h: "You can retake it twice.", min_score=0.8)
    assert r["found"] is False and r["reason"] == "no_citations"


def test_only_cited_sources_are_returned_with_page():
    r = answer("How often can I retake an exam?", retriever=FakeRetriever(HITS),
               llm=lambda q, h: "You can retake a failed exam twice [1].", min_score=0.8)
    assert r["found"] is True
    assert [(s["source"], s["page"]) for s in r["sources"]] == [("po.pdf", 12)]
    assert "zweimal" in r["sources"][0]["snippet"]


def test_normalize_citations_handles_model_styles():
    from src.generate import normalize_citations
    assert normalize_citations("A【1】 B【2†L3-L5】 C [1, 3] D (Source 2)") == "A[1] B[2] C [1][3] D [2]"
    assert cited_numbers("Max 120 pages【1】.", n_sources=5) == [1]


def test_fullwidth_citation_answer_is_accepted_and_normalized():
    r = answer("What is the maximum length of the thesis?", retriever=FakeRetriever(HITS),
               llm=lambda q, h: "At most 120 pages【1】.", min_score=0.8)
    assert r["found"] is True and r["answer"] == "At most 120 pages[1]."


GOOD = lambda q, h: "You can retake a failed exam twice [1]."


def test_parse_verdict_handles_fences_and_garbage():
    from src.generate import parse_verdict
    assert parse_verdict('```json\n{"supported": false, "unsupported_claims": ["x"]}\n```') == \
        {"supported": False, "unsupported_claims": ["x"]}
    assert parse_verdict("no json here")["supported"] is None      # unknown is not a pass


def test_report_mode_attaches_verdict_but_keeps_answer():
    seen = {}
    def judge(text, hits):
        seen["hits"] = hits
        return '{"supported": false, "unsupported_claims": ["twice"]}'
    r = answer("How often?", retriever=FakeRetriever(HITS), llm=GOOD, min_score=0.8, verify="report", judge=judge)
    assert r["found"] is True and r["faithfulness"]["supported"] is False
    assert [h["source"] for h in seen["hits"]] == ["po.pdf"], "judge must only see the cited sources"


def test_enforce_mode_refuses_unsupported_answer():
    r = answer("How often?", retriever=FakeRetriever(HITS), llm=GOOD, min_score=0.8, verify="enforce",
               judge=lambda t, h: '{"supported": false, "unsupported_claims": ["twice"]}')
    assert r["found"] is False and r["reason"] == "unfaithful"


def test_enforce_mode_keeps_supported_and_unparseable_verdicts():
    for raw in ('{"supported": true, "unsupported_claims": []}', "judge crashed"):
        r = answer("How often?", retriever=FakeRetriever(HITS), llm=GOOD, min_score=0.8, verify="enforce",
                   judge=lambda t, h, raw=raw: raw)
        assert r["found"] is True


def test_off_mode_never_calls_judge():
    r = answer("How often?", retriever=FakeRetriever(HITS), llm=GOOD, min_score=0.8, verify="off",
               judge=lambda t, h: (_ for _ in ()).throw(AssertionError("judge called")))
    assert "faithfulness" not in r
