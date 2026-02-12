#!/bin/bash
set -e

# BoilerJuice Tank Monitor - Add-on Entry Point

echo "[INFO] Starting BoilerJuice Tank Monitor..."

# Set environment variables
export DATA_DIR="/data"
export LOG_LEVEL="INFO"
export PORT="8099"

# Create data directory if it doesn't exist
mkdir -p "${DATA_DIR}"

echo "[INFO] Starting web server on port ${PORT}..."

# Start the FastAPI server with uvicorn
cd /app
exec python3 -m uvicorn server:app \
    --host 0.0.0.0 \
    --port "${PORT}" \
    --log-level info \
    --no-access-log
