                     import logging
from homeassistant.components.sensor import SensorEntity
from homeassistant.core import callback
from homeassistant.helpers.entity import Entity
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the OpenWrt MQTT sensors."""
    sensors = []
    for unique_id, data in hass.data[DOMAIN].items():
        sensors.append(OpenWrtMQTTSensor(hass, data))

    async_add_entities(sensors, True)

class OpenWrtMQTTSensor(SensorEntity):
    """Representation of an OpenWrt MQTT sensor."""

    def __init__(self, hass, data):
        """Initialize the sensor."""
        self.hass = hass
        self._data = data
        self._state = None
        self._attr_unique_id = data["unique_id"]
        self._attr_name = f"OpenWrt {data['hostname']} {data['metric_type'].replace('/', ' ')}"
        self._attr_native_unit_of_measurement = "%" if "memory" in data["metric_type"] or "load" in data["metric_type"] else None

    async def async_added_to_hass(self):
        """Subscribe to MQTT events."""
        @callback
        def message_received(message):
            """Handle new MQTT messages."""
            self._state = message.payload
            self.async_write_ha_state()

        await self.hass.components.mqtt.async_subscribe(
            self._data["topic"], message_received, 0
        )

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return self._state
