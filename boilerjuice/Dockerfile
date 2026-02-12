ARG BUILD_FROM
FROM ${BUILD_FROM}

# Install Python, Chromium, and dependencies
RUN apk add --no-cache \
    python3 \
    py3-pip \
    py3-aiohttp \
    chromium \
    chromium-chromedriver \
    nss \
    freetype \
    harfbuzz \
    ca-certificates \
    ttf-freefont \
    libstdc++

# Set environment for Chromium
ENV CHROME_BIN=/usr/bin/chromium-browser
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver

# Copy application
COPY app /app

# Install Python dependencies
RUN pip3 install --no-cache-dir --break-system-packages \
    selenium==4.27.1 \
    paho-mqtt==2.1.0

# Labels
LABEL \
    io.hass.version="1.0.5" \
    io.hass.type="addon" \
    io.hass.arch="amd64|aarch64|armv7"

# Copy run script
COPY run.sh /
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
