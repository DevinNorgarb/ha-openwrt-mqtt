# OpenWrt MQTT Auto-Discovery for Home Assistant

<img src="https://raw.githubusercontent.com/aldweb/ha-openwrt-mqtt/master/images/openwrt-one-router.png" align="left" width="300" style="margin-right: 20px; margin-bottom: 20px;">
A comprehensive monitoring solution that brings your OpenWrt router metrics into Home Assistant through MQTT auto-discovery.
<br clear="all" />

## Overview

This is a two-part project that enables seamless monitoring of OpenWrt routers in Home Assistant:

1. **OpenWrt Script** - A lightweight shell script that collects and publishes router metrics to your MQTT broker
2. **Home Assistant Integration** - A custom integration that automatically discovers and creates sensors for your OpenWrt devices

### Why This Approach?

**Security-First Design**: Unlike other router monitoring solutions, this project offers a significant security advantage - **Home Assistant never needs to connect to your router**. The router pushes its metrics to the MQTT broker, which means:

- ✅ No router credentials (username/password) stored in Home Assistant
- ✅ No SSH/web access required from Home Assistant to your router
- ✅ No open ports or services exposed on your router for Home Assistant
- ✅ One-way communication: router → MQTT broker ← Home Assistant
- ✅ Router remains isolated and secure in your network

This is a **critical security benefit** for routers, which are the gateway to your entire network. By eliminating the need for Home Assistant to authenticate to your router, you significantly reduce your attack surface and potential security risks.

## Features

### Router Metrics

The integration monitors the following metrics from your OpenWrt router:

- **System Information**
  - Hostname
  - Model
  - Target platform
  - Architecture
  - OpenWrt version
  - Uptime

- **CPU**
  - Load average (1-minute, 5-minute, 15-minute)
  - Load percentage (based on number of cores)
  - Temperature

- **Memory Usage**
  - Free memory
  - Cached memory
  - Used memory

- **Disk Space**
  - Total disk space
  - Used disk space
  - Free disk space
  - Usage percentage

- **Temporary Storage (tmpfs)**
  - Total tmpfs space
  - Used tmpfs space
  - Free tmpfs space
  - Usage percentage

- **Network**
  - Active connections (connection tracking)

- **Network Interfaces** (for each interface)
  - RX/TX bytes (total and rate)
  - RX/TX packets (total and rate)
  - RX/TX errors (total and rate)
  - RX/TX dropped packets (total and rate)

All network metrics include both cumulative counters and automatically calculated rates (per second).

## Publishing Methods

The OpenWrt script supports two methods for publishing metrics to your MQTT broker:

### Method 1: Native MQTT (`mqtt`)

**Recommended for most users.** Uses the standard MQTT protocol via `mosquitto_pub`.

**Advantages:**
- âœ… Direct connection to MQTT broker
- âœ… Lower latency
- âœ… More efficient (lightweight protocol)
- âœ… Works with any MQTT broker
- âœ… Standard MQTT features (QoS, retain, etc.)

**Requirements:**
- MQTT broker accessible from OpenWrt router
- `mosquitto-client` package (installed automatically)

**Use case:** You have a dedicated MQTT broker (like Mosquitto) accessible on your network.

### Method 2: HTTP via Home Assistant REST API (`http`)

Uses Home Assistant's MQTT REST API endpoint to publish messages.

**Advantages:**
- âœ… No direct MQTT broker access needed from router
- âœ… Uses Home Assistant as a proxy to MQTT
- âœ… Useful when MQTT broker is not directly accessible

**Requirements:**
- Home Assistant accessible from OpenWrt router
- Long-Lived Access Token from Home Assistant
- `curl` package (installed automatically)

**Use case:** Your MQTT broker is not directly accessible from the router, but Home Assistant is (e.g., Home Assistant Cloud setup, or firewall restrictions).

**Note:** This method requires Home Assistant to relay messages to the MQTT broker, adding a slight overhead compared to the native MQTT method.

## Installation

### Part 1: OpenWrt Router Setup

