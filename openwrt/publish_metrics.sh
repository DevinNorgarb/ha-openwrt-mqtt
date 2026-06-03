#!/bin/sh
# Installed by setup_metrics.sh — credentials live in /etc/openwrt-metrics.env

ENV_FILE="/etc/openwrt-metrics.env"
if [ ! -f "$ENV_FILE" ]; then
    echo "Missing $ENV_FILE — run setup_metrics.sh or copy openwrt-metrics.env.example" >&2
    exit 1
fi
. "$ENV_FILE"

if command -v uci >/dev/null 2>&1; then
    HOSTNAME=$(uci get system.@system[0].hostname 2>/dev/null || hostname)
else
    HOSTNAME=$(hostname)
fi

publish_metric() {
    local topic=$1
    local payload=$2
    local full_topic="$MQTT_TOPIC_PREFIX/$HOSTNAME/$topic"

    if [ "$PUBLISH_METHOD" = "mqtt" ]; then
        mosquitto_pub \
            -h "$MQTT_BROKER" \
            -p "$MQTT_PORT" \
            -u "$MQTT_USER" \
            -P "$MQTT_PASSWORD" \
            -t "$full_topic" \
            -m "$payload" \
            -q 1
    elif [ "$PUBLISH_METHOD" = "http" ]; then
        curl -s -X POST \
            -H "Authorization: Bearer $HA_TOKEN" \
            -H "Content-Type: application/json" \
            -d "{\"topic\":\"$full_topic\",\"payload\":\"$payload\"}" \
            "$HA_URL:$HA_PORT/api/services/mqtt/publish" > /dev/null 2>&1
    fi
}

# ---------- System information ----------
MODEL=$(cat /tmp/sysinfo/model 2>/dev/null || echo "Unknown Model")
VERSION=$(cat /etc/openwrt_version 2>/dev/null || echo "Unknown Version")
TARGET_PLATFORM=$(cat /tmp/sysinfo/board_name 2>/dev/null || echo "Unknown Platform")
ARCHITECTURE=$(uname -m)
UPTIME=$(cut -d. -f1 /proc/uptime)

publish_metric "system/hostname"        "$HOSTNAME"
publish_metric "system/model"           "$MODEL"
publish_metric "system/target_platform" "$TARGET_PLATFORM"
publish_metric "system/architecture"    "$ARCHITECTURE"
publish_metric "system/version"         "$VERSION"
publish_metric "system/uptime"          "$UPTIME"

# ---------- CPU ----------
LOAD_AVG=$(awk '{print $1","$2","$3}' /proc/loadavg)
publish_metric "cpu/load" "load:$LOAD_AVG"

CPU_CORES=$(grep -c "^processor" /proc/cpuinfo)
LOAD_1MIN=$(awk '{print $1}' /proc/loadavg)
CPU_LOAD_PERCENT=$(awk -v load="$LOAD_1MIN" -v cores="$CPU_CORES" \
    'BEGIN {printf "%.0f", (load / cores) * 100}')
publish_metric "cpu/load_percent" "value:$CPU_LOAD_PERCENT"

# ---------- Memory ----------
MEMORY_FREE=$(awk '/MemFree/  {print $2}' /proc/meminfo)
MEMORY_CACHED=$(awk '/^Cached:/ {print $2}' /proc/meminfo)
MEMORY_USED=$(awk '/MemTotal/ {total=$2} /MemFree/ {free=$2} /Buffers/ {buffers=$2} /^Cached:/ {cached=$2} END {print total-free-buffers-cached}' /proc/meminfo)
MEMORY_TOTAL=$((MEMORY_USED + MEMORY_CACHED + MEMORY_FREE))

if [ "$MEMORY_TOTAL" -gt 0 ]; then
    MEMORY_USAGE_PERCENT=$((100 * (MEMORY_USED + MEMORY_CACHED) / MEMORY_TOTAL))
else
    MEMORY_USAGE_PERCENT=0
fi

publish_metric "memory/memory-free"          "value:$MEMORY_FREE"
publish_metric "memory/memory-cached"        "value:$MEMORY_CACHED"
publish_metric "memory/memory-used"          "value:$MEMORY_USED"
publish_metric "memory/memory-usage-percent" "value:$MEMORY_USAGE_PERCENT"

# ---------- Disk (overlay or full) ----------
if df -k | grep -q ":/overlay"; then
    DISK_STATS=$(df -k | awk '$6 == "/" {print $2, $3, $4}')
else
    DISK_STATS=$(df -k | awk 'NR>1 && $1 !~ /^(tmpfs|devtmpfs|none)$/ {t+=$2; u+=$3; a+=$4} END {print t, u, a}')
fi

DISK_TOTAL=$(echo "$DISK_STATS" | awk '{print $1}')
DISK_USED=$(echo "$DISK_STATS"  | awk '{print $2}')
DISK_FREE=$(echo "$DISK_STATS"  | awk '{print $3}')
DISK_PERCENT=$([ "$DISK_TOTAL" -gt 0 ] && echo $((100 * DISK_USED / DISK_TOTAL)) || echo 0)

