# BoilerJuice Tank Monitor for Home Assistant

[![Home Assistant Add-on](https://img.shields.io/badge/Home%20Assistant-Add--on-blue?logo=home-assistant)](https://www.home-assistant.io/)
[![GitHub Release](https://img.shields.io/github/v/release/finalbillybong/boilerjuice-homeassistant-addon?label=version)](https://github.com/finalbillybong/boilerjuice-homeassistant-addon/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A Home Assistant add-on that monitors your **BoilerJuice** oil tank level. It scrapes data from [boilerjuice.com](https://www.boilerjuice.com) using a headless browser, handles AWS WAF CAPTCHA challenges through a remote browser UI, and publishes tank data to Home Assistant via MQTT auto-discovery.

---

## Features

- **Modern Web UI** — Animated tank gauge, stats cards, dark/light theme, fully responsive on desktop and mobile.
- **CAPTCHA-Aware Login** — BoilerJuice is protected by AWS WAF. The add-on shows the page as a live screenshot you can click on to solve CAPTCHAs directly from the HA panel.
- **Auto Refresh** — Configurable polling interval from 15 minutes up to 24 hours.
- **MQTT Auto-Discovery** — Tank sensors appear automatically in Home Assistant — no manual YAML needed.
- **Persistent Sessions** — Browser cookies are saved to disk so you don't have to re-authenticate every time.
- **User-Configurable Tank Capacity** — Set your actual tank size (litres) in settings; remaining oil is calculated from the percentage level.

---

## Installation

### 1. Add the repository

In Home Assistant, go to **Settings > Add-ons > Add-on Store** (bottom-right menu) **> Repositories** and add:

```
https://github.com/finalbillybong/boilerjuice-homeassistant-addon
```

### 2. Install the add-on

Find **BoilerJuice Tank Monitor** in the store and click **Install**. The first build may take a few minutes (it installs Chromium).

### 3. Start and open the Web UI

Start the add-on, then click **Open Web UI** (or find it in the sidebar under **BoilerJuice**).

---

## Configuration

All configuration is done through the web UI — there are no YAML options to set.

### Settings tab

| Field | Description |
|---|---|
| **Email** | Your BoilerJuice account email |
| **Password** | Your BoilerJuice account password |
| **Tank ID** | Numeric ID from your tank page URL (see below) |
| **Tank Capacity** | Your tank's total capacity in litres (e.g. `1150`) |
| **Auto-refresh Interval** | How often to poll for new data (15 min – 24 hours, or disabled) |

### Finding your Tank ID

1. Log in to [boilerjuice.com](https://www.boilerjuice.com/uk/users/login) in your browser.
2. Navigate to your tank page.
3. The URL will look like: `https://www.boilerjuice.com/uk/users/tanks/123456/edit`
4. Your Tank ID is the number — in this example, **123456**.

---

## Login Flow

BoilerJuice uses AWS WAF CAPTCHA protection, so the first login requires human interaction:

1. Go to the **Login** tab in the add-on.
2. Click **Start Login** — a headless browser navigates to BoilerJuice and you see the page as a screenshot.
3. If a CAPTCHA appears, click on it in the screenshot to solve it.
4. Once the login form is visible, click **Auto-fill Credentials** to enter your saved email/password.
5. After login succeeds, click **Fetch Tank Data**.

The session cookies are saved, so subsequent auto-refreshes will work without re-authenticating (until the WAF token expires, typically 12–24 hours).

---

## Dashboard

Once data is fetched, the Dashboard shows:

- **Animated tank gauge** with percentage fill
- **Oil Remaining** — litres of oil in your tank
- **Level** — percentage full
- **Tank Capacity** — your configured tank size
- **Level indicator** — High / Medium / Low badge
- **Last updated** timestamp

---

## MQTT Integration

Enable MQTT in the Settings tab to automatically create Home Assistant sensors via MQTT auto-discovery.

### Requirements

- An MQTT broker running (e.g. the [Mosquitto add-on](https://github.com/home-assistant/addons/tree/master/mosquitto))
- The [MQTT integration](https://www.home-assistant.io/integrations/mqtt/) configured in Home Assistant

### MQTT Settings

| Field | Default | Description |
|---|---|---|
| **Enable MQTT** | Off | Toggle MQTT publishing |
| **Broker Host** | `core-mosquitto` | Hostname of your MQTT broker |
| **Port** | `1883` | MQTT broker port |
| **Username** | _(optional)_ | MQTT authentication username |
| **Password** | _(optional)_ | MQTT authentication password |

### Entities created

All sensors appear under the **BoilerJuice Oil Tank** device in Home Assistant:

| Entity ID | Name | Unit | Description |
|---|---|---|---|
| `sensor.boilerjuice_oil_remaining` | Oil Remaining | L | Litres of oil in the tank |
| `sensor.boilerjuice_oil_percentage` | Oil Level | % | Tank fill percentage |
| `sensor.boilerjuice_tank_capacity` | Tank Capacity | L | Total tank capacity |

**State topic:** `boilerjuice/tank/state`
**Availability topic:** `boilerjuice/tank/availability`

---

## Architecture

| Component | Technology |
|---|---|
| Web server | Python / aiohttp |
| Browser automation | Selenium + Chromium (headless) |
| MQTT | paho-mqtt |
| Base image | Home Assistant Alpine Linux |
| Supported architectures | `amd64`, `aarch64`, `armv7` |

### How it works

```
┌─────────────────────────────┐
│   Home Assistant Ingress    │
│   (HA panel / sidebar)      │
└──────────┬──────────────────┘
           │ HTTP
┌──────────▼──────────────────┐
│   aiohttp Web Server        │
│   (port 8099)               │
│                             │
│  ┌─── Web UI (inlined) ──┐ │
│  │  Dashboard / Settings  │ │
│  │  Login / Remote Browser│ │
│  └────────────────────────┘ │
│                             │
│  ┌─── Selenium Scraper ──┐  │
│  │  Chromium (headless)   │  │
│  │  Cookie persistence    │  │
│  │  CAPTCHA relay         │  │
│  └────────────────────────┘  │
│                             │
│  ┌─── MQTT Publisher ────┐  │
│  │  Auto-discovery        │  │
│  │  State + availability  │  │
│  └────────────────────────┘  │
└─────────────────────────────┘
```

---

## Troubleshooting

### "Session expired" or "CAPTCHA required"

Go to the **Login** tab and re-authenticate. AWS WAF tokens typically last 12–24 hours.

### No data showing on Dashboard

1. Check you've entered credentials and Tank ID in Settings.
2. Complete the login flow (including solving any CAPTCHAs).
3. Click **Fetch Tank Data** or wait for auto-refresh.

### Oil Remaining shows 0

Make sure you've set your **Tank Capacity** in Settings. If the scraper can only find the percentage, it calculates litres from `capacity * percent / 100`.

### MQTT entities not appearing

- Ensure the Mosquitto add-on (or your MQTT broker) is running.
- Confirm the MQTT integration is set up in HA (Settings > Devices & Services > MQTT).
- Check the broker host — use `core-mosquitto` for the HA Mosquitto add-on.
- Verify username/password if your broker requires auth.
- Do a manual **Refresh** after enabling MQTT — discovery messages are published on each data fetch.

### Add-on fails to build

Check the Supervisor logs (`ha supervisor logs`). Common issues:
- Slow first build due to Chromium download — give it a few minutes.
- Ensure you're on a supported architecture (`amd64`, `aarch64`, `armv7`).

---

## File Structure

```
boilerjuice/
├── config.yaml          # HA add-on metadata
├── build.yaml           # Multi-arch build config
├── Dockerfile           # Container definition
├── run.sh               # Entry point script
├── requirements.txt     # Python dependencies
├── DOCS.md              # HA add-on documentation tab
├── CHANGELOG.md         # Version history
├── app/
│   ├── server.py        # aiohttp web server + API
│   ├── scraper.py       # Selenium browser automation
│   ├── mqtt.py          # MQTT auto-discovery publisher
│   └── static/
│       ├── index.html   # Web UI markup
│       ├── app.js       # Frontend logic
│       └── style.css    # Styling (dark/light themes)
└── translations/
    └── en.yaml          # English translations
```

---

## Credits

Inspired by [boilerjuice-tank-api](https://github.com/mylesagray/boilerjuice-tank-api) by Myles Gray.

---

## License

MIT
