#!/usr/bin/with-contenv bashio

bashio::log.info "Starting BoilerJuice Tank Monitor..."

exec python3 /app/server.py
