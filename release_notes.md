## BoilerJuice Tank Monitor v1.1.2

### What's New
- **Simplified scraper** - Only scrapes the percentage from BoilerJuice; calculates remaining oil from your configured tank capacity. No more false matches from page content.
- **MQTT auto-discovery fixed** - Discovery config messages are now properly published so HA automatically creates sensors under the "BoilerJuice Oil Tank" device.
- **paho-mqtt v2 compatibility** - Fixed Client API for paho-mqtt 2.x.
- **Non-blocking scraper** - Selenium runs in a thread executor so the web UI stays responsive during data fetches.
- **Startup delay** - Auto-refresh waits 10 seconds after startup so the UI is immediately accessible.
- **12h and 24h refresh intervals** added.
- **MQTT entity reference** shown in Settings.
- **Add-on icon and logo** added.
- **Full README** with setup guide, architecture diagram, and troubleshooting.

### Sensors (MQTT)
| Entity ID | Name | Unit |
|---|---|---|
| `sensor.boilerjuice_oil_remaining` | Oil Remaining | L |
| `sensor.boilerjuice_oil_percentage` | Oil Level | % |
| `sensor.boilerjuice_tank_capacity` | Tank Capacity | L |

### Setup
1. Add repo: `https://github.com/finalbillybong/boilerjuice-homeassistant-addon`
2. Install add-on, open Web UI
3. Enter credentials + tank capacity in Settings
4. Log in via the Login tab (solve CAPTCHA if needed)
5. Fetch tank data
