"""Chat UI, laid out like a small website: navbar, hero, topic cards, chat, sources, footer.

Two backends:
  UI_BACKEND=api   (default) talks to the FastAPI service:  uvicorn src.api:app  +  streamlit run src/ui.py
  UI_BACKEND=local runs retrieval + LLM inside the Streamlit process (used by streamlit_app.py on
                   Streamlit Community Cloud, where only one process runs). Builds the index on first start.
"""
import html
import os
import re
import sys
import time
from pathlib import Path

import requests
import streamlit as st

# `streamlit run src/ui.py` puts src/ (not the project root) on sys.path, so `import src` would fail.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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
    "upb_beurlaubung_de.html": ("Beurlaubung (Urlaubssemester)", "DE", "Study organisation"),
    "upb_exmatrikulation_de.html": ("Exmatrikulation und Streichung", "DE", "Study organisation"),
    "upb_studiengangwechsel_de.html": ("Studiengang wechseln, Parallelstudium", "DE", "Study organisation"),
    "upb_io_finances_en.html": ("Finances & cost of living", "EN", "Living in Paderborn"),
    "upb_io_visa_first_steps_en.html": ("Visa application & first steps", "EN", "Living in Paderborn"),
    "upb_io_housing_en.html": ("Housing options", "EN", "Living in Paderborn"),
}

TOPICS = [  # (icon, name, accent colour, example questions)
    ("📝", "Exams & retakes", "#2563eb", ["How many times can I retake an exam?",
                                          "Bis wann kann ich mich von einer Prüfung abmelden?"]),
    ("🎓", "Master's thesis", "#7c3aed", ["How long do I have to write my master's thesis?",
                                          "Wie lade ich meine Masterarbeit elektronisch in PAUL hoch?"]),
    ("💶", "Enrolment & fees", "#059669", ["How much is the semester fee?",
                                           "Which documents do I need for enrolment?"]),
    ("📅", "Semester dates", "#ea580c", ["When does the lecture period start in the winter semester?",
                                         "Wann ist die vorlesungsfreie Zeit an Weihnachten?"]),
    ("🏥", "Health insurance", "#e11d48", ["Do I need German health insurance as a student?",
                                           "What if I am over 30 years old?"]),
    ("🌍", "Admission", "#0891b2", ["What IELTS score do I need for admission?",
                                    "Do I need German language skills to be admitted to ESE?"]),
    ("⏸️", "Leave & de-registration", "#d97706", ["Kann ich ein Urlaubssemester beantragen?",
                                                  "How do I de-register from the university?"]),
    ("🏠", "Living & visa", "#4f46e5", ["How much money do I need per month in Paderborn?",
                                        "Where can I find a room in a student dormitory?"]),
]

