"""Entry point for Streamlit Community Cloud (it runs streamlit_app.py from the repo root).

Runs everything in one process (UI_BACKEND=local). Settings come from the app's Secrets
(Settings -> Secrets in Streamlit Cloud), e.g.:
    LLM_BASE_URL = "https://api.groq.com/openai/v1"
    LLM_API_KEY  = "gsk_..."
    LLM_MODEL    = "openai/gpt-oss-120b"
"""
import os
import runpy
from pathlib import Path

import streamlit as st

# Copy secrets into environment variables BEFORE src.config is imported (it reads os.environ).
try:
    for key, value in st.secrets.items():
        if isinstance(value, (str, int, float)):
            os.environ.setdefault(key, str(value))
except Exception:  # no secrets configured (e.g. running locally with a .env file)
    pass
os.environ.setdefault("UI_BACKEND", "local")

runpy.run_path(str(Path(__file__).parent / "src" / "ui.py"), run_name="__main__")
