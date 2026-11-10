"""Chat UI that talks to the FastAPI backend.

Run (with the API already running):  streamlit run src/ui.py
"""
import html
import os
import re

import requests
import streamlit as st

API_BASE = os.getenv("API_URL", "http://localhost:8000")

# Readable names for the source PDFs (falls back to the file name).
DOC_NAMES = {
    "upb_eim_master_general_provisions_v3.pdf": ("General Provisions, EIM Master", "EN"),
    "upb_eim_master_allgemeine_bestimmungen_v3_de.pdf": ("Allgemeine Bestimmungen, EIM Master", "DE"),
    "upb_ese_special_provisions_v3.pdf": ("Special Provisions, ESE Master v3", "EN"),
    "upb_ese_besondere_bestimmungen_v3_de.pdf": ("Besondere Bestimmungen, ESE Master v3", "DE"),
    "upb_ese_besondere_bestimmungen_v3_aenderung_2024_09_de.pdf": ("Änderung der Besonderen Bestimmungen (09/2024)", "DE"),
    "upb_ese_module_handbook_v3_ws2627.pdf": ("Module Handbook ESE v3, WS 26/27", "EN"),
    "upb_ese_preamble_v3.pdf": ("Preamble to the Module Handbook", "EN"),
    "upb_ese_transitional_regulations_v2_to_v3_en.pdf": ("Transitional Regulations v2 → v3", "EN"),
    "upb_paul_guide_students_2026_de.pdf": ("PAUL-Anleitung für Studierende", "DE"),
    "upb_introducing_paul_en.pdf": ("Introducing PAUL", "EN"),
    "upb_thesis_electronic_submission_de.pdf": ("Elektronische Abgabe der Abschlussarbeit", "DE"),
}

EXAMPLES = [
    "How many times can I retake an exam?",
    "Bis wann kann ich mich von einer Prüfung abmelden?",
    "How long do I have to write my master's thesis?",
    "What IELTS score do I need for admission?",
]

CSS = """
<style>
.block-container {max-width: 820px; padding-top: 2rem;}
.hero {
  background: linear-gradient(135deg, #1e3a8a 0%, #2563eb 55%, #0ea5e9 100%);
  color: white; padding: 1.6rem 1.8rem; border-radius: 18px; margin-bottom: 1.2rem;
  box-shadow: 0 8px 24px rgba(37, 99, 235, .25);
}
.hero h1 {color: white; font-size: 1.75rem; margin: 0 0 .3rem 0; padding: 0;}
.hero p {margin: 0; opacity: .92; font-size: .98rem;}
.hero .tags {margin-top: .8rem;}
.hero .tag {
  display: inline-block; background: rgba(255,255,255,.18); border: 1px solid rgba(255,255,255,.3);
  padding: .15rem .6rem; border-radius: 999px; font-size: .78rem; margin-right: .35rem;
}
.cite {
  display: inline-block; min-width: 1.25rem; padding: 0 .35rem; margin: 0 .1rem;
  background: #dbeafe; color: #1e40af; border-radius: 6px; font-size: .75rem;
  font-weight: 700; text-align: center; vertical-align: super; line-height: 1.2rem;
}
.answer {font-size: 1.02rem; line-height: 1.6;}
.notfound {
  background: #fffbeb; border: 1px solid #fcd34d; border-left: 5px solid #f59e0b;
  padding: .8rem 1rem; border-radius: 10px; color: #78350f;
}
.notfound small {display: block; margin-top: .3rem; color: #92400e; opacity: .85;}
.src {
  border: 1px solid #e5e7eb; border-radius: 12px; padding: .7rem .9rem; margin: .45rem 0;
  background: #f9fafb;
}
.src .head {display: flex; align-items: center; gap: .5rem; flex-wrap: wrap;}
.src .num {background: #1e40af; color: white; border-radius: 6px; padding: 0 .45rem; font-weight: 700; font-size: .8rem;}
.src .title {font-weight: 600; color: #111827;}
.src .badge {background: #e0e7ff; color: #3730a3; border-radius: 999px; padding: .05rem .55rem; font-size: .75rem;}
.src .lang {background: #f3f4f6; color: #374151; border-radius: 999px; padding: .05rem .5rem; font-size: .72rem;}
.src .quote {margin-top: .45rem; color: #4b5563; font-size: .86rem; font-style: italic; border-left: 3px solid #cbd5e1; padding-left: .6rem;}
.meta {color: #9ca3af; font-size: .78rem; margin-top: .4rem;}
.unverified {
  background: #fff7ed; border: 1px solid #fdba74; border-radius: 10px; padding: .6rem .9rem;
  margin-top: .5rem; color: #7c2d12; font-size: .86rem;
}
.unverified ul {margin: .3rem 0 0 1rem; padding: 0;}
.status-dot {display:inline-block; width:.6rem; height:.6rem; border-radius:50%; margin-right:.4rem;}
</style>
"""


