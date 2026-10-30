# -*- coding: utf-8 -*-
"""Detect a panel's location from its API URL host (DNS -> IP -> geo-IP)."""
import asyncio
import ipaddress
import logging
import time
from typing import Optional
from urllib.parse import urlparse

import geo_scan

logger = logging.getLogger(__name__)

_RETRY_AFTER = 1800
_failed_at: dict = {}


def _host_of(api_url: str) -> str:
    raw = (api_url or "").strip()
    if "://" not in raw:
        raw = "//" + raw
    return (urlparse(raw).hostname or "").strip()


def _is_public(ip: str) -> bool:
    try:
        return ipaddress.ip_address(ip).is_global
    except ValueError:
        return False


async def detect(api_url: str) -> Optional[dict]:
    """Return {cc, city, lat, lon} for the panel host, or None when it cannot be located."""
    host = _host_of(api_url)
    if not host:
        return None
    ip = await geo_scan._resolve(host, asyncio.Semaphore(1))
    if not ip or not _is_public(ip):
        return None
    geo = (await geo_scan._geolocate([ip])).get(ip)
    if not geo or geo.get("lat") is None or geo.get("lon") is None:
        return None
    return {
        "cc": (geo.get("country_code") or "").lower(),
        "city": geo.get("city") or geo.get("country") or "",
        "lat": round(float(geo["lat"]), 2),
        "lon": round(float(geo["lon"]), 2),
    }


def _save(db, server_id: int, geo: dict) -> None:
    db.update_panel_server(
        server_id, geo_cc=geo["cc"], geo_city=geo["city"], geo_lat=geo["lat"], geo_lon=geo["lon"], geo_manual=0,
    )


async def ensure(db, server) -> bool:
    """Auto-fill a panel's location when it has none and was never set by an admin."""
    sid = int(server["id"])
    if server["geo_lat"] is not None or server["geo_manual"]:
        return True
    if time.monotonic() - _failed_at.get(sid, -_RETRY_AFTER) < _RETRY_AFTER:
        return False
    try:
        geo = await detect(server["api_url"])
    except Exception:
        logger.exception("panel geo detect failed for %s", sid)
        geo = None
    if not geo:
        _failed_at[sid] = time.monotonic()
        return False
    await asyncio.to_thread(_save, db, sid, geo)
    return True


async def redetect(db, server_id: int, api_url: str) -> Optional[dict]:
    """Re-detect after the URL changed, unless the admin set the location manually."""
    server = await asyncio.to_thread(db.get_panel_server, server_id)
    if not server or server["geo_manual"]:
        return None
    _failed_at.pop(server_id, None)
    try:
        geo = await detect(api_url)
    except Exception:
        logger.exception("panel geo redetect failed for %s", server_id)
        return None
    if geo:
        await asyncio.to_thread(_save, db, server_id, geo)
    return geo
