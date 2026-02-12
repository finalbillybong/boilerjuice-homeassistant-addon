# BoilerJuice Tank Monitor

Monitor your BoilerJuice oil tank level directly from Home Assistant.

## Features

- **Modern Web UI** — View your tank level with an animated gauge, stats cards, and history. Works on desktop and mobile.
- **CAPTCHA-Aware Login** — BoilerJuice uses AWS WAF CAPTCHA protection. This add-on provides a remote browser interface where you can solve the CAPTCHA through the web UI.
- **Automatic Data Refresh** — Configurable polling interval (15 min to 4 hours) to keep your tank data up-to-date.
- **MQTT Auto-Discovery** — Publishes tank sensors to Home Assistant automatically via MQTT. No manual sensor configuration needed.
- **Persistent Sessions** — Login sessions are saved to disk so you don't need to re-authenticate frequently.

## Setup

### 1. Install the Add-on

Add this repository to your Home Assistant add-on store, then install the BoilerJuice Tank Monitor add-on.

### 2. Configure Credentials

1. Open the add-on's web UI from the sidebar (or click "Open Web UI").
2. Go to the **Settings** tab.
3. Enter your BoilerJuice email, password, and Tank ID.
4. Click **Save Settings**.

### 3. Log In

1. Go to the **Login** tab.
2. Click **Start Login** — this opens a browser session to BoilerJuice.
3. You'll see the BoilerJuice page as a screenshot. If a CAPTCHA appears, click on it to solve it.
4. Once the login form is visible, click **Auto-fill Credentials** to enter your details.
5. After successful login, click **Fetch Tank Data**.

### 4. MQTT Sensors (Optional)

If you have an MQTT broker (like Mosquitto), enable MQTT in Settings. The add-on will automatically publish these sensors:

| Sensor | Entity ID | Unit |
|--------|-----------|------|
| Oil Level | `sensor.boilerjuice_oil_level` | L |
| Oil Percentage | `sensor.boilerjuice_oil_percentage` | % |
| Total Oil Level | `sensor.boilerjuice_total_oil_level` | L |
| Total Oil Percentage | `sensor.boilerjuice_total_oil_percentage` | % |
| Tank Capacity | `sensor.boilerjuice_tank_capacity` | L |

## Finding Your Tank ID

1. Log in to [boilerjuice.com](https://www.boilerjuice.com/uk/users/login) in your browser.
2. Navigate to your tank page.
3. Look at the URL — it will be like: `https://www.boilerjuice.com/uk/users/tanks/123456/edit`
4. Your Tank ID is the number (e.g., `123456`).

## Troubleshooting

### Session Expired
If you see "Session expired" or "CAPTCHA required", go to the Login tab and re-authenticate. AWS WAF tokens typically last 12-24 hours.

### No Data Showing
Make sure you've:
1. Entered your credentials in Settings
2. Completed the login flow (including solving any CAPTCHAs)
3. Clicked "Fetch Tank Data" or waited for auto-refresh

### MQTT Not Working
- Ensure your MQTT broker is running (e.g., Mosquitto add-on)
- Check the MQTT host is correct (`core-mosquitto` for the HA Mosquitto add-on)
- Verify username/password if authentication is required

## Support

For issues or feature requests, please visit the [GitHub repository](https://github.com/mylesagray/boilerjuice-tank-api).
