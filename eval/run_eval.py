"""STEP 6 — Evaluation. Measures quality with numbers so you can PROVE improvements.

Question file (eval/questions.jsonl), one JSON object per line:
  {"question": "...", "expected": [{"source": "a_en.pdf", "pages": [9]}, {"source": "a_de.pdf", "pages": [9]}],
   "answer": "..."}
  {"question": "...", "expected": []}      <- unanswerable: the assistant must refuse
"expected" lists every acceptable citation (e.g. the English translation AND the German
original). Retrieving any one of them counts as a hit. Omit "pages" to accept any page.

Retrieval metrics (answerable questions, free, no LLM):
  Hit@k (doc)  : expected PDF among the top-k chunks
  Hit@k (page) : expected PDF *and page* among the top-k (this is what the citation shows)
  MRR          : 1 / rank of the first correct chunk (1.0 = always first)
Abstention (retrieval gate only, free):
  refusal rate on unanswerable questions (want high) vs. false refusals on answerable ones (want low)
End-to-end, with --answers (calls the LLM, costs money):
  same abstention numbers for the full pipeline, plus citation accuracy
  (does the answer cite the expected PDF?)

Run:
  python -m eval.run_eval                        # baseline
  python -m eval.run_eval --mode dense --name dense-only
  python -m eval.run_eval --answers              # full pipeline
  python -m eval.run_eval --min-hit 0.8          # exit code 1 if Hit@k(doc) < 0.8 (for CI)
Results are saved to eval/results/<name>.json; each run prints a Markdown row for the README table.
"""
import argparse
import json
import sys
from pathlib import Path

from src.config import MIN_DENSE_SCORE, RETRIEVAL_MODE, TOP_K

HERE = Path(__file__).parent
QUESTIONS = HERE / "questions.jsonl"
RESULTS_DIR = HERE / "results"


def load_items(path: Path = QUESTIONS) -> list[dict]:
    items = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    placeholders = [i for i in items if "REPLACE" in json.dumps(i.get("expected"))]
    if placeholders:
        sys.exit(f"{len(placeholders)} questions still have placeholder sources in {path}. Fill them in first.")
    return items


def answerable(item: dict) -> bool:
    return bool(item.get("expected"))


def matches(hit: dict, item: dict, check_page: bool) -> bool:
    for e in item["expected"]:
        if hit["source"] == e["source"] and (not check_page or "pages" not in e or hit["page"] in e["pages"]):
            return True
    return False


def first_correct_rank(hits: list[dict], item: dict, check_page: bool) -> int | None:
    for rank, h in enumerate(hits, 1):
        if matches(h, item, check_page):
            return rank
    return None


def retrieval_metrics(items: list[dict], hits_per_item: list[list[dict]], min_score: float) -> dict:
    ans = [(i, h) for i, h in zip(items, hits_per_item) if answerable(i)]
    unans = [(i, h) for i, h in zip(items, hits_per_item) if not answerable(i)]

    def best(h):
        return max((x.get("dense_score", 0.0) for x in h), default=0.0)

    doc_ranks = [first_correct_rank(h, i, check_page=False) for i, h in ans]
    page_ranks = [first_correct_rank(h, i, check_page=True) for i, h in ans]
    n = len(ans) or 1
    return {
        "n_answerable": len(ans),
        "n_unanswerable": len(unans),
        "hit_doc": sum(r is not None for r in doc_ranks) / n,
        "hit_page": sum(r is not None for r in page_ranks) / n,
        "mrr": sum(1 / r for r in doc_ranks if r) / n,
        "gate_refusal_unanswerable": (sum(best(h) < min_score for _, h in unans) / len(unans)) if unans else None,
        "gate_false_refusal": sum(best(h) < min_score for _, h in ans) / n,
        "best_scores_answerable": sorted(round(best(h), 3) for _, h in ans),
        "best_scores_unanswerable": sorted(round(best(h), 3) for _, h in unans),
        "per_question": [
            {"question": i["question"], "doc_rank": dr, "page_rank": pr}
            for (i, _), dr, pr in zip(ans, doc_ranks, page_ranks)
        ],
    }


