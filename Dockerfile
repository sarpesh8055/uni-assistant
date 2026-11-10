# One container: FastAPI backend (internal, :8000) + Streamlit UI (public, :7860).
# Works locally (docker compose up --build) and on Hugging Face Spaces (Docker SDK, app_port 7860).
FROM python:3.11-slim

# Hugging Face Spaces runs containers as user 1000; give it a home and own the app dir.
RUN useradd -m -u 1000 user
WORKDIR /app
ENV PYTHONUNBUFFERED=1 HOME=/home/user HF_HOME=/app/.cache/huggingface

# CPU-only torch keeps the image ~2 GB smaller than the default CUDA build
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY start.sh .

# Build the corpus and index at build time, so the container starts in seconds and works offline.
ARG EMBED_MODEL=intfloat/multilingual-e5-small
ENV EMBED_MODEL=${EMBED_MODEL}
RUN python -m src.download && python -m src.ingest && python -m src.index \
    && chown -R user:user /app && chmod +x start.sh

USER user
# Models are already in the image; don't contact the Hugging Face Hub at runtime.
ENV HF_HUB_OFFLINE=1
EXPOSE 7860
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1
CMD ["./start.sh"]
