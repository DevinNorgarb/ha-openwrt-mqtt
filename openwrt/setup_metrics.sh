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
publish_metric "cpu/load" "load:$LOAD_AVG"

# Publish CPU load percentage (based on load average and number of cores)
# Get the number of CPU cores
CPU_CORES=$(grep -c "^processor" /proc/cpuinfo)

# Get 1-minute load average
LOAD_1MIN=$(cat /proc/loadavg | awk '{print $1}')

# Calculate CPU load percentage (load average / number of cores * 100)
# Using awk for floating point arithmetic
CPU_LOAD_PERCENT=$(awk -v load="$LOAD_1MIN" -v cores="$CPU_CORES" 'BEGIN {printf "%.0f", (load / cores) * 100}')

publish_metric "cpu/load_percent" "value:$CPU_LOAD_PERCENT"

# Publish memory usage (in KB)
MEMORY_FREE=$(awk '/MemFree/ {print $2}' /proc/meminfo)
MEMORY_CACHED=$(awk '/Cached/ {print $2}' /proc/meminfo | head -n 1)
MEMORY_USED=$(awk '/MemTotal/ {total=$2} /MemFree/ {free=$2} /Buffers/ {buffers=$2} /Cached/ {cached=$2} END {print total-free-buffers-cached}' /proc/meminfo)
publish_metric "memory/memory-free" "value:$MEMORY_FREE"
publish_metric "memory/memory-cached" "value:$MEMORY_CACHED"
publish_metric "memory/memory-used" "value:$MEMORY_USED"

# Publish disk usage (total for all partitions combined)
# On OpenWRT with overlay, we need to use only the overlay partition stats
# Check if overlay exists
if df -k | grep -q ":/overlay"; then
    # System with overlay - use only overlay stats
    DISK_STATS=$(df -k | awk '$6 == "/" {print $2, $3, $4}')
else
    # No overlay - sum all mounted partitions (excluding tmpfs, devtmpfs, etc.)
    DISK_STATS=$(df -k | awk 'NR>1 && $1 != "Filesystem" && $1 !~ /^tmpfs$/ && $1 !~ /^devtmpfs$/ && $1 !~ /^none$/ {total+=$2; used+=$3; avail+=$4} END {print total, used, avail}')
fi

DISK_TOTAL=$(echo $DISK_STATS | awk '{print $1}')
DISK_USED=$(echo $DISK_STATS | awk '{print $2}')
DISK_FREE=$(echo $DISK_STATS | awk '{print $3}')

# Calculate percentage used
if [ $DISK_TOTAL -gt 0 ]; then
    DISK_PERCENT=$((100 * DISK_USED / DISK_TOTAL))
else
    DISK_PERCENT=0
fi

publish_metric "disk/total" "value:$DISK_TOTAL"
publish_metric "disk/used" "value:$DISK_USED"
publish_metric "disk/free" "value:$DISK_FREE"
publish_metric "disk/percent" "value:$DISK_PERCENT"

# Publish tmpfs (/tmp) usage
TMP_STATS=$(df -k /tmp 2>/dev/null | awk 'NR==2 {print $2, $3, $4}')
if [ -n "$TMP_STATS" ]; then
    TMP_TOTAL=$(echo $TMP_STATS | awk '{print $1}')
    TMP_USED=$(echo $TMP_STATS | awk '{print $2}')
    TMP_FREE=$(echo $TMP_STATS | awk '{print $3}')
    
    # Calculate percentage used
    if [ $TMP_TOTAL -gt 0 ]; then
        TMP_PERCENT=$((100 * TMP_USED / TMP_TOTAL))
    else
        TMP_PERCENT=0
    fi
    
    publish_metric "disk_tmp/total" "value:$TMP_TOTAL"
    publish_metric "disk_tmp/used" "value:$TMP_USED"
    publish_metric "disk_tmp/free" "value:$TMP_FREE"
    publish_metric "disk_tmp/percent" "value:$TMP_PERCENT"
fi

# Publish network connection tracking statistics (total connections only)
if [ -f /proc/net/nf_conntrack ]; then
    CONN_TOTAL=$(wc -l < /proc/net/nf_conntrack)
    publish_metric "conntrack/total" "value:$CONN_TOTAL"
fi

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
