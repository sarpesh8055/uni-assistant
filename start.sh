#!/bin/sh
# Start the API in the background, then the UI in the foreground (the container lives as long as the UI).
set -e
uvicorn src.api:app --host 0.0.0.0 --port 8000 &
exec streamlit run src/ui.py \
  --server.port "${PORT:-7860}" --server.address 0.0.0.0 --server.headless true \
  --server.enableCORS false --server.enableXsrfProtection false \
  --browser.gatherUsageStats false
