#!/bin/sh

# ============================================================
# FIRST RUN ONLY: defaults below are written to /etc/openwrt-metrics.env
# Re-runs keep that file — you never re-enter MQTT details in this script.
#
# Ongoing edits: vi /etc/openwrt-metrics.env
# ============================================================
ENV_FILE="/etc/openwrt-metrics.env"
GITHUB_RAW="https://github.com/DevinNorgarb/ha-openwrt-mqtt/raw/main/openwrt"

PUBLISH_METHOD="mqtt"
MQTT_BROKER="<mqtt_broker_ip>"
MQTT_PORT="1883"
MQTT_USER="<mqtt_user>"
MQTT_PASSWORD="<mqtt_password>"
HA_URL="<ha_url>"
HA_PORT="8123"
HA_TOKEN="<ha_token>"
MQTT_TOPIC_PREFIX="openwrt"
ENABLE_NLBW="true"

# ============================================================

get_legacy_kv() {
    grep "^$1=" /usr/bin/publish_metrics.sh 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"'
}

write_env_file() {
    cat > "$ENV_FILE" << EOF
# OpenWrt MQTT metrics — edited by setup_metrics.sh or by you
PUBLISH_METHOD="$PUBLISH_METHOD"
MQTT_BROKER="$MQTT_BROKER"
MQTT_PORT="$MQTT_PORT"
MQTT_USER="$MQTT_USER"
MQTT_PASSWORD="$MQTT_PASSWORD"
HA_URL="$HA_URL"
HA_PORT="$HA_PORT"
HA_TOKEN="$HA_TOKEN"
MQTT_TOPIC_PREFIX="$MQTT_TOPIC_PREFIX"
ENABLE_NLBW="$ENABLE_NLBW"
EOF
    chmod 600 "$ENV_FILE"
}

load_or_create_config() {
    if [ -f "$ENV_FILE" ]; then
        # shellcheck disable=SC1090
        . "$ENV_FILE"
        echo "Using existing $ENV_FILE (unchanged)."
        return 0
    fi

    if [ -f /usr/bin/publish_metrics.sh ]; then
        _b=$(get_legacy_kv MQTT_BROKER)
        if [ -n "$_b" ] && [ "$_b" != "<mqtt_broker_ip>" ]; then
            PUBLISH_METHOD=$(get_legacy_kv PUBLISH_METHOD); PUBLISH_METHOD=${PUBLISH_METHOD:-mqtt}
            MQTT_BROKER="$_b"
            MQTT_PORT=$(get_legacy_kv MQTT_PORT); MQTT_PORT=${MQTT_PORT:-1883}
            MQTT_USER=$(get_legacy_kv MQTT_USER)
            MQTT_PASSWORD=$(get_legacy_kv MQTT_PASSWORD)
            HA_URL=$(get_legacy_kv HA_URL)
            HA_PORT=$(get_legacy_kv HA_PORT); HA_PORT=${HA_PORT:-8123}
            HA_TOKEN=$(get_legacy_kv HA_TOKEN)
            MQTT_TOPIC_PREFIX=$(get_legacy_kv MQTT_TOPIC_PREFIX); MQTT_TOPIC_PREFIX=${MQTT_TOPIC_PREFIX:-openwrt}
            ENABLE_NLBW=$(get_legacy_kv ENABLE_NLBW); ENABLE_NLBW=${ENABLE_NLBW:-true}
            write_env_file
            echo "Migrated MQTT settings from old publish_metrics.sh → $ENV_FILE"
            return 0
        fi
    fi

    write_env_file
    echo "Created $ENV_FILE — set MQTT_BROKER and credentials there, then re-run if needed."
}

load_or_create_config

# ---------- Install dependencies ----------

detect_pkg_manager() {
    if command -v opkg >/dev/null 2>&1; then
        echo "opkg"
        return 0
    fi
    if command -v apk >/dev/null 2>&1; then
        echo "apk"
        return 0
    fi
    return 1
}

pkg_update() {
    case "$PKG_MGR" in
        opkg) opkg update ;;
        apk) : ;; # apk doesn't need update when using --no-cache
        *) return 1 ;;
    esac
}

pkg_is_installed() {
    # usage: pkg_is_installed <package>
    case "$PKG_MGR" in
        opkg) opkg list-installed 2>/dev/null | grep -q "^$1 " ;;
        apk) apk info -e "$1" >/dev/null 2>&1 ;;
        *) return 1 ;;
    esac
}

pkg_install() {
    # usage: pkg_install <packages...>
    case "$PKG_MGR" in
        opkg) opkg install "$@" ;;
        apk) apk add --no-cache "$@" ;;
        *) return 1 ;;
    esac
}

