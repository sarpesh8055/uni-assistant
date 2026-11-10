from eval.run_eval import answer_metrics, retrieval_metrics
from src.retrieve import rrf_fuse


def test_rrf_rewards_items_found_by_both_rankings():
    fused = rrf_fuse([[1, 2, 3], [3, 4, 5]])
    assert max(fused, key=fused.get) == 3


def h(source, page, score=0.9):
    return {"source": source, "page": page, "dense_score": score}


def test_retrieval_metrics_doc_vs_page_and_gate():
    items = [
        {"question": "q1", "expected": [{"source": "a.pdf", "pages": [2]}]},
        {"question": "q2", "expected": [{"source": "b.pdf", "pages": [7, 8]}, {"source": "b_de.pdf", "pages": [9]}]},
        {"question": "q3", "expected": []},
    ]
    hits = [
        [h("x.pdf", 1), h("a.pdf", 2)],          # doc and page at rank 2
        [h("b.pdf", 1), h("x.pdf", 8)],          # right doc, wrong page
        [h("x.pdf", 1, score=0.5)],              # unanswerable, low score -> gate refuses
    ]
    m = retrieval_metrics(items, hits, min_score=0.8)
    assert m["hit_doc"] == 1.0
    assert m["hit_page"] == 0.5
    assert m["mrr"] == (1 / 2 + 1 / 1) / 2
    assert m["gate_refusal_unanswerable"] == 1.0
    assert m["gate_false_refusal"] == 0.0


def test_answer_metrics():
    items = [{"expected": [{"source": "a.pdf"}]}, {"expected": [{"source": "b.pdf"}]}, {"expected": []}]
    answers = [
        {"found": True, "sources": [{"source": "a.pdf"}]},
        {"found": False, "sources": []},
        {"found": False, "sources": []},
    ]
    a = answer_metrics(items, answers)
    assert a == {"refusal_unanswerable": 1.0, "false_refusal": 0.5, "citation_accuracy": 1.0}


def test_translation_or_original_both_count_as_hit():
    items = [{"question": "q", "expected": [{"source": "en.pdf", "pages": [9]}, {"source": "de.pdf", "pages": [8]}]}]
    m = retrieval_metrics(items, [[h("x.pdf", 1), h("de.pdf", 8)]], min_score=0.8)
    assert m["hit_page"] == 1.0 and m["mrr"] == 0.5
