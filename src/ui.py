"""Chat UI, laid out like a small website: navbar, hero, topic cards, chat, sources, footer.

Two backends:
  UI_BACKEND=api   (default) talks to the FastAPI service:  uvicorn src.api:app  +  streamlit run src/ui.py
  UI_BACKEND=local runs retrieval + LLM inside the Streamlit process (used by streamlit_app.py on
                   Streamlit Community Cloud, where only one process runs). Builds the index on first start.
"""
import html
import os
import re
import time

import requests
import streamlit as st

from src.download import SOURCE_URLS

API_BASE = os.getenv("API_URL", "http://localhost:8000")
UI_BACKEND = os.getenv("UI_BACKEND", "api")
QUOTA_MESSAGE = ("The free daily LLM quota of this demo is used up. Please try again later "
                 "(it frees up within 24 hours), or run the project locally with your own key.")

# Readable names for the sources: (title, language, group). Falls back to the file name.
DOC_NAMES = {
    "upb_eim_master_general_provisions_v3.pdf": ("General Provisions, EIM Master", "EN", "Exam regulations"),
    "upb_eim_master_allgemeine_bestimmungen_v3_de.pdf": ("Allgemeine Bestimmungen, EIM Master", "DE", "Exam regulations"),
    "upb_ese_special_provisions_v3.pdf": ("Special Provisions, ESE Master v3", "EN", "Exam regulations"),
    "upb_ese_besondere_bestimmungen_v3_de.pdf": ("Besondere Bestimmungen, ESE Master v3", "DE", "Exam regulations"),
    "upb_ese_besondere_bestimmungen_v3_aenderung_2024_09_de.pdf":
        ("Änderung der Besonderen Bestimmungen (09/2024)", "DE", "Exam regulations"),
    "upb_ese_transitional_regulations_v2_to_v3_en.pdf": ("Transitional Regulations v2 → v3", "EN", "Exam regulations"),
    "upb_ese_module_handbook_v3_ws2627.pdf": ("Module Handbook ESE v3, WS 26/27", "EN", "Programme"),
    "upb_ese_preamble_v3.pdf": ("Preamble to the Module Handbook", "EN", "Programme"),
    "upb_einschreibungsordnung_2026_de.pdf": ("Einschreibungsordnung (28.04.2026)", "DE", "Enrolment & fees"),
    "upb_io_enrolment_manual_en.pdf": ("Enrolment Manual, International Office", "EN", "Enrolment & fees"),
    "upb_io_short_guide_ss26_en.pdf": ("Enrolment & Arrival Short Guide (SS 26)", "EN", "Enrolment & fees"),
    "upb_io_enrollment_en.html": ("Enrolment, International Office", "EN", "Enrolment & fees"),
    "upb_rueckmeldung_gebuehren_de.html": ("Rückmeldung und Gebühren", "DE", "Enrolment & fees"),
    "upb_io_health_insurance_en.html": ("Health Insurance for Students", "EN", "Living in Paderborn"),
    "upb_semestertermine_de.html": ("Semesterdauer und Vorlesungszeiten", "DE", "Dates & PAUL"),
    "upb_paul_fristen_termine_de.html": ("PAUL: Fristen und Termine", "DE", "Dates & PAUL"),
    "upb_paul_guide_students_2026_de.pdf": ("PAUL-Anleitung für Studierende", "DE", "Dates & PAUL"),
    "upb_introducing_paul_en.pdf": ("Introducing PAUL", "EN", "Dates & PAUL"),
    "upb_thesis_electronic_submission_de.pdf": ("Elektronische Abgabe der Abschlussarbeit", "DE", "Thesis"),
}

TOPICS = [
    ("📝", "Exams & retakes", ["How many times can I retake an exam?",
                               "Bis wann kann ich mich von einer Prüfung abmelden?"]),
    ("🎓", "Master's thesis", ["How long do I have to write my master's thesis?",
                               "Wie lade ich meine Masterarbeit elektronisch in PAUL hoch?"]),
    ("💶", "Enrolment & fees", ["How much is the semester fee?",
                                "Which documents do I need for enrolment?"]),
    ("📅", "Semester dates", ["When does the lecture period start in the winter semester?",
                              "Wann ist die vorlesungsfreie Zeit an Weihnachten?"]),
    ("🏥", "Health insurance", ["Do I need German health insurance as a student?",
                                "What if I am over 30 years old?"]),
    ("🌍", "Admission", ["What IELTS score do I need for admission?",
                         "Do I need German language skills to be admitted to ESE?"]),
]

