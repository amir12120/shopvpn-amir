# -*- coding: utf-8 -*-
#‍​‌‌​​​‌‌​‌‌​​‌​‌​‌‌​‌‌​​​‌‌​​‌​‌​‌‌​‌‌‌​​‌‌​‌‌‌‌​‌‌‌​​‌​‍
"""
نقشه‌ی پس‌زمینه‌ی «نقشه‌ی جهانی سرورها»ی داشبورد.

قبلاً مرورگر ادمین مستقیماً از سه CDN خارجی (jsdelivr/unpkg/cdnjs) هم
کتابخانه‌های d3-geo/topojson-client و هم فایل نقشه‌ی world-atlas را دانلود
می‌کرد. اگر مرورگر ادمین به آن دامنه‌ها دسترسی نداشته باشد (فیلتر/قطعی
اینترنت)، آن دانلود بی‌سروصدا fail می‌شد و فقط گرید خالی می‌ماند — بدون هیچ
خط ساحلی‌ای روی نقشه.

این ماژول این کار را یک‌بار روی خودِ سرور پنل انجام می‌دهد (که معمولاً
دسترسی اینترنت پایدارتری دارد) و نتیجه را از دامنه‌ی خودِ پنل serve می‌کند؛
یعنی مرورگر ادمین دیگر هیچ‌وقت مستقیماً به CDN نیاز ندارد. نتیجه هم در
حافظه و هم روی دیسک cache می‌شود تا با ری‌استارت سرور دوباره لازم به
دانلود نباشد.
"""

import asyncio
import json
import os
import time
from typing import Optional

import aiohttp

_MIRRORS = [
    "https://cdn.jsdelivr.net/npm/world-atlas@2/land-50m.json",
    "https://unpkg.com/world-atlas@2/land-50m.json",
    "https://cdn.jsdelivr.net/npm/world-atlas@2.0.2/land-50m.json",
]
_TIMEOUT = aiohttp.ClientTimeout(total=25)
# اسم فایل نسخه‌دار است: با هر تغییر در نحوه‌ی تولید مسیر (رزولوشن منبع یا
# الگوریتم ساده‌سازی) باید عوض شود، وگرنه سرور کش قدیمی/سنگین‌تر را برای
# همیشه serve می‌کند. v3: اعمال ساده‌سازی Douglas-Peucker چون مسیر خامِ
# land-50m آن‌قدر نقطه داشت که زوم روی موبایل (به‌خصوص سافاری iOS) صفحه را
# کاملاً هنگ می‌کرد.
_CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_world_map_cache_v3.json")

_mem_cache = None  # {"ok": True, "land_path": "..."} پس از اولین موفقیت در طول عمر پروسه
_fetch_lock = None  # asyncio.Lock ساخته‌شده lazy چون این ماژول ممکن است بدون event loop هم import شود‍​‌‌​​​‌‌​‌‌​​‌​‌​‌‌​‌‌​​​‌‌​​‌​‌​‌‌​‌‌‌​​‌‌​‌‌‌‌​‌‌‌​​‌​‍


def _get_lock() -> asyncio.Lock:
    global _fetch_lock
    if _fetch_lock is None:
        _fetch_lock = asyncio.Lock()
    return _fetch_lock
#‍​‌‌​​​‌‌​‌‌​​‌​‌​‌‌​‌‌​​​‌‌​​‌​‌​‌‌​‌‌‌​​‌‌​‌‌‌‌​‌‌‌​​‌​‍


# ------------------------------------------------------------- projection --
# دقیقاً معادل خطیِ svProject سمت کلاینت (d3.geoEquirectangular با
# fitSize([1000, 500], {type:'Sphere'})) — تا پین‌های سمت کلاینت روی همین
# تصویربرداری بیفتند.
def _project(lon: float, lat: float):
    x = (lon + 180.0) / 360.0 * 1000.0
    y = (90.0 - lat) / 180.0 * 500.0
    return x, y


# ----------------------------------------------------------- topojson decode --
def _decode_arc(deltas, transform):
    tx, ty = transform["translate"]
    sx, sy = transform["scale"]
    x = 0
    y = 0
    pts = []
    for dx, dy in deltas:
        x += dx
        y += dy
        pts.append((tx + x * sx, ty + y * sy))
    return pts


def _arc_points(index: int, arcs_decoded: list) -> list:
    if index >= 0:
        return arcs_decoded[index]
    return list(reversed(arcs_decoded[~index]))


def _build_ring(arc_indices: list, arcs_decoded: list) -> list:
    ring = []
    for i, idx in enumerate(arc_indices):
        pts = _arc_points(idx, arcs_decoded)
        ring.extend(pts if i == 0 else pts[1:])
    return ring


