"""
BoilerJuice MQTT Auto-Discovery Module

Publishes tank data to Home Assistant via MQTT auto-discovery.
Sensors appear automatically in HA without any manual configuration.

Discovery topic format:
  homeassistant/sensor/boilerjuice/<object_id>/config

State topic:
  boilerjuice/tank/state
"""

import json
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

# Try importing paho-mqtt (optional dependency)
try:
    import paho.mqtt.client as mqtt_client
    MQTT_AVAILABLE = True
    # paho-mqtt 2.x requires CallbackAPIVersion
    try:
        from paho.mqtt.enums import CallbackAPIVersion
        PAHO_V2 = True
    except ImportError:
        PAHO_V2 = False
except ImportError:
    MQTT_AVAILABLE = False
    PAHO_V2 = False
    logger.warning("paho-mqtt not installed — MQTT integration disabled")


DISCOVERY_PREFIX = "homeassistant"
STATE_TOPIC = "boilerjuice/tank/state"
AVAILABILITY_TOPIC = "boilerjuice/tank/availability"

# Sensor definitions for auto-discovery
SENSORS = [
    {
        "object_id": "oil_remaining",
        "name": "Oil Remaining",
        "value_key": "litres",
        "unit": "L",
        "device_class": "volume_storage",
        "icon": "mdi:oil",
        "state_class": "measurement",
    },
    {
        "object_id": "oil_percentage",
        "name": "Oil Level",
        "value_key": "percent",
        "unit": "%",
        "device_class": None,
        "icon": "mdi:gauge",
        "state_class": "measurement",
    },
    {
        "object_id": "tank_capacity",
        "name": "Tank Capacity",
        "value_key": "capacity",
        "unit": "L",
        "device_class": "volume_storage",
        "icon": "mdi:barrel",
        "state_class": None,
    },
]

# Device info shared across all sensors
DEVICE_INFO = {
    "identifiers": ["boilerjuice_tank"],
    "name": "BoilerJuice Oil Tank",
    "manufacturer": "BoilerJuice",
    "model": "Oil Tank Monitor",
    "sw_version": "1.1.1",
}


def _get_mqtt_client(config: dict) -> Optional["mqtt_client.Client"]:
    """Create and connect an MQTT client from config."""
    if not MQTT_AVAILABLE:
        logger.error("paho-mqtt not installed")
        return None

    host = config.get("mqtt_host", "core-mosquitto")
    port = int(config.get("mqtt_port", 1883))
    user = config.get("mqtt_user", "")
    password = config.get("mqtt_password", "")

    try:
        # paho-mqtt 2.x requires CallbackAPIVersion
        if PAHO_V2:
            client = mqtt_client.Client(
                callback_api_version=CallbackAPIVersion.VERSION2,
                client_id="boilerjuice-addon",
                protocol=mqtt_client.MQTTv311,
            )
        else:
            client = mqtt_client.Client(
                client_id="boilerjuice-addon",
                protocol=mqtt_client.MQTTv311,
            )

        if user:
            client.username_pw_set(user, password)

        client.connect(host, port, keepalive=60)
        # Start the network loop so QoS 1 publishes are actually sent
        client.loop_start()
        return client

    except Exception as e:
        logger.error("MQTT connection failed: %s", e)
        return None


def _disconnect(client):
    """Cleanly stop the network loop and disconnect."""
    try:
        # Give a moment for queued messages to be sent
        time.sleep(0.5)
        client.loop_stop()
        client.disconnect()
    except Exception:
        pass


def publish_discovery(config: dict):
    """
    Publish MQTT auto-discovery config messages for all sensors.
    Call this once at startup or when MQTT settings change.
    """
    client = _get_mqtt_client(config)
    if not client:
        return False

    try:
        for sensor in SENSORS:
            discovery_topic = (
                f"{DISCOVERY_PREFIX}/sensor/boilerjuice/"
                f"{sensor['object_id']}/config"
            )

            payload = {
                "name": sensor["name"],
                "unique_id": f"boilerjuice_{sensor['object_id']}",
                "object_id": f"boilerjuice_{sensor['object_id']}",
                "state_topic": STATE_TOPIC,
                "value_template": f"{{{{ value_json.{sensor['value_key']} }}}}",
                "unit_of_measurement": sensor["unit"],
                "icon": sensor["icon"],
                "device": DEVICE_INFO,
                "availability_topic": AVAILABILITY_TOPIC,
                "payload_available": "online",
                "payload_not_available": "offline",
            }

            if sensor["device_class"]:
                payload["device_class"] = sensor["device_class"]
            if sensor["state_class"]:
                payload["state_class"] = sensor["state_class"]

            result = client.publish(
                discovery_topic,
                json.dumps(payload),
                retain=True,
                qos=1,
            )
            result.wait_for_publish()
            logger.info("Published discovery: %s (rc=%s)", discovery_topic, result.rc)

        # Publish availability
        result = client.publish(AVAILABILITY_TOPIC, "online", retain=True, qos=1)
        result.wait_for_publish()

        _disconnect(client)
        logger.info("MQTT auto-discovery published successfully")
        return True

    except Exception as e:
        logger.error("MQTT discovery publish failed: %s", e)
        _disconnect(client)
        return False


def publish_tank_data(config: dict, data: dict):
    """
    Publish discovery config (if not yet done) and tank state data.
    Called after each successful data fetch.
    """
    if not config.get("mqtt_enabled"):
        return

    # Always publish discovery first to ensure HA knows about our sensors
    publish_discovery(config)

    client = _get_mqtt_client(config)
    if not client:
        return False

    try:
        # Publish state
        result = client.publish(
            STATE_TOPIC,
            json.dumps(data),
            retain=True,
            qos=1,
        )
        result.wait_for_publish()

        # Update availability
        result = client.publish(AVAILABILITY_TOPIC, "online", retain=True, qos=1)
        result.wait_for_publish()

        _disconnect(client)
        logger.info("MQTT tank data published")
        return True

    except Exception as e:
        logger.error("MQTT data publish failed: %s", e)
        _disconnect(client)
        return False


def publish_offline(config: dict):
    """Mark the sensor as offline."""
    client = _get_mqtt_client(config)
    if not client:
        return
    try:
        result = client.publish(AVAILABILITY_TOPIC, "offline", retain=True, qos=1)
        result.wait_for_publish()
        _disconnect(client)
    except Exception:
        pass


def test_mqtt_connection(config: dict) -> dict:
    """Test MQTT broker connectivity."""
    if not MQTT_AVAILABLE:
        return {"success": False, "error": "paho-mqtt not installed"}

    client = _get_mqtt_client(config)
    if client:
        _disconnect(client)
        return {"success": True, "message": "MQTT connection successful"}
    return {"success": False, "error": "Could not connect to MQTT broker"}
