from src.retrieve import cap_per_source

CHUNKS = [{"source": s} for s in ["guide.pdf"] * 5 + ["visa.html", "rules.pdf"]]


def test_cap_lets_other_documents_in():
    # chunks 0-4 are all from one guide; with a cap of 3 the visa page (5) and rules (6) get the free slots
    assert cap_per_source([0, 1, 2, 3, 4, 5, 6], CHUNKS, k=5, cap=3) == [0, 1, 2, 5, 6]


def test_cap_off_keeps_plain_top_k():
    assert cap_per_source([0, 1, 2, 3, 4, 5, 6], CHUNKS, k=5, cap=0) == [0, 1, 2, 3, 4]


def test_fewer_candidates_than_k():
    assert cap_per_source([0, 1, 2, 3], CHUNKS, k=5, cap=3) == [0, 1, 2]