def _rings_of_geometry(geom: dict):
    """تمام رینگ‌ها (لیست‌های arc index) را از یک geometry (Polygon/MultiPolygon/
    GeometryCollection تودرتو) استخراج می‌کند."""
    gtype = geom.get("type")
    if gtype == "Polygon":
        for ring in geom.get("arcs", []):
            yield ring
    elif gtype == "MultiPolygon":
        for polygon in geom.get("arcs", []):
            for ring in polygon:
                yield ring
    elif gtype == "GeometryCollection":
        for sub in geom.get("geometries", []):
            yield from _rings_of_geometry(sub)
    # سایر انواع (Point/LineString/...) برای «زمین» انتظار نمی‌رود پیش بیایند‍​‌‌​​​‌‌​‌‌​​‌​‌​‌‌​‌‌​​​‌‌​​‌​‌​‌‌​‌‌‌​​‌‌​‌‌‌‌​‌‌‌​​‌​‍


def _rdp_simplify(points: list, epsilon: float) -> list:
    """Ramer-Douglas-Peucker روی نقاط پروجکت‌شده (فضای صفحه‌ی SVG، نه lon/lat)
    اجرا می‌شود چون در مقیاس نمایشیِ نهاییِ ۱۰۰۰x۵۰۰ معنا دارد: در آن مقیاس،
    خطوط ساحلیِ خامِ land-50m ده‌ها هزار نقطه دارند که هیچ تفاوت بصری‌ای در
    یک نقشه‌ی کوچک روی موبایل ایجاد نمی‌کنند ولی رندر/زوم SVG را بسیار سنگین
    و روی سافاری iOS باعث هنگ صفحه می‌کنند. پیاده‌سازی تکراری (نه بازگشتی)
    است تا برای حلقه‌های خیلی طولانی به عمق پشته‌ی پایتون نخوریم.
    """
    n = len(points)
    if n < 3 or epsilon <= 0:
        return points

    def _perp_dist(p, a, b):
        ax, ay = a
        bx, by = b
        px, py = p
        dx, dy = bx - ax, by - ay
        if dx == 0 and dy == 0:
            return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
        t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
        cx, cy = ax + t * dx, ay + t * dy
        return ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5

    keep = bytearray(n)
    keep[0] = keep[n - 1] = 1
    stack = [(0, n - 1)]
    while stack:
        start, end = stack.pop()
        if end - start < 2:
            continue
        a, b = points[start], points[end]
        max_dist, max_idx = -1.0, -1
        for i in range(start + 1, end):
            d = _perp_dist(points[i], a, b)
            if d > max_dist:
                max_dist, max_idx = d, i
        if max_dist > epsilon:
            keep[max_idx] = 1
            stack.append((start, max_idx))
            stack.append((max_idx, end))
    return [p for i, p in enumerate(points) if keep[i]]


# فاصله‌ی مجاز خطا در واحدهای همان فضای SVG (viewBox 0..1000 x 0..500).
# مقداری که تفاوت بصری‌اش در نمایش موبایل/دسکتاپ محسوس نیست ولی تعداد
# نقاط را معمولاً بیش از ۹۰٪ کم می‌کند.
_SIMPLIFY_EPSILON = 0.6


def _topology_to_svg_path(topo: dict, object_name: str = "land") -> str:
    transform = topo["transform"]
    arcs_decoded = [_decode_arc(arc, transform) for arc in topo["arcs"]]
    geom = topo["objects"][object_name]

    d_parts = []
    for arc_indices in _rings_of_geometry(geom):
        ring = _build_ring(arc_indices, arcs_decoded)
        if len(ring) < 2:
            continue
        projected = [_project(lon, lat) for lon, lat in ring]
        projected = _rdp_simplify(projected, _SIMPLIFY_EPSILON)
        if len(projected) < 2:
            continue
        seg = ["M"]
        for i, (x, y) in enumerate(projected):
            seg.append(f"{x:.1f},{y:.1f}" if i == 0 else f"L{x:.1f},{y:.1f}")
        seg.append("Z")
        d_parts.append("".join(seg))
    return "".join(d_parts)


# ------------------------------------------------------------------ fetch --
async def _fetch_topology() -> dict:
    last_err = None
    async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
        for url in _MIRRORS:
            try:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        last_err = f"HTTP {resp.status} از {url}"
                        continue
                    return await resp.json(content_type=None)
            except Exception as e:  # noqa: BLE001 - می‌خواهیم mirror بعدی را امتحان کنیم
                last_err = str(e)
                continue
    raise RuntimeError(last_err or "هیچ‌کدام از mirrorها جواب ندادند")


