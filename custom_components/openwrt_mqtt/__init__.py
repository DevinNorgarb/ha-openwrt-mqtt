"""The OpenWrt MQTT integration."""
import logging
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.typing import ConfigType
from homeassistant.components import mqtt
from .const import DOMAIN, DEFAULT_TOPIC_PREFIX, DISCOVERY_TOPICS

_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the OpenWrt MQTT integration."""
    hass.data.setdefault(DOMAIN, {})
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

                if unique_id not in hass.data[DOMAIN]:
                    hass.data[DOMAIN][unique_id] = {
                        "topic": topic,
                        "hostname": hostname,
                        "metric_type": metric_type,
                        "unique_id": unique_id,
                        "entity_id": entity_id,
                    }
                    _LOGGER.info("Adding new sensor: %s", entity_id)

                    hass.async_create_task(
                        hass.config_entries.async_forward_entry_setup(entry, "sensor")
                    )

    await mqtt.async_subscribe(hass, f"{topic_prefix}#", discover_devices, qos=0)

    return True
