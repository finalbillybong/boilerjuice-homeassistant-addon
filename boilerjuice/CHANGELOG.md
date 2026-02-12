# Changelog

## 1.1.0

- Fix: Selenium scraper no longer blocks the web server event loop (runs in thread executor)
- Fix: Auto-refresh waits 10 seconds after startup so the UI is immediately accessible
- Fix: Removed greedy regex patterns that matched tank model names (e.g. "Balmoral 2000L") as oil litres
- Fix: Capacity text regex disabled — dropdown options on the edit page gave false matches
- Simplified data model: "Oil Remaining", "Level %", "Tank Capacity"
- Added user-configurable tank capacity in Settings
- Added 12-hour and 24-hour auto-refresh intervals
- MQTT entity IDs listed in Settings for easy reference
- Updated README and documentation

## 1.0.0

- Initial release
- Modern web UI with animated tank gauge
- CAPTCHA-aware remote browser login
- Automatic data refresh (configurable interval)
- MQTT auto-discovery for Home Assistant sensors
- Persistent session storage
- Mobile-responsive design with dark/light theme
