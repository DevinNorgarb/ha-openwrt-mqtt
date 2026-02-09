import logging
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.components.mqtt import subscription
from .const import DOMAIN, DEFAULT_TOPIC_PREFIX, DISCOVERY_TOPICS

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    entities = []

    @subscription(DEFAULT_TOPIC_PREFIX + "#")
    def message_received(topic, payload, qos):
        try:
            parts = topic.split("/")
            hostname = parts[1]
            device_id = f"{DOMAIN}_{hostname}"
            topic_suffix = "/".join(parts[2:])
            unique_id = f"{device_id}_{topic_suffix.replace('/', '_').replace('-', '_')}"

            if "memory" in topic_suffix:
                entities.append(OpenWrtMemorySensor(device_name=f"OpenWRT {hostname}", unique_id=unique_id, topic=topic, payload=payload.decode(), topic_suffix=topic_suffix))
            elif "interface-" in topic_suffix:
                entities.append(OpenWrtInterfaceSensor(device_name=f"OpenWRT {hostname}", unique_id=unique_id, topic=topic, payload=payload.decode(), topic_suffix=topic_suffix))
            else:
                entities.append(OpenWrtSensor(device_name=f"OpenWRT {hostname}", unique_id=unique_id, topic=topic, payload=payload.decode(), topic_suffix=topic_suffix))

            async_add_entities(entities, update_before_add=True)
        except Exception as e:
            _LOGGER.error(f"Erreur lors de la réception du message MQTT: {e}")

    for discovery_topic in DISCOVERY_TOPICS:
        full_topic = DEFAULT_TOPIC_PREFIX + discovery_topic
        await subscription.subscribe(hass, full_topic, message_received)

    return True