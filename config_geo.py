# -*- coding: utf-8 -*-
"""Locate store products from the config links stored in their inventory."""
import asyncio
import logging
import time
from typing import Optional

import geo_scan

logger = logging.getLogger(__name__)

SAMPLE_PER_PRODUCT = 40
TARGETS_PER_LOCATION = 3
_TTL_OK = 6 * 3600
_TTL_FAIL = 1800
_TCP_TTL = 120

_host_cache: dict = {}
_tcp_cache: dict = {}


def _fresh(entry: Optional[dict], now: float) -> bool:
    if not entry:
        return False
    return now - entry["at"] < (_TTL_OK if entry["geo"] else _TTL_FAIL)


async def _resolve_hosts(hosts: set) -> None:
    now = time.time()
    todo = [h for h in hosts if not _fresh(_host_cache.get(h), now)]
    if not todo:
        return
    sem = asyncio.Semaphore(geo_scan._DNS_CONCURRENCY)
    ips = await asyncio.gather(*(geo_scan._resolve(h, sem) for h in todo))
    host_ip = dict(zip(todo, ips))
    unique_ips = sorted({ip for ip in ips if ip})
    geo = await geo_scan._geolocate(unique_ips) if unique_ips else {}
    for host, ip in host_ip.items():
        _host_cache[host] = {"ip": ip or "", "geo": geo.get(ip) if ip else None, "at": now}


def _locate(entry: dict) -> Optional[dict]:
    cached = _host_cache.get(entry["host"]) or {}
    geo = cached.get("geo")
    label_cc = geo_scan.detect_label_country(entry.get("remark") or "")
    if label_cc:
        name, lat, lon = geo_scan.COUNTRY_INFO[label_cc]
        cc, city = label_cc, ""
        if geo and geo["country_code"] == label_cc:
            lat, lon, city = geo["lat"], geo["lon"], geo["city"]
    elif geo:
        cc, lat, lon, city = geo["country_code"], geo["lat"], geo["lon"], geo["city"]
    else:
        return None
    port = int(entry["port"]) if str(entry.get("port") or "").isdigit() else 0
    return {"cc": cc.lower(), "city": city, "lat": float(lat), "lon": float(lon), "ip": cached.get("ip") or "", "port": port}


def _name_fallback(name: str) -> Optional[dict]:
    cc = geo_scan.detect_label_country(name or "")
    if not cc:
        return None
    label, lat, lon = geo_scan.COUNTRY_INFO[cc]
    return {"cc": cc.lower(), "city": label, "lat": lat, "lon": lon, "ip": "", "port": 0}


async def locate_products(db, products: list) -> dict:
    """Return {product_id: {(lat1, lon1): {cc, city, lat, lon, targets}}} based on stored configs."""
    links_by_product = {}
    for p in products:
        links_by_product[p["id"]] = await asyncio.to_thread(db.get_config_links_for_geo, p["id"], SAMPLE_PER_PRODUCT)
    entries_by_product = {}
    hosts = set()
    for pid, links in links_by_product.items():
        found = []
        for link in links:
            items = geo_scan.parse_subscription_text(link)
            if items:
                found.append(items[0])
                hosts.add(items[0]["host"])
        entries_by_product[pid] = found
    await _resolve_hosts(hosts)

    result = {}
    for p in products:
        locations: dict = {}
        for entry in entries_by_product[p["id"]]:
            loc = _locate(entry)
            if not loc:
                continue
            key = (round(loc["lat"], 1), round(loc["lon"], 1))
            node = locations.setdefault(key, {**{k: loc[k] for k in ("cc", "city", "lat", "lon")}, "targets": []})
            target = (loc["ip"], loc["port"])
            if loc["ip"] and loc["port"] and target not in node["targets"] and len(node["targets"]) < TARGETS_PER_LOCATION:
                node["targets"].append(target)
        if not locations and not entries_by_product[p["id"]]:
            loc = _name_fallback(p["name"])
            if loc:
                locations[(round(loc["lat"], 1), round(loc["lon"], 1))] = {**{k: loc[k] for k in ("cc", "city", "lat", "lon")}, "targets": []}
        result[p["id"]] = locations
    return result


async def _tcp_status(ip: str, port: int) -> str:
    now = time.time()
    cached = _tcp_cache.get((ip, port))
    if cached and now - cached[0] < _TCP_TTL:
        return cached[1]
    status = await geo_scan._tcp_check(ip, port, asyncio.Semaphore(1), timeout=4.0)
    _tcp_cache[(ip, port)] = (now, status)
    return status


async def location_status(targets: list) -> str:
    """'down' only when every probed config endpoint is unreachable."""
    if not targets:
        return "up"
    states = await asyncio.gather(*(_tcp_status(ip, port) for ip, port in targets))
    return "down" if all(s == "offline" for s in states) else "up"