CSS = """
<style>
@import url("https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Plus+Jakarta+Sans:wght@700;800&display=swap");

:root {
  --ink: #0f172a; --muted: #64748b; --line: #e2e8f0; --brand: #2563eb; --brand-dark: #1e3a8a;
  --card: rgba(255,255,255,.82); --shadow: 0 10px 30px -12px rgba(15,23,42,.18);
}

/* hide Streamlit's own chrome so the page reads as a website */
#MainMenu, footer, header[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"] {display: none;}
html, body, [class*="st-"] {font-family: "Inter", "Segoe UI", system-ui, -apple-system, sans-serif;}
.stApp {
  background:
    radial-gradient(1200px 500px at 10% -10%, rgba(37,99,235,.10), transparent 60%),
    radial-gradient(900px 500px at 100% 0%, rgba(124,58,237,.08), transparent 60%),
    linear-gradient(180deg, #f8fafc 0%, #ffffff 40%, #f8fafc 100%);
}
.block-container {max-width: 1200px; padding: 0 1.5rem 7rem 1.5rem;}
h1, h2, h3 {font-family: "Plus Jakarta Sans", "Inter", sans-serif !important; letter-spacing: -.02em;}

/* ---------- navbar */
.nav {
  position: sticky; top: .6rem; z-index: 50; display: flex; align-items: center; justify-content: space-between;
  padding: .7rem 1.1rem; margin: .6rem 0 1.4rem 0; border-radius: 16px;
  background: rgba(255,255,255,.75); backdrop-filter: saturate(180%) blur(12px);
  border: 1px solid rgba(226,232,240,.9); box-shadow: 0 4px 20px -8px rgba(15,23,42,.12);
}
.nav .brand {display: flex; align-items: center; gap: .65rem; font-weight: 800; font-size: 1.05rem; color: var(--ink);}
.nav .logo {
  width: 2.3rem; height: 2.3rem; border-radius: 12px; display: grid; place-items: center; color: white; font-size: 1.15rem;
  background: linear-gradient(135deg, #1e3a8a, #2563eb 55%, #7c3aed); box-shadow: 0 6px 16px -4px rgba(37,99,235,.55);
}
.nav .brand small {display: block; font-weight: 500; color: var(--muted); font-size: .74rem; margin-top: -.1rem;}
.nav .links {display: flex; gap: .3rem; align-items: center;}
.nav .links a {color: #334155; text-decoration: none; font-size: .88rem; font-weight: 500; padding: .4rem .75rem; border-radius: 10px;
  transition: all .15s ease;}
.nav .links a:hover {color: var(--brand); background: #eff6ff;}
.pill {display: inline-flex; align-items: center; gap: .45rem; font-size: .78rem; font-weight: 600; margin-left: .4rem;
  padding: .3rem .75rem; border-radius: 999px; border: 1px solid var(--line); background: white; color: #334155;}
.pill .dot {width: .5rem; height: .5rem; border-radius: 50%; box-shadow: 0 0 0 3px rgba(34,197,94,.18);}
.pill .dot.off {box-shadow: 0 0 0 3px rgba(239,68,68,.18);}

/* ---------- hero */
.hero {
  position: relative; overflow: hidden; border-radius: 28px; padding: 3.4rem 3rem 2.6rem 3rem; margin-bottom: 1rem; color: white;
  background: linear-gradient(135deg, #0b1442 0%, #1e3a8a 42%, #2563eb 78%, #4f46e5 100%);
  box-shadow: 0 30px 60px -20px rgba(30,58,138,.55);
}
.hero::before {  /* faint grid */
  content: ""; position: absolute; inset: 0; opacity: .14; pointer-events: none;
  background-image: linear-gradient(rgba(255,255,255,.5) 1px, transparent 1px),
                    linear-gradient(90deg, rgba(255,255,255,.5) 1px, transparent 1px);
  background-size: 38px 38px;
  -webkit-mask-image: radial-gradient(circle at 70% 30%, black, transparent 70%);
          mask-image: radial-gradient(circle at 70% 30%, black, transparent 70%);
}
.hero .blob {position: absolute; border-radius: 50%; filter: blur(60px); opacity: .55; pointer-events: none;
  animation: float 14s ease-in-out infinite;}
.hero .b1 {width: 340px; height: 340px; background: #38bdf8; top: -120px; right: -60px;}
.hero .b2 {width: 280px; height: 280px; background: #a855f7; bottom: -140px; right: 28%; animation-delay: -5s;}
.hero .b3 {width: 200px; height: 200px; background: #22d3ee; top: 40%; left: -80px; animation-delay: -9s; opacity: .35;}
@keyframes float {0%,100% {transform: translate(0,0) scale(1);} 50% {transform: translate(-30px,25px) scale(1.08);}}
.hero > * {position: relative;}
.hero .eyebrow {display: inline-flex; align-items: center; gap: .45rem; font-size: .76rem; font-weight: 600; letter-spacing: .05em;
  text-transform: uppercase; background: rgba(255,255,255,.12); border: 1px solid rgba(255,255,255,.25);
  padding: .3rem .8rem; border-radius: 999px; backdrop-filter: blur(6px);}
.hero h1 {color: white; font-size: 2.9rem; line-height: 1.1; font-weight: 800; margin: 1rem 0 .8rem 0; padding: 0; max-width: 760px;}
.hero h1 .grad {background: linear-gradient(90deg, #7dd3fc, #c4b5fd); -webkit-background-clip: text; background-clip: text; color: transparent;}
.hero p {font-size: 1.1rem; opacity: .9; max-width: 640px; margin: 0; line-height: 1.6;}
.hero .cta {display: flex; gap: .7rem; margin-top: 1.6rem; flex-wrap: wrap;}
.hero .cta a {text-decoration: none; font-weight: 600; font-size: .92rem; padding: .7rem 1.25rem; border-radius: 12px; transition: all .15s ease;}
.hero .cta .primary {background: white; color: #1e3a8a; box-shadow: 0 8px 20px -6px rgba(0,0,0,.35);}
.hero .cta .primary:hover {transform: translateY(-1px); box-shadow: 0 12px 24px -6px rgba(0,0,0,.4);}
.hero .cta .ghost {color: white; border: 1px solid rgba(255,255,255,.35); background: rgba(255,255,255,.06);}
.hero .cta .ghost:hover {background: rgba(255,255,255,.14);}
.hero .stats {display: grid; grid-template-columns: repeat(4, 1fr); gap: .8rem; margin-top: 2.2rem;}
.hero .stat {background: rgba(255,255,255,.09); border: 1px solid rgba(255,255,255,.18); border-radius: 16px;
  padding: .9rem 1rem; backdrop-filter: blur(8px);}
.hero .stat b {display: block; font-size: 1.45rem; font-weight: 800; font-family: "Plus Jakarta Sans", sans-serif;}
.hero .stat span {font-size: .8rem; opacity: .78;}

/* ---------- sections */
.section-title {margin: 2.8rem 0 .4rem 0;}
.section-title .kicker {display: inline-block; font-size: .74rem; font-weight: 700; letter-spacing: .08em; text-transform: uppercase;
  color: var(--brand); background: #eff6ff; padding: .2rem .6rem; border-radius: 999px; margin-bottom: .45rem;}
.section-title h2 {font-size: 1.75rem; font-weight: 800; color: var(--ink); margin: 0; padding: 0;}
.section-title p {color: var(--muted); margin: .3rem 0 0 0;}
.anchor {position: relative; top: -90px;}

/* ---------- topic cards (containers are keyed topic-0 … topic-7) */
div[class*="st-key-topic-"] {
  background: var(--card); border: 1px solid var(--line); border-radius: 18px; padding: 1rem 1rem .6rem 1rem;
  box-shadow: var(--shadow); transition: transform .18s ease, box-shadow .18s ease, border-color .18s ease;
  border-top: 4px solid var(--accent, var(--brand)); height: 100%;
}
div[class*="st-key-topic-"]:hover {transform: translateY(-3px); box-shadow: 0 18px 40px -14px rgba(15,23,42,.28);}
.topic-head {display: flex; align-items: center; gap: .6rem; font-weight: 700; color: var(--ink); margin-bottom: .1rem; font-size: .98rem;}
.topic-head .ico {width: 2.3rem; height: 2.3rem; border-radius: 11px; display: grid; place-items: center; font-size: 1.1rem;}
div[class*="st-key-topic-"] .stButton > button {
  border-radius: 10px; border: 1px solid transparent; background: #f8fafc; color: #1e293b; font-size: .84rem;
  text-align: left; justify-content: flex-start; padding: .45rem .7rem; line-height: 1.35; min-height: 2.6rem; transition: all .15s ease;
}
div[class*="st-key-topic-"] .stButton > button:hover {border-color: var(--accent, var(--brand)); color: var(--accent, var(--brand)); background: white;}
div[class*="st-key-topic-"] .stButton > button p {font-size: .84rem; text-align: left;}
div[class*="st-key-topic-"] .stButton > button > div {justify-content: flex-start; width: 100%;}

/* ---------- chat */
div.st-key-chat {
  background: white; border: 1px solid var(--line); border-radius: 22px; padding: 1.2rem 1.3rem;
  box-shadow: var(--shadow); margin-top: .9rem;
}
[data-testid="stChatMessage"] {background: transparent; padding: .6rem .2rem; gap: .8rem;}
[data-testid="stChatMessage"]:has([aria-label="Chat message from user"]) [data-testid="stChatMessageContent"] {
  background: linear-gradient(135deg, #eff6ff, #eef2ff); border: 1px solid #dbeafe; border-radius: 4px 16px 16px 16px;
  padding: .65rem 1rem; flex: 0 1 auto;
}
[data-testid="stChatMessage"]:has([aria-label="Chat message from assistant"]) [data-testid="stChatMessageContent"] {
  background: #fcfdff; border: 1px solid var(--line); border-radius: 4px 16px 16px 16px; padding: .85rem 1.1rem;
}
[data-testid="stChatMessageAvatarCustom"] {background: linear-gradient(135deg, #e0e7ff, #dbeafe); border-radius: 12px;}
[data-testid="stChatInput"] {border-radius: 16px; box-shadow: 0 10px 30px -10px rgba(37,99,235,.35);}
[data-testid="stChatInput"] > div {border-radius: 16px; border: 1px solid #c7d2fe;}
[data-testid="stBottomBlockContainer"], [data-testid="stBottom"] > div {background: transparent;}

.cite {
  display: inline-block; min-width: 1.25rem; padding: 0 .35rem; margin: 0 .1rem;
  background: linear-gradient(135deg, #dbeafe, #e0e7ff); color: #1e40af; border-radius: 6px; font-size: .72rem;
  font-weight: 700; text-align: center; vertical-align: super; line-height: 1.15rem; border: 1px solid #bfdbfe;
}
.answer {font-size: 1.02rem; line-height: 1.7; color: var(--ink);}
.notfound {
  background: linear-gradient(135deg, #fffbeb, #fef3c7); border: 1px solid #fcd34d; border-left: 5px solid #f59e0b;
  padding: .85rem 1.05rem; border-radius: 12px; color: #78350f;
}
.notfound small {display: block; margin-top: .3rem; color: #92400e; opacity: .85;}
.src-label {margin: .9rem 0 .2rem 0; font-size: .74rem; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; color: var(--muted);}
.src {border: 1px solid var(--line); border-radius: 14px; padding: .7rem .95rem; margin: .45rem 0; background: white;
  transition: border-color .15s ease, box-shadow .15s ease;}
.src:hover {border-color: #93c5fd; box-shadow: 0 6px 18px -8px rgba(37,99,235,.35);}
.src .head {display: flex; align-items: center; gap: .5rem; flex-wrap: wrap;}
.src .num {background: linear-gradient(135deg, #1e40af, #4f46e5); color: white; border-radius: 7px; padding: 0 .45rem; font-weight: 700; font-size: .78rem;}
.src .title {font-weight: 600; color: #111827; font-size: .92rem;}
.src a {margin-left: auto; font-size: .78rem; color: var(--brand); text-decoration: none; font-weight: 600;}
.badge {background: #eef2ff; color: #3730a3; border-radius: 999px; padding: .05rem .55rem; font-size: .72rem; font-weight: 600;}
.lang {background: #f1f5f9; color: #334155; border-radius: 999px; padding: .05rem .5rem; font-size: .7rem; font-weight: 700;}
.src .quote {margin-top: .45rem; color: #475569; font-size: .85rem; font-style: italic; border-left: 3px solid #c7d2fe; padding-left: .65rem;}
.meta {display: inline-flex; gap: .35rem; align-items: center; color: var(--muted); font-size: .76rem; margin: .5rem .5rem 0 0;
  background: #f8fafc; border: 1px solid var(--line); border-radius: 999px; padding: .15rem .6rem;}
.meta.ok {color: #047857; background: #ecfdf5; border-color: #a7f3d0;}
.unverified {
  background: #fff7ed; border: 1px solid #fdba74; border-radius: 12px; padding: .65rem .95rem;
  margin-top: .6rem; color: #7c2d12; font-size: .86rem;
}
.unverified ul {margin: .3rem 0 0 1rem; padding: 0;}
.empty-chat {text-align: center; color: var(--muted); padding: 2rem 0 1.2rem 0;}
.empty-chat .big {font-size: 2.4rem; display: block; margin-bottom: .4rem;}
.empty-chat b {display: block; color: var(--ink); font-size: 1.05rem; margin-bottom: .2rem;}

/* ---------- source library */
.docs {display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: .8rem; margin-top: 1rem;}
.group-title {grid-column: 1 / -1; margin: .9rem 0 -.2rem 0; font-size: .78rem; font-weight: 700; letter-spacing: .06em;
  text-transform: uppercase; color: var(--muted); display: flex; align-items: center; gap: .6rem;}
.group-title::after {content: ""; flex: 1; height: 1px; background: var(--line);}
.doc {display: flex; gap: .8rem; align-items: center; border: 1px solid var(--line); border-radius: 14px; padding: .8rem 1rem;
  background: white; text-decoration: none !important; transition: all .15s ease; box-shadow: 0 1px 2px rgba(15,23,42,.04);}
.doc:hover {border-color: #93c5fd; box-shadow: 0 10px 24px -10px rgba(37,99,235,.35); transform: translateY(-2px);}
.doc .kind {flex: none; font-size: .66rem; font-weight: 800; width: 2.5rem; height: 2.5rem; display: grid; place-items: center;
  border-radius: 10px; color: white;}
.doc .kind.pdf {background: linear-gradient(135deg, #ef4444, #b91c1c);} .doc .kind.web {background: linear-gradient(135deg, #06b6d4, #0e7490);}
.doc .t {font-weight: 600; color: var(--ink); font-size: .9rem; line-height: 1.3;}
.doc .g {color: var(--muted); font-size: .75rem; margin-top: .2rem;}
.doc .arrow {margin-left: auto; color: #cbd5e1; font-size: 1rem; transition: color .15s ease;}
.doc:hover .arrow {color: var(--brand);}

/* ---------- how it works */
.steps {display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 1rem; margin-top: 1rem;}
.step {position: relative; border-radius: 18px; padding: 1.3rem; background: white; border: 1px solid var(--line); box-shadow: var(--shadow);}
.step .n {width: 2.4rem; height: 2.4rem; border-radius: 12px; display: grid; place-items: center; font-weight: 800; font-size: 1.1rem;
  background: linear-gradient(135deg, #2563eb, #7c3aed); color: white; margin-bottom: .75rem; box-shadow: 0 8px 18px -6px rgba(79,70,229,.6);}
.step b {color: var(--ink); font-size: 1rem;} .step p {color: #475569; font-size: .88rem; margin: .35rem 0 0 0; line-height: 1.55;}

/* ---------- buttons outside cards (clear conversation) */
.stButton > button {border-radius: 10px;}

/* ---------- footer */
.site-footer {margin-top: 3.5rem; padding: 1.6rem 1.8rem; border-radius: 20px; color: #cbd5e1; font-size: .82rem;
  background: linear-gradient(135deg, #0f172a, #1e293b); display: flex; justify-content: space-between; flex-wrap: wrap; gap: .8rem;}
.site-footer b {color: white;}

@media (max-width: 900px) {.hero .stats {grid-template-columns: repeat(2, 1fr);}}
@media (max-width: 720px) {
  .nav .links a {display: none;}
  .hero {padding: 2.2rem 1.4rem;} .hero h1 {font-size: 1.9rem;}
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
        if data["sources"]:
            st.markdown('<div class="src-label">Sources</div>', unsafe_allow_html=True)
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
    checked = ""
    if data.get("found", True) and verdict.get("supported") is True:
        checked = '<span class="meta ok">✅ Checked against the cited pages</span>'
    st.markdown(f'{checked}<span class="meta">⏱ {data["latency_ms"] / 1000:.1f} s</span>', unsafe_allow_html=True)


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


def section(anchor: str, kicker: str, title: str, subtitle: str) -> None:
    st.markdown(f'<div class="anchor" id="{anchor}"></div><div class="section-title"><span class="kicker">{kicker}</span>'
                f"<h2>{title}</h2><p>{subtitle}</p></div>", unsafe_allow_html=True)


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
        <span class="pill"><span class="dot{'' if online else ' off'}"
          style="background:{'#22c55e' if online else '#ef4444'}"></span>{status}</span>
      </div></div>""",
    unsafe_allow_html=True,
)
if not online:
    st.warning("The answer service is offline. Start it with `uvicorn src.api:app --port 8000`, then reload this page.")