publish_metric "disk/total"   "value:$DISK_TOTAL"
publish_metric "disk/used"    "value:$DISK_USED"
publish_metric "disk/free"    "value:$DISK_FREE"
publish_metric "disk/percent" "value:$DISK_PERCENT"

# ---------- Tmpfs (/tmp) ----------
TMP_STATS=$(df -k /tmp 2>/dev/null | awk 'NR==2 {print $2, $3, $4}')
if [ -n "$TMP_STATS" ]; then
    TMP_TOTAL=$(echo "$TMP_STATS" | awk '{print $1}')
    TMP_USED=$(echo "$TMP_STATS"  | awk '{print $2}')
    TMP_FREE=$(echo "$TMP_STATS"  | awk '{print $3}')
    TMP_PERCENT=$([ "$TMP_TOTAL" -gt 0 ] && echo $((100 * TMP_USED / TMP_TOTAL)) || echo 0)

    publish_metric "disk_tmp/total"   "value:$TMP_TOTAL"
    publish_metric "disk_tmp/used"    "value:$TMP_USED"
    publish_metric "disk_tmp/free"    "value:$TMP_FREE"
    publish_metric "disk_tmp/percent" "value:$TMP_PERCENT"
fi

# ---------- Connection tracking ----------
if [ -f /proc/net/nf_conntrack ]; then
    CONN_TOTAL=$(wc -l < /proc/net/nf_conntrack)
    publish_metric "conntrack/total" "value:$CONN_TOTAL"
fi

# ---------- Network interfaces ----------
for INTERFACE in $(ls /sys/class/net/ | grep -v lo); do
    RX_BYTES=$(cat "/sys/class/net/$INTERFACE/statistics/rx_bytes")
    TX_BYTES=$(cat "/sys/class/net/$INTERFACE/statistics/tx_bytes")
    RX_PACKETS=$(cat "/sys/class/net/$INTERFACE/statistics/rx_packets")
    TX_PACKETS=$(cat "/sys/class/net/$INTERFACE/statistics/tx_packets")
    RX_DROPPED=$(cat "/sys/class/net/$INTERFACE/statistics/rx_dropped")
    TX_DROPPED=$(cat "/sys/class/net/$INTERFACE/statistics/tx_dropped")
    RX_ERRORS=$(cat "/sys/class/net/$INTERFACE/statistics/rx_errors")
    TX_ERRORS=$(cat "/sys/class/net/$INTERFACE/statistics/tx_errors")

    publish_metric "interface-$INTERFACE/if_octets"  "rx:$RX_BYTES,tx:$TX_BYTES"
    publish_metric "interface-$INTERFACE/if_packets" "rx:$RX_PACKETS,tx:$TX_PACKETS"
    publish_metric "interface-$INTERFACE/if_dropped" "rx:$RX_DROPPED,tx:$TX_DROPPED"
    publish_metric "interface-$INTERFACE/if_errors"  "rx:$RX_ERRORS,tx:$TX_ERRORS"
done

# ---------- Per-device bandwidth (nlbwmon) ----------
publish_nlbw_devices() {
    [ "$ENABLE_NLBW" = "true" ] || return 0
    command -v nlbw >/dev/null 2>&1 && command -v jq >/dev/null 2>&1 || return 0

    # OpenWrt jq is often built without ONIGURUMA — no gsub/test/match. Slugify in shell.
    nlbw -c json -n 2>/dev/null | jq -r '
        .columns as $cols | .data as $rows |
        ($cols | index("mac")) as $mi |
        ($cols | index("ip")) as $ii |
        ($cols | index("rx_bytes")) as $rxi |
        ($cols | index("tx_bytes")) as $txi |
        if ($mi != null and $rxi != null and $txi != null) then
            $rows
            | map(select(.[$mi] != null and .[$mi] != "" and .[$mi] != "00:00:00"))
            | group_by(.[$mi])
            | .[]
            | [
                (.[0][$mi] | tostring),
                ((map(.[$ii] // empty) | map(select(. != "" and . != "00:00:00")) | .[0] // "") | tostring),
                (map(.[$rxi] // 0) | add),
                (map(.[$txi] // 0) | add)
              ]
            | @tsv
        else empty end
    ' | while IFS="$(printf '\t')" read -r mac ip rx tx; do
        [ -n "$mac" ] || continue
        [ -n "$rx" ] && [ -n "$tx" ] || continue
        slug=""
        if [ -n "$ip" ] && [ "$ip" != "0.0.0.0" ]; then
            slug=$(printf '%s' "$ip" | tr '[:upper:]' '[:lower:]' | tr -cd '0-9.' | tr '.' '_')
        fi
        if [ -z "$slug" ]; then
            slug=$(printf '%s' "$mac" | tr -d ':' | tr '[:upper:]' '[:lower:]' | tr -cd 'a-f0-9')
        fi
        slug=$(printf '%s' "$slug" | cut -c1-48)
        [ -n "$slug" ] || continue
        publish_metric "nlbw-$slug/if_octets" "rx:$rx,tx:$tx"
    done
}
publish_nlbw_devices