CSS = """
<style>
/* hide Streamlit's own chrome so the page reads as a website */
#MainMenu, footer, header[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"] {display: none;}
.block-container {max-width: 1080px; padding: 0 1.5rem 7rem 1.5rem;}
html, body, [class*="st-"] {font-family: "Inter", "Segoe UI", system-ui, -apple-system, sans-serif;}

.nav {
  position: sticky; top: 0; z-index: 50; display: flex; align-items: center; justify-content: space-between;
  padding: .9rem 0; margin-bottom: 1.2rem; background: rgba(255,255,255,.92); backdrop-filter: blur(8px);
  border-bottom: 1px solid #e5e7eb;
}
.nav .brand {display: flex; align-items: center; gap: .6rem; font-weight: 800; font-size: 1.08rem; color: #0f172a;}
.nav .logo {
  width: 2.1rem; height: 2.1rem; border-radius: 10px; display: grid; place-items: center; color: white;
  background: linear-gradient(135deg, #1e3a8a, #2563eb); font-size: 1.1rem;
}
.nav .brand small {display: block; font-weight: 500; color: #64748b; font-size: .74rem; margin-top: -.15rem;}
.nav .links {display: flex; gap: 1.4rem; align-items: center;}
.nav .links a {color: #334155; text-decoration: none; font-size: .9rem; font-weight: 500;}
.nav .links a:hover {color: #2563eb;}
.pill {display: inline-flex; align-items: center; gap: .4rem; font-size: .78rem; font-weight: 600;
  padding: .25rem .7rem; border-radius: 999px; border: 1px solid #e5e7eb; background: #f8fafc; color: #334155;}
.pill .dot {width: .5rem; height: .5rem; border-radius: 50%;}

.hero {
  position: relative; overflow: hidden; border-radius: 24px; padding: 3rem 2.6rem; margin-bottom: 2.2rem; color: white;
  background: radial-gradient(circle at 85% 15%, rgba(14,165,233,.55), transparent 45%),
              linear-gradient(135deg, #0f1f5c 0%, #1e3a8a 45%, #2563eb 100%);
  box-shadow: 0 20px 45px rgba(30, 58, 138, .28);
}
.hero .eyebrow {display: inline-block; font-size: .78rem; font-weight: 600; letter-spacing: .04em; text-transform: uppercase;
  background: rgba(255,255,255,.14); border: 1px solid rgba(255,255,255,.25); padding: .25rem .75rem; border-radius: 999px;}
.hero h1 {color: white; font-size: 2.5rem; line-height: 1.15; font-weight: 800; margin: .9rem 0 .7rem 0; padding: 0; max-width: 680px;}
.hero p {font-size: 1.08rem; opacity: .92; max-width: 620px; margin: 0;}
.hero .stats {display: flex; gap: 2.2rem; margin-top: 1.8rem; flex-wrap: wrap;}
.hero .stat b {display: block; font-size: 1.6rem; font-weight: 800;}
.hero .stat span {font-size: .82rem; opacity: .8;}

.section-title {margin: 2.4rem 0 .3rem 0;}
.section-title h2 {font-size: 1.5rem; font-weight: 800; color: #0f172a; margin: 0; padding: 0;}
.section-title p {color: #64748b; margin: .25rem 0 0 0;}
.anchor {position: relative; top: -80px;}

.topic-head {display: flex; align-items: center; gap: .55rem; font-weight: 700; color: #0f172a; margin-bottom: .2rem;}
.topic-head .ico {width: 2rem; height: 2rem; border-radius: 9px; display: grid; place-items: center; background: #eff6ff;}
div[data-testid="stVerticalBlockBorderWrapper"] {border-radius: 16px !important;}
.stButton > button {
  border-radius: 10px; border: 1px solid #e2e8f0; background: #f8fafc; color: #1e293b; font-size: .86rem;
  text-align: left; justify-content: flex-start; padding: .45rem .75rem; transition: all .15s ease;
}
.stButton > button:hover {border-color: #2563eb; color: #1d4ed8; background: #eff6ff;}

.cite {
  display: inline-block; min-width: 1.25rem; padding: 0 .35rem; margin: 0 .1rem;
  background: #dbeafe; color: #1e40af; border-radius: 6px; font-size: .75rem;
  font-weight: 700; text-align: center; vertical-align: super; line-height: 1.2rem;
}
.answer {font-size: 1.02rem; line-height: 1.65; color: #0f172a;}
.notfound {
  background: #fffbeb; border: 1px solid #fcd34d; border-left: 5px solid #f59e0b;
  padding: .8rem 1rem; border-radius: 10px; color: #78350f;
}
.notfound small {display: block; margin-top: .3rem; color: #92400e; opacity: .85;}
.src {border: 1px solid #e5e7eb; border-radius: 12px; padding: .7rem .9rem; margin: .45rem 0; background: #f9fafb;}
.src .head {display: flex; align-items: center; gap: .5rem; flex-wrap: wrap;}
.src .num {background: #1e40af; color: white; border-radius: 6px; padding: 0 .45rem; font-weight: 700; font-size: .8rem;}
.src .title {font-weight: 600; color: #111827;}
.src a {margin-left: auto; font-size: .78rem; color: #2563eb; text-decoration: none;}
.badge {background: #e0e7ff; color: #3730a3; border-radius: 999px; padding: .05rem .55rem; font-size: .75rem;}
.lang {background: #f3f4f6; color: #374151; border-radius: 999px; padding: .05rem .5rem; font-size: .72rem;}
.src .quote {margin-top: .45rem; color: #4b5563; font-size: .86rem; font-style: italic; border-left: 3px solid #cbd5e1; padding-left: .6rem;}
.meta {color: #94a3b8; font-size: .78rem; margin-top: .4rem;}
.unverified {
  background: #fff7ed; border: 1px solid #fdba74; border-radius: 10px; padding: .6rem .9rem;
  margin-top: .5rem; color: #7c2d12; font-size: .86rem;
}
.unverified ul {margin: .3rem 0 0 1rem; padding: 0;}
.empty-chat {text-align: center; color: #94a3b8; padding: 1.6rem 0 .6rem 0; font-size: .92rem;}

.docs {display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: .8rem; margin-top: 1rem;}
.doc {display: flex; gap: .75rem; align-items: flex-start; border: 1px solid #e5e7eb; border-radius: 14px; padding: .85rem 1rem;
  background: white; text-decoration: none !important; transition: all .15s ease;}
.doc:hover {border-color: #93c5fd; box-shadow: 0 6px 18px rgba(37,99,235,.10); transform: translateY(-1px);}
.doc .kind {flex: none; font-size: .68rem; font-weight: 800; padding: .3rem .45rem; border-radius: 7px; color: white;}
.doc .kind.pdf {background: #dc2626;} .doc .kind.web {background: #0891b2;}
.doc .t {font-weight: 600; color: #0f172a; font-size: .9rem; line-height: 1.3;}
.doc .g {color: #64748b; font-size: .76rem; margin-top: .2rem;}

.steps {display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 1rem; margin-top: 1rem;}
.step {border-radius: 16px; padding: 1.2rem; background: #f8fafc; border: 1px solid #e5e7eb;}
.step .n {width: 2rem; height: 2rem; border-radius: 50%; display: grid; place-items: center; font-weight: 800;
  background: #2563eb; color: white; margin-bottom: .6rem;}
.step b {color: #0f172a;} .step p {color: #475569; font-size: .88rem; margin: .3rem 0 0 0;}

.site-footer {margin-top: 3rem; padding: 1.6rem 0; border-top: 1px solid #e5e7eb; color: #64748b; font-size: .82rem;
  display: flex; justify-content: space-between; flex-wrap: wrap; gap: .8rem;}

@media (max-width: 720px) {
  .nav .links a {display: none;}
  .hero {padding: 2rem 1.4rem;} .hero h1 {font-size: 1.8rem;}
}
</style>
"""


