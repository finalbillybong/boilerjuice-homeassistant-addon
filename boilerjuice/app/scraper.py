"""
BoilerJuice Scraper Module

Uses Playwright with a persistent browser context to authenticate with
BoilerJuice (including solving AWS WAF CAPTCHA via remote browser UI)
and fetch tank data.

The persistent context stores cookies/session so the user only needs
to solve CAPTCHA occasionally (when the WAF token expires).
"""

import asyncio
import base64
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

logger = logging.getLogger(__name__)

# BoilerJuice URLs
LOGIN_URL = "https://www.boilerjuice.com/uk/users/login"
TANK_URL_TEMPLATE = "https://www.boilerjuice.com/uk/users/tanks/{tank_id}/edit"
DASHBOARD_URL = "https://www.boilerjuice.com/uk/users/dashboard"
MY_ACCOUNT_URL = "https://www.boilerjuice.com/my-account"

DATA_DIR = os.environ.get("DATA_DIR", "/data")
BROWSER_DATA_DIR = os.path.join(DATA_DIR, "browser_context")
HISTORY_FILE = os.path.join(DATA_DIR, "history.json")

# Page detection constants
CAPTCHA_INDICATORS = ["human verification", "captcha", "awswaf", "confirm you are human"]
LOGIN_INDICATORS = ['user[email]', 'user[password]', 'log in', 'sign in']
TANK_INDICATORS = ["tank", "litres", "oil", "capacity", "usable"]


class TankData:
    """Represents tank reading data."""

    def __init__(
        self,
        litres: float = 0,
        total_litres: float = 0,
        percent: float = 0,
        total_percent: float = 0,
        capacity: float = 0,
        level_name: str = "Unknown",
        timestamp: Optional[str] = None,
    ):
        self.litres = litres
        self.total_litres = total_litres
        self.percent = percent
        self.total_percent = total_percent
        self.capacity = capacity
        self.level_name = level_name
        self.timestamp = timestamp or datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "litres": self.litres,
            "total_litres": self.total_litres,
            "percent": self.percent,
            "total_percent": self.total_percent,
            "capacity": self.capacity,
            "level_name": self.level_name,
            "timestamp": self.timestamp,
        }

    @staticmethod
    def from_dict(data: dict) -> "TankData":
        return TankData(**data)


