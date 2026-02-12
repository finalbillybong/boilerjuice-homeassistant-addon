#!/bin/bash
set -e

echo "[INFO] Starting BoilerJuice Tank Monitor..."

exec python3 /app/server.py
