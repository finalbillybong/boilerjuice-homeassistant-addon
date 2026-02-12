"""
BoilerJuice Tank Monitor - FastAPI Server

Serves the web UI and provides API endpoints for:
- Tank status data
- Configuration management
- Authentication flow (remote browser for CAPTCHA)
- Manual data refresh
- History

Designed to run as a Home Assistant add-on with ingress support.
"""

import asyncio
import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

# Add app directory to path
APP_DIR = Path(__file__).parent
STATIC_DIR = APP_DIR / "static"
sys.path.insert(0, str(APP_DIR))

from scraper import BoilerJuiceScraper

# ── Configuration ────────────────────────────────────────────
DATA_DIR = os.environ.get("DATA_DIR", "/data")
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("boilerjuice")

# ── Global state ─────────────────────────────────────────────
scraper = BoilerJuiceScraper()
refresh_task: asyncio.Task = None


def load_config() -> dict:
    """Load configuration from persistent storage."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error("Failed to load config: %s", e)
    return {}


def save_config(config: dict):
    """Save configuration to persistent storage."""
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)
    logger.info("Configuration saved")


async def auto_refresh_loop():
    """Background loop that periodically fetches tank data."""
    while True:
        try:
            config = load_config()
            interval = config.get("refresh_interval", 60)
            if interval <= 0:
                await asyncio.sleep(60)
                continue

            tank_id = config.get("tank_id", "")
            if not tank_id:
                logger.debug("No tank_id configured, skipping auto-refresh")
                await asyncio.sleep(60)
                continue

            logger.info("Auto-refresh: fetching tank data")
            result = await scraper.fetch_tank_data(tank_id)

            if result.get("success"):
                logger.info("Auto-refresh: data fetched successfully")
                if config.get("mqtt_enabled"):
                    try:
                        from mqtt import publish_tank_data
                        publish_tank_data(config, result["data"])
                    except Exception as e:
                        logger.error("MQTT publish failed: %s", e)
            else:
                logger.warning("Auto-refresh failed: %s", result.get("error"))

            await asyncio.sleep(interval * 60)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("Auto-refresh error: %s", e)
            await asyncio.sleep(300)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    global refresh_task
    logger.info("BoilerJuice Tank Monitor starting up")
    logger.info("Static directory: %s (exists: %s)", STATIC_DIR, STATIC_DIR.exists())
    logger.info("Index file: %s (exists: %s)", STATIC_DIR / "index.html", (STATIC_DIR / "index.html").exists())

    refresh_task = asyncio.create_task(auto_refresh_loop())
    yield

    logger.info("Shutting down")
    if refresh_task:
        refresh_task.cancel()
        try:
            await refresh_task
        except asyncio.CancelledError:
            pass
    scraper.close()


# ── FastAPI App ──────────────────────────────────────────────
app = FastAPI(title="BoilerJuice Tank Monitor", lifespan=lifespan)


# ── Request Logging Middleware ───────────────────────────────
class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        logger.info("REQUEST: %s %s", request.method, request.url.path)
        response = await call_next(request)
        logger.info("RESPONSE: %s %s -> %d", request.method, request.url.path, response.status_code)
        return response

app.add_middleware(RequestLoggingMiddleware)


# ── Static File Helper ───────────────────────────────────────
MIME_TYPES = {
    ".html": "text/html",
    ".css": "text/css",
    ".js": "application/javascript",
    ".json": "application/json",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
}


def serve_static(filename: str):
    """Serve a static file by name."""
    filepath = STATIC_DIR / filename
    if filepath.exists() and filepath.is_file():
        suffix = filepath.suffix.lower()
        media_type = MIME_TYPES.get(suffix, "application/octet-stream")
        return FileResponse(str(filepath), media_type=media_type)
    return JSONResponse(status_code=404, content={"detail": f"File not found: {filename}"})


# ── Web UI ───────────────────────────────────────────────────
@app.get("/")
async def serve_ui():
    """Serve the main web UI."""
    return serve_static("index.html")


@app.get("/index.html")
async def serve_index():
    """Serve index.html explicitly."""
    return serve_static("index.html")


@app.get("/static/{filepath:path}")
async def serve_static_file(filepath: str):
    """Serve static files (CSS, JS, images)."""
    return serve_static(filepath)


# ── Config Endpoints ─────────────────────────────────────────
@app.get("/api/config")
async def get_config():
    """Get current configuration (passwords masked)."""
    config = load_config()
    masked = {**config}
    masked["has_password"] = bool(config.get("password"))
    masked.pop("password", None)
    masked.pop("mqtt_password", None)
    if config.get("mqtt_password"):
        masked["has_mqtt_password"] = True
    masked["success"] = True
    return masked


@app.post("/api/config")
async def set_config(request: Request):
    """Update configuration."""
    try:
        body = await request.json()
        config = load_config()

        for key in [
            "email", "tank_id", "refresh_interval",
            "mqtt_enabled", "mqtt_host", "mqtt_port", "mqtt_user",
        ]:
            if key in body:
                config[key] = body[key]

        if body.get("password"):
            config["password"] = body["password"]
        if body.get("mqtt_password"):
            config["mqtt_password"] = body["mqtt_password"]

        save_config(config)
        return {"success": True}

    except Exception as e:
        logger.error("Config save error: %s", e)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)},
        )


# ── Status / Data Endpoints ─────────────────────────────────
@app.get("/api/status")
async def get_status():
    """Get the latest tank data (from cache)."""
    data = scraper.get_last_data()
    if data:
        return {"success": True, "data": data}
    return {"success": False, "error": "No data available yet"}


@app.post("/api/refresh")
async def refresh_data():
    """Trigger a manual data refresh."""
    config = load_config()
    tank_id = config.get("tank_id", "")
    if not tank_id:
        return {"success": False, "error": "Tank ID not configured. Go to Settings."}

    result = await scraper.fetch_tank_data(tank_id)

    if result.get("success") and config.get("mqtt_enabled"):
        try:
            from mqtt import publish_tank_data
            publish_tank_data(config, result["data"])
        except Exception as e:
            logger.error("MQTT publish failed: %s", e)

    return result


@app.get("/api/history")
async def get_history():
    """Get historical tank readings."""
    history = scraper.get_history(limit=100)
    return {"success": True, "history": history}


# ── Auth / Remote Browser Endpoints ─────────────────────────
@app.post("/api/auth/start")
async def auth_start():
    """Start the authentication flow."""
    result = await scraper.start_auth()
    return result


@app.post("/api/auth/click")
async def auth_click(request: Request):
    """Click at a position on the browser page."""
    body = await request.json()
    x = body.get("x", 0)
    y = body.get("y", 0)
    result = await scraper.auth_click(x, y)
    return result


@app.post("/api/auth/type")
async def auth_type(request: Request):
    """Type text on the browser page."""
    body = await request.json()
    text = body.get("text", "")
    result = await scraper.auth_type(text)
    return result


@app.post("/api/auth/key")
async def auth_key(request: Request):
    """Press a key on the browser page."""
    body = await request.json()
    key = body.get("key", "Enter")
    result = await scraper.auth_press_key(key)
    return result


@app.post("/api/auth/fill-login")
async def auth_fill_login(request: Request):
    """Auto-fill the login form with credentials."""
    body = await request.json()
    email = body.get("email", "")
    password = body.get("password", "")

    if password == "__saved__":
        config = load_config()
        password = config.get("password", "")

    if not email or not password:
        config = load_config()
        email = email or config.get("email", "")
        password = password or config.get("password", "")

    if not email or not password:
        return {
            "success": False,
            "error": "No credentials available. Please enter them in Settings first.",
        }

    result = await scraper.auth_fill_login(email, password)
    return result


@app.post("/api/auth/finish")
async def auth_finish():
    """Mark authentication as complete."""
    await scraper.finish_auth()
    return {"success": True}


@app.get("/api/auth/screenshot")
async def auth_screenshot():
    """Get the current browser screenshot."""
    screenshot = scraper.get_screenshot_base64()
    if screenshot:
        return {"success": True, "screenshot": screenshot}
    return {"success": False, "error": "No screenshot available"}


@app.get("/api/auth/page-info")
async def auth_page_info():
    """Get information about the current browser page."""
    info = scraper.get_page_info()
    return info


# ── Health Check ─────────────────────────────────────────────
@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "auth_in_progress": scraper.is_auth_in_progress,
        "has_data": scraper.get_last_data() is not None,
    }


# ── Catch-all: serve index.html for SPA routing ─────────────
@app.get("/{full_path:path}")
async def catch_all(full_path: str):
    """Catch-all route — serve index.html for any unmatched path."""
    logger.info("Catch-all hit for path: /%s", full_path)
    return serve_static("index.html")


# ── Run ──────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8099"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
