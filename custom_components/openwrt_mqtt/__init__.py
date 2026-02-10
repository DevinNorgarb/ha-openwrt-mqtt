"""The OpenWrt MQTT integration."""
import logging
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.typing import ConfigType
from homeassistant.components import mqtt
from .const import DOMAIN, DEFAULT_TOPIC_PREFIX, DISCOVERY_TOPICS

_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the OpenWrt MQTT integration."""
    hass.data.setdefault(DOMAIN, {"devices": {}, "setup_entities": set()})
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigType) -> bool:
    """Set up OpenWrt MQTT from a config entry."""
    topic_prefix = entry.data.get("topic_prefix", DEFAULT_TOPIC_PREFIX)

    @callback
    def discover_devices(topic: str, payload: str, qos: int) -> None:
        """Handle MQTT discovery messages."""
        _LOGGER.debug("Discovered topic: %s, payload: %s", topic, payload)

        parts = topic.split("/")
        if len(parts) < 3:
            return

        hostname = parts[1]
        metric_type = "/".join(parts[2:])

        for discovery_topic in DISCOVERY_TOPICS:
            if discovery_topic.replace("+", hostname).replace("/", "\\/") in metric_type.replace("/", "\\/"):
                unique_id = f"openwrt_{hostname}_{metric_type.replace('/', '_')}"
                entity_id = f"sensor.openwrt_{hostname}_{metric_type.replace('/', '_')}"

                if unique_id not in hass.data[DOMAIN]["devices"]:
                    hass.data[DOMAIN]["devices"][unique_id] = {
                        "topic": topic,
                        "hostname": hostname,
                        "metric_type": metric_type,
                        "unique_id": unique_id,
                        "entity_id": entity_id,
                    }
                    _LOGGER.info("Adding new sensor: %s", entity_id)

                    # Déclencher la configuration des capteurs
                    hass.async_create_task(
                        hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
                    )

    async def mqtt_message_received(msg):
        """Handle new MQTT messages."""
        discover_devices(msg.topic, msg.payload, msg.qos)

    await mqtt.async_subscribe(hass, f"{topic_prefix}#", mqtt_message_received, qos=0)

    return True