"""Run the faithfulness judge on answers that were already generated, without generating them again.

Why: generating answers is the expensive part (rate limits / cost). Retrieval is deterministic,
so we can rebuild the exact sources each saved answer cited and only pay for the judge calls.

Run:  python -m eval.judge_saved eval/results/fixes-llm.json
Output: eval/results/<input-name>-judged.json
"""
import json
import sys
from pathlib import Path

from eval.run_eval import RESULTS_DIR, faithfulness_metrics, fmt, load_items


def main(path: str):
    from src.config import JUDGE_MODEL
    from src.generate import check_faithfulness
    from src.retrieve import get_retriever

    saved = json.loads(Path(path).read_text(encoding="utf-8"))
    by_q = {d["question"]: d for d in saved["answer_details"]}
    items = [i for i in load_items() if i["question"] in by_q]
    retriever = get_retriever(saved.get("reranker") or "")

    answers, mismatched = [], 0
    for item in items:
        d = dict(by_q[item["question"]])
        d.pop("faithfulness", None)
        if d["found"]:
            hits = retriever.search(item["question"], k=saved["k"], mode=saved["mode"])
            # safety check: the rebuilt sources must be exactly the ones the saved answer cited
            if all(s["n"] <= len(hits) and (hits[s["n"] - 1]["source"], hits[s["n"] - 1]["page"]) ==
                   (s["source"], s["page"]) for s in d["sources"]):
                cited = [{**hits[s["n"] - 1], "n": s["n"]} for s in d["sources"]]
                d["faithfulness"] = check_faithfulness(d["answer"], cited)
            else:
                mismatched += 1
        answers.append(d)

    f = faithfulness_metrics(items, answers)
    print(f"Judge model: {JUDGE_MODEL}   answers judged: {f['n_judged']}   source mismatches skipped: {mismatched}")
    print(f"  judged supported {fmt(f['supported_rate'])}   unsupported {f['n_unsupported']}   unparseable {f['n_unknown']}")
    print(f"  if enforced: false refusals would be {fmt(f['false_refusal_if_enforced'])}")
    for d in answers:
        v = d.get("faithfulness") or {}
        if v.get("supported") is False:
            print(f"\n  ✗ {d['question']}\n    answer: {d['answer'][:200]}\n    judge:  {v['unsupported_claims'][:2]}")

    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / f"{Path(path).stem}-judged.json"
    out.write_text(json.dumps({"source_run": Path(path).name, "judge_model": JUDGE_MODEL, "faithfulness": f,
                               "mismatched": mismatched, "answer_details": answers},
                              indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved -> {out}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "eval/results/faithfulness-llm.json")