# hero
st.markdown(
    f"""<div class="hero"><div class="blob b1"></div><div class="blob b2"></div><div class="blob b3"></div>
    <span class="eyebrow">✨ For students of Paderborn University</span>
    <h1>Your study questions, answered <span class="grad">straight from the official documents.</span></h1>
    <p>Exam rules, retakes, thesis deadlines, enrolment, fees, semester dates, health insurance, housing and visas,
    in English or German. Every answer cites the exact document and page.</p>
    <div class="cta"><a class="primary" href="#ask">💬 Ask a question</a><a class="ghost" href="#topics">Browse topics</a>
      <a class="ghost" href="#sources">See the sources</a></div>
    <div class="stats"><div class="stat"><b>{n_sources}</b><span>official sources</span></div>
    <div class="stat"><b>EN · DE</b><span>ask in either language</span></div>
    <div class="stat"><b>Page-level</b><span>citations on every answer</span></div>
    <div class="stat"><b>No guessing</b><span>“I don't know” when the documents don't say</span></div></div></div>""",
    unsafe_allow_html=True,
)

if "history" not in st.session_state:
    st.session_state.history = []   # list of (role, payload); payload is str (user) or dict (assistant)

if UI_BACKEND == "local":
    with st.spinner("Starting up: loading the search index. On a fresh server this downloads the documents "
                    "and builds the index first (about 3-5 minutes, only once)…"):
        local_retriever()

