#!/usr/bin/env python3
"""
Reolink NVR Prometheus Exporter
Scrapes channel status, HDD info, and device info from the Reolink HTTP API.
"""

import os
import time
import logging
import requests
from prometheus_client import start_http_server, Gauge, Info

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

NVR_HOST     = os.environ.get("NVR_HOST", "192.168.0.4")
NVR_USER     = os.environ.get("NVR_USER", "admin")
NVR_PASSWORD = os.environ["NVR_PASSWORD"]
SCRAPE_PORT  = int(os.environ.get("SCRAPE_PORT", "9720"))
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "30"))

BASE_URL = f"http://{NVR_HOST}/api.cgi"

# --- Metrics ---

nvr_up = Gauge(
    "reolink_nvr_up",
    "1 if the NVR API is reachable, 0 otherwise"
)

channel_online = Gauge(
    "reolink_nvr_channel_online",
    "1 if the camera channel is online, 0 otherwise",
    ["channel"]
)

hdd_capacity_mb = Gauge(
    "reolink_nvr_hdd_capacity_mb",
    "Total HDD capacity in MB",
    ["id"]
)

hdd_used_mb = Gauge(
    "reolink_nvr_hdd_used_mb",
    "Used HDD space in MB",
    ["id"]
)

hdd_mounted = Gauge(
    "reolink_nvr_hdd_mounted",
    "1 if the HDD is mounted, 0 otherwise",
    ["id"]
)

nvr_info = Info(
    "reolink_nvr",
    "Static device information from the NVR"
)


def api_get(cmd):
    """Hit the NVR CGI API and return parsed JSON or None on failure."""
    try:
        resp = requests.get(
            BASE_URL,
            params={"cmd": cmd, "user": NVR_USER, "password": NVR_PASSWORD},
            timeout=10
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logging.error("API request failed for cmd=%s: %s", cmd, e)
        return None


def collect():
    data = api_get("GetDevInfo")
    if data is None:
        nvr_up.set(0)
        return

    nvr_up.set(1)

    # Device info
    try:
        dev = data[0]["value"]["DevInfo"]
        nvr_info.info({
            "model":    dev.get("model", "unknown"),
            "firmware": dev.get("firmVer", "unknown"),
            "hardware": dev.get("hardVer", "unknown"),
            "name":     dev.get("name", "unknown"),
        })
    except (KeyError, IndexError) as e:
        logging.warning("Failed to parse DevInfo: %s", e)

    # Channel status
    chan_data = api_get("GetChannelstatus")
    if chan_data:
        try:
            for ch in chan_data[0]["value"]["status"]:
                channel_online.labels(channel=str(ch["channel"])).set(ch["online"])
        except (KeyError, IndexError) as e:
            logging.warning("Failed to parse ChannelStatus: %s", e)

    # HDD info
    hdd_data = api_get("GetHddInfo")
    if hdd_data:
        try:
            for disk in hdd_data[0]["value"]["HddInfo"]:
                did = str(disk["id"])
                hdd_capacity_mb.labels(id=did).set(disk.get("capacity", 0))
                hdd_used_mb.labels(id=did).set(disk.get("size", 0))
                hdd_mounted.labels(id=did).set(disk.get("mount", 0))
        except (KeyError, IndexError) as e:
            logging.warning("Failed to parse HddInfo: %s", e)


if __name__ == "__main__":
    logging.info("Starting Reolink NVR exporter on port %d", SCRAPE_PORT)
    start_http_server(SCRAPE_PORT)
    while True:
        collect()
        time.sleep(POLL_INTERVAL)