def doc_name(source: str) -> tuple[str, str]:
    return DOC_NAMES.get(source, (source, ""))


def render_answer(text: str) -> str:
    """Escape the model output (never trust it as HTML), then turn [1] into citation badges."""
    safe = html.escape(text).replace("\n", "<br>")
    return re.sub(r"\[(\d+)\]", r'<span class="cite">\1</span>', safe)


def render_reply(data: dict) -> None:
    if not data.get("found", True):
        st.markdown(
            f'<div class="notfound">🔎 <b>{html.escape(data["answer"])}</b>'
            "<small>The uploaded documents don't cover this. I don't guess. Try rephrasing, "
            "or ask the Student Advisory Service.</small></div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(f'<div class="answer">{render_answer(data["answer"])}</div>', unsafe_allow_html=True)
        for s in data["sources"]:
            title, lang = doc_name(s["source"])
            snippet = html.escape(" ".join(s["snippet"].split())[:220])
            st.markdown(
                f'<div class="src"><div class="head"><span class="num">{s["n"]}</span>'
                f'<span class="title">{html.escape(title)}</span>'
                f'<span class="badge">page {s["page"]}</span>'
                + (f'<span class="lang">{lang}</span>' if lang else "")
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


def ask_api(question: str) -> dict:
    try:
        r = requests.post(f"{API_BASE}/ask", json={"question": question}, timeout=120)
    except requests.ConnectionError:
        return {"error": f"Can't reach the API at {API_BASE}. Is `uvicorn src.api:app` running?"}
    if not r.ok:
        return {"error": f"Error {r.status_code}: {r.text[:300]}"}
    return r.json()


def api_online() -> bool:
    try:
        return requests.get(f"{API_BASE}/health", timeout=2).ok
    except requests.RequestException:
        return False


# ---------------------------------------------------------------- page
st.set_page_config(page_title="Uni Paderborn Study Assistant", page_icon="🎓", layout="centered")
st.markdown(CSS, unsafe_allow_html=True)

with st.sidebar:
    online = api_online()
    color, label = ("#22c55e", "API online") if online else ("#ef4444", "API offline")
    st.markdown(f'<span class="status-dot" style="background:{color}"></span>**{label}**', unsafe_allow_html=True)
    if not online:
        st.caption("Start it with `uvicorn src.api:app --port 8000`")
    st.divider()
    st.markdown("### 📚 Documents")
    st.caption("Uni Paderborn · Electrical Systems Engineering M.Sc. (v3)")
    for title, lang in DOC_NAMES.values():
        st.markdown(f"<small>• {html.escape(title)} <span style='color:#9ca3af'>({lang})</span></small>",
                    unsafe_allow_html=True)
    st.divider()
    st.caption("Answers come **only** from these documents and always cite document + page. "
               "Only the German versions are legally binding.")
    if st.button("🗑️ Clear chat", width="stretch"):
        st.session_state.history = []
        st.rerun()

st.markdown(
    """<div class="hero"><h1>🎓 Study Assistant</h1>
    <p>Ask about exam rules, retakes, deadlines and your thesis, in English or German.
    Every answer cites the exact document and page.</p>
    <div class="tags"><span class="tag">🇬🇧 English</span><span class="tag">🇩🇪 Deutsch</span>
    <span class="tag">📄 Cited sources</span><span class="tag">🚫 No guessing</span></div></div>""",
    unsafe_allow_html=True,
)

if "history" not in st.session_state:
    st.session_state.history = []   # list of (role, payload); payload is str (user) or dict (assistant)

pending = None
if not st.session_state.history:
    st.markdown("**Try one of these:**")
    cols = st.columns(2)
    for i, ex in enumerate(EXAMPLES):
        if cols[i % 2].button(ex, key=f"ex{i}", width="stretch"):
            pending = ex

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
            data = ask_api(question)
        if "error" in data:
            st.error(data["error"])
        else:
            render_reply(data)
    st.session_state.history += [("user", question), ("assistant", data)]
    if pending:
        st.rerun()
