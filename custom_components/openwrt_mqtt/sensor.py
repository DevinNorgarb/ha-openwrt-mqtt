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
                    
                    # Créer potentiellement plusieurs capteurs pour certains types
                    new_sensors = create_sensors_for_metric(hass, data, device_info_obj)
                    sensors.extend(new_sensors)

    if sensors:
        async_add_entities(sensors, True)
        _LOGGER.info("Created %d OpenWrt MQTT sensors at startup", len(sensors))
    else:
        _LOGGER.info("No sensors to create at startup - will be added dynamically as MQTT messages arrive")

def create_sensors_for_metric(hass, data, device_info):
    """Create one or more sensors based on the metric type."""
    sensors = []
    metric_type = data["metric_type"]
    
    # Load : créer 3 capteurs séparés
    if metric_type == "load/load":
        for load_type in ["1min", "5min", "15min"]:
            sensor_data = data.copy()
            sensor_data["load_type"] = load_type
            sensors.append(OpenWrtMQTTSensor(hass, sensor_data, device_info))
    
    # Interfaces réseau : créer 2 capteurs (RX et TX)
    elif metric_type.startswith("interface-") and metric_type.endswith(("/if_octets", "/if_packets", "/if_errors", "/if_dropped")):
        for direction in ["rx", "tx"]:
            sensor_data = data.copy()
            sensor_data["direction"] = direction
            sensors.append(OpenWrtMQTTSensor(hass, sensor_data, device_info))
    
    # Autres capteurs : 1 seul capteur
    else:
        sensors.append(OpenWrtMQTTSensor(hass, data, device_info))
    
    return sensors

