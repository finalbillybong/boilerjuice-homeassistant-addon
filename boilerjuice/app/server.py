"""
BoilerJuice Tank Monitor - aiohttp Server

Serves the web UI (with inlined CSS/JS for ingress compatibility)
and provides API endpoints for tank data, config, and auth.
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

from aiohttp import web

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


def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error("Failed to load config: %s", e)
    return {}


def save_config(config: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)
    logger.info("Configuration saved")


# ═══════════════════════════════════════════════════════════
# UI Route — inlines CSS/JS into HTML (like ClawBridge)
# ═══════════════════════════════════════════════════════════

async def handle_index(request):
    """Serve the main UI with CSS/JS inlined for ingress compatibility."""
    try:
        html = (STATIC_DIR / "index.html").read_text()
        css = (STATIC_DIR / "style.css").read_text()
        js = (STATIC_DIR / "app.js").read_text()
    except FileNotFoundError as e:
        logger.error("Static file not found: %s", e)
        return web.Response(text=f"File not found: {e}", status=500)

    # Inline CSS and JS
    html = html.replace(
        '<link rel="stylesheet" href="static/style.css">',
        f"<style>{css}</style>"
    )
    html = html.replace(
        '<script src="static/app.js"></script>',
        f"<script>{js}</script>"
    )

    # Determine base path from ingress header
    base_path = request.headers.get("X-Ingress-Path", "")
    logger.info("Serving index with base_path: %s", base_path)

    # Inject base path into JavaScript
    html = html.replace(
        'const BASE = "";',
        f'const BASE = "{base_path}";'
    )

    return web.Response(text=html, content_type="text/html",
                        headers={"Cache-Control": "no-store"})


async def handle_static(request):
    """Serve static files (fallback)."""
    filename = request.match_info.get("filename", "")
    filepath = STATIC_DIR / filename

    if not filepath.exists():
        return web.Response(text="Not found", status=404)

    content_types = {
        ".css": "text/css",
        ".js": "application/javascript",
        ".png": "image/png",
        ".svg": "image/svg+xml",
        ".ico": "image/x-icon",
    }
    ext = filepath.suffix
    content_type = content_types.get(ext, "application/octet-stream")

    if ext in (".css", ".js", ".svg"):
        content = filepath.read_text()
        return web.Response(text=content, content_type=content_type)
    else:
        content = filepath.read_bytes()
        return web.Response(body=content, content_type=content_type)


# ═══════════════════════════════════════════════════════════
# Config API
# ═══════════════════════════════════════════════════════════

async def api_get_config(request):
    config = load_config()
    masked = {**config}
    masked["has_password"] = bool(config.get("password"))
    masked.pop("password", None)
    masked.pop("mqtt_password", None)
    if config.get("mqtt_password"):
        masked["has_mqtt_password"] = True
    masked["success"] = True
    return web.json_response(masked)


async def api_set_config(request):
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
        return web.json_response({"success": True})

    except Exception as e:
        logger.error("Config save error: %s", e)
        return web.json_response({"success": False, "error": str(e)}, status=500)


# ═══════════════════════════════════════════════════════════
# Status / Data API
# ═══════════════════════════════════════════════════════════

async def api_get_status(request):
    data = scraper.get_last_data()
    if data:
        return web.json_response({"success": True, "data": data})
    return web.json_response({"success": False, "error": "No data available yet"})


async def api_refresh(request):
    config = load_config()
    tank_id = config.get("tank_id", "")
    if not tank_id:
        return web.json_response({"success": False, "error": "Tank ID not configured. Go to Settings."})

    result = await scraper.fetch_tank_data(tank_id)

    if result.get("success") and config.get("mqtt_enabled"):
        try:
            from mqtt import publish_tank_data
            publish_tank_data(config, result["data"])
        except Exception as e:
            logger.error("MQTT publish failed: %s", e)

    return web.json_response(result)


async def api_get_history(request):
    history = scraper.get_history(limit=100)
    return web.json_response({"success": True, "history": history})


# ═══════════════════════════════════════════════════════════
# Auth / Remote Browser API
# ═══════════════════════════════════════════════════════════

async def api_auth_start(request):
    result = await scraper.start_auth()
    return web.json_response(result)


async def api_auth_click(request):
    body = await request.json()
    result = await scraper.auth_click(body.get("x", 0), body.get("y", 0))
    return web.json_response(result)


async def api_auth_type(request):
    body = await request.json()
    result = await scraper.auth_type(body.get("text", ""))
    return web.json_response(result)


async def api_auth_key(request):
    body = await request.json()
    result = await scraper.auth_press_key(body.get("key", "Enter"))
    return web.json_response(result)


async def api_auth_fill_login(request):
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
        return web.json_response({
            "success": False,
            "error": "No credentials available. Please enter them in Settings first.",
        })

    result = await scraper.auth_fill_login(email, password)
    return web.json_response(result)


async def api_auth_finish(request):
    await scraper.finish_auth()
    return web.json_response({"success": True})


async def api_auth_screenshot(request):
    screenshot = scraper.get_screenshot_base64()
    if screenshot:
        return web.json_response({"success": True, "screenshot": screenshot})
    return web.json_response({"success": False, "error": "No screenshot available"})


async def api_health(request):
    return web.json_response({
        "status": "ok",
        "auth_in_progress": scraper.is_auth_in_progress,
        "has_data": scraper.get_last_data() is not None,
    })


# ═══════════════════════════════════════════════════════════
# Background auto-refresh
# ═══════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════
# App setup and startup
# ═══════════════════════════════════════════════════════════

async def on_startup(app):
    logger.info("BoilerJuice Tank Monitor starting up")
    logger.info("Static dir: %s (exists: %s)", STATIC_DIR, STATIC_DIR.exists())
    app["refresh_task"] = asyncio.create_task(auto_refresh_loop())


async def on_cleanup(app):
    logger.info("Shutting down")
    task = app.get("refresh_task")
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    scraper.close()


def create_app():
    app = web.Application()

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)

    # UI routes
    app.router.add_get("/", handle_index)
    app.router.add_get("/index.html", handle_index)
    app.router.add_get("/static/{filename:.+}", handle_static)

    # Config API
    app.router.add_get("/api/config", api_get_config)
    app.router.add_post("/api/config", api_set_config)

    # Status / Data API
    app.router.add_get("/api/status", api_get_status)
    app.router.add_post("/api/refresh", api_refresh)
    app.router.add_get("/api/history", api_get_history)

    # Auth API
    app.router.add_post("/api/auth/start", api_auth_start)
    app.router.add_post("/api/auth/click", api_auth_click)
    app.router.add_post("/api/auth/type", api_auth_type)
    app.router.add_post("/api/auth/key", api_auth_key)
    app.router.add_post("/api/auth/fill-login", api_auth_fill_login)
    app.router.add_post("/api/auth/finish", api_auth_finish)
    app.router.add_get("/api/auth/screenshot", api_auth_screenshot)

    # Health
    app.router.add_get("/api/health", api_health)

    return app


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8099"))
    app = create_app()
    web.run_app(app, host="0.0.0.0", port=port)