def doc_name(source: str) -> tuple[str, str, str]:
    return DOC_NAMES.get(source, (source, "", "Other"))


def render_answer(text: str) -> str:
    """Escape the model output (never trust it as HTML), then turn [1] into citation badges."""
    safe = html.escape(text).replace("\n", "<br>")
    return re.sub(r"\[(\d+)\]", r'<span class="cite">\1</span>', safe)


def source_link(source: str) -> str:
    url = SOURCE_URLS.get(source)
    return f'<a href="{html.escape(url)}" target="_blank" rel="noopener">Open original ↗</a>' if url else ""


def render_reply(data: dict) -> None:
    if not data.get("found", True):
        st.markdown(
            f'<div class="notfound">🔎 <b>{html.escape(data["answer"])}</b>'
            "<small>The documents don't cover this. I don't guess. Try rephrasing, "
            "or ask the Student Advisory Service.</small></div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(f'<div class="answer">{render_answer(data["answer"])}</div>', unsafe_allow_html=True)
        for s in data["sources"]:
            title, lang, _ = doc_name(s["source"])
            where = "web page" if s["source"].endswith(".html") else f'page {s["page"]}'
            snippet = html.escape(" ".join(s["snippet"].split())[:220])
            st.markdown(
                f'<div class="src"><div class="head"><span class="num">{s["n"]}</span>'
                f'<span class="title">{html.escape(title)}</span>'
                f'<span class="badge">{where}</span>'
                + (f'<span class="lang">{lang}</span>' if lang else "")
                + source_link(s["source"])
                + f'</div><div class="quote">“{snippet}…”</div></div>',
                unsafe_allow_html=True,
            )
    verdict = data.get("faithfulness") or {}
    if data.get("found", True) and verdict.get("supported") is False:
        claims = "".join(f"<li>{html.escape(c[:160])}</li>" for c in verdict.get("unsupported_claims", [])[:3])
        st.markdown(
            '<div class="unverified">⚠️ <b>Partly unverified.</b> An automatic check could not find these '
            f"statements on the cited pages. Please check the source before relying on them:<ul>{claims}</ul></div>",
            unsafe_allow_html=True,
        )
    elif data.get("found", True) and verdict.get("supported") is True:
        st.markdown('<div class="meta">✅ Checked against the cited pages</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="meta">⏱ {data["latency_ms"] / 1000:.1f} s</div>', unsafe_allow_html=True)


def friendly_error(text: str) -> str:
    low = text.lower()
    if "429" in low or "rate limit" in low or "rate_limit" in low:
        return QUOTA_MESSAGE
    if "missing credentials" in low or "api_key" in low or "401" in low:
        return ("The LLM API key is missing or invalid. Set LLM_API_KEY in .env (local) or in the app's "
                "Secrets on Streamlit Cloud, then reboot the app.")
    return f"Something went wrong: {text[:300]}"


def ask_api(question: str) -> dict:
    try:
        r = requests.post(f"{API_BASE}/ask", json={"question": question}, timeout=120)
    except requests.ConnectionError:
        return {"error": f"Can't reach the API at {API_BASE}. Is `uvicorn src.api:app` running?"}
    if not r.ok:
        return {"error": friendly_error(f"Error {r.status_code}: {r.text}")}
    return r.json()


@st.cache_resource(show_spinner=False)
def local_retriever():
    """Load the index once per server process; build it first if it doesn't exist (fresh cloud container)."""
    from src.config import BM25_FILE, CHUNKS_FILE, EMBEDDINGS_FILE

    if not (CHUNKS_FILE.exists() and EMBEDDINGS_FILE.exists() and BM25_FILE.exists()):
        from src import download, index, ingest

        download.main()
        ingest.main()
        index.main()
    from src.retrieve import get_retriever

    return get_retriever()


def ask_local(question: str) -> dict:
    from src.generate import answer

    start = time.perf_counter()
    try:
        result = answer(question, retriever=local_retriever())
    except Exception as e:  # LLM down, quota used up, wrong key...
        return {"error": friendly_error(f"{type(e).__name__}: {e}")}
    return {**result, "latency_ms": int((time.perf_counter() - start) * 1000)}


def ask(question: str) -> dict:
    return ask_local(question) if UI_BACKEND == "local" else ask_api(question)


def api_online() -> bool:
    try:
        return requests.get(f"{API_BASE}/health", timeout=2).ok
    except requests.RequestException:
        return False


def section(anchor: str, title: str, subtitle: str) -> None:
    st.markdown(f'<div class="anchor" id="{anchor}"></div><div class="section-title"><h2>{title}</h2>'
                f"<p>{subtitle}</p></div>", unsafe_allow_html=True)


# ---------------------------------------------------------------- page
st.set_page_config(page_title="UPB Study Assistant", page_icon="🎓", layout="wide",
                   initial_sidebar_state="collapsed")
st.markdown(CSS, unsafe_allow_html=True)

if UI_BACKEND == "local":
    online, status = True, "Online"
else:
    online = api_online()
    status = "Online" if online else "API offline"
n_sources = len(SOURCE_URLS)
n_web = sum(name.endswith(".html") for name in SOURCE_URLS)

# navbar
st.markdown(
    f"""<div class="nav">
      <div class="brand"><div class="logo">🎓</div><div>UPB Study Assistant<small>Paderborn University</small></div></div>
      <div class="links"><a href="#topics">Topics</a><a href="#ask">Ask</a><a href="#sources">Sources</a>
        <a href="#how">How it works</a>
        <span class="pill"><span class="dot" style="background:{'#22c55e' if online else '#ef4444'}"></span>{status}</span>
      </div></div>""",
    unsafe_allow_html=True,
)
if not online:
    st.warning("The answer service is offline. Start it with `uvicorn src.api:app --port 8000`, then reload this page.")

# hero
st.markdown(
    f"""<div class="hero"><span class="eyebrow">For students of Paderborn University</span>
    <h1>Answers to your study questions, straight from the official documents.</h1>
    <p>Exam rules, retakes, thesis deadlines, enrolment, fees, semester dates and health insurance,
    in English or German. Every answer cites the exact document and page.</p>
    <div class="stats"><div class="stat"><b>{n_sources}</b><span>official sources</span></div>
    <div class="stat"><b>EN · DE</b><span>ask in either language</span></div>
    <div class="stat"><b>Page-level</b><span>citations on every answer</span></div>
    <div class="stat"><b>“I don't know”</b><span>when the documents don't say</span></div></div></div>""",
    unsafe_allow_html=True,
)

if "history" not in st.session_state:
    st.session_state.history = []   # list of (role, payload); payload is str (user) or dict (assistant)

if UI_BACKEND == "local":
    with st.spinner("Starting up: loading the search index. On a fresh server this downloads the documents "
                    "and builds the index first (about 3-5 minutes, only once)…"):
        local_retriever()

# topics: each example question is a button that asks it
pending = None
section("topics", "Popular topics", "Click a question to ask it, or type your own below.")
for row in range(0, len(TOPICS), 3):
    cols = st.columns(3)
    for col, (icon, name, questions) in zip(cols, TOPICS[row:row + 3]):
        with col.container(border=True):
            st.markdown(f'<div class="topic-head"><span class="ico">{icon}</span>{name}</div>', unsafe_allow_html=True)
            for q in questions:
                if st.button(q, key=f"q-{q}", width="stretch"):
                    pending = q

# chat
section("ask", "Ask a question", "Answers come only from the documents listed below. "
        "Only the German versions of regulations are legally binding.")
if not st.session_state.history and not pending:
    st.markdown('<div class="empty-chat">💬 Your conversation will appear here.</div>', unsafe_allow_html=True)
for role, payload in st.session_state.history:
    with st.chat_message(role, avatar="🧑‍🎓" if role == "user" else "🎓"):
        if role == "user":
            st.markdown(payload)
        elif "error" in payload:
            st.error(payload["error"])
        else:
            render_reply(payload)

question = st.chat_input("Ask a question, e.g. “Wie oft darf ich eine Prüfung wiederholen?”") or pending
if question:
    with st.chat_message("user", avatar="🧑‍🎓"):
        st.markdown(question)
    with st.chat_message("assistant", avatar="🎓"):
        with st.spinner("Searching the documents…"):
            data = ask(question)
        if "error" in data:
            st.error(data["error"])
        else:
            render_reply(data)
    st.session_state.history += [("user", question), ("assistant", data)]
if st.session_state.history:
    if st.button("🗑️ Clear conversation"):
        st.session_state.history = []
        st.rerun()

# sources
section("sources", "Sources", f"{n_sources - n_web} official PDFs and {n_web} university web pages. "
        "Click one to open the original.")
cards = []
for name in sorted(SOURCE_URLS, key=lambda n: (doc_name(n)[2], doc_name(n)[0])):
    title, lang, group = doc_name(name)
    kind = ("web", "WEB") if name.endswith(".html") else ("pdf", "PDF")
    cards.append(
        f'<a class="doc" href="{html.escape(SOURCE_URLS[name])}" target="_blank" rel="noopener">'
        f'<span class="kind {kind[0]}">{kind[1]}</span><div><div class="t">{html.escape(title)}</div>'
        f'<div class="g">{html.escape(group)} · {lang}</div></div></a>'
    )
st.markdown(f'<div class="docs">{"".join(cards)}</div>', unsafe_allow_html=True)

# how it works
section("how", "How it works", "Built to be trustworthy rather than chatty.")
st.markdown(
    """<div class="steps">
    <div class="step"><div class="n">1</div><b>Search</b><p>Your question is matched against every page of the
    official documents, by meaning and by keywords, in English and German.</p></div>
    <div class="step"><div class="n">2</div><b>Answer with citations</b><p>The AI may only use the passages it found
    and must cite each one. Without a source, there is no answer.</p></div>
    <div class="step"><div class="n">3</div><b>Check</b><p>A second model checks the answer against the cited pages
    and flags anything it can't find there.</p></div>
    <div class="step"><div class="n">4</div><b>Say “I don't know”</b><p>If the documents don't cover your question,
    you are told so instead of getting a guess.</p></div></div>""",
    unsafe_allow_html=True,
)

st.markdown(
    """<div class="site-footer"><span>🎓 UPB Study Assistant · a student project, not an official service of
    Paderborn University.</span><span>Always confirm important deadlines with the Studierendenservice or your
    examination office.</span></div>""",
    unsafe_allow_html=True,
)