def answer_metrics(items: list[dict], answers: list[dict]) -> dict:
    ans = [(i, a) for i, a in zip(items, answers) if answerable(i)]
    unans = [(i, a) for i, a in zip(items, answers) if not answerable(i)]
    answered = [(i, a) for i, a in ans if a["found"]]
    return {
        "refusal_unanswerable": (sum(not a["found"] for _, a in unans) / len(unans)) if unans else None,
        "false_refusal": (sum(not a["found"] for _, a in ans) / len(ans)) if ans else None,
        "citation_accuracy": (
            sum(any(matches(s, i, check_page=False) for s in a["sources"]) for i, a in answered) / len(answered)
        ) if answered else None,
    }


def fmt(x) -> str:
    return "–" if x is None else f"{x:.0%}"


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--k", type=int, default=TOP_K)
    p.add_argument("--mode", default=RETRIEVAL_MODE, choices=["hybrid", "dense", "sparse"])
    p.add_argument("--min-score", type=float, default=MIN_DENSE_SCORE)
    p.add_argument("--answers", action="store_true", help="also run the LLM (costs money)")
    p.add_argument("--name", default=None, help="experiment name for the results file")
    p.add_argument("--min-hit", type=float, default=None, help="fail (exit 1) if Hit@k(doc) is below this")
    args = p.parse_args(argv)
    name = args.name or args.mode

    from src.retrieve import get_retriever

    items = load_items()
    retriever = get_retriever()
    hits_per_item = [retriever.search(i["question"], k=args.k, mode=args.mode) for i in items]
    m = retrieval_metrics(items, hits_per_item, args.min_score)

    for row in m["per_question"]:
        mark = "✓" if row["page_rank"] else ("~" if row["doc_rank"] else "✗")
        print(f"{mark} doc@{row['doc_rank'] or '-'} page@{row['page_rank'] or '-'}  {row['question'][:70]}")
    print("  (✓ right page, ~ right document but wrong page, ✗ missed)\n")

    print(f"Retrieval  ({args.mode}, k={args.k}, n={m['n_answerable']})")
    print(f"  Hit@{args.k} doc {fmt(m['hit_doc'])}   Hit@{args.k} page {fmt(m['hit_page'])}   MRR {m['mrr']:.3f}")
    print(f"Abstention gate (cosine < {args.min_score}, n_unanswerable={m['n_unanswerable']})")
    print(f"  refuses unanswerable {fmt(m['gate_refusal_unanswerable'])}   false refusals {fmt(m['gate_false_refusal'])}")
    print(f"  best cosine, answerable:   {m['best_scores_answerable']}")
    print(f"  best cosine, unanswerable: {m['best_scores_unanswerable']}")
    print("  -> pick MIN_DENSE_SCORE between the two groups.")

    result = {"name": name, "mode": args.mode, "k": args.k, "min_score": args.min_score, "retrieval": m}

    if args.answers:
        from src.generate import answer

        answers = [answer(i["question"], retriever=retriever, min_score=args.min_score) for i in items]
        a = answer_metrics(items, answers)
        result["answers"] = a
        result["answer_details"] = [{"question": i["question"], **ans} for i, ans in zip(items, answers)]
        print("\nEnd-to-end (LLM)")
        print(f"  refuses unanswerable {fmt(a['refusal_unanswerable'])}   false refusals {fmt(a['false_refusal'])}"
              f"   citation accuracy {fmt(a['citation_accuracy'])}")

    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / f"{name}.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved -> {out}")
    print("\nREADME row:")
    print(f"| {name} | {fmt(m['hit_doc'])} | {fmt(m['hit_page'])} | {m['mrr']:.3f} "
          f"| {fmt(m['gate_refusal_unanswerable'])} | {fmt(m['gate_false_refusal'])} |")

    if args.min_hit is not None and m["hit_doc"] < args.min_hit:
        sys.exit(f"FAIL: Hit@{args.k} doc {m['hit_doc']:.2%} < required {args.min_hit:.2%}")


if __name__ == "__main__":
    main()
