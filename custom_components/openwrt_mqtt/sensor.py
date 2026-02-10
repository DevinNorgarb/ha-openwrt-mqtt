"""Sensor platform for OpenWrt MQTT integration."""
import logging
import re
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfInformation, UnitOfDataRate
from homeassistant.core import callback
from homeassistant.components import mqtt
from homeassistant.helpers.device_registry import DeviceInfo
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the OpenWrt MQTT sensors."""
    # Stocker le callback pour permettre l'ajout dynamique d'entités
    hass.data[DOMAIN]["add_entities_callback"] = async_add_entities
    
    sensors = []

    if DOMAIN not in hass.data:
        return False

    # Créer les capteurs pour les entités déjà découvertes
    for hostname, device_info in hass.data[DOMAIN]["devices"].items():
        if "entities" in device_info:
            for unique_id, data in device_info["entities"].items():
                if unique_id in hass.data[DOMAIN]["setup_entities"]:
                    device_info_obj = DeviceInfo(
                        identifiers=device_info["identifiers"],
                        name=device_info["name"],
                        manufacturer=device_info["manufacturer"],
                        model=device_info["model"],
                        sw_version=device_info["sw_version"],
                    )
                    sensors.append(OpenWrtMQTTSensor(hass, data, device_info_obj))

    if sensors:
        async_add_entities(sensors, True)
        _LOGGER.info("Created %d OpenWrt MQTT sensors at startup", len(sensors))
    else:
        _LOGGER.info("No sensors to create at startup - will be added dynamically as MQTT messages arrive")

class OpenWrtMQTTSensor(SensorEntity):
    """Representation of an OpenWrt MQTT sensor."""

    def __init__(self, hass, data, device_info):
        """Initialize the sensor."""
        self.hass = hass
        self._data = data
        self._device_info = device_info
        self._state = None
        self._attr_unique_id = data["unique_id"]
        self._extra_attributes = {}
        
        metric_type = data["metric_type"]
        
        # Nom du capteur
        self._attr_name = self._generate_name(metric_type)
        
        # Configuration des unités et device class
        self._configure_sensor_properties(metric_type)

    def _generate_name(self, metric_type):
        """Generate a friendly name from metric type."""
        parts = metric_type.split('/')
        
        if metric_type.startswith("interface-"):
            interface = parts[0].replace("interface-", "")
            metric = parts[1] if len(parts) > 1 else ""
            
            if metric == "if_octets":
                return f"{interface} Octets"
            elif metric == "if_packets":
                return f"{interface} Packets"
            elif metric == "if_errors":
                return f"{interface} Errors"
            elif metric == "if_dropped":
                return f"{interface} Dropped"
        
        elif metric_type.startswith("memory/"):
            mem_type = parts[1].replace("memory-", "")
            return f"Memory {mem_type.title()}"
        
        elif metric_type.startswith("system/"):
            sys_type = parts[1]
            return f"System {sys_type.replace('_', ' ').title()}"
        
        elif metric_type == "load/load":
            return "Load Average"
        
        return metric_type.replace('/', ' ').replace('-', ' ').title()

    def _configure_sensor_properties(self, metric_type):
        """Configure sensor properties based on metric type."""
        # Valeurs par défaut
        self._attr_native_unit_of_measurement = None
        self._attr_device_class = None
        self._attr_state_class = None
        self._attr_suggested_display_precision = None
        
        if "memory" in metric_type:
            # Mémoire en kibibytes
            self._attr_native_unit_of_measurement = UnitOfInformation.KIBIBYTES
            self._attr_device_class = SensorDeviceClass.DATA_SIZE
            self._attr_state_class = SensorStateClass.MEASUREMENT
        
        elif "if_octets" in metric_type:
            # Octets réseau - on affichera les valeurs RX et TX séparément
            self._attr_native_unit_of_measurement = UnitOfInformation.BYTES
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        
        elif "if_packets" in metric_type or "if_errors" in metric_type or "if_dropped" in metric_type:
            # Paquets/Erreurs/Dropped
            self._attr_native_unit_of_measurement = "packets"
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING
        
        elif "load" in metric_type:
            # Load average - sans unité
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_suggested_display_precision = 2
        
        elif "uptime" in metric_type:
            # Uptime en secondes
            self._attr_native_unit_of_measurement = "s"
            self._attr_device_class = SensorDeviceClass.DURATION
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING

    @property
    def device_info(self):
        """Return the device info."""
        return self._device_info

    async def async_added_to_hass(self):
        """Subscribe to MQTT events."""
        @callback
        def message_received(message):
            """Handle new MQTT messages."""
            payload = message.payload
            parsed_value = self._parse_payload(payload)
            
            if parsed_value is not None:
                self._state = parsed_value
                self.async_write_ha_state()
            else:
                _LOGGER.warning("Could not parse payload '%s' for %s", payload, self._attr_name)

        await mqtt.async_subscribe(self.hass, self._data["topic"], message_received, qos=0)

    def _parse_payload(self, payload):
        """Parse MQTT payload based on metric type."""
        metric_type = self._data["metric_type"]
        
        try:
            # Pour les métriques avec format "value:XXXX"
            if metric_type.startswith("memory/"):
                # Nettoyer les doublons "value:value:" et extraire la valeur
                cleaned = re.sub(r'^value:', '', payload)
                cleaned = re.sub(r'^value:', '', cleaned)  # Au cas où il y aurait un double
                value = float(cleaned)
                return value
            
            # Pour la charge système "load:X.XX,Y.YY,Z.ZZ"
            elif metric_type == "load/load":
                match = re.search(r'load:([\d.]+),([\d.]+),([\d.]+)', payload)
                if match:
                    load_1 = float(match.group(1))
                    load_5 = float(match.group(2))
                    load_15 = float(match.group(3))
                    
                    # Stocker les valeurs supplémentaires en attributs
                    self._extra_attributes = {
                        "load_1min": load_1,
                        "load_5min": load_5,
                        "load_15min": load_15
                    }
                    
                    # Retourner la charge 1 min comme valeur principale
                    return load_1
            
            # Pour les interfaces réseau "rx:XXXX,tx:YYYY"
            elif metric_type.startswith("interface-"):
                match = re.search(r'rx:([\d]+),tx:([\d]+)', payload)
                if match:
                    rx_value = int(match.group(1))
                    tx_value = int(match.group(2))
                    
                    # Stocker RX et TX en attributs
                    self._extra_attributes = {
                        "rx": rx_value,
                        "tx": tx_value
                    }
                    
                    # Retourner RX comme valeur principale
                    return rx_value
            
            # Pour les informations système (texte brut)
            elif metric_type.startswith("system/"):
                if metric_type == "system/uptime":
                    # Uptime est un nombre
                    return int(payload)
                else:
                    # Autres infos système (hostname, model, etc.) - retourner tel quel
                    return payload
            
            # Sinon, essayer de parser comme nombre
            else:
                try:
                    return float(payload)
                except ValueError:
                    return payload
                    
        except (ValueError, AttributeError) as e:
            _LOGGER.error("Error parsing payload '%s' for %s: %s", payload, metric_type, e)
            return None

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return self._state
    
    @property
    def extra_state_attributes(self):
        """Return additional attributes."""
        return self._extra_attributes
