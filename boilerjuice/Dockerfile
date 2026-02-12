ARG BUILD_FROM
FROM ${BUILD_FROM}

# Install Python, Chromium, and dependencies
RUN apk add --no-cache \
    python3 \
    py3-pip \
    bash \
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

# Create app directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

# Copy application
COPY app/ ./

# Labels
LABEL \
    io.hass.version="1.0.2" \
    io.hass.type="addon" \
    io.hass.arch="amd64|aarch64|armv7"

# Expose ingress port
EXPOSE 8099

# Copy run script
COPY run.sh /
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
