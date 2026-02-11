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
            # Générer les unique_id pour tous les capteurs qui seront créés à partir de ce topic
            unique_ids = generate_unique_ids_for_metric(hostname, metric_type)
            
            # Vérifier si au moins un des capteurs n'a pas encore été créé
            new_sensors_needed = False
            for unique_id in unique_ids:
                if unique_id not in hass.data[DOMAIN]["setup_entities"]:
                    new_sensors_needed = True
                    break
            
            if new_sensors_needed:
                # Stocker les données du topic
                base_unique_id = f"openwrt_{hostname}_{metric_type.replace('/', '_').replace('-', '_')}"
                entity_id = f"sensor.{base_unique_id}"
                
                hass.data[DOMAIN]["devices"][hostname]["entities"][base_unique_id] = {
                    "topic": topic,
                    "metric_type": metric_type,
                    "unique_id": base_unique_id,
                    "entity_id": entity_id,
                    "hostname": hostname,
                }
                
                # Marquer tous les unique_ids comme créés
                for unique_id in unique_ids:
                    hass.data[DOMAIN]["setup_entities"].add(unique_id)
                
                _LOGGER.info("Discovered new sensor(s) for topic %s (%d entities)", topic, len(unique_ids))
                
                # Si le callback add_entities est disponible, créer les entités immédiatement
                if hass.data[DOMAIN]["add_entities_callback"] is not None:
                    from homeassistant.helpers.device_registry import DeviceInfo
                    from .sensor import create_sensors_for_metric
                    
                    device_info = hass.data[DOMAIN]["devices"][hostname]
                    device_info_obj = DeviceInfo(
                        identifiers=device_info["identifiers"],
                        name=device_info["name"],
                        manufacturer=device_info["manufacturer"],
                        model=device_info["model"],
                        sw_version=device_info["sw_version"],
                    )
                    
                    data = hass.data[DOMAIN]["devices"][hostname]["entities"][base_unique_id]
                    new_sensors = create_sensors_for_metric(hass, data, device_info_obj)
                    hass.data[DOMAIN]["add_entities_callback"](new_sensors, True)
                    _LOGGER.info("Added %d sensor(s) dynamically for %s", len(new_sensors), metric_type)

    async def mqtt_message_received(msg):
        """Handle new MQTT messages."""
        discover_devices(msg.topic, msg.payload, msg.qos)

    # S'abonner au topic MQTT
    await mqtt.async_subscribe(hass, f"{topic_prefix}#", mqtt_message_received, qos=0)
    _LOGGER.info("Subscribed to MQTT topic: %s#", topic_prefix)

    # Configuration initiale des capteurs
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])

    return True

def generate_unique_ids_for_metric(hostname, metric_type):
    """Generate all unique_ids that will be created for a given metric type."""
    unique_ids = []
    
    # Load : 3 capteurs
    if metric_type == "load/load":
        for load_type in ["1min", "5min", "15min"]:
            unique_ids.append(f"openwrt_{hostname}_load_{load_type}")
    
    # Interfaces réseau : 2 capteurs (RX et TX)
    elif metric_type.startswith("interface-") and metric_type.endswith(("/if_octets", "/if_packets", "/if_errors", "/if_dropped")):
        base_id = metric_type.replace('/', '_').replace('-', '_')
        for direction in ["rx", "tx"]:
            unique_ids.append(f"openwrt_{hostname}_{base_id}_{direction}")
    
    # Autres : 1 seul capteur
    else:
        unique_ids.append(f"openwrt_{hostname}_{metric_type.replace('/', '_').replace('-', '_')}")
    
    return unique_ids

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
