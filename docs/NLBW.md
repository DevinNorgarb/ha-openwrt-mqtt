# Per-device bandwidth (nlbwmon)

This extends [ha-openwrt-mqtt](../README.md) with **per-host** download/upload counters from OpenWrt **nlbwmon** (`luci-app-nlbwmon`), published over the same MQTT prefix as interface stats.

## What you get in Home Assistant

For each LAN client seen by nlbwmon, the integration auto-creates (under your OpenWrt router device):

| Sensor | Meaning |
|--------|---------|
| `… <host> RX` | Cumulative download bytes (period totals from nlbw) |
| `… <host> TX` | Cumulative upload bytes |
| `… <host> RX Rate` | Live download speed (B/s, computed in HA) |
| `… <host> TX Rate` | Live upload speed |

MQTT topics look like:

```text
openwrt/<router-hostname>/nlbw-192_168_1_42/if_octets
payload: rx:123456789,tx:9876543
```

The slug (`192_168_1_42` or MAC-based) comes from DHCP hostname or IP; friendly names use the slug with `.` for underscores.

## Router setup

1. **Update** `openwrt/setup_metrics.sh` on the router (or re-download from this repo).
2. Set `ENABLE_NLBW="true"` (default in current script).
3. Configure MQTT the same as existing metrics (`PUBLISH_METHOD`, broker, credentials).
4. Run the setup script (MQTT credentials live in `/etc/openwrt-metrics.env`, not inside the script):

   ```sh
   sh /tmp/setup_metrics.sh
   ```

   First run only: edit `/etc/openwrt-metrics.env` if placeholders were written. Re-runs do **not** overwrite that file.

5. **LuCI check:** Status → **Bandwidth Monitor** — confirm hosts appear after some LAN traffic.
6. **CLI check:**

   ```sh
   nlbw -c json -n | jq -r '.columns, (.data | length)'
   /usr/bin/publish_metrics.sh
   mosquitto_sub -h <broker> -t 'openwrt/+/nlbw-+/if_octets' -v
   ```

### Packages installed

- `nlbwmon` — accounting daemon
- `luci-app-nlbwmon` — UI (optional but useful)
- `jq` — parses `nlbw -c json` for the publish script

Set `ENABLE_NLBW="false"` before running setup if you only want interface-level stats.

## Home Assistant setup

1. **Update** the `openwrt_mqtt` custom component (includes `nlbw-+/if_octets` discovery).
2. **Reload** the integration: Settings → Devices & services → OpenWrt MQTT → Reload.
3. Wait for the next cron run (every 5 minutes) or run `/usr/bin/publish_metrics.sh` on the router.
4. New entities appear under the same OpenWrt router device; filter entities with `nlbw` in the entity id.

### Dashboard ideas

- **History graph** — top devices by `RX` / `TX` totals (period resets when nlbw rolls the database).
- **Gauge or sensor card** — `RX Rate` / `TX Rate` for a known host (phone, TV, HA box).
- **Statistics graph** — daily usage after a few days of history.

Combine with WAN interface sensors (`pppoe-wan`, `wan_download_mbit_s`) for “whole line vs one device.”

## Notes

- **nlbwmon** attributes traffic to **LAN hosts** (IP/MAC); WAN interface counters can differ slightly from vnStat/nlbw totals.
- Counters are **per accounting period** (default often daily); when the period rolls, values jump down — rate sensors handle resets.
- **Privacy:** every tracked DHCP client gets sensors; disable with `ENABLE_NLBW="false"` or restrict nlbwmon in LuCI.
- **vnStat** remains better for long-term *interface* history; use nlbw for *who* used the data.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| No `nlbw-*` entities | Run `nlbw -c show` on router; generate traffic; check `jq` installed |
| Empty MQTT | `ENABLE_NLBW=true` in `/usr/bin/publish_metrics.sh`; re-run setup script |
| Wrong host names | Set static DHCP hostnames in OpenWrt; slug uses hostname when present |
| `Cannot index array with string "mac"` | Old jq expected objects; update script from `main` (uses `columns` + `data` rows) |
| JSON parse errors | Run `nlbw -c json -n \| jq '.columns'` and confirm `mac`, `rx_bytes`, `tx_bytes` exist |
