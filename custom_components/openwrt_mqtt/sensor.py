import logging
import re
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.components.mqtt import subscription
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.config_entries import ConfigEntry
from .const import DOMAIN, DEFAULT_TOPIC_PREFIX, DISCOVERY_TOPICS

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    topic_prefix = config_entry.options.get("topic_prefix", DEFAULT_TOPIC_PREFIX)
    discovered_sensors = {}

    @callback
    def discover_sensors(topic: str, payload: str, qos: int, properties: dict) -> None:
        _LOGGER.debug(f"Received MQTT message on {topic}: {payload}")
        parts = topic.split("/")
        if len(parts) < 4:
            return

        device_id = parts[1]
        metric_type = parts[2]
        metric_name = parts[3]

        # Device info (extracted from topic)
        device_info = {
            "identifiers": {(DOMAIN, device_id)},
            "name": device_id,
            "model": "OpenWrt Device",
            "manufacturer": "OpenWrt",
        }

        if metric_type == "load" and metric_name == "load":
            # CPU Load
            values = payload.split(":")[1].split(",")
            if len(values) >= 3:
                for i, load_type in enumerate(["L1", "L5", "L15"]):
                    unique_id = f"{device_id}_cpu_{load_type.lower()}"
                    if unique_id not in discovered_sensors:
                        discovered_sensors[unique_id] = OpenWrtSensor(
                            name=f"{device_id} CPU {load_type}",
                            state_topic=topic,
                            value_template=f"{{{{ (value.split(':')[1].split(',')[{i}] | float(0)) | round(2) }}}}",
                            unit="load",
                            unique_id=unique_id,
                            icon="mdi:gauge",
                            device_info=device_info,
                        )

        elif metric_type == "memory":
            # RAM
            memory_type = metric_name.split("-")[1]
            unique_id = f"{device_id}_ram_{memory_type}"
            if unique_id not in discovered_sensors:
                discovered_sensors[unique_id] = OpenWrtSensor(
                    name=f"{device_id} RAM {memory_type.title()}",
                    state_topic=topic,
                    value_template="{{ (value.split(':')[1] | float(0) / 1024) | round(1) }}",
                    unit="MB",
                    unique_id=unique_id,
                    device_class=SensorDeviceClass.DATA_SIZE,
                    icon="mdi:memory",
                    device_info=device_info,
                )

        elif metric_type.startswith("interface-"):
            # Network Interface
            interface = metric_type.split("-")[1]
            if metric_name == "if_dropped":
                unique_id = f"{device_id}_{interface}_dropped"
                if unique_id not in discovered_sensors:
                    discovered_sensors[unique_id] = OpenWrtSensor(
                        name=f"{device_id} {interface} dropped",
                        state_topic=topic,
                        value_template="{{ value.split(',')[0].split(':')[1] | int + value.split(',')[1].split(':')[1] | int }}",
                        unit="packets",
                        unique_id=unique_id,
                        icon="mdi:lan-pending",
                        device_info=device_info,
                    )

            elif metric_name == "if_errors":
                unique_id = f"{device_id}_{interface}_errors"
                if unique_id not in discovered_sensors:
                    discovered_sensors[unique_id] = OpenWrtSensor(
                        name=f"{device_id} {interface} errors",
                        state_topic=topic,
                        value_template="{{ value.split(',')[0].split(':')[1] | int + value.split(',')[1].split(':')[1] | int }}",
                        unit="packets",
                        unique_id=unique_id,
                        icon="mdi:lan-disconnect",
                        device_info=device_info,
                    )

            elif metric_name == "if_octets":
                unique_id_tx = f"{device_id}_{interface}_tx_mbits"
                unique_id_rx = f"{device_id}_{interface}_rx_mbits"
                if unique_id_tx not in discovered_sensors:
                    discovered_sensors[unique_id_tx] = OpenWrtSensor(
                        name=f"{device_id} {interface} TX Mb/s",
                        state_topic=topic,
                        value_template="{{ (value.split(',')[1].split(':')[1] | float(0) * 8 / 1048576) | round(2) }}",
                        unit="Mbit/s",
                        unique_id=unique_id_tx,
                        device_class=SensorDeviceClass.DATA_RATE,
                        icon="mdi:upload-network",
                        device_info=device_info,
                    )
                if unique_id_rx not in discovered_sensors:
                    discovered_sensors[unique_id_rx] = OpenWrtSensor(
                        name=f"{device_id} {interface} RX Mb/s",
                        state_topic=topic,
                        value_template="{{ (value.split(',')[0].split(':')[1] | float(0) * 8 / 1048576) | round(2) }}",
                        unit="Mbit/s",
                        unique_id=unique_id_rx,
                        device_class=SensorDeviceClass.DATA_RATE,
                        icon="mdi:download-network",
                        device_info=device_info,
                    )

            elif metric_name == "if_packets":
                unique_id = f"{device_id}_{interface}_packets"
                if unique_id not in discovered_sensors:
                    discovered_sensors[unique_id] = OpenWrtSensor(
                        name=f"{device_id} {interface} packets/s",
                        state_topic=topic,
                        value_template="{{ value.split(',')[0].split(':')[1] | int + value.split(',')[1].split(':')[1] | int }}",
                        unit="packets/s",
                        unique_id=unique_id,
                        icon="mdi:lan-connect",
                        device_info=device_info,
                    )

        elif metric_type == "system":
            if metric_name == "hostname":
                hostname = payload
                for sensor in discovered_sensors.values():
                    if sensor._device_info["identifiers"] == {(DOMAIN, device_id)}:
                        sensor._device_info = DeviceInfo(
                            identifiers={(DOMAIN, device_id)},
                            name=hostname,
                            model=sensor._device_info.get("model", "OpenWrt Device"),
                            manufacturer=sensor._device_info.get("manufacturer", "OpenWrt"),
                            sw_version=sensor._device_info.get("sw_version", "Unknown"),
                        )

            elif metric_name == "model":
                model = payload
                for sensor in discovered_sensors.values():
                    if sensor._device_info["identifiers"] == {(DOMAIN, device_id)}:
                        sensor._device_info = DeviceInfo(
                            identifiers={(DOMAIN, device_id)},
                            name=sensor._device_info.get("name", device_id),
                            model=model,
                            manufacturer=sensor._device_info.get("manufacturer", "OpenWrt"),
                            sw_version=sensor._device_info.get("sw_version", "Unknown"),
                        )

            elif metric_name == "target_platform":
                target_platform = payload
                for sensor in discovered_sensors.values():
                    if sensor._device_info["identifiers"] == {(DOMAIN, device_id)}:
                        sensor._device_info = DeviceInfo(
                            identifiers={(DOMAIN, device_id)},
                            name=sensor._device_info.get("name", device_id),
                            model=sensor._device_info.get("model", "OpenWrt Device"),
                            manufacturer=target_platform,
                            sw_version=sensor._device_info.get("sw_version", "Unknown"),
                        )

            elif metric_name == "architecture":
                architecture = payload
                for sensor in discovered_sensors.values():
                    if sensor._device_info["identifiers"] == {(DOMAIN, device_id)}:
                        sensor._device_info = DeviceInfo(
                            identifiers={(DOMAIN, device_id)},
                            name=sensor._device_info.get("name", device_id),
                            model=sensor._device_info.get("model", "OpenWrt Device"),
                            manufacturer=sensor._device_info.get("manufacturer", "OpenWrt"),
                            sw_version=sensor._device_info.get("sw_version", "Unknown"),
                            configuration_url=f"Architecture: {architecture}",
                        )

            elif metric_name == "version":
                version = payload
                for sensor in discovered_sensors.values():
                    if sensor._device_info["identifiers"] == {(DOMAIN, device_id)}:
                        sensor._device_info = DeviceInfo(
                            identifiers={(DOMAIN, device_id)},
                            name=sensor._device_info.get("name", device_id),
                            model=sensor._device_info.get("model", "OpenWrt Device"),
                            manufacturer=sensor._device_info.get("manufacturer", "OpenWrt"),
                            sw_version=version,
                        )

            elif metric_name == "uptime":
                unique_id = f"{device_id}_uptime"
                if unique_id not in discovered_sensors:
                    discovered_sensors[unique_id] = OpenWrtSensor(
                        name=f"{device_id} Uptime",
                        state_topic=topic,
                        value_template="{{ (value | float(0) / 86400) | round(2) }}",
                        unit="days",
                        unique_id=unique_id,
                        icon="mdi:clock",
                        device_info=DeviceInfo(
                            identifiers={(DOMAIN, device_id)},
                            name=device_id,
                            model="OpenWrt Device",
                            manufacturer="OpenWrt",
                        ),
                    )

        async_add_entities(discovered_sensors.values(), True)

    for discovery_topic in DISCOVERY_TOPICS:
        await subscription.async_subscribe_topics(
            hass,
            config_entry.entry_id,
            {f"{topic_prefix}{discovery_topic}": {"topic": f"{topic_prefix}{discovery_topic}", "qos": 1, "encoding": "utf-8"}},
            discover_sensors,
        )

