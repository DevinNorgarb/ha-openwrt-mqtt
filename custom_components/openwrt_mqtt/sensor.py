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

    async def async_added_to_hass(self):
        """Subscribe to MQTT events."""
        @callback
        def message_received(message):
            """Handle new MQTT messages."""
            self._state = message.payload
            self.async_write_ha_state()

        await mqtt.async_subscribe(self.hass, self._data["topic"], message_received, qos=0)

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return self._state