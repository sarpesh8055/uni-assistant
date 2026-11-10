FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 HF_HOME=/app/.cache/huggingface

# CPU-only torch keeps the image ~2 GB smaller than the default CUDA build
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download the embedding model at build time, so the container starts fast and works offline
ARG EMBED_MODEL=intfloat/multilingual-e5-small
ENV EMBED_MODEL=${EMBED_MODEL}
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${EMBED_MODEL}')"

COPY src/ src/
# Build the index first (python -m src.ingest && python -m src.index), then build the image
COPY data/processed/ data/processed/

EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1
CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000"]
