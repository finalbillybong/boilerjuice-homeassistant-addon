"""
BoilerJuice Scraper Module

Uses Selenium with system Chromium to authenticate with BoilerJuice
(including solving AWS WAF CAPTCHA via remote browser UI) and fetch
tank data.

Cookies are persisted to disk so the user only needs to solve CAPTCHA
occasionally (when the WAF token expires).
"""

import base64
import json
import logging
import os
import re
import threading
from datetime import datetime, timezone
from typing import Optional

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

logger = logging.getLogger(__name__)

# BoilerJuice URLs
LOGIN_URL = "https://www.boilerjuice.com/uk/users/login"
TANK_URL_TEMPLATE = "https://www.boilerjuice.com/uk/users/tanks/{tank_id}/edit"
DASHBOARD_URL = "https://www.boilerjuice.com/uk/users/dashboard"
MY_ACCOUNT_URL = "https://www.boilerjuice.com/my-account"

DATA_DIR = os.environ.get("DATA_DIR", "/data")
COOKIE_FILE = os.path.join(DATA_DIR, "cookies.json")
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
    """Manages Selenium browser for BoilerJuice interaction."""

    def __init__(self):
        self._driver: Optional[webdriver.Chrome] = None
        self._lock = threading.Lock()
        self._auth_in_progress = False
        self._last_tank_data: Optional[TankData] = None
        self._last_error: Optional[str] = None

    def _create_driver(self) -> webdriver.Chrome:
        """Create a new Chrome/Chromium WebDriver instance."""
        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1280,800")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--lang=en-GB")
        chrome_options.add_argument(
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )

        # Use system chromium-browser if available
        chrome_bin = os.environ.get("CHROME_BIN")
        if chrome_bin and os.path.exists(chrome_bin):
            chrome_options.binary_location = chrome_bin
        elif os.path.exists("/usr/bin/chromium-browser"):
            chrome_options.binary_location = "/usr/bin/chromium-browser"
        elif os.path.exists("/usr/bin/chromium"):
            chrome_options.binary_location = "/usr/bin/chromium"

        # Use system chromedriver if available
        chromedriver_path = os.environ.get("CHROMEDRIVER_PATH")
        if chromedriver_path and os.path.exists(chromedriver_path):
            service = Service(executable_path=chromedriver_path)
        elif os.path.exists("/usr/bin/chromedriver"):
            service = Service(executable_path="/usr/bin/chromedriver")
        else:
            service = Service()

        # Hide webdriver flag
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)

        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
        )
        driver.set_page_load_timeout(30)
        driver.implicitly_wait(3)
        return driver

    def _ensure_driver(self):
        """Ensure we have a running driver."""
        if self._driver is None:
            self._driver = self._create_driver()
            self._load_cookies()

    def _save_cookies(self):
        """Save browser cookies to persistent storage."""
        if self._driver is None:
            return
        try:
            cookies = self._driver.get_cookies()
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(COOKIE_FILE, "w") as f:
                json.dump(cookies, f, indent=2)
            logger.info("Saved %d cookies", len(cookies))
        except Exception as e:
            logger.error("Failed to save cookies: %s", e)

    def _load_cookies(self):
        """Load cookies into the browser from persistent storage."""
        if self._driver is None or not os.path.exists(COOKIE_FILE):
            return
        try:
            with open(COOKIE_FILE, "r") as f:
                cookies = json.load(f)
            if not cookies:
                return
            # Navigate to the domain first so we can set cookies
            self._driver.get("https://www.boilerjuice.com")
            import time
            time.sleep(1)
            for cookie in cookies:
                # Remove problematic fields that Selenium doesn't accept
                for key in ["sameSite", "httpOnly", "expiry"]:
                    cookie.pop(key, None)
                try:
                    self._driver.add_cookie(cookie)
                except Exception:
                    pass
            logger.info("Loaded %d cookies", len(cookies))
        except Exception as e:
            logger.error("Failed to load cookies: %s", e)

    def close(self):
        """Close browser and cleanup."""
        try:
            if self._driver:
                self._driver.quit()
        except Exception as e:
            logger.error("Error closing browser: %s", e)
        finally:
            self._driver = None

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

    def get_screenshot_base64(self) -> Optional[str]:
        """Take a screenshot and return as base64."""
        if self._driver is None:
            return None
        try:
            png = self._driver.get_screenshot_as_png()
            return base64.b64encode(png).decode("utf-8")
        except Exception as e:
            logger.error("Screenshot failed: %s", e)
            return None

    def get_page_info(self) -> dict:
        """Get info about the current page."""
        if self._driver is None:
            return {"status": "no_page", "url": "", "page_type": "none"}
        try:
            html = self._driver.page_source
            return {
                "status": "ready",
                "url": self._driver.current_url,
                "page_type": self._detect_page_type(html),
                "title": self._driver.title,
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ── Auth flow (remote browser for CAPTCHA solving) ──────────────

    async def start_auth(self) -> dict:
        """Start authentication — navigate to login page."""
        self._auth_in_progress = True
        self._last_error = None
        try:
            self._ensure_driver()
            self._driver.get(LOGIN_URL)
            import time
            time.sleep(3)  # Wait for WAF challenge JS

            screenshot = self.get_screenshot_base64()
            page_info = self.get_page_info()
            return {"success": True, "screenshot": screenshot, "page_info": page_info}
        except Exception as e:
            self._last_error = str(e)
            logger.error("Auth start failed: %s", e)
            return {"success": False, "error": str(e)}

    async def auth_click(self, x: int, y: int) -> dict:
        """Click at coordinates on the page (for CAPTCHA solving)."""
        if self._driver is None:
            return {"success": False, "error": "No active browser"}
        try:
            actions = ActionChains(self._driver)
            # Move to absolute position on the page using JavaScript
            self._driver.execute_script(
                f"document.elementFromPoint({x}, {y}).click();"
            )
            import time
            time.sleep(1.5)
            screenshot = self.get_screenshot_base64()
            page_info = self.get_page_info()
            return {"success": True, "screenshot": screenshot, "page_info": page_info}
        except Exception as e:
            # Fallback: try ActionChains click
            try:
                body = self._driver.find_element(By.TAG_NAME, "body")
                actions = ActionChains(self._driver)
                actions.move_to_element_with_offset(body, x, y).click().perform()
                import time
                time.sleep(1.5)
                screenshot = self.get_screenshot_base64()
                page_info = self.get_page_info()
                return {"success": True, "screenshot": screenshot, "page_info": page_info}
            except Exception as e2:
                return {"success": False, "error": str(e2)}

    async def auth_type(self, text: str) -> dict:
        """Type text into the focused element."""
        if self._driver is None:
            return {"success": False, "error": "No active browser"}
        try:
            active = self._driver.switch_to.active_element
            active.send_keys(text)
            import time
            time.sleep(0.5)
            screenshot = self.get_screenshot_base64()
            page_info = self.get_page_info()
            return {"success": True, "screenshot": screenshot, "page_info": page_info}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def auth_press_key(self, key: str) -> dict:
        """Press a keyboard key."""
        if self._driver is None:
            return {"success": False, "error": "No active browser"}
        try:
            from selenium.webdriver.common.keys import Keys
            key_map = {
                "Enter": Keys.RETURN,
                "Tab": Keys.TAB,
                "Escape": Keys.ESCAPE,
            }
            selenium_key = key_map.get(key, key)
            active = self._driver.switch_to.active_element
            active.send_keys(selenium_key)
            import time
            time.sleep(1)
            screenshot = self.get_screenshot_base64()
            page_info = self.get_page_info()
            return {"success": True, "screenshot": screenshot, "page_info": page_info}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def auth_fill_login(self, email: str, password: str) -> dict:
        """Fill and submit the login form."""
        if self._driver is None:
            return {"success": False, "error": "No active browser"}

        try:
            html = self._driver.page_source
            page_type = self._detect_page_type(html)

            if page_type == "captcha":
                return {
                    "success": False,
                    "error": "CAPTCHA detected. Please solve it first using the remote browser.",
                    "page_info": self.get_page_info(),
                    "screenshot": self.get_screenshot_base64(),
                }

            if page_type != "login":
                return {
                    "success": False,
                    "error": f"Not on login page (detected: {page_type}). URL: {self._driver.current_url}",
                    "page_info": self.get_page_info(),
                    "screenshot": self.get_screenshot_base64(),
                }

            # Fill email
            try:
                email_field = self._driver.find_element(By.CSS_SELECTOR,
                    'input[name="user[email]"], input[type="email"], input#user_email')
                email_field.clear()
                email_field.send_keys(email)
            except Exception:
                pass

            # Fill password
            try:
                password_field = self._driver.find_element(By.CSS_SELECTOR,
                    'input[name="user[password]"], input[type="password"], input#user_password')
                password_field.clear()
                password_field.send_keys(password)
            except Exception:
                pass

            # Submit
            try:
                submit_btn = self._driver.find_element(By.CSS_SELECTOR,
                    'input[type="submit"], button[type="submit"]')
                submit_btn.click()
            except Exception:
                from selenium.webdriver.common.keys import Keys
                password_field.send_keys(Keys.RETURN)

            import time
            time.sleep(5)

            # Save cookies after login
            self._save_cookies()

            screenshot = self.get_screenshot_base64()
            page_info = self.get_page_info()

            new_html = self._driver.page_source
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
        self._save_cookies()

    # ── Data fetching ───────────────────────────────────────────────

    async def fetch_tank_data(self, tank_id: str) -> dict:
        """Fetch tank data from BoilerJuice."""
        try:
            self._ensure_driver()

            tank_url = TANK_URL_TEMPLATE.format(tank_id=tank_id)
            logger.info("Fetching tank data from %s", tank_url)

            self._driver.get(tank_url)
            import time
            time.sleep(3)

            html = self._driver.page_source
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

            tank_data = self._extract_tank_data()

            if tank_data:
                self._last_tank_data = tank_data
                self._save_cookies()
                self._save_history(tank_data)
                return {"success": True, "data": tank_data.to_dict()}

            # Try alternative URLs
            for alt_url in [
                f"https://www.boilerjuice.com/uk/users/tanks/{tank_id}",
                DASHBOARD_URL,
                MY_ACCOUNT_URL,
            ]:
                logger.info("Trying alternative URL: %s", alt_url)
                self._driver.get(alt_url)
                time.sleep(3)
                tank_data = self._extract_tank_data()
                if tank_data:
                    self._last_tank_data = tank_data
                    self._save_cookies()
                    self._save_history(tank_data)
                    return {"success": True, "data": tank_data.to_dict()}

            # Last resort: return page text
            try:
                text = self._driver.find_element(By.TAG_NAME, "body").text
            except Exception:
                text = ""
            return {
                "success": False,
                "error": "Could not extract tank data from page.",
                "page_text_preview": text[:500],
                "url": self._driver.current_url,
            }

        except Exception as e:
            logger.error("Fetch tank data failed: %s", e)
            return {"success": False, "error": str(e)}

    def _extract_tank_data(self) -> Optional[TankData]:
        """Try to extract tank data from the current page."""
        try:
            html = self._driver.page_source
            try:
                text = self._driver.find_element(By.TAG_NAME, "body").text
            except Exception:
                text = ""

            data = {}

            # Method 1: Try specific selectors
            try:
                el = self._driver.find_element(By.CSS_SELECTOR, "#usable-oil, [id*='usable-oil']")
                usable_text = el.text
                m = re.search(r"([\d,]+\.?\d*)\s*litres", usable_text, re.IGNORECASE)
                if m:
                    data["litres"] = float(m.group(1).replace(",", ""))
            except Exception:
                pass

            try:
                el = self._driver.find_element(By.CSS_SELECTOR, "#total-oil, [id*='total-oil']")
                total_text = el.text
                m = re.search(r"([\d,]+\.?\d*)\s*litres", total_text, re.IGNORECASE)
                if m:
                    data["total_litres"] = float(m.group(1).replace(",", ""))
            except Exception:
                pass

            try:
                el = self._driver.find_element(By.CSS_SELECTOR,
                    "input[title='tank-size-count'], [data-tank-size], [class*='capacity']")
                val = el.get_attribute("value")
                if val:
                    data["capacity"] = float(val.replace(",", ""))
            except Exception:
                pass

            try:
                el = self._driver.find_element(By.CSS_SELECTOR, "[data-percentage]")
                pct = el.get_attribute("data-percentage")
                if pct:
                    data["percent"] = float(pct)
            except Exception:
                pass

            # Method 2: Regex on page text
            if not data.get("litres"):
                patterns = [
                    r"you have\s+([\d,]+\.?\d*)\s*litres?\s+of usable oil",
                    r"([\d,]+\.?\d*)\s*litres?\s+(?:of\s+)?usable",
                    r"usable[:\s]+([\d,]+\.?\d*)\s*(?:litres?|L)",
                    r"([\d,]+\.?\d*)\s*litres?\s+remaining",
                ]
                for p in patterns:
                    m = re.search(p, text, re.IGNORECASE)
                    if m:
                        data["litres"] = float(m.group(1).replace(",", ""))
                        break

            if not data.get("total_litres"):
                patterns = [
                    r"you have\s+([\d,]+\.?\d*)\s*litres?\s+of oil",
                    r"total[:\s]+([\d,]+\.?\d*)\s*(?:litres?|L)",
                    r"([\d,]+\.?\d*)\s*litres?\s+total",
                ]
                for p in patterns:
                    m = re.search(p, text, re.IGNORECASE)
                    if m:
                        data["total_litres"] = float(m.group(1).replace(",", ""))
                        break

            if not data.get("capacity"):
                patterns = [
                    r"capacity[:\s]+([\d,]+\.?\d*)\s*(?:litres?|L)?",
                    r"tank\s+size[:\s]+([\d,]+\.?\d*)",
                    r"([\d,]+\.?\d*)\s*(?:litres?\s+)?capacity",
                ]
                for p in patterns:
                    m = re.search(p, text, re.IGNORECASE)
                    if m:
                        data["capacity"] = float(m.group(1).replace(",", ""))
                        break

            if not data.get("percent"):
                patterns = [
                    r"(\d+(?:\.\d+)?)\s*%",
                    r"percentage[:\s]+(\d+(?:\.\d+)?)",
                ]
                for p in patterns:
                    m = re.search(p, text, re.IGNORECASE)
                    if m:
                        data["percent"] = float(m.group(1))
                        break

            # Method 3: Look for JSON in script tags
            try:
                scripts = self._driver.find_elements(By.TAG_NAME, "script")
                for script in scripts:
                    script_text = script.get_attribute("innerHTML") or ""
                    json_matches = re.findall(r'\{[^{}]*"litres?"[^{}]*\}', script_text, re.IGNORECASE)
                    for json_str in json_matches:
                        try:
                            json_data = json.loads(json_str)
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
