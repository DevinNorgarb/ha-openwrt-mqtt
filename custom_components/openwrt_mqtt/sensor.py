"""Sensor platform for OpenWrt MQTT integration."""
import logging
from homeassistant.components.sensor import SensorEntity
from homeassistant.core import callback
from homeassistant.components import mqtt
from homeassistant.helpers.device_registry import DeviceInfo
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the OpenWrt MQTT sensors."""
    sensors = []

    if DOMAIN not in hass.data:
        return False

    for hostname, device_info in hass.data[DOMAIN]["devices"].items():
        if "entities" in device_info:
            for unique_id, data in device_info["entities"].items():
                if unique_id not in hass.data[DOMAIN].get("configured_entities", set()):
                    device_info_obj = DeviceInfo(
                        identifiers=device_info["identifiers"],
                        name=device_info["name"],
                        manufacturer=device_info["manufacturer"],
                        model=device_info["model"],
                        sw_version=device_info["sw_version"],
                    )
                    sensors.append(OpenWrtMQTTSensor(hass, data, device_info_obj))
                    hass.data[DOMAIN].setdefault("configured_entities", set()).add(unique_id)

    if sensors:
        async_add_entities(sensors, True)

class OpenWrtMQTTSensor(SensorEntity):
    """Representation of an OpenWrt MQTT sensor."""

    def __init__(self, hass, data, device_info):
        """Initialize the sensor."""
        self.hass = hass
        self._data = data
        self._device_info = device_info
        self._state = None
        self._attr_unique_id = data["unique_id"]
        self._attr_name = f"{data['metric_type'].replace('/', ' ').replace('-', ' ').title()}"
        self._attr_native_unit_of_measurement = "%" if "memory" in data["metric_type"] or "load" in data["metric_type"] else None

    @property
    def device_info(self):
        """Return the device info."""
        return self._device_info

    @property
    def available(self):
        """Return True if entity is available."""
        return self._state is not None

    async def async_added_to_hass(self):
        """Subscribe to MQTT events."""
        @callback
        def message_received(message):
            """Handle new MQTT messages."""
            payload = message.payload.decode() if isinstance(message.payload, bytes) else message.payload
            self._state = self._parse_payload(payload)
            self.async_write_ha_state()

        await mqtt.async_subscribe(self.hass, self._data["topic"], message_received, qos=0)

    def _parse_payload(self, payload):
        """Parse the MQTT payload."""
        if "load:" in payload:
            return payload.split(":")[1]
        elif payload.startswith("value:"):
            return payload.split(":")[1].strip()
        elif "rx:" in payload and "tx:" in payload:
            parts = payload.split(",")
            rx = parts[0].split(":")[1]
            tx = parts[1].split(":")[1]
            return {"rx": rx, "tx": tx}
        else:
            return payload

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        if isinstance(self._state, dict):
            return self._state
        return None