class OpenWrtSensor(SensorEntity):
    def __init__(
        self,
        name: str,
        state_topic: str,
        value_template: str,
        unit: str,
        unique_id: str,
        device_class: SensorDeviceClass | None = None,
        icon: str | None = None,
        device_info: DeviceInfo | None = None,
    ) -> None:
        self._name = name
        self._state_topic = state_topic
        self._value_template = value_template
        self._unit = unit
        self._unique_id = unique_id
        self._device_class = device_class
        self._icon = icon
        self._device_info = device_info
        self._state = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def state(self):
        return self._state

    @property
    def native_unit_of_measurement(self) -> str | None:
        return self._unit

    @property
    def unique_id(self) -> str:
        return self._unique_id

    @property
    def device_class(self) -> SensorDeviceClass | None:
        return self._device_class

    @property
    def icon(self) -> str | None:
        return self._icon

    @property
    def device_info(self) -> DeviceInfo | None:
        return self._device_info

    @callback
    def _handle_mqtt_message(self, message: str) -> None:
        try:
            from jinja2 import Template
            template = Template(self._value_template)
            self._state = template.render({"value": message})
            self.async_write_ha_state()
        except Exception as e:
            _LOGGER.error(f"Error processing MQTT message: {e}")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.hass.bus.async_listen_once(
            "mqtt_message_received",
            lambda msg: self._handle_mqtt_message(msg.data["payload"])
            if msg.data["topic"] == self._state_topic
            else None,
        )
