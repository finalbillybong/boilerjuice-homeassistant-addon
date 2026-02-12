## BoilerJuice Tank Monitor v1.1.4

### What's New (since initial release)

**Scraper**
- Simplified to only scrape the percentage from BoilerJuice — no more false matches from dropdown text or tank model names (e.g. "Balmoral 2000L")
- Oil remaining is calculated from your configured tank capacity: `capacity x percent / 100`
- Selenium runs in a background thread so the web UI stays responsive during fetches
- Auto-refresh skips fetching while you're in the login/CAPTCHA flow — no more browser collisions

**Web UI**
- Dashboard shows: Oil Remaining (litres), Level (%), Tank Capacity
- Tank Capacity field added to Settings — enter your actual tank size
- 12-hour and 24-hour auto-refresh intervals added
- MQTT entity IDs listed in Settings for easy reference
- Auto-refresh waits 10 seconds after startup so the UI loads immediately
- Add-on icon and logo

**MQTT**
- Fixed auto-discovery — discovery config messages are now properly published
- Fixed paho-mqtt v2.x compatibility (CallbackAPIVersion, wait_for_publish)
- Discovery is re-published on every data fetch to ensure HA picks up sensors

**Infrastructure**
- Full README with setup guide, architecture diagram, and troubleshooting
- MIT License added
- Fixed HA Ingress path handling (catch-all route for multi-slash paths)

### Sensors (MQTT)
| Entity ID | Name | Unit |
|---|---|---|
| `sensor.boilerjuice_oil_remaining` | Oil Remaining | L |
| `sensor.boilerjuice_oil_percentage` | Oil Level | % |
| `sensor.boilerjuice_tank_capacity` | Tank Capacity | L |

All sensors appear under the **BoilerJuice Oil Tank** device in Home Assistant.

### Setup
1. Add repo: `https://github.com/finalbillybong/boilerjuice-homeassistant-addon`
2. Install add-on, open Web UI
3. Enter credentials + tank capacity in Settings
4. Log in via the Login tab (solve CAPTCHA if needed)
5. Click Fetch Tank Data