# topics: each example question is a button that asks it. Containers are keyed topic-<i>, which
# Streamlit turns into the CSS class st-key-topic-<i>; that is how each card gets its accent colour.
pending = None
section("topics", "Start here", "Popular topics", "Click a question to ask it, or type your own below.")
accents = "".join(f"div.st-key-topic-{i} {{--accent: {color};}}" for i, (_, _, color, _) in enumerate(TOPICS))
st.markdown(f"<style>{accents}</style>", unsafe_allow_html=True)
for row in range(0, len(TOPICS), 4):
    cols = st.columns(4)
    for i, (col, (icon, name, color, questions)) in enumerate(zip(cols, TOPICS[row:row + 4]), start=row):
        with col.container(key=f"topic-{i}"):
            st.markdown(f'<div class="topic-head"><span class="ico" style="background:{color}1a">{icon}</span>'
                        f"{name}</div>", unsafe_allow_html=True)
            for q in questions:
                if st.button(q, key=f"q-{q}", width="stretch"):
                    pending = q

# chat
section("ask", "Chat", "Ask a question", "Answers come only from the documents listed below. "
        "Only the German versions of regulations are legally binding.")
question = st.chat_input("Ask a question, e.g. “Wie oft darf ich eine Prüfung wiederholen?”") or pending
with st.container(key="chat"):
    if not st.session_state.history and not question:
        st.markdown('<div class="empty-chat"><span class="big">💬</span><b>Ask anything about studying in Paderborn</b>'
                    "Pick a topic above or type below. Answers usually take a few seconds.</div>",
                    unsafe_allow_html=True)
    for role, payload in st.session_state.history:
        with st.chat_message(role, avatar="🧑‍🎓" if role == "user" else "🎓"):
            if role == "user":
                st.markdown(payload)
            elif "error" in payload:
                st.error(payload["error"])
            else:
                render_reply(payload)

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