#### Prerequisites

- OpenWrt router with internet access
- SSH access to your router
- MQTT broker (e.g., Mosquitto) already set up and accessible from your router

#### Installation Steps

1. **Connect to your OpenWrt router via SSH:**
   ```bash
   ssh root@<your-router-ip>
   ```

2. **Download the setup script:**
   ```bash
   wget https://raw.githubusercontent.com/aldweb/ha-openwrt-mqtt/main/setup_metrics.sh -O /tmp/setup_metrics.sh
   chmod +x /tmp/setup_metrics.sh
   ```

3. **Configure publishing method and MQTT settings:**
   
   Before running the setup script, edit it to choose your publishing method and configure your MQTT broker details:
   ```bash
   vi /tmp/setup_metrics.sh
   ```
   
   **Choose your publishing method:**
   ```bash
   PUBLISH_METHOD="mqtt"    # or "http"
   ```
   
   - **`mqtt`** (default): Uses native MQTT protocol via `mosquitto_pub` (installed automatically via opkg)
   - **`http`**: Uses Home Assistant's MQTT REST API (requires `curl`, installed automatically via opkg)
   
   **For native MQTT method (`mqtt`)**, update these variables:
   ```bash
   MQTT_BROKER="<mqtt_broker_ip>"        # Your MQTT broker IP address
   MQTT_PORT="<mqtt_port>"                # MQTT port (usually 1883)
   MQTT_USER="<mqtt_user>"                # MQTT username
   MQTT_PASSWORD="<mqtt_password>"        # MQTT password
   ```
   
   **For HTTP/Home Assistant method (`http`)**, update these variables:
   ```bash
   HA_URL="<ha_url>"                      # e.g. http://homeassistant.local
   HA_PORT="<ha_port>"                    # e.g. 8123
   HA_TOKEN="<ha_token>"                  # Long-Lived Access Token from HA
   ```
   
   Save and exit (`:wq` in vi).
   
   **Alternative**: You can also run the setup script first and then edit `/usr/bin/publish_metrics.sh` afterwards to configure these settings.

4. **Run the setup script:**
   ```bash
   /tmp/setup_metrics.sh
   ```

5. **Test the script manually:**
   ```bash
   /usr/bin/publish_metrics.sh
   ```
   
   Check your MQTT broker to verify that messages are being published under the `openwrt/<hostname>/` topic.

6. **The script is automatically scheduled to run every 5 minutes via cron.**

#### What the Setup Script Does

The setup script automatically configures your OpenWrt router based on the chosen publishing method:

**For `mqtt` method:**
- Installs `mosquitto-client` (mosquitto_pub) if not already present
- Intelligently handles SSL and non-SSL mosquitto library dependencies

**For `http` method:**
- Installs `curl` if not already present

**For both methods:**
- Creates `/usr/bin/publish_metrics.sh` configured with your chosen method to collect and publish metrics
- Adds a cron job to run the script every 5 minutes

### Part 2: Home Assistant Integration

#### Prerequisites

- Home Assistant with MQTT integration configured
- MQTT broker accessible from Home Assistant

#### Installation Methods

Choose one of the following installation methods:

##### Option 1: Install via HACS (Recommended)

1. **Ensure HACS is installed:**
   - If you don't have HACS yet, visit [https://hacs.xyz/](https://hacs.xyz/) for installation instructions

2. **Add this repository to HACS:**
   - Open HACS in Home Assistant
   - Click on "Integrations"
   - Click the three dots (⋮) in the top right corner
   - Select "Custom repositories"
   - Add the repository URL: `https://github.com/aldweb/ha-openwrt-mqtt`
   - Select category: "Integration"
   - Click "Add"

3. **Install the integration:**
   - Search for "OpenWrt MQTT Auto-Discovery" in HACS
   - Click "Download"
   - Restart Home Assistant