def _load_disk_cache() -> Optional[dict]:
    try:
        with open(_CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _save_disk_cache(data: dict) -> None:
    try:
        with open(_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception:
        pass  # کش دیسک اختیاری است؛ اگر ننوشت مهم نیست


async def get_world_map(force_refresh: bool = False) -> dict:
    """{"ok": True, "land_path": "<svg path d>"} یا {"ok": False, "error": "..."}"""
    global _mem_cache
    if _mem_cache and not force_refresh:
        return _mem_cache

    async with _get_lock():
        if _mem_cache and not force_refresh:  # ممکن است تا رسیدن به لاک، یکی دیگر پر کرده باشد
            return _mem_cache

        if not force_refresh:
            disk = _load_disk_cache()
            if disk and disk.get("ok") and disk.get("land_path"):
                _mem_cache = disk
                return _mem_cache

        try:
            topo = await _fetch_topology()
            land_path = _topology_to_svg_path(topo, "land")
            if not land_path:
                raise RuntimeError("مسیر SVG خالی تولید شد")
            result = {"ok": True, "land_path": land_path, "at": int(time.time())}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"دریافت نقشه‌ی جهان ناموفق بود: {e}"}

        _mem_cache = result
        _save_disk_cache(result)
        return result
#‍​‌‌​​​‌‌​‌‌​​‌​‌​‌‌​‌‌​​​‌‌​​‌​‌​‌‌​‌‌‌​​‌‌​‌‌‌‌​‌‌‌​​‌​‍
# 		   		 		  	 	 		 		   		  	 	 		 			  		 				 			  	 


# ============================================================ countries ====
# مرز کشورها برای «نقشه زنده شبکه»ی فروشگاه: کشورهای دارای سرور رنگی می‌شوند و
# پین سرور به نزدیک‌ترین/شامل‌شونده‌ترین کشور می‌چسبد (جزایر کوچک مثل سنگاپور
# هم حذف نمی‌شوند). خروجی: [{"n": "Germany", "d": "M..Z"}, ...] در همان فضای
# 1000x500 معادل-مستطیلی که land_path دارد.
_COUNTRY_MIRRORS = [
    "https://cdn.jsdelivr.net/npm/world-atlas@2/countries-50m.json",
    "https://unpkg.com/world-atlas@2/countries-50m.json",
    "https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json",
    "https://unpkg.com/world-atlas@2/countries-110m.json",
]
_COUNTRY_CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_world_countries_cache_v1.json")
_COUNTRY_EPS = 0.3          # ساده‌سازی کشورهای بزرگ (واحد SVG)
_TINY_SPAN = 3.0            # رینگی که هر دو بعدش کوچک‌تر است، بدون ساده‌سازی می‌ماند
_countries_mem = None


def _ring_path(projected: list) -> str:
    seg = []
    for i, (x, y) in enumerate(projected):
        seg.append(("M%.2f,%.2f" if i == 0 else "L%.2f,%.2f") % (x, y))
    seg.append("Z")
    return "".join(seg)


def _topology_to_countries(topo: dict) -> list:
    objs = topo.get("objects", {})
    obj = objs.get("countries") or next(iter(objs.values()))
    transform = topo["transform"]
    arcs_decoded = [_decode_arc(arc, transform) for arc in topo["arcs"]]
    out = []
    for geom in obj.get("geometries", []):
        name = (geom.get("properties") or {}).get("name") or ""
        parts = []
        for arc_indices in _rings_of_geometry(geom):
            ring = _build_ring(arc_indices, arcs_decoded)
            if len(ring) < 3:
                continue
            pts = [_project(lon, lat) for lon, lat in ring]
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            tiny = (max(xs) - min(xs)) < _TINY_SPAN and (max(ys) - min(ys)) < _TINY_SPAN
            if not tiny:
                pts = _rdp_simplify(pts, _COUNTRY_EPS)
            if len(pts) >= 3:
                parts.append(_ring_path(pts))
        if parts:
            out.append({"n": name, "d": "".join(parts)})
    return out


async def _fetch_country_topology() -> dict:
    last_err = None
    async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
        for url in _COUNTRY_MIRRORS:
            try:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        last_err = f"HTTP {resp.status} از {url}"
                        continue
                    return await resp.json(content_type=None)
            except Exception as e:  # noqa: BLE001
                last_err = str(e)
    raise RuntimeError(last_err or "هیچ‌کدام از mirrorها جواب ندادند")


async def get_countries(force_refresh: bool = False) -> dict:
    """{"ok": True, "countries": [{"n","d"}...]} یا {"ok": False, "error": "..."}"""
    global _countries_mem
    if _countries_mem and not force_refresh:
        return _countries_mem
    async with _get_lock():
        if _countries_mem and not force_refresh:
            return _countries_mem
        if not force_refresh:
            try:
                with open(_COUNTRY_CACHE_FILE, "r", encoding="utf-8") as f:
                    disk = json.load(f)
                if disk.get("ok") and disk.get("countries"):
                    _countries_mem = disk
                    return _countries_mem
            except Exception:
                pass
        try:
            topo = await _fetch_country_topology()
            countries = await asyncio.to_thread(_topology_to_countries, topo)
            if not countries:
                raise RuntimeError("لیست کشورها خالی تولید شد")
            result = {"ok": True, "countries": countries, "at": int(time.time())}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"دریافت مرز کشورها ناموفق بود: {e}"}
        _countries_mem = result
        try:
            with open(_COUNTRY_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(result, f)
        except Exception:
            pass
        return result
