#!/usr/bin/env python3
"""
AV Device Prometheus Exporter
Supports: Kiloview N5/N6 (HTTP JSON API), Blackmagic Web Presenter (REST API v1)
"""

import os
import time
import logging
import yaml
import requests
from prometheus_client import start_http_server, REGISTRY
from prometheus_client.core import GaugeMetricFamily, CounterMetricFamily

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger(__name__)

SCRAPE_INTERVAL = int(os.environ.get("SCRAPE_INTERVAL", 15))
EXPORTER_PORT   = int(os.environ.get("EXPORTER_PORT", 9200))
CONFIG_PATH     = os.environ.get("CONFIG_PATH", "/app/config/devices.yml")
REQUEST_TIMEOUT = 5


def load_config(path):
    with open(path) as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Kiloview helpers  (HTTP API base: http://<ip>/api/)
# ---------------------------------------------------------------------------

def kv_get(ip, endpoint, auth):
    try:
        r = requests.get(
            f"http://{ip}/api/{endpoint}",
            auth=auth, timeout=REQUEST_TIMEOUT
        )
        r.raise_for_status()
        data = r.json()
        if data.get("result") == "ok":
            return data.get("data", {})
    except Exception as e:
        log.warning("Kiloview %s /%s error: %s", ip, endpoint, e)
    return None


def collect_kiloview(device, model_label):
    """Return list of (metric_name, help, labels_dict, value) tuples."""
    ip    = device["ip"]
    auth  = (device.get("username", "admin"), device.get("password", "admin"))
    base_labels = {
        "device_id":   device["id"],
        "device_name": device["name"],
        "device_type": model_label,
        "ip":          ip,
    }
    results = []

    # -- Reachability --
    info = kv_get(ip, "info/get.json", auth)
    reachable = 1 if info is not None else 0
    results.append(("av_device_up", "Device is reachable (1=up, 0=down)", base_labels, reachable))
    if not reachable:
        return results

    # -- System info --
    sys_info = kv_get(ip, "system/info.json", auth) or {}
    if sys_info:
        if "cpuUsage" in sys_info:
            results.append(("av_device_cpu_usage_percent", "CPU usage %", base_labels, float(sys_info["cpuUsage"])))
        if "memUsage" in sys_info:
            results.append(("av_device_mem_usage_percent", "Memory usage %", base_labels, float(sys_info["memUsage"])))
        if "temperature" in sys_info:
            results.append(("av_device_temperature_celsius", "Device temperature (°C)", base_labels, float(sys_info["temperature"])))

    # -- Streaming status  (streamer/list.json → iterate active streams) --
    streams = kv_get(ip, "streamer/list.json", auth)
    if streams and isinstance(streams, list):
        for stream in streams:
            s_labels = {**base_labels, "stream_id": str(stream.get("id", "0")), "stream_name": stream.get("name", "")}
            state = 1 if str(stream.get("state", "")).lower() in ("running", "streaming", "1") else 0
            results.append(("av_stream_active", "Stream is active (1=running)", s_labels, state))
            if "bitrate" in stream:
                results.append(("av_stream_bitrate_bps", "Stream output bitrate (bps)", s_labels, float(stream["bitrate"])))

    # -- NDI status (N5/N6 specific) --
    ndi = kv_get(ip, "ndi/status.json", auth)
    if ndi:
        ndi_labels = {**base_labels}
        ndi_active = 1 if ndi.get("status", "") in ("running", "active", "1", 1) else 0
        results.append(("av_ndi_active", "NDI output is active", ndi_labels, ndi_active))
        if "bitrate" in ndi:
            results.append(("av_ndi_bitrate_bps", "NDI output bitrate (bps)", ndi_labels, float(ndi["bitrate"])))

    # -- Video input signal lock --
    video = kv_get(ip, "video/status.json", auth) or kv_get(ip, "source/status.json", auth)
    if video:
        locked = 1 if video.get("lock", video.get("signal", 0)) in (1, "1", "locked", True) else 0
        results.append(("av_video_input_locked", "Video input signal is locked", base_labels, locked))
        if "resolution" in video or "format" in video:
            fmt = video.get("resolution", video.get("format", ""))
            fmt_labels = {**base_labels, "format": str(fmt)}
            results.append(("av_video_input_format_info", "Video input format label", fmt_labels, 1))

    return results


# ---------------------------------------------------------------------------
# Blackmagic Web Presenter helpers  (REST API: http://<ip>/control/api/v1/)
# ---------------------------------------------------------------------------

def bm_get(ip, endpoint):
    try:
        r = requests.get(
            f"http://{ip}/control/api/v1/{endpoint}",
            timeout=REQUEST_TIMEOUT
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.warning("BlackMagic %s /%s error: %s", ip, endpoint, e)
    return None


# Livestream status string → numeric
BM_STATUS_MAP = {
    "Idle": 0,
    "Connecting": 1,
    "Streaming": 2,
    "Flushing": 3,
    "Interrupted": 4,
}


def collect_blackmagic(device):
    ip = device["ip"]
    base_labels = {
        "device_id":   device["id"],
        "device_name": device["name"],
        "device_type": "blackmagic_web_presenter",
        "ip":          ip,
    }
    results = []

    # -- Reachability via product endpoint --
    product = bm_get(ip, "system/product")
    reachable = 1 if product is not None else 0
    results.append(("av_device_up", "Device is reachable (1=up, 0=down)", base_labels, reachable))
    if not reachable:
        return results

    if product:
        fw_labels = {**base_labels, "software_version": product.get("softwareVersion", ""), "product_name": product.get("productName", "")}
        results.append(("av_device_info", "Device firmware/product info label", fw_labels, 1))

    # -- System video format --
    sys = bm_get(ip, "system")
    if sys and "videoFormat" in sys:
        vf = sys["videoFormat"]
        vf_labels = {**base_labels, "format": vf.get("name", ""), "frame_rate": str(vf.get("frameRate", ""))}
        results.append(("av_video_input_format_info", "Current video input format", vf_labels, 1))
        results.append(("av_video_input_height", "Video input height (px)", base_labels, float(vf.get("height", 0))))
        results.append(("av_video_input_width",  "Video input width (px)",  base_labels, float(vf.get("width", 0))))

    # -- Livestream status --
    ls = bm_get(ip, "livestreams/0")
    if ls:
        status_str = ls.get("status", "Idle")
        status_num = BM_STATUS_MAP.get(status_str, -1)
        s_labels = {**base_labels, "stream_status": status_str}
        results.append(("av_stream_status", "Livestream state (0=Idle,1=Connecting,2=Streaming,3=Flushing,4=Interrupted)", s_labels, status_num))
        results.append(("av_stream_active", "Stream is active (1=Streaming)", base_labels, 1 if status_str == "Streaming" else 0))

        bitrate = ls.get("bitrate", 0)
        results.append(("av_stream_bitrate_bps", "Current livestream bitrate (bps)", base_labels, float(bitrate)))

        if "duration" in ls:
            results.append(("av_stream_duration_seconds", "Current stream duration (s)", base_labels, float(ls["duration"])))

        if "cache" in ls:
            results.append(("av_stream_cache_percent", "Livestream buffer cache usage %", base_labels, float(ls["cache"])))

        fmt_labels = {**base_labels, "format": ls.get("effectiveVideoFormat", "")}
        results.append(("av_stream_effective_format_info", "Effective video format being streamed", fmt_labels, 1))

    return results


# ---------------------------------------------------------------------------
# Prometheus Collector
# ---------------------------------------------------------------------------

class AVCollector:
    def __init__(self, config_path):
        self.config_path = config_path

    def collect(self):
        cfg = load_config(self.config_path)

        # Aggregate all samples into metric families keyed by metric name
        families: dict[str, GaugeMetricFamily] = {}

        def add(name, helptext, labels, value):
            if name not in families:
                families[name] = GaugeMetricFamily(name, helptext, labels=list(labels.keys()))
            families[name].add_metric(list(labels.values()), value)

        # Kiloview N5
        for dev in cfg.get("kiloview_n5", []):
            for name, helptext, labels, value in collect_kiloview(dev, "kiloview_n5"):
                add(name, helptext, labels, value)

        # Kiloview N6
        for dev in cfg.get("kiloview_n6", []):
            for name, helptext, labels, value in collect_kiloview(dev, "kiloview_n6"):
                add(name, helptext, labels, value)

        # Blackmagic Web Presenter
        for dev in cfg.get("blackmagic_web_presenter", []):
            for name, helptext, labels, value in collect_blackmagic(dev):
                add(name, helptext, labels, value)

        yield from families.values()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    log.info("Starting AV Exporter on port %d", EXPORTER_PORT)
    REGISTRY.register(AVCollector(CONFIG_PATH))
    start_http_server(EXPORTER_PORT)
    log.info("Exporter running. Ctrl+C to stop.")
    while True:
        time.sleep(SCRAPE_INTERVAL)
