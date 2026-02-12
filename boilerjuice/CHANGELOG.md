# Changelog

## 1.1.4

- Fix: Auto-refresh now skips fetching while auth/login is in progress (prevents browser collision)
- Fix: Manual refresh clears the auth-in-progress flag

## 1.1.3

- Version bump for HA update detection

## 1.1.2

- Fix: MQTT auto-discovery config messages are now actually published (were never called before)
- Fix: paho-mqtt v2.x compatibility (CallbackAPIVersion, loop_start, wait_for_publish)
- Discovery is re-published on every data fetch to ensure HA picks up sensors

## 1.1.1

- Simplified scraper: only scrapes percentage, calculates litres from user-configured tank capacity
- Removed all litre/capacity regex and selector parsing (source of false matches)

## 1.1.0

- Fix: Selenium scraper no longer blocks the web server event loop (runs in thread executor)
- Fix: Auto-refresh waits 10 seconds after startup so the UI is immediately accessible
- Fix: Removed greedy regex patterns that matched tank model names (e.g. "Balmoral 2000L")
- Simplified data model: "Oil Remaining", "Level %", "Tank Capacity"
- Added user-configurable tank capacity in Settings
- Added 12-hour and 24-hour auto-refresh intervals
- MQTT entity IDs listed in Settings for easy reference
- Add-on icon and logo
- Full README with setup guide, architecture diagram, and troubleshooting

## 1.0.0

- Initial release
- Modern web UI with animated tank gauge
- CAPTCHA-aware remote browser login
- Automatic data refresh (configurable interval)
- MQTT auto-discovery for Home Assistant sensors
- Persistent session storage
- Mobile-responsive design with dark/light theme
