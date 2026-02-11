#!/bin/sh

# Update packages
opkg update

# Check if mosquitto_pub is already installed
if ! command -v mosquitto_pub &> /dev/null; then
    echo "Installing mosquitto-client..."

    # Check if libmosquitto-ssl is installed
    if opkg list-installed | grep -q "libmosquitto-ssl"; then
        echo "libmosquitto-ssl is already installed, installing mosquitto-client-ssl..."
        opkg install mosquitto-client-ssl
    else
        # Check if libmosquitto-nossl is installed
        if opkg list-installed | grep -q "libmosquitto-nossl"; then
            echo "libmosquitto-nossl is already installed, installing mosquitto-client-nossl..."
            opkg install mosquitto-client-nossl
        else
            echo "Installing libmosquitto-nossl and mosquitto-client-nossl..."
            opkg install libmosquitto-nossl mosquitto-client-nossl
        fi
    fi
else
    echo "mosquitto_pub is already installed."
fi

# Check if mosquitto_pub is now available
if ! command -v mosquitto_pub &> /dev/null; then
    echo "Error: mosquitto_pub is not installed."
    exit 1
fi

# Create the script to publish metrics
cat > /usr/bin/publish_metrics.sh << 'SCRIPT_END'
#!/bin/sh

# MQTT Configuration
MQTT_BROKER="<mqtt_broker_ip>"
MQTT_PORT="<mqtt_port>"
MQTT_USER="<mqtt_user>"
MQTT_PASSWORD="<mqtt_password>"
MQTT_TOPIC_PREFIX="openwrt"
HOSTNAME=$(uci get system.@system[0].hostname)

# Function to publish a metric
publish_metric() {
    local topic=$1
    local payload=$2
    mosquitto_pub -h "$MQTT_BROKER" -p "$MQTT_PORT" -u "$MQTT_USER" -P "$MQTT_PASSWORD" -t "$MQTT_TOPIC_PREFIX/$HOSTNAME/$topic" -m "$payload" -q 1
}

# Publish system information in separate sub-topics
MODEL=$(cat /tmp/sysinfo/model 2>/dev/null || echo "Unknown Model")
VERSION=$(cat /etc/openwrt_version 2>/dev/null || echo "Unknown Version")
TARGET_PLATFORM=$(cat /tmp/sysinfo/board_name 2>/dev/null || echo "Unknown Platform")
ARCHITECTURE=$(cat /proc/cpuinfo | grep "model name" | head -n 1 | cut -d ':' -f 2 | sed 's/^[ \t]*//' 2>/dev/null || cat /proc/cpuinfo | grep "Processor" | head -n 1 | cut -d ':' -f 2 | sed 's/^[ \t]*//' 2>/dev/null || echo "Unknown Architecture")
UPTIME=$(cut -d. -f1 /proc/uptime)

publish_metric "system/hostname" "$HOSTNAME"
publish_metric "system/model" "$MODEL"
publish_metric "system/target_platform" "$TARGET_PLATFORM"
publish_metric "system/architecture" "$ARCHITECTURE"
publish_metric "system/version" "$VERSION"
publish_metric "system/uptime" "$UPTIME"

# Publish CPU load
LOAD_AVG=$(cat /proc/loadavg | awk '{print $1","$2","$3}')
publish_metric "load/load" "load:$LOAD_AVG"

# Publish memory usage (in KB)
MEMORY_FREE=$(awk '/MemFree/ {print $2}' /proc/meminfo)
MEMORY_CACHED=$(awk '/Cached/ {print $2}' /proc/meminfo | head -n 1)
MEMORY_USED=$(awk '/MemTotal/ {total=$2} /MemFree/ {free=$2} /Buffers/ {buffers=$2} /Cached/ {cached=$2} END {print total-free-buffers-cached}' /proc/meminfo)
publish_metric "memory/memory-free" "value:$MEMORY_FREE"
publish_metric "memory/memory-cached" "value:$MEMORY_CACHED"
publish_metric "memory/memory-used" "value:$MEMORY_USED"

# Publish network interface statistics
for INTERFACE in $(ls /sys/class/net/ | grep -v lo); do
    RX_BYTES=$(cat /sys/class/net/$INTERFACE/statistics/rx_bytes)
    TX_BYTES=$(cat /sys/class/net/$INTERFACE/statistics/tx_bytes)
    RX_PACKETS=$(cat /sys/class/net/$INTERFACE/statistics/rx_packets)
    TX_PACKETS=$(cat /sys/class/net/$INTERFACE/statistics/tx_packets)
    RX_DROPPED=$(cat /sys/class/net/$INTERFACE/statistics/rx_dropped)
    TX_DROPPED=$(cat /sys/class/net/$INTERFACE/statistics/tx_dropped)
    RX_ERRORS=$(cat /sys/class/net/$INTERFACE/statistics/rx_errors)
    TX_ERRORS=$(cat /sys/class/net/$INTERFACE/statistics/tx_errors)

    publish_metric "interface-$INTERFACE/if_octets" "rx:$RX_BYTES,tx:$TX_BYTES"
    publish_metric "interface-$INTERFACE/if_packets" "rx:$RX_PACKETS,tx:$TX_PACKETS"
    publish_metric "interface-$INTERFACE/if_dropped" "rx:$RX_DROPPED,tx:$TX_DROPPED"
    publish_metric "interface-$INTERFACE/if_errors" "rx:$RX_ERRORS,tx:$TX_ERRORS"
done
SCRIPT_END

# Make the script executable
chmod +x /usr/bin/publish_metrics.sh

# Schedule the script to run every 5 minutes
(crontab -l 2>/dev/null; echo "*/5 * * * * /usr/bin/publish_metrics.sh") | crontab -
