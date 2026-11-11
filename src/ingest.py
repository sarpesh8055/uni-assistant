"""STEP 1 — Ingestion: PDFs and saved web pages -> clean text -> chunks with metadata.

Run:  python -m src.ingest
Output: data/processed/chunks.jsonl  (one JSON object per chunk)
"""
import json
import re

from src.config import CHUNK_OVERLAP, CHUNK_SIZE, CHUNKS_FILE, PROCESSED_DIR, RAW_DIR


def clean_text(text: str) -> str:
    """Fix the usual PDF mess: hyphenated line breaks, extra spaces, page noise."""
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)      # "Prüfungs-\nordnung" -> "Prüfungsordnung"
    text = re.sub(r"(?:\s*[.…]){4,}", " … ", text)    # table-of-contents dot leaders "......"
    text = re.sub(r"[ \t]+", " ", text)                # collapse spaces
    text = re.sub(r"\n{3,}", "\n\n", text)             # max one empty line
    return text.strip()


DE_WORDS = {"der", "die", "das", "und", "ist", "nicht", "für", "mit", "werden", "ich", "wie", "was", "wann",
            "wo", "kann", "darf", "muss", "mein", "meine", "eine", "einen", "ein", "bis", "oder", "auf", "im", "zu"}
EN_WORDS = {"the", "and", "is", "not", "for", "with", "are", "of", "to", "i", "how", "what", "when", "where",
            "can", "do", "does", "my", "a", "an", "until", "if", "or", "on", "in", "much", "many"}


def guess_language(text: str) -> str:
    """Very simple DE/EN detector based on common words. Good enough for metadata and for
    picking the answer language. Ties (e.g. very short text) count as German only if the
    text contains umlauts or ß; otherwise English."""
    words = re.findall(r"\b\w+\b", text.lower())
    de = sum(w in DE_WORDS for w in words)
    en = sum(w in EN_WORDS for w in words)
    if de == en:
        return "de" if re.search(r"[äöüß]", text.lower()) else "en"
    return "de" if de > en else "en"


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split on paragraphs, then pack paragraphs into chunks of ~`size` chars.

    Keeping paragraph boundaries gives the LLM complete thoughts instead of
    sentences cut in half. The overlap keeps context across chunk borders.
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks, current = [], ""
    for para in paragraphs:
        # a single paragraph longer than `size` gets hard-split
        while len(para) > size:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(para[:size])
            para = para[size - overlap:]
        if len(current) + len(para) + 2 <= size:
            current = f"{current}\n\n{para}" if current else para
        elif not current:
            current = para
        else:
            chunks.append(current)
            tail = current[-overlap:] if overlap else ""
            # start the overlap at a word boundary instead of mid-word
            if " " in tail:
                tail = tail[tail.index(" ") + 1:]
            if len(tail) + len(para) + 2 > size:   # never exceed the chunk size
                tail = ""
            current = f"{tail}\n\n{para}" if tail else para
    if current:
        chunks.append(current)
    return chunks


PAGE_NUMBER_LINE = re.compile(r"^\s*(page|seite)?\s*\d+(\s*(of|von|/)\s*\d+)?\s*$", re.I)


def _norm(line: str) -> str:
    return " ".join(line.split())   # exact match only: lines differing by a number are different content


def remove_boilerplate(pages: list[str], min_share: float = 0.5, min_len: int = 25) -> list[str]:
    """Drop running headers/footers: long lines that repeat on at least `min_share` of the pages
    (e.g. "This is a translation of ... only the German original is legally binding"),
    plus bare page-number lines. Short repeated lines are kept on purpose: in module
    handbooks labels like "Credits" or "Workload" repeat on every page and carry meaning."""
    if len(pages) < 3:
        return [ "\n".join(l for l in p.splitlines() if not PAGE_NUMBER_LINE.match(l)) for p in pages]
    counts: dict[str, int] = {}
    for p in pages:
        for key in {_norm(l) for l in p.splitlines()}:
            counts[key] = counts.get(key, 0) + 1
    repeated = {k for k, c in counts.items() if len(k) >= min_len and c >= min_share * len(pages)}
    return [
        "\n".join(l for l in p.splitlines() if _norm(l) not in repeated and not PAGE_NUMBER_LINE.match(l))
        for p in pages
    ]


def load_pdf(path):
    """Yield (page_number, text) for each page, with repeated headers/footers removed."""
    import pymupdf  # imported here so chunk_text can be tested without it

    with pymupdf.open(path) as doc:
        pages = remove_boilerplate([page.get_text() for page in doc])
    yield from enumerate(pages, start=1)


BLOCK_TAGS = ["h1", "h2", "h3", "h4", "h5", "p", "li", "tr", "dt", "dd", "div", "section", "table", "ul", "ol"]
INVISIBLE = dict.fromkeys(map(ord, "­​‌‍﻿"))   # soft hyphens, zero-width chars


def html_to_text(raw: bytes | str) -> str:
    """Main content of a university web page as text with paragraph breaks.
    Navigation, header and footer live outside <main> and are dropped."""
    from bs4 import BeautifulSoup  # imported here so the rest can be tested without it

    soup = BeautifulSoup(raw, "html.parser")
    root = soup.find("main") or soup.body or soup
    for tag in root.find_all(["script", "style", "nav", "form", "button", "svg", "noscript"]):
        tag.decompose()
    for br in root.find_all("br"):
        br.replace_with("\n")
    for cell in root.find_all(["td", "th"]):
        cell.insert_after(" ")
    for block in root.find_all(BLOCK_TAGS):
        block.insert_after("\n\n")
    text = root.get_text().translate(INVISIBLE)
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def load_html(path):
    """A web page has no pages; it becomes a single "page 1"."""
    yield 1, html_to_text(path.read_bytes())


def load_source(path):
    return load_html(path) if path.suffix == ".html" else load_pdf(path)


def main():
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    pdfs = sorted([*RAW_DIR.glob("*.pdf"), *RAW_DIR.glob("*.html")])
    if not pdfs:
        raise SystemExit(f"No PDFs or web pages found in {RAW_DIR}. Run `python -m src.download` first.")

    n = 0
    with open(CHUNKS_FILE, "w", encoding="utf-8") as out:
        for pdf in pdfs:
            for page_no, raw in load_source(pdf):
                text = clean_text(raw)
                if len(text) < 50:          # skip empty / cover pages
                    continue
                for j, chunk in enumerate(chunk_text(text)):
                    record = {
                        "id": f"{pdf.stem}-p{page_no}-c{j}",
                        "source": pdf.name,
                        "page": page_no,
                        "lang": guess_language(chunk),
                        "text": chunk,
                    }
                    out.write(json.dumps(record, ensure_ascii=False) + "\n")
                    n += 1
            print(f"✓ {pdf.name}")
    print(f"\nSaved {n} chunks from {len(pdfs)} sources -> {CHUNKS_FILE}")


if __name__ == "__main__":
    main()
