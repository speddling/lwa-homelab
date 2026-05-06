#!/usr/bin/env python3
"""
T-Mobile FAST 5688W Prometheus Exporter
Scrapes the unauthenticated local gateway API and exposes metrics for Prometheus.
"""

import time
import logging
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler

GATEWAY_URL = "http://192.168.12.1/TMI/v1/gateway?get=all"
METRICS_PORT = 9719
SCRAPE_INTERVAL = 30

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

latest_metrics = ""


def fetch_gateway_data():
    try:
        r = requests.get(GATEWAY_URL, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.error(f"Failed to fetch gateway data: {e}")
        return None


def build_metrics(data):
    if not data:
        return "# ERROR: Could not fetch gateway data\n"

    lines = []

    def gauge(name, help_text, value, labels=""):
        label_str = f"{{{labels}}}" if labels else ""
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} gauge")
        lines.append(f"{name}{label_str} {value}")

    # Signal — 4G
    sig4g = data.get("signal", {}).get("4g", {})
    bands_4g = sig4g.get("bands", [])
    band_4g_str = bands_4g[0].upper() if bands_4g else "unknown"

    gauge("tmobile_4g_rsrp_dbm", "4G Reference Signal Received Power (dBm)", sig4g.get("rsrp", 0), f'band="{band_4g_str}"')
    gauge("tmobile_4g_rsrq_db", "4G Reference Signal Received Quality (dB)", sig4g.get("rsrq", 0), f'band="{band_4g_str}"')
    gauge("tmobile_4g_rssi_dbm", "4G Received Signal Strength Indicator (dBm)", sig4g.get("rssi", 0), f'band="{band_4g_str}"')
    gauge("tmobile_4g_sinr_db", "4G Signal to Interference plus Noise Ratio (dB)", sig4g.get("sinr", 0), f'band="{band_4g_str}"')
    gauge("tmobile_4g_bars", "4G signal bars (0-5)", sig4g.get("bars", 0), f'band="{band_4g_str}"')
    gauge("tmobile_4g_cid", "4G Cell ID", sig4g.get("cid", 0))
    gauge("tmobile_4g_enbid", "4G eNodeB ID", sig4g.get("eNBID", 0))

    # Signal — 5G (optional, may not be present)
    sig5g = data.get("signal", {}).get("5g", {})
    if sig5g:
        bands_5g = sig5g.get("bands", [])
        band_5g_str = bands_5g[0].upper() if bands_5g else "unknown"
        gauge("tmobile_5g_rsrp_dbm", "5G Reference Signal Received Power (dBm)", sig5g.get("rsrp", 0), f'band="{band_5g_str}"')
        gauge("tmobile_5g_rsrq_db", "5G Reference Signal Received Quality (dB)", sig5g.get("rsrq", 0), f'band="{band_5g_str}"')
        gauge("tmobile_5g_rssi_dbm", "5G Received Signal Strength Indicator (dBm)", sig5g.get("rssi", 0), f'band="{band_5g_str}"')
        gauge("tmobile_5g_sinr_db", "5G Signal to Interference plus Noise Ratio (dB)", sig5g.get("sinr", 0), f'band="{band_5g_str}"')
        gauge("tmobile_5g_bars", "5G signal bars (0-5)", sig5g.get("bars", 0), f'band="{band_5g_str}"')

    # Generic connection info
    generic = data.get("signal", {}).get("generic", {})
    roaming = 1 if generic.get("roaming", False) else 0
    registered = 1 if generic.get("registration") == "registered" else 0
    ipv6 = 1 if generic.get("hasIPv6", False) else 0

    gauge("tmobile_roaming", "1 if gateway is roaming, 0 if not", roaming)
    gauge("tmobile_registered", "1 if gateway is registered on network, 0 if not", registered)
    gauge("tmobile_ipv6_enabled", "1 if IPv6 is available, 0 if not", ipv6)

    # Uptime
    uptime = data.get("time", {}).get("upTime", 0)
    gauge("tmobile_uptime_seconds", "Gateway uptime in seconds", uptime)

    # Device info as info metric
    device = data.get("device", {})
    lines.append("# HELP tmobile_device_info T-Mobile gateway device information")
    lines.append("# TYPE tmobile_device_info gauge")
    lines.append(
        f'tmobile_device_info{{model="{device.get("model","unknown")}",'
        f'software_version="{device.get("softwareVersion","unknown")}",'
        f'serial="{device.get("serial","unknown")}",'
        f'update_state="{device.get("updateState","unknown")}"}} 1'
    )

    return "\n".join(lines) + "\n"


def collector_loop():
    global latest_metrics
    while True:
        data = fetch_gateway_data()
        latest_metrics = build_metrics(data)
        logger.info("Metrics updated successfully")
        time.sleep(SCRAPE_INTERVAL)


class MetricsHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/metrics":
            payload = latest_metrics.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.send_header("Content-Length", len(payload))
            self.end_headers()
            self.wfile.write(payload)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # suppress per-request HTTP logs


if __name__ == "__main__":
    import threading

    logger.info(f"Starting T-Mobile exporter on port {METRICS_PORT}")

    # Prime metrics before serving
    data = fetch_gateway_data()
    latest_metrics = build_metrics(data)

    collector = threading.Thread(target=collector_loop, daemon=True)
    collector.start()

    server = HTTPServer(("", METRICS_PORT), MetricsHandler)
    logger.info(f"Serving metrics at http://0.0.0.0:{METRICS_PORT}/metrics")
    server.serve_forever()
