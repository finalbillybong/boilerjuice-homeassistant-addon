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
from typing import Optional

logger = logging.getLogger(__name__)

# Try importing paho-mqtt (optional dependency)
try:
    import paho.mqtt.client as mqtt_client
    import paho.mqtt.publish as mqtt_publish
    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False
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
    "sw_version": "1.0.0",
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
        client = mqtt_client.Client(
            client_id="boilerjuice-addon",
            protocol=mqtt_client.MQTTv311,
        )
        if user:
            client.username_pw_set(user, password)

        client.connect(host, port, keepalive=60)
        return client

    except Exception as e:
        logger.error("MQTT connection failed: %s", e)
        return None


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

            client.publish(
                discovery_topic,
                json.dumps(payload),
                retain=True,
                qos=1,
            )
            logger.info("Published discovery: %s", discovery_topic)

        # Publish availability
        client.publish(AVAILABILITY_TOPIC, "online", retain=True, qos=1)

        client.disconnect()
        logger.info("MQTT auto-discovery published successfully")
        return True

    except Exception as e:
        logger.error("MQTT discovery publish failed: %s", e)
        try:
            client.disconnect()
        except Exception:
            pass
        return False


def publish_tank_data(config: dict, data: dict):
    """
    Publish tank data to the MQTT state topic.
    Call this after each successful data fetch.
    """
    if not config.get("mqtt_enabled"):
        return

    client = _get_mqtt_client(config)
    if not client:
        return False

    try:
        # Publish state
        client.publish(
            STATE_TOPIC,
            json.dumps(data),
            retain=True,
            qos=1,
        )

        # Update availability
        client.publish(AVAILABILITY_TOPIC, "online", retain=True, qos=1)

        client.disconnect()
        logger.info("MQTT tank data published")
        return True

    except Exception as e:
        logger.error("MQTT data publish failed: %s", e)
        try:
            client.disconnect()
        except Exception:
            pass
        return False


def publish_offline(config: dict):
    """Mark the sensor as offline."""
    client = _get_mqtt_client(config)
    if not client:
        return
    try:
        client.publish(AVAILABILITY_TOPIC, "offline", retain=True, qos=1)
        client.disconnect()
    except Exception:
        pass


def test_mqtt_connection(config: dict) -> dict:
    """Test MQTT broker connectivity."""
    if not MQTT_AVAILABLE:
        return {"success": False, "error": "paho-mqtt not installed"}

    client = _get_mqtt_client(config)
    if client:
        try:
            client.disconnect()
            return {"success": True, "message": "MQTT connection successful"}
        except Exception:
            pass
    return {"success": False, "error": "Could not connect to MQTT broker"}