apk_has_package() {
    # usage: apk_has_package <package>
    # `apk info -e` only works for installed packages; we need to query repositories.
    apk search -q -x "$1" >/dev/null 2>&1
}

PKG_MGR="$(detect_pkg_manager)" || {
    echo "Error: no supported package manager found (need opkg or apk)."
    exit 1
}

if [ "$PUBLISH_METHOD" = "mqtt" ]; then
    if ! command -v mosquitto_pub > /dev/null 2>&1; then
        echo "Installing mosquitto_pub using $PKG_MGR..."
        pkg_update

        if [ "$PKG_MGR" = "opkg" ]; then
            if pkg_is_installed "libmosquitto-ssl"; then
                echo "libmosquitto-ssl is already installed, installing mosquitto-client-ssl..."
                pkg_install mosquitto-client-ssl
            elif pkg_is_installed "libmosquitto-nossl"; then
                echo "libmosquitto-nossl is already installed, installing mosquitto-client-nossl..."
                pkg_install mosquitto-client-nossl
            else
                echo "Installing libmosquitto-nossl and mosquitto-client-nossl..."
                pkg_install libmosquitto-nossl mosquitto-client-nossl
            fi
        else
            # OpenWrt apk feeds typically expose mosquitto-client-{ssl,nossl}
            if apk_has_package "mosquitto-client-ssl"; then
                pkg_install mosquitto-client-ssl || { echo "Error: mosquitto-client-ssl installation failed."; exit 1; }
            elif apk_has_package "mosquitto-client-nossl"; then
                pkg_install mosquitto-client-nossl || { echo "Error: mosquitto-client-nossl installation failed."; exit 1; }
            else
                echo "Error: no mosquitto_pub package found via apk (expected mosquitto-client-ssl or mosquitto-client-nossl)."
                exit 1
            fi
        fi
    else
        echo "mosquitto_pub is already installed."
    fi

    if ! command -v mosquitto_pub > /dev/null 2>&1; then
        echo "Error: mosquitto_pub is not installed."
        exit 1
    fi

elif [ "$PUBLISH_METHOD" = "http" ]; then
    if ! command -v curl > /dev/null 2>&1; then
        echo "curl not found, installing using $PKG_MGR..."
        pkg_update
        pkg_install curl || { echo "Error: curl installation failed."; exit 1; }
    else
        echo "curl is already installed."
    fi

else
    echo "Error: PUBLISH_METHOD must be 'mqtt' or 'http'."
    exit 1
fi

# ---------- Optional: nlbwmon (per-device bandwidth) ----------
if [ "$ENABLE_NLBW" = "true" ]; then
    echo "Installing nlbwmon for per-device bandwidth..."
    pkg_update
    if [ "$PKG_MGR" = "opkg" ]; then
        pkg_install nlbwmon luci-app-nlbwmon jq || pkg_install nlbwmon jq
    else
        pkg_install nlbwmon jq || pkg_install nlbwmon
    fi
    if [ -x /etc/init.d/nlbwmon ]; then
        /etc/init.d/nlbwmon enable 2>/dev/null
        /etc/init.d/nlbwmon start 2>/dev/null
    fi
    if ! command -v nlbw >/dev/null 2>&1; then
        echo "Warning: nlbw CLI not found; per-device stats will be skipped."
        ENABLE_NLBW="false"
    elif ! command -v jq >/dev/null 2>&1; then
        echo "Warning: jq not found; install jq for per-device nlbw export."
        ENABLE_NLBW="false"
    fi
fi

# ---------- Install publish script (no heredoc — jq stays intact) ----------
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
PUBLISH_DEST="/usr/bin/publish_metrics.sh"

if [ -f "$SCRIPT_DIR/publish_metrics.sh" ]; then
    cp "$SCRIPT_DIR/publish_metrics.sh" "$PUBLISH_DEST"
    echo "Installed publish_metrics.sh from $SCRIPT_DIR"
elif wget -q -O "$PUBLISH_DEST" "$GITHUB_RAW/publish_metrics.sh"; then
    echo "Installed publish_metrics.sh from GitHub"
else
    echo "Error: could not install publish_metrics.sh (wget failed, no local copy)."
    echo "Download: $GITHUB_RAW/publish_metrics.sh"
    exit 1
fi
chmod +x "$PUBLISH_DEST"

echo "publish_metrics.sh ready (config: $ENV_FILE, method: $PUBLISH_METHOD)"

# Schedule the script to run every 5 minutes
(crontab -l 2>/dev/null | grep -v "publish_metrics.sh"; echo "*/5 * * * * /usr/bin/publish_metrics.sh") | crontab -

echo "Cron job configured. Done."
