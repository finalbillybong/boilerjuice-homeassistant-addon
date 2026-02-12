#!/usr/bin/env bashio

# BoilerJuice Tank Monitor - Add-on Entry Point

bashio::log.info "Starting BoilerJuice Tank Monitor..."

# Set environment variables
export DATA_DIR="/data"
export LOG_LEVEL="INFO"
export PORT="8099"

# Create data directory if it doesn't exist
mkdir -p "${DATA_DIR}"

# Check for MQTT service and auto-configure if available
if bashio::services.available "mqtt"; then
    bashio::log.info "MQTT service detected — auto-configuring..."
    export MQTT_HOST=$(bashio::services mqtt "host")
    export MQTT_PORT=$(bashio::services mqtt "port")
    export MQTT_USER=$(bashio::services mqtt "username")
    export MQTT_PASSWORD=$(bashio::services mqtt "password")
    bashio::log.info "MQTT broker: ${MQTT_HOST}:${MQTT_PORT}"
fi

bashio::log.info "Starting web server on port ${PORT}..."

# Start the FastAPI server with uvicorn
cd /app
exec python3 -m uvicorn server:app \
    --host 0.0.0.0 \
    --port "${PORT}" \
    --log-level info \
    --no-access-log
