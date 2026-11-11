from src.ingest import chunk_text, clean_text, guess_language, remove_boilerplate


def test_remove_boilerplate_drops_running_header_and_page_numbers_only():
    header = "This is a translation; only the German original is legally binding."
    pages = [f"{header}\npage {i}\nCredits\nSection {i} real content number {i}" for i in range(1, 6)]
    cleaned = remove_boilerplate(pages)
    assert all(header not in p and "page" not in p for p in cleaned)
    assert all("Credits" in p for p in cleaned), "short repeated labels must be kept"
    assert "Section 3 real content number 3" in cleaned[2]


def test_clean_text_joins_hyphenated_line_breaks():
    assert clean_text("Prüfungs-\nordnung   gilt") == "Prüfungsordnung gilt"


def test_clean_text_removes_toc_dot_leaders():
    assert clean_text("§ 18 Masterarbeit ............................ 15") == "§ 18 Masterarbeit … 15"


def test_chunks_are_never_empty_and_respect_size():
    paras = ["a" * 799, "b " * 300, "c" * 2000, "kurzer Absatz", "d " * 390]
    chunks = chunk_text("\n\n".join(paras), size=800, overlap=150)
    assert chunks, "expected some chunks"
    assert all(c.strip() for c in chunks), "no empty chunks"
    assert all(len(c) <= 800 for c in chunks), [len(c) for c in chunks]


def test_overlap_starts_on_word_boundary():
    words = " ".join(f"wort{i}" for i in range(300))
    p1, p2 = words[:700], "zweiter Absatz " * 30
    chunks = chunk_text(f"{p1}\n\n{p2}", size=800, overlap=150)
    second = chunks[1]
    first_token = second.split()[0]
    assert first_token.startswith("wort") and first_token in p1.split()


def test_guess_language():
    assert guess_language("Die Prüfung ist nicht bestanden und wird wiederholt") == "de"
    assert guess_language("How many times is the exam repeated for the students") == "en"


def test_guess_language_short_english_question_without_stopwords():
    assert guess_language("Until when can I cancel my exam registration?") == "en"
    assert guess_language("Bis wann kann ich mich abmelden?") == "de"
    assert guess_language("Prüfungsanmeldung stornieren") == "de"


def test_html_to_text_keeps_main_content_only_and_strips_soft_hyphens():
    from src.ingest import html_to_text
    page = ("<html><body><nav>Menu Home Login</nav><main><h1>Ge\u00adb\u00fch\u00adren</h1>"
            "<p>Gesamt: 351,15 \u20ac</p><ul><li>Sozialbeitrag 110,00 \u20ac</li></ul>"
            "<script>track()</script></main><footer>Impressum</footer></body></html>")
    text = html_to_text(page)
    assert text.split("\n\n")[:3] == ["Gebühren", "Gesamt: 351,15 €", "Sozialbeitrag 110,00 €"]
    assert "Menu" not in text and "Impressum" not in text and "track" not in text
