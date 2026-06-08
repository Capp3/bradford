# AV Fleet Monitor – Docker Compose Stack

Prometheus + Grafana + Custom Python Exporter for:
- **4x Kiloview N5** NDI encoders
- **12x Kiloview N6** NDI encoders
- **2x Blackmagic Web Presenter HD/4K**

---

## Quick Start

```bash
# 1. Clone / copy this directory
# 2. Edit device IP addresses
nano config/devices.yml

# 3. Set a secure Grafana password
nano .env

# 4. Start the stack
docker compose up -d

# 5. Open Grafana
open http://localhost:3000
# Login: admin / (password from .env)
```

---

## Architecture

```
                  ┌──────────────────────────────────┐
                  │         Docker Network           │
                  │                                  │
  ┌──────────┐    │  ┌──────────────────┐            │
  │ Kiloview │◄───┼──│   av_exporter    │ :9200      │
  │ N5 × 4   │    │  │  (Python/Flask)  │            │
  └──────────┘    │  └────────┬─────────┘            │
  ┌──────────┐    │           │scrapes               │
  │ Kiloview │◄───┼───────────┤                      │
  │ N6 × 12  │    │  ┌────────▼─────────┐            │
  └──────────┘    │  │   prometheus     │ :9090      │
  ┌──────────┐    │  └────────┬─────────┘            │
  │ BM Web   │◄───┼───────────┤                      │
  │ Presenter│    │  ┌────────▼─────────┐            │
  └──────────┘    │  │    grafana       │ :3000      │
                  │  └──────────────────┘            │
                  └──────────────────────────────────┘
```

---

## Collected Metrics

| Metric | Description | Devices |
|--------|-------------|---------|
| `av_device_up` | 1=reachable, 0=down | All |
| `av_stream_active` | 1=streaming, 0=idle | All |
| `av_stream_bitrate_bps` | Live bitrate (bps) | All |
| `av_stream_status` | 0-4 state enum (BM only) | BM WP |
| `av_stream_duration_seconds` | Seconds on-air | BM WP |
| `av_stream_cache_percent` | Buffer cache % | BM WP |
| `av_ndi_active` | NDI output active | N5/N6 |
| `av_ndi_bitrate_bps` | NDI bitrate | N5/N6 |
| `av_video_input_locked` | Signal lock | N5/N6 |
| `av_video_input_format_info` | Format label | All |
| `av_device_cpu_usage_percent` | CPU % | N5/N6 |
| `av_device_mem_usage_percent` | Memory % | N5/N6 |
| `av_device_temperature_celsius` | Temperature °C | N5/N6 |
| `av_device_info` | Firmware/version label | BM WP |

---

## Kiloview API Notes

The N5/N6 use Kiloview's HTTP JSON API at `http://<ip>/api/`.
Authenticate with basic auth (default: `admin`/`admin`).

Key endpoints used:
- `GET /api/info/get.json` – device identity
- `GET /api/system/info.json` – CPU, memory, temperature
- `GET /api/streamer/list.json` – active stream list with state/bitrate
- `GET /api/ndi/status.json` – NDI output status
- `GET /api/video/status.json` – input signal lock

> **Note:** Exact endpoint paths vary slightly between firmware versions.
> Check `http://<ip>/api/info/nav.json` to enumerate available endpoints.
> The exporter handles missing endpoints gracefully (logs a warning, skips metric).

---

## Blackmagic Web Presenter API Notes

Requires firmware **3.4+** for REST API support.
Base URL: `http://<ip>/control/api/v1/`

Key endpoints used:
- `GET /system/product` – device name, firmware version
- `GET /system` – current video format
- `GET /livestreams/0` – stream status, bitrate, duration, cache

Full API documentation available from the device itself at:
`http://<ip>/control/documentation.html`

---

## Alerts

Pre-configured Prometheus alert rules in `prometheus/alerts/av_alerts.yml`:

| Alert | Condition | Severity |
|-------|-----------|----------|
| `AVDeviceDown` | Device unreachable >1 min | critical |
| `AVStreamNotActive` | Up but no stream >2 min | warning |
| `AVHighCPU` | CPU >90% for 5 min | warning |
| `AVHighTemperature` | Temp >75°C for 2 min | critical |
| `AVVideoNoSignal` | No signal lock >30s | warning |
| `AVBMPresenterInterrupted` | BM state=Interrupted | critical |

---

## Customisation

**Add more devices:** Edit `config/devices.yml` – the exporter reads it live.

**Change scrape interval:** Set `SCRAPE_INTERVAL` env var in `docker-compose.yml`.

**Add Alertmanager:** Uncomment the `alertmanagers` block in `prometheus/prometheus.yml`
and add a new service in `docker-compose.yml`.

**Persist config changes without restart:**
```bash
curl -X POST http://localhost:9090/-/reload
```