class OpenWrtMQTTSensor(SensorEntity):
    """Representation of an OpenWrt MQTT sensor."""

    def __init__(self, hass, data, device_info):
        """Initialize the sensor."""
        self.hass = hass
        self._data = data
        self._device_info = device_info
        self._state = None
        self._extra_attributes = {}
        
        metric_type = data["metric_type"]
        hostname = data.get("hostname", "unknown")
        
        # Générer unique_id en fonction du type
        if "load_type" in data:
            # Load : unique_id inclut le type (1min, 5min, 15min)
            self._attr_unique_id = f"openwrt_{hostname}_load_{data['load_type']}"
        elif "direction" in data:
            # Interface : unique_id inclut la direction (rx ou tx)
            base_id = metric_type.replace('/', '_').replace('-', '_')
            self._attr_unique_id = f"openwrt_{hostname}_{base_id}_{data['direction']}"
        else:
            # Autres : unique_id standard
            self._attr_unique_id = data["unique_id"]
        
        # Nom du capteur (préfixé avec hostname)
        self._attr_name = self._generate_name(hostname, metric_type)
        
        # Configuration des unités et device class
        self._configure_sensor_properties(metric_type)

    def _generate_name(self, hostname, metric_type):
        """Generate a friendly name from metric type, prefixed with hostname."""
        parts = metric_type.split('/')
        
        # Load : noms spécifiques
        if metric_type == "load/load":
            if "load_type" in self._data:
                load_type = self._data["load_type"]
                if load_type == "1min":
                    return f"{hostname} Load 1min"
                elif load_type == "5min":
                    return f"{hostname} Load 5min"
                elif load_type == "15min":
                    return f"{hostname} Load 15min"
        
        # Interfaces réseau
        if metric_type.startswith("interface-"):
            interface = parts[0].replace("interface-", "")
            metric = parts[1] if len(parts) > 1 else ""
            direction = self._data.get("direction", "").upper()
            
            if metric == "if_octets":
                return f"{hostname} {interface} {direction}"
            elif metric == "if_packets":
                return f"{hostname} {interface} Packets {direction}"
            elif metric == "if_errors":
                return f"{hostname} {interface} Errors {direction}"
            elif metric == "if_dropped":
                return f"{hostname} {interface} Dropped {direction}"
        
        # Mémoire
        elif metric_type.startswith("memory/"):
            mem_type = parts[1].replace("memory-", "")
            return f"{hostname} Memory {mem_type.title()}"
        
        # Système
        elif metric_type.startswith("system/"):
            sys_type = parts[1]
            return f"{hostname} {sys_type.replace('_', ' ').title()}"
        
        # Par défaut
        return f"{hostname} {metric_type.replace('/', ' ').replace('-', ' ').title()}"

    def _configure_sensor_properties(self, metric_type):
        """Configure sensor properties based on metric type."""
        # Valeurs par défaut
        self._attr_native_unit_of_measurement = None
        self._attr_device_class = None
        self._attr_state_class = None
        self._attr_suggested_display_precision = None
        self._attr_icon = None
        
        # Load
        if metric_type == "load/load":
            self._attr_icon = "mdi:gauge"
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_suggested_display_precision = 2
        
        # Mémoire en MB (conversion depuis KiB)
        elif "memory" in metric_type:
            self._attr_native_unit_of_measurement = UnitOfInformation.MEGABYTES
            self._attr_device_class = SensorDeviceClass.DATA_SIZE
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_icon = "mdi:memory"
        
        # Octets réseau
        elif "if_octets" in metric_type:
            self._attr_native_unit_of_measurement = UnitOfInformation.BYTES
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING
            
            direction = self._data.get("direction", "rx")
            if direction == "tx":
                self._attr_icon = "mdi:upload-network"
            else:
                self._attr_icon = "mdi:download-network"
        
        # Paquets réseau
        elif "if_packets" in metric_type:
            self._attr_native_unit_of_measurement = "packets"
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING
            self._attr_icon = "mdi:lan-connect"
        
        # Erreurs réseau
        elif "if_errors" in metric_type:
            self._attr_native_unit_of_measurement = "packets"
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING
            self._attr_icon = "mdi:lan-disconnect"
        
        # Paquets dropped
        elif "if_dropped" in metric_type:
            self._attr_native_unit_of_measurement = "packets"
            self._attr_state_class = SensorStateClass.TOTAL_INCREASING
            self._attr_icon = "mdi:lan-pending"
        
        # Uptime
        elif "uptime" in metric_type:
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
            # Load : extraire la valeur spécifique (1min, 5min ou 15min)
            if metric_type == "load/load":
                match = re.search(r'load:([\d.]+),([\d.]+),([\d.]+)', payload)
                if match:
                    load_1min = float(match.group(1))
                    load_5min = float(match.group(2))
                    load_15min = float(match.group(3))
                    
                    if self._data.get("load_type") == "1min":
                        return load_1min
                    elif self._data.get("load_type") == "5min":
                        return load_5min
                    elif self._data.get("load_type") == "15min":
                        return load_15min
            
            # Mémoire : convertir KiB en MB
            elif metric_type.startswith("memory/"):
                # Nettoyer les doublons "value:value:" et extraire la valeur
                cleaned = re.sub(r'^value:', '', payload)
                cleaned = re.sub(r'^value:', '', cleaned)  # Au cas où il y aurait un double
                value_kib = float(cleaned)
                # Convertir KiB en MB (1 KiB = 0.001024 MB)
                value_mb = value_kib / 1024
                return round(value_mb, 1)
            
            # Interfaces réseau : extraire RX ou TX selon la direction
            elif metric_type.startswith("interface-"):
                match = re.search(r'rx:([\d]+),tx:([\d]+)', payload)
                if match:
                    rx_value = int(match.group(1))
                    tx_value = int(match.group(2))
                    
                    direction = self._data.get("direction", "rx")
                    if direction == "rx":
                        return rx_value
                    elif direction == "tx":
                        return tx_value
            
            # Informations système
            elif metric_type.startswith("system/"):
                if metric_type == "system/uptime":
                    return int(payload)
                else:
                    # Texte brut
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
        return self._extra_attributes if self._extra_attributes else None
