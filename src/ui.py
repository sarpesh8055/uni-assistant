"""Simple chat UI that talks to the FastAPI backend.

Run (with the API already running):  streamlit run src/ui.py
"""
import os

import requests
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000") + "/ask"

st.set_page_config(page_title="Uni & Behörden Assistant", page_icon="🎓")
st.title("🎓 Uni & Behörden Assistant")
st.caption("Ask about exam rules, re-registration, residence permits… in English or German.")

if "history" not in st.session_state:
    st.session_state.history = []

for role, content in st.session_state.history:
    st.chat_message(role).markdown(content)

if question := st.chat_input("Your question"):
    st.chat_message("user").markdown(question)
    with st.spinner("Searching documents…"):
        try:
            r = requests.post(API_URL, json={"question": question}, timeout=120)
        except requests.ConnectionError:
            r = None
    if r is None:
        reply = f"⚠️ Can't reach the API at {API_URL}. Is `uvicorn src.api:app` running?"
    elif r.ok:
        data = r.json()
        reply = data["answer"]
        if data["sources"]:
            sources = "\n".join(
                f"- **[{s['n']}] {s['source']}, p.{s['page']}** — _“{s['snippet'][:160]}…”_"
                for s in data["sources"]
            )
            reply += f"\n\n**Sources**\n{sources}"
        reply += f"\n\n_{data['latency_ms']} ms_"
    else:
        reply = f"⚠️ Error {r.status_code}: {r.text}"
    st.chat_message("assistant").markdown(reply)
    st.session_state.history += [("user", question), ("assistant", reply)]
