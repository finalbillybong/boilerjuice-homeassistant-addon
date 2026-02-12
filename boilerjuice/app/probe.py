"""
BoilerJuice API Probe Script

Uses Playwright to log in to BoilerJuice and intercept all network
requests to discover internal JSON API endpoints. Run this once to
find out which APIs the BoilerJuice frontend uses, so we can call
them directly without needing a headless browser at runtime.

Usage:
    python probe.py --email you@example.com --password yourpass --tank-id 12345
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime
from playwright.async_api import async_playwright


async def probe_boilerjuice(email: str, password: str, tank_id: str):
    """Log in to BoilerJuice and intercept network requests."""

    discovered_apis = []
    page_contents = {}

    print("=" * 70)
    print("BoilerJuice API Probe")
    print(f"Started: {datetime.now().isoformat()}")
    print("=" * 70)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )
        page = await context.new_page()

        # Intercept all network responses
        async def handle_response(response):
            url = response.url
            content_type = response.headers.get("content-type", "")

            # Capture JSON/API responses
            if any(ct in content_type for ct in ["application/json", "text/json"]):
                try:
                    body = await response.json()
                    entry = {
                        "url": url,
                        "status": response.status,
                        "method": response.request.method,
                        "content_type": content_type,
                        "body_preview": json.dumps(body)[:500],
                    }
                    discovered_apis.append(entry)
                    print(f"\n[API] {response.request.method} {url}")
                    print(f"  Status: {response.status}")
                    print(f"  Body: {json.dumps(body, indent=2)[:300]}")
                except Exception:
                    pass

            # Also capture XHR/fetch to non-static URLs
            elif response.request.resource_type in ("xhr", "fetch"):
                try:
                    text = await response.text()
                    entry = {
                        "url": url,
                        "status": response.status,
                        "method": response.request.method,
                        "content_type": content_type,
                        "body_preview": text[:500],
                    }
                    discovered_apis.append(entry)
                    print(f"\n[XHR] {response.request.method} {url}")
                    print(f"  Status: {response.status}")
                    print(f"  Content-Type: {content_type}")
                    print(f"  Body: {text[:300]}")
                except Exception:
                    pass

        page.on("response", handle_response)

        # Step 1: Navigate to login page
        print("\n--- Step 1: Loading login page ---")
        try:
            await page.goto(
                "https://www.boilerjuice.com/uk/users/login",
                wait_until="networkidle",
                timeout=30000,
            )
            print(f"  URL: {page.url}")
            page_contents["login_page"] = await page.content()
        except Exception as e:
            print(f"  Error loading login page: {e}")
            await browser.close()
            return

        # Step 2: Fill login form and submit
        print("\n--- Step 2: Logging in ---")
        try:
            # Look for form fields
            email_field = await page.query_selector(
                'input[name="user[email]"], input[type="email"], input#user_email'
            )
            password_field = await page.query_selector(
                'input[name="user[password]"], input[type="password"], input#user_password'
            )

            if email_field and password_field:
                await email_field.fill(email)
                await password_field.fill(password)
                print("  Filled credentials")

                # Find and click submit button
                submit_btn = await page.query_selector(
                    'input[type="submit"], button[type="submit"], '
                    'button:has-text("Log"), input[value="Log"]'
                )
                if submit_btn:
                    await submit_btn.click()
                    await page.wait_for_load_state("networkidle", timeout=15000)
                    print(f"  After login URL: {page.url}")
                else:
                    # Try submitting the form directly
                    await page.press('input[type="password"]', "Enter")
                    await page.wait_for_load_state("networkidle", timeout=15000)
                    print(f"  After login URL: {page.url}")
            else:
                print("  Could not find login form fields!")
                # Dump page HTML for debugging
                html = await page.content()
                print(f"  Page HTML (first 1000 chars): {html[:1000]}")

            page_contents["after_login"] = await page.content()

            # Check cookies
            cookies = await context.cookies()
            print(f"  Cookies: {[c['name'] for c in cookies]}")
            jwt_cookies = [c for c in cookies if "jwt" in c["name"].lower()]
            session_cookies = [c for c in cookies if "session" in c["name"].lower()]
            print(f"  JWT cookies: {jwt_cookies}")
            print(f"  Session cookies: {session_cookies}")

        except Exception as e:
            print(f"  Login error: {e}")

        # Step 3: Navigate to tank page
        print("\n--- Step 3: Navigating to tank page ---")
        tank_urls = [
            f"https://www.boilerjuice.com/uk/users/tanks/{tank_id}/edit",
            f"https://www.boilerjuice.com/uk/users/tanks/{tank_id}",
            "https://www.boilerjuice.com/my-account",
            "https://www.boilerjuice.com/uk/users/dashboard",
        ]

        for tank_url in tank_urls:
            try:
                print(f"\n  Trying: {tank_url}")
                await page.goto(tank_url, wait_until="networkidle", timeout=20000)
                print(f"  Final URL: {page.url}")
                content = await page.content()
                page_contents[tank_url] = content

                # Check if page has tank-related data
                has_tank_data = any(
                    keyword in content.lower()
                    for keyword in [
                        "tank", "litres", "litre", "oil", "capacity",
                        "usable", "level", "percent",
                    ]
                )
                print(f"  Has tank keywords: {has_tank_data}")

                if has_tank_data:
                    print(f"  Page length: {len(content)} chars")
                    # Try to extract visible text
                    text = await page.inner_text("body")
                    print(f"  Visible text (first 500 chars): {text[:500]}")
                    break
            except Exception as e:
                print(f"  Error: {e}")

        # Step 4: Wait a bit more for any lazy-loaded API calls
        print("\n--- Step 4: Waiting for additional API calls ---")
        await asyncio.sleep(5)

        # Step 5: Try clicking around for more API discovery
        print("\n--- Step 5: Looking for navigation elements ---")
        try:
            links = await page.query_selector_all("a")
            for link in links[:20]:
                text = await link.inner_text()
                href = await link.get_attribute("href")
                if text.strip():
                    print(f"  Link: '{text.strip()}' -> {href}")
        except Exception as e:
            print(f"  Error listing links: {e}")

        await browser.close()

    # Summary
    print("\n" + "=" * 70)
    print("DISCOVERY SUMMARY")
    print("=" * 70)
    print(f"\nDiscovered {len(discovered_apis)} API/XHR endpoints:\n")
    for i, api in enumerate(discovered_apis, 1):
        print(f"  {i}. [{api['method']}] {api['url']}")
        print(f"     Status: {api['status']}, Type: {api['content_type']}")
        print(f"     Preview: {api['body_preview'][:200]}")
        print()

    # Save results
    results = {
        "timestamp": datetime.now().isoformat(),
        "discovered_apis": discovered_apis,
        "pages_captured": list(page_contents.keys()),
    }

    output_file = "probe_results.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nFull results saved to: {output_file}")

    # Save page HTML for analysis
    for name, html in page_contents.items():
        safe_name = name.replace("https://", "").replace("/", "_").replace(":", "")
        filename = f"probe_page_{safe_name}.html"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"Saved page HTML: {filename}")

    return results


def main():
    parser = argparse.ArgumentParser(description="Probe BoilerJuice for API endpoints")
    parser.add_argument("--email", required=True, help="BoilerJuice email")
    parser.add_argument("--password", required=True, help="BoilerJuice password")
    parser.add_argument("--tank-id", required=True, help="Tank ID")
    args = parser.parse_args()

    asyncio.run(probe_boilerjuice(args.email, args.password, args.tank_id))


if __name__ == "__main__":
    main()
