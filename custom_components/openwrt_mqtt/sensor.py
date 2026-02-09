import logging
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.device_registry import DeviceInfo
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

class OpenWrtSensor(Entity):
    def __init__(self, device_name, unique_id, topic, payload, topic_suffix):
        self._device_name = device_name
        self._unique_id = unique_id
        self._topic = topic
        self._state = payload
        self._topic_suffix = topic_suffix
        self.hostname = topic.split("/")[1]
        self._device_info = DeviceInfo(
            identifiers={(DOMAIN, self.hostname)},
            name=device_name,
            manufacturer="OpenWrt"
        )

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def device_info(self):
        return self._device_info

    @property
    def name(self):
        return f"{self._device_name} {self._topic_suffix.replace('/', ' ').replace('-', ' ')}"

    @property
    def state(self):
        return self._state

    def update(self):
        pass

class OpenWrtMemorySensor(OpenWrtSensor):
    @property
    def state(self):
        try:
            return int(self._state.split(":")[1]) / 1000  # Convertir en Mo
        except Exception as e:
            _LOGGER.error(f"Erreur de parsing pour {self._topic}: {e}")
            return None

    @property
    def icon(self):
        return "mdi:memory"

    @property
    def unit_of_measurement(self):
        return "MB"

class OpenWrtInterfaceSensor(OpenWrtSensor):
    @property
    def state(self):
        try:
            if "rx:" in self._state and "tx:" in self._state:
                rx = int(self._state.split("rx:")[1].split(",")[0])
                tx = int(self._state.split("tx:")[1])
                return {"rx": rx, "tx": tx}
            return None
        except Exception as e:
            _LOGGER.error(f"Erreur de parsing pour {self._topic}: {e}")
            return None

    @property
    def icon(self):
        return "mdi:ethernet"

    @property
    def unit_of_measurement(self):
        return "bytes"
