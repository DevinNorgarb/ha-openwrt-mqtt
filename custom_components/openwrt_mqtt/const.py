DOMAIN = "openwrt_mqtt"
DEFAULT_TOPIC_PREFIX = "openwrt/+/"
DISCOVERY_TOPICS = [
    "load/load",
    "memory/memory-free",
    "memory/memory-cached",
    "memory/memory-used",
    "system/hostname",
    "system/model",
    "system/target_platform",
    "system/architecture",
    "system/version",
    "system/uptime"
]