# sources, grouped by topic
section("sources", "Library", "Sources", f"{n_sources - n_web} official PDFs and {n_web} university web pages. "
        "Click one to open the original.")
cards, last_group = [], None
for name in sorted(SOURCE_URLS, key=lambda n: (doc_name(n)[2], doc_name(n)[0])):
    title, lang, group = doc_name(name)
    if group != last_group:
        cards.append(f'<div class="group-title">{html.escape(group)}</div>')
        last_group = group
    web = name.endswith(".html")
    cards.append(
        f'<a class="doc" href="{html.escape(SOURCE_URLS[name])}" target="_blank" rel="noopener">'
        f'<span class="kind {"web" if web else "pdf"}">{"WEB" if web else "PDF"}</span>'
        f'<div><div class="t">{html.escape(title)}</div>'
        f'<div class="g">{"Web page" if web else "PDF document"} · {lang}</div></div><span class="arrow">↗</span></a>'
    )
st.markdown(f'<div class="docs">{"".join(cards)}</div>', unsafe_allow_html=True)

# how it works
section("how", "Under the hood", "How it works", "Built to be trustworthy rather than chatty.")
st.markdown(
    """<div class="steps">
    <div class="step"><div class="n">1</div><b>🔍 Search</b><p>Your question is matched against every page of the
    official documents, by meaning and by keywords, in English and German.</p></div>
    <div class="step"><div class="n">2</div><b>✍️ Answer with citations</b><p>The AI may only use the passages it
    found and must cite each one. Without a source, there is no answer.</p></div>
    <div class="step"><div class="n">3</div><b>✅ Check</b><p>A second model checks the answer against the cited
    pages and flags anything it can't find there.</p></div>
    <div class="step"><div class="n">4</div><b>🤚 Say “I don't know”</b><p>If the documents don't cover your
    question, you are told so instead of getting a guess.</p></div></div>""",
    unsafe_allow_html=True,
)

st.markdown(
    """<div class="site-footer"><span>🎓 <b>UPB Study Assistant</b> · a student project, not an official service of
    Paderborn University.</span><span>Always confirm important deadlines with the Studierendenservice or your
    examination office.</span></div>""",
    unsafe_allow_html=True,
)