class BoilerJuiceScraper:
    """Manages Playwright browser for BoilerJuice interaction."""

    def __init__(self):
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._auth_in_progress = False
        self._last_tank_data: Optional[TankData] = None
        self._last_error: Optional[str] = None

    async def _ensure_browser(self):
        """Launch browser if not already running."""
        if self._playwright is None:
            self._playwright = await async_playwright().start()

        if self._browser is None or not self._browser.is_connected():
            # Detect system Chromium (used in Docker/HA add-on)
            launch_kwargs = {
                "headless": True,
                "args": [
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                ],
            }

            # Use system Chromium if available (Docker/Alpine)
            chromium_path = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH")
            if chromium_path and os.path.exists(chromium_path):
                launch_kwargs["executable_path"] = chromium_path
                logger.info("Using system Chromium at %s", chromium_path)
            elif os.path.exists("/usr/bin/chromium-browser"):
                launch_kwargs["executable_path"] = "/usr/bin/chromium-browser"
                logger.info("Using system Chromium at /usr/bin/chromium-browser")
            elif os.path.exists("/usr/bin/chromium"):
                launch_kwargs["executable_path"] = "/usr/bin/chromium"
                logger.info("Using system Chromium at /usr/bin/chromium")

            self._browser = await self._playwright.chromium.launch(**launch_kwargs)

        if self._context is None:
            # Use persistent-like context by saving/loading cookies
            self._context = await self._browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 800},
                locale="en-GB",
            )

            # Hide webdriver flag
            await self._context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                window.chrome = { runtime: {} };
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5],
                });
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-GB', 'en-US', 'en'],
                });
            """)

            # Restore cookies from persistent storage
            await self._load_cookies()

        if self._page is None or self._page.is_closed():
            self._page = await self._context.new_page()

    async def _save_cookies(self):
        """Save cookies to persistent storage."""
        if self._context is None:
            return
        try:
            cookies = await self._context.cookies()
            cookie_file = os.path.join(DATA_DIR, "cookies.json")
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(cookie_file, "w") as f:
                json.dump(cookies, f, indent=2)
            logger.info("Saved %d cookies to %s", len(cookies), cookie_file)
        except Exception as e:
            logger.error("Failed to save cookies: %s", e)

    async def _load_cookies(self):
        """Load cookies from persistent storage."""
        if self._context is None:
            return
        cookie_file = os.path.join(DATA_DIR, "cookies.json")
        if os.path.exists(cookie_file):
            try:
                with open(cookie_file, "r") as f:
                    cookies = json.load(f)
                if cookies:
                    await self._context.add_cookies(cookies)
                    logger.info("Loaded %d cookies from %s", len(cookies), cookie_file)
            except Exception as e:
                logger.error("Failed to load cookies: %s", e)

    async def close(self):
        """Close browser and cleanup."""
        try:
            if self._page and not self._page.is_closed():
                await self._page.close()
            if self._context:
                await self._context.close()
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception as e:
            logger.error("Error closing browser: %s", e)
        finally:
            self._page = None
            self._context = None
            self._browser = None
            self._playwright = None

    def _detect_page_type(self, html: str) -> str:
        """Detect what type of page we're on."""
        html_lower = html.lower()
        if any(indicator in html_lower for indicator in CAPTCHA_INDICATORS):
            return "captcha"
        if any(indicator in html_lower for indicator in LOGIN_INDICATORS):
            return "login"
        if any(indicator in html_lower for indicator in TANK_INDICATORS):
            return "tank"
        return "unknown"

    async def get_screenshot_base64(self) -> Optional[str]:
        """Take a screenshot of the current page and return as base64."""
        if self._page is None or self._page.is_closed():
            return None
        try:
            screenshot_bytes = await self._page.screenshot(type="png")
            return base64.b64encode(screenshot_bytes).decode("utf-8")
        except Exception as e:
            logger.error("Screenshot failed: %s", e)
            return None

    async def get_page_info(self) -> dict:
        """Get info about the current page state."""
        if self._page is None or self._page.is_closed():
            return {"status": "no_page", "url": "", "page_type": "none"}
        try:
            html = await self._page.content()
            return {
                "status": "ready",
                "url": self._page.url,
                "page_type": self._detect_page_type(html),
                "title": await self._page.title(),
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ── Auth flow (remote browser for CAPTCHA solving) ──────────────

    async def start_auth(self) -> dict:
        """
        Start the authentication flow. Navigate to the login page
        and return a screenshot for the user to interact with.
        """
        self._auth_in_progress = True
        self._last_error = None
        try:
            await self._ensure_browser()
            await self._page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
            # Wait a bit for WAF challenge JS to execute
            await asyncio.sleep(3)

            screenshot = await self.get_screenshot_base64()
            page_info = await self.get_page_info()

            return {
                "success": True,
                "screenshot": screenshot,
                "page_info": page_info,
            }
        except Exception as e:
            self._last_error = str(e)
            logger.error("Auth start failed: %s", e)
            return {"success": False, "error": str(e)}

    async def auth_click(self, x: int, y: int) -> dict:
        """Click at coordinates on the page (for CAPTCHA solving)."""
        if self._page is None or self._page.is_closed():
            return {"success": False, "error": "No active page"}
        try:
            await self._page.mouse.click(x, y)
            await asyncio.sleep(1)  # Wait for page reaction
            screenshot = await self.get_screenshot_base64()
            page_info = await self.get_page_info()
            return {"success": True, "screenshot": screenshot, "page_info": page_info}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def auth_type(self, text: str) -> dict:
        """Type text on the current page."""
        if self._page is None or self._page.is_closed():
            return {"success": False, "error": "No active page"}
        try:
            await self._page.keyboard.type(text, delay=50)
            await asyncio.sleep(0.5)
            screenshot = await self.get_screenshot_base64()
            page_info = await self.get_page_info()
            return {"success": True, "screenshot": screenshot, "page_info": page_info}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def auth_press_key(self, key: str) -> dict:
        """Press a keyboard key (e.g., 'Enter', 'Tab')."""
        if self._page is None or self._page.is_closed():
            return {"success": False, "error": "No active page"}
        try:
            await self._page.keyboard.press(key)
            await asyncio.sleep(1)
            screenshot = await self.get_screenshot_base64()
            page_info = await self.get_page_info()
            return {"success": True, "screenshot": screenshot, "page_info": page_info}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def auth_fill_login(self, email: str, password: str) -> dict:
        """
        Attempt to fill and submit the login form.
        Only works if we're on the actual login page (not CAPTCHA).
        """
        if self._page is None or self._page.is_closed():
            return {"success": False, "error": "No active page"}

        try:
            html = await self._page.content()
            page_type = self._detect_page_type(html)

            if page_type == "captcha":
                return {
                    "success": False,
                    "error": "CAPTCHA detected. Please solve it first using the remote browser.",
                    "page_info": await self.get_page_info(),
                    "screenshot": await self.get_screenshot_base64(),
                }

            if page_type != "login":
                return {
                    "success": False,
                    "error": f"Not on login page (detected: {page_type}). Current URL: {self._page.url}",
                    "page_info": await self.get_page_info(),
                    "screenshot": await self.get_screenshot_base64(),
                }

            # Fill email
            email_field = await self._page.query_selector(
                'input[name="user[email]"], input[type="email"], input#user_email'
            )
            if email_field:
                await email_field.fill(email)

            # Fill password
            password_field = await self._page.query_selector(
                'input[name="user[password]"], input[type="password"], input#user_password'
            )
            if password_field:
                await password_field.fill(password)

            # Submit
            submit_btn = await self._page.query_selector(
                'input[type="submit"], button[type="submit"], '
                'button:has-text("Log"), input[value*="Log"]'
            )
            if submit_btn:
                await submit_btn.click()
            else:
                await self._page.keyboard.press("Enter")

            await self._page.wait_for_load_state("networkidle", timeout=15000)
            await asyncio.sleep(2)

            # Save cookies after login
            await self._save_cookies()

            screenshot = await self.get_screenshot_base64()
            page_info = await self.get_page_info()

            # Check if we landed on another CAPTCHA or error
            new_html = await self._page.content()
            new_type = self._detect_page_type(new_html)
            logged_in = new_type not in ("captcha", "login")

            self._auth_in_progress = not logged_in

            return {
                "success": True,
                "logged_in": logged_in,
                "screenshot": screenshot,
                "page_info": page_info,
            }

        except Exception as e:
            logger.error("Login fill failed: %s", e)
            return {"success": False, "error": str(e)}

    async def finish_auth(self):
        """Mark auth as complete and save session."""
        self._auth_in_progress = False
        await self._save_cookies()

    # ── Data fetching ───────────────────────────────────────────────

    async def fetch_tank_data(self, tank_id: str) -> dict:
        """
        Fetch tank data from BoilerJuice.
        Returns tank data dict on success, error dict on failure.
        """
        try:
            await self._ensure_browser()

            tank_url = TANK_URL_TEMPLATE.format(tank_id=tank_id)
            logger.info("Fetching tank data from %s", tank_url)

            await self._page.goto(tank_url, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)

            html = await self._page.content()
            page_type = self._detect_page_type(html)

            if page_type == "captcha":
                return {
                    "success": False,
                    "error": "CAPTCHA required. Please re-authenticate via the web UI.",
                    "needs_auth": True,
                }

            if page_type == "login":
                return {
                    "success": False,
                    "error": "Session expired. Please re-authenticate via the web UI.",
                    "needs_auth": True,
                }

            # Try to extract tank data from the page
            tank_data = await self._extract_tank_data()

            if tank_data:
                self._last_tank_data = tank_data
                await self._save_cookies()
                self._save_history(tank_data)
                return {"success": True, "data": tank_data.to_dict()}
            else:
                # Maybe we need to try a different URL pattern
                for alt_url in [
                    f"https://www.boilerjuice.com/uk/users/tanks/{tank_id}",
                    DASHBOARD_URL,
                    MY_ACCOUNT_URL,
                ]:
                    logger.info("Trying alternative URL: %s", alt_url)
                    await self._page.goto(alt_url, wait_until="networkidle", timeout=20000)
                    await asyncio.sleep(2)
                    tank_data = await self._extract_tank_data()
                    if tank_data:
                        self._last_tank_data = tank_data
                        await self._save_cookies()
                        self._save_history(tank_data)
                        return {"success": True, "data": tank_data.to_dict()}

                # Last resort: return page text for debugging
                text = await self._page.inner_text("body")
                return {
                    "success": False,
                    "error": "Could not extract tank data from page.",
                    "page_text_preview": text[:500],
                    "url": self._page.url,
                }

        except Exception as e:
            logger.error("Fetch tank data failed: %s", e)
            return {"success": False, "error": str(e)}

    async def _extract_tank_data(self) -> Optional[TankData]:
        """Try to extract tank data from the current page."""
        try:
            html = await self._page.content()
            text = await self._page.inner_text("body")

            # Method 1: Try the original XPath-style selectors via Playwright
            data = {}

            # Try to find tank level elements
            try:
                usable_oil = await self._page.query_selector("#usable-oil, [id*='usable-oil']")
                if usable_oil:
                    usable_text = await usable_oil.inner_text()
                    litres_match = re.search(r"([\d,]+\.?\d*)\s*litres", usable_text, re.IGNORECASE)
                    if litres_match:
                        data["litres"] = float(litres_match.group(1).replace(",", ""))
            except Exception:
                pass

            try:
                total_oil = await self._page.query_selector("#total-oil, [id*='total-oil']")
                if total_oil:
                    total_text = await total_oil.inner_text()
                    litres_match = re.search(r"([\d,]+\.?\d*)\s*litres", total_text, re.IGNORECASE)
                    if litres_match:
                        data["total_litres"] = float(litres_match.group(1).replace(",", ""))
            except Exception:
                pass

            try:
                capacity_el = await self._page.query_selector(
                    "input[title='tank-size-count'], [data-tank-size], [class*='capacity']"
                )
                if capacity_el:
                    capacity_val = await capacity_el.get_attribute("value")
                    if capacity_val:
                        data["capacity"] = float(capacity_val.replace(",", ""))
            except Exception:
                pass

            # Try percentage from data attributes
            try:
                pct_el = await self._page.query_selector("[data-percentage]")
                if pct_el:
                    pct = await pct_el.get_attribute("data-percentage")
                    if pct:
                        data["percent"] = float(pct)
            except Exception:
                pass

            # Method 2: Try regex on the full page text
            if not data.get("litres"):
                litres_patterns = [
                    r"you have\s+([\d,]+\.?\d*)\s*litres?\s+of usable oil",
                    r"([\d,]+\.?\d*)\s*litres?\s+(?:of\s+)?usable",
                    r"usable[:\s]+([\d,]+\.?\d*)\s*(?:litres?|L)",
                    r"([\d,]+\.?\d*)\s*litres?\s+remaining",
                ]
                for pattern in litres_patterns:
                    match = re.search(pattern, text, re.IGNORECASE)
                    if match:
                        data["litres"] = float(match.group(1).replace(",", ""))
                        break

            if not data.get("total_litres"):
                total_patterns = [
                    r"you have\s+([\d,]+\.?\d*)\s*litres?\s+of oil",
                    r"total[:\s]+([\d,]+\.?\d*)\s*(?:litres?|L)",
                    r"([\d,]+\.?\d*)\s*litres?\s+total",
                ]
                for pattern in total_patterns:
                    match = re.search(pattern, text, re.IGNORECASE)
                    if match:
                        data["total_litres"] = float(match.group(1).replace(",", ""))
                        break

            if not data.get("capacity"):
                cap_patterns = [
                    r"capacity[:\s]+([\d,]+\.?\d*)\s*(?:litres?|L)?",
                    r"tank\s+size[:\s]+([\d,]+\.?\d*)",
                    r"([\d,]+\.?\d*)\s*(?:litres?\s+)?capacity",
                ]
                for pattern in cap_patterns:
                    match = re.search(pattern, text, re.IGNORECASE)
                    if match:
                        data["capacity"] = float(match.group(1).replace(",", ""))
                        break

            if not data.get("percent"):
                pct_patterns = [
                    r"(\d+(?:\.\d+)?)\s*%",
                    r"percentage[:\s]+(\d+(?:\.\d+)?)",
                ]
                for pattern in pct_patterns:
                    match = re.search(pattern, text, re.IGNORECASE)
                    if match:
                        data["percent"] = float(match.group(1))
                        break

            # Method 3: Try to find data in JavaScript variables / JSON in the page
            try:
                scripts = await self._page.query_selector_all("script")
                for script in scripts:
                    script_text = await script.inner_text()
                    # Look for JSON data embedded in scripts
                    json_matches = re.findall(r'\{[^{}]*"litres?"[^{}]*\}', script_text, re.IGNORECASE)
                    for json_str in json_matches:
                        try:
                            json_data = json.loads(json_str)
                            if "litres" in json_data or "litre" in json_data:
                                if "litres" in json_data:
                                    data["litres"] = float(json_data["litres"])
                                if "capacity" in json_data:
                                    data["capacity"] = float(json_data["capacity"])
                                break
                        except (json.JSONDecodeError, ValueError):
                            pass
            except Exception:
                pass

            # Check if we got meaningful data
            if data.get("litres") or data.get("percent"):
                # Determine level name from percentage
                pct = data.get("percent", 0)
                if pct >= 60:
                    level_name = "High"
                elif pct >= 30:
                    level_name = "Medium"
                else:
                    level_name = "Low"

                return TankData(
                    litres=data.get("litres", 0),
                    total_litres=data.get("total_litres", data.get("litres", 0)),
                    percent=data.get("percent", 0),
                    total_percent=data.get("total_percent", data.get("percent", 0)),
                    capacity=data.get("capacity", 0),
                    level_name=level_name,
                )

            return None

        except Exception as e:
            logger.error("Tank data extraction failed: %s", e)
            return None

    def _save_history(self, tank_data: TankData):
        """Append tank reading to history file."""
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            history = []
            if os.path.exists(HISTORY_FILE):
                with open(HISTORY_FILE, "r") as f:
                    history = json.load(f)

            history.append(tank_data.to_dict())

            # Keep last 500 readings
            if len(history) > 500:
                history = history[-500:]

            with open(HISTORY_FILE, "w") as f:
                json.dump(history, f, indent=2)

        except Exception as e:
            logger.error("Failed to save history: %s", e)

    def get_last_data(self) -> Optional[dict]:
        """Get the last fetched tank data."""
        if self._last_tank_data:
            return self._last_tank_data.to_dict()
        # Try loading from history
        try:
            if os.path.exists(HISTORY_FILE):
                with open(HISTORY_FILE, "r") as f:
                    history = json.load(f)
                if history:
                    self._last_tank_data = TankData.from_dict(history[-1])
                    return self._last_tank_data.to_dict()
        except Exception:
            pass
        return None

    def get_history(self, limit: int = 50) -> list:
        """Get recent history readings."""
        try:
            if os.path.exists(HISTORY_FILE):
                with open(HISTORY_FILE, "r") as f:
                    history = json.load(f)
                return history[-limit:]
        except Exception:
            pass
        return []

    @property
    def is_auth_in_progress(self) -> bool:
        return self._auth_in_progress

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error