4. **Configure the integration:**
   - Go to Settings → Devices & Services
   - Click "+ Add Integration"
   - Search for "OpenWrt MQTT Auto-Discovery"
   - Configure the MQTT topic prefix:
     - Use `openwrt/+/` for multiple devices (+ is a wildcard for any hostname)
     - Use `openwrt/hostname/` for a single specific device

5. **Sensors will be automatically discovered** as MQTT messages arrive from your OpenWrt router.

##### Option 2: Manual Installation

1. **Download the integration:**
   
   Copy the `openwrt_mqtt` folder to your Home Assistant `custom_components` directory:
   ```
   custom_components/
   └── openwrt_mqtt/
       ├── __init__.py
       ├── config_flow.py
       ├── const.py
       ├── manifest.json
       └── sensor.py
       └── strings.json
       └── translations/
          └── en.json
   ```

   You can download the files from the [GitHub repository](https://github.com/aldweb/ha-openwrt-mqtt).

2. **Restart Home Assistant**

3. **Add the integration:**
   - Go to Settings → Devices & Services
   - Click "+ Add Integration"
   - Search for "OpenWrt MQTT Auto-Discovery"
   - Configure the MQTT topic prefix:
     - Use `openwrt/+/` for multiple devices (+ is a wildcard for any hostname)
     - Use `openwrt/hostname/` for a single specific device

4. **Sensors will be automatically discovered** as MQTT messages arrive from your OpenWrt router.

## Configuration

### Topic Prefix

The topic prefix determines which MQTT topics the integration will monitor:

- **Multiple devices**: `openwrt/+/` - Automatically discovers all devices publishing to `openwrt/<any-hostname>/`
- **Single device**: `openwrt/myhostname/` - Only discovers the specific hostname
- **Custom prefix**: You can change `openwrt` to any prefix you prefer, just ensure it matches in both the OpenWrt script and the Home Assistant integration

### MQTT Topic Structure

Metrics are published to the following topic structure:
```
<topic_prefix>/<hostname>/<metric_type>/<metric_name>
```

Examples:
- `openwrt/myrouter/system/hostname`
- `openwrt/myrouter/cpu/load`
- `openwrt/myrouter/cpu/load_percent`
- `openwrt/myrouter/memory/memory-free`
- `openwrt/myrouter/disk/total`
- `openwrt/myrouter/disk_tmp/used`
- `openwrt/myrouter/conntrack/total`
- `openwrt/myrouter/interface-eth0/if_octets`

## Sensor Naming

All sensors are automatically named with the hostname prefix for easy identification:

- `<hostname> CPU Load 1min`, `<hostname> CPU Load 5min`, `<hostname> CPU Load 15min`
- `<hostname> CPU Load %`
- `<hostname> Memory Free`, `<hostname> Memory Used`, `<hostname> Memory Cached`
- `<hostname> Disk Total`, `<hostname> Disk Used`, `<hostname> Disk Free`, `<hostname> Disk Usage`
- `<hostname> Temp Disk Total`, `<hostname> Temp Disk Used`, `<hostname> Temp Disk Free`, `<hostname> Temp Disk Usage`
- `<hostname> Active Connections`
- `<hostname> eth0 RX` (bytes total)
- `<hostname> eth0 RX Rate` (bytes/s)
- `<hostname> System Uptime`

## Data Format

The OpenWrt script publishes data in the following formats:

- **CPU Load**: `load:1.23,4.56,7.89` (1min, 5min, 15min)
- **CPU Load %**: `value:75` (percentage)
- **Memory**: `value:123456` (in KB)
- **Disk**: `value:123456` (in KB for space metrics, percentage for usage)
- **Disk Tmp**: `value:123456` (in KB for space metrics, percentage for usage)
- **Connections**: `value:1234` (number of active connections)
- **Network**: `rx:123456,tx:789012` (in bytes, packets, errors, or dropped)
- **System info**: Plain text values
- **Uptime**: Seconds as integer

## Troubleshooting

### No sensors appearing in Home Assistant

1. Verify MQTT messages are being published:
   - Use an MQTT client (like MQTT Explorer) to check for messages under your topic prefix
   - Run the OpenWrt script manually: `/usr/bin/publish_metrics.sh`

2. Check Home Assistant logs for errors:
   - Settings → System → Logs
   - Look for entries related to `openwrt_mqtt`

3. Verify MQTT integration is working in Home Assistant:
   - Settings → Devices & Services → MQTT

### Sensors show "Unknown" or "Unavailable"

- Wait for the next scheduled run (every 5 minutes)
- Check MQTT broker connectivity from both OpenWrt and Home Assistant
- Verify the topic prefix configuration matches in both parts

### Script not running on OpenWrt

1. Check cron is running:
   ```bash
   /etc/init.d/cron status
   /etc/init.d/cron start
   /etc/init.d/cron enable
   ```

2. Verify cron job is configured:
   ```bash
   crontab -l
   ```

3. Check script permissions:
   ```bash
   ls -l /usr/bin/publish_metrics.sh
   ```

## Customization

### Change Publishing Frequency

Edit the cron job on your OpenWrt router:
```bash
crontab -e
```

Modify the schedule (default is `*/5 * * * *` for every 5 minutes).

### Add Custom Metrics

Edit `/usr/bin/publish_metrics.sh` on your OpenWrt router to add additional metrics using the `publish_metric` function:

```bash
publish_metric "custom/my-metric" "value:123"
```

Then add the corresponding topic to `const.py` in the Home Assistant integration:
```python
DISCOVERY_TOPICS = [
    # ... existing topics ...
    "custom/my-metric",
]
```

### Potential Additional Metrics

The OpenWrt script can be easily extended to monitor many other useful metrics. Here are some examples that could be added:

**Hardware & Temperature**
- CPU / SoC temperature

**Network & Connectivity**
- WAN IP address
- Internet connection status (ping test)
- Wi-Fi statistics (connected clients, signal strength, channel utilization)

**System Performance**
- Per-core CPU usage
- Disk I/O statistics

**Services & Security**
- Firewall status
- Individual service status (dnsmasq, firewall, etc.)
- Active DHCP leases
- VPN connection status
- DNS query statistics

**Example - Adding CPU Temperature:**

In `/usr/bin/publish_metrics.sh`, add:
```bash
# CPU Temperature (if available)
if [ -f /sys/class/thermal/thermal_zone0/temp ]; then
    TEMP=$(cat /sys/class/thermal/thermal_zone0/temp)
    TEMP_C=$((TEMP / 1000))
    publish_metric "thermal/cpu_temp" "value:$TEMP_C"
fi
```

In Home Assistant's `const.py`:
```python
DISCOVERY_TOPICS = [
    # ... existing topics ...
    "thermal/cpu_temp",
]
```

The modular design makes it simple to extend the monitoring capabilities to suit your specific needs!

## Requirements

### OpenWrt Router
- OpenWrt 19.07 or newer (tested on recent versions)
- Minimum 8MB flash / 64MB RAM (typical for most routers)
- Internet access for package installation
- **For `mqtt` method:** mosquitto-client package (installed automatically by setup script)
- **For `http` method:** curl package (installed automatically by setup script)

### Home Assistant
- Home Assistant 2023.1 or newer
- MQTT integration configured
- MQTT broker (Mosquitto recommended)

## Use with Other Linux-Based Routers

While this project was primarily designed for OpenWrt, it can be easily adapted for other Linux-based routers with little to no modification, depending on their configuration and available commands. The main requirements are:

- Shell script support (sh/bash)
- Access to `/proc` filesystem for system metrics
- `mosquitto_pub` or similar MQTT client
- Cron for scheduling (or alternative task scheduler)

Key areas that may need adaptation:
- System information paths (adjust paths in the script based on your router's filesystem)
- Package management commands (replace `opkg` with your router's package manager)
- Configuration storage (replace `uci` commands if your router uses different configuration)

## License

This project is released under the MIT License.

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

## Credits

Developed by @aldweb

## Support

For issues, questions, or feature requests, please visit:
https://github.com/aldweb/ha-openwrt-mqtt/issues
