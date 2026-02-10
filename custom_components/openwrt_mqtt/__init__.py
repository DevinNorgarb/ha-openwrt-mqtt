"""The OpenWrt MQTT integration."""
import logging
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.typing import ConfigType
from homeassistant.components import mqtt
from .const import DOMAIN, DEFAULT_TOPIC_PREFIX, DISCOVERY_TOPICS

_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the OpenWrt MQTT integration."""
    hass.data.setdefault(DOMAIN, {
        "devices": {},
        "setup_entities": set(),
        "add_entities_callback": None
    })
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

        # Initialiser le device si nécessaire
        if hostname not in hass.data[DOMAIN]["devices"]:
            hass.data[DOMAIN]["devices"][hostname] = {
                "identifiers": {(DOMAIN, hostname)},
                "name": hostname,
                "manufacturer": "OpenWrt",
                "model": "Router",
                "sw_version": "Unknown",
                "entities": {}
            }
            _LOGGER.info("Discovered new OpenWrt device: %s", hostname)

        # Mettre à jour les informations du device si c'est une info système
        if metric_type == "system/model":
            hass.data[DOMAIN]["devices"][hostname]["model"] = payload
            _LOGGER.debug("Updated device model for %s: %s", hostname, payload)
        elif metric_type == "system/version":
            hass.data[DOMAIN]["devices"][hostname]["sw_version"] = payload
            _LOGGER.debug("Updated device version for %s: %s", hostname, payload)

        # Vérifier si ce topic correspond à un topic de découverte
        should_create_entity = False
        matched_pattern = None
        for discovery_topic in DISCOVERY_TOPICS:
            # Convertir le pattern avec wildcards (+) en regex
            # Le "+" match n'importe quoi sauf un slash "/"
            import re
            pattern = discovery_topic.replace("+", "[^/]+")
            pattern = f"^{pattern}$"
            
            if re.match(pattern, metric_type):
                should_create_entity = True
                matched_pattern = discovery_topic
                _LOGGER.debug("Topic %s matches discovery pattern %s", metric_type, discovery_topic)
                break

        if should_create_entity:
            unique_id = f"openwrt_{hostname}_{metric_type.replace('/', '_').replace('-', '_')}"
            entity_id = f"sensor.openwrt_{hostname}_{metric_type.replace('/', '_').replace('-', '_')}"

            if unique_id not in hass.data[DOMAIN]["setup_entities"]:
                hass.data[DOMAIN]["devices"][hostname]["entities"][unique_id] = {
                    "topic": topic,
                    "metric_type": metric_type,
                    "unique_id": unique_id,
                    "entity_id": entity_id,
                    "hostname": hostname,
                }
                hass.data[DOMAIN]["setup_entities"].add(unique_id)
                _LOGGER.info("Discovered new sensor: %s (topic: %s)", entity_id, topic)
                
                # Si le callback add_entities est disponible, créer l'entité immédiatement
                if hass.data[DOMAIN]["add_entities_callback"] is not None:
                    from homeassistant.helpers.device_registry import DeviceInfo
                    from .sensor import OpenWrtMQTTSensor
                    
                    device_info = hass.data[DOMAIN]["devices"][hostname]
                    device_info_obj = DeviceInfo(
                        identifiers=device_info["identifiers"],
                        name=device_info["name"],
                        manufacturer=device_info["manufacturer"],
                        model=device_info["model"],
                        sw_version=device_info["sw_version"],
                    )
                    
                    data = hass.data[DOMAIN]["devices"][hostname]["entities"][unique_id]
                    new_sensor = OpenWrtMQTTSensor(hass, data, device_info_obj)
                    hass.data[DOMAIN]["add_entities_callback"]([new_sensor], True)
                    _LOGGER.info("Added sensor dynamically: %s", entity_id)

    async def mqtt_message_received(msg):
        """Handle new MQTT messages."""
        discover_devices(msg.topic, msg.payload, msg.qos)

    # S'abonner au topic MQTT
    await mqtt.async_subscribe(hass, f"{topic_prefix}#", mqtt_message_received, qos=0)
    _LOGGER.info("Subscribed to MQTT topic: %s#", topic_prefix)

    # Configuration initiale des capteurs
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigType) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_forward_entry_unload(entry, "sensor")
    
    if unload_ok:
        # Nettoyer les données
        if DOMAIN in hass.data:
            hass.data[DOMAIN]["devices"].clear()
            hass.data[DOMAIN]["setup_entities"].clear()
            hass.data[DOMAIN]["add_entities_callback"] = None
    
    return unload_ok
