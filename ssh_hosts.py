# -*- coding: utf-8 -*-
"""«هاست» برای نودهای SSH / OpenVPN / WireGuard (مشابه Hostهای پاسارگاد).

هر نود می‌تواند برای هر پروتکل یک یا چند هاست داشته باشد؛ هاست = آدرسی که به کاربر
نشان داده می‌شود (دامنه/IP نود، یا آدرس یک سرور تانل/رله) + پورت اختیاری. آدرس واقعی
نود (که ربات با Agent آن صحبت می‌کند) دست نمی‌خورد؛ فقط خروجی‌ی کاربر (لینک ssh://،
فایل .ovpn و .conf) در لحظه‌ی نمایش ساخته می‌شود، پس تغییر هاست روی حساب‌های قدیمی هم
اعمال می‌شود.

قواعد پورت:
  • OpenVPN / WireGuard: هاست می‌تواند پورت اختیاری داشته باشد (مثلاً پورتِ تانل)؛
    خالی = پورت خود نود.
  • SSH: هر حساب پورت اختصاصی خودش را روی نود دارد (حسابداری حجم بر اساس پورت است)،
    پس هاست فقط «آدرس» را عوض می‌کند. بازه‌ی پورت‌هایی که نود برای حساب‌های جدید
    می‌سازد جداگانه با ssh_port_min / ssh_port_max در تنظیمات نود تعیین می‌شود.

همه‌ی داده‌ها در config_json نود ذخیره می‌شوند:
    {"hosts": [{"id","protocol","remark","address","port","enabled"}...],
     "ssh_port_min": 20000, "ssh_port_max": 39999}
"""
from __future__ import annotations

import json
import re
import uuid
from typing import Optional

PROTOCOLS = ("ssh", "openvpn", "wireguard")
FILE_PROTOCOLS = ("openvpn", "wireguard")
DEFAULT_SSH_PORT_MIN = 20000
DEFAULT_SSH_PORT_MAX = 39999
MIN_SSH_PORT = 1024
MAX_HOSTS_PER_NODE = 30

ADDRESS_RE = re.compile(r"^[A-Za-z0-9.\-:]{3,255}$")
_OVPN_REMOTE_RE = re.compile(r"(?m)^remote[ \t]+\S+[ \t]+\d+[ \t]*$")
_WG_ENDPOINT_RE = re.compile(r"(?m)^Endpoint[ \t]*=[ \t]*.+$")


class HostConfigError(ValueError):
    pass


def node_config(obj) -> dict:
    """config_json نود را از dict نود (یا ردیف join شده‌ی node_config_json) می‌خواند."""
    if not obj:
        return {}
    raw = None
    if isinstance(obj, dict):
        raw = obj.get("config_json")
        if raw is None:
            raw = obj.get("node_config_json")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            data = json.loads(raw)
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}
    return {}


def _clean_address(value) -> str:
    address = str(value or "").strip()
    if address.startswith("[") and address.endswith("]"):
        address = address[1:-1]
    if not ADDRESS_RE.fullmatch(address):
        raise HostConfigError("آدرس هاست نامعتبر است (فقط دامنه یا IP؛ بدون http و بدون پورت).")
    return address


def _clean_port(value, protocol: str) -> Optional[int]:
    if value in (None, "", 0, "0"):
        return None
    if protocol == "ssh":
        raise HostConfigError("برای SSH پورت هاست قابل تعیین نیست؛ هر حساب پورت اختصاصی دارد. "
                              "بازه‌ی پورت‌های SSH را در تنظیمات نود بدهید.")
    try:
        port = int(value)
    except (TypeError, ValueError):
        raise HostConfigError("پورت هاست نامعتبر است.")
    if not 1 <= port <= 65535:
        raise HostConfigError("پورت هاست باید بین 1 تا 65535 باشد.")
    return port


def normalize_host(entry: dict) -> dict:
    if not isinstance(entry, dict):
        raise HostConfigError("ساختار هاست نامعتبر است.")
    protocol = str(entry.get("protocol") or "").strip().lower()
    if protocol not in PROTOCOLS:
        raise HostConfigError("پروتکل هاست باید ssh، openvpn یا wireguard باشد.")
    remark = " ".join(str(entry.get("remark") or "").split())[:60]
    host_id = re.sub(r"[^a-f0-9]", "", str(entry.get("id") or "").lower())[:12] or uuid.uuid4().hex[:8]
    enabled = entry.get("enabled", True)
    if isinstance(enabled, str):
        enabled = enabled.strip().lower() not in {"0", "false", "no", "off", ""}
    return {"id": host_id, "protocol": protocol, "remark": remark,
            "address": _clean_address(entry.get("address")),
            "port": _clean_port(entry.get("port"), protocol), "enabled": bool(enabled)}


def normalize_hosts(entries) -> list:
    entries = list(entries or [])
    if len(entries) > MAX_HOSTS_PER_NODE:
        raise HostConfigError(f"حداکثر {MAX_HOSTS_PER_NODE} هاست برای هر نود مجاز است.")
    out, seen = [], set()
    for entry in entries:
        item = normalize_host(entry)
        while item["id"] in seen:
            item["id"] = uuid.uuid4().hex[:8]
        seen.add(item["id"])
        out.append(item)
    return out


def list_hosts(obj, protocol: str = None, enabled_only: bool = False) -> list:
    raw = node_config(obj).get("hosts") or []
    out = []
    for entry in raw if isinstance(raw, list) else []:
        try:
            item = normalize_host(entry)
        except HostConfigError:
            continue  # ورودی خراب نباید خروجی کاربر را بشکند
        if protocol and item["protocol"] != protocol:
            continue
        if enabled_only and not item["enabled"]:
            continue
        out.append(item)
    return out


def ssh_port_range(obj) -> tuple:
    cfg = node_config(obj)
    try:
        low = int(cfg.get("ssh_port_min") or DEFAULT_SSH_PORT_MIN)
        high = int(cfg.get("ssh_port_max") or DEFAULT_SSH_PORT_MAX)
    except (TypeError, ValueError):
        return DEFAULT_SSH_PORT_MIN, DEFAULT_SSH_PORT_MAX
    if not MIN_SSH_PORT <= low <= high <= 65535:
        return DEFAULT_SSH_PORT_MIN, DEFAULT_SSH_PORT_MAX
    return low, high


def ssh_port_range_is_custom(obj) -> bool:
    cfg = node_config(obj)
    return bool(cfg.get("ssh_port_min") or cfg.get("ssh_port_max"))


def validate_ssh_port_range(port_min, port_max, reserved=()) -> tuple:
    try:
        low, high = int(port_min), int(port_max)
    except (TypeError, ValueError):
        raise HostConfigError("بازه‌ی پورت SSH نامعتبر است.")
    if not MIN_SSH_PORT <= low <= 65535 or not MIN_SSH_PORT <= high <= 65535:
        raise HostConfigError(f"پورت‌های SSH حساب‌ها باید بین {MIN_SSH_PORT} تا 65535 باشند.")
    if low > high:
        raise HostConfigError("پورت شروع نباید از پورت پایان بزرگ‌تر باشد.")
    for port in reserved:
        if port and low <= int(port) <= high and low == high:
            raise HostConfigError(f"پورت {int(port)} برای سرویس دیگری روی نود رزرو است.")
    return low, high


def endpoints(obj, protocol: str, base_host: str, base_port: int) -> list:
    """لیست آدرس/پورتی که باید به کاربر نمایش داده شود.

    بدون هاست فعال: همان آدرس/پورت واقعیِ حساب (رفتار قبلی). با هاست فعال: به ازای
    هر هاست یک خروجی.
    """
    protocol = str(protocol or "ssh").lower()
    hosts = list_hosts(obj, protocol, enabled_only=True)
    base_port = int(base_port or 0)
    if not hosts:
        return [{"host_id": None, "address": str(base_host or ""), "port": base_port, "remark": ""}]
    out = []
    for item in hosts:
        port = base_port if protocol == "ssh" else int(item.get("port") or base_port)
        out.append({"host_id": item["id"], "address": item["address"], "port": port, "remark": item["remark"]})
    return out


def rewrite_ovpn_profile(profile: str, address: str, port: int) -> str:
    return _OVPN_REMOTE_RE.sub(lambda _m: f"remote {address} {int(port)}", str(profile or ""), count=1)


def rewrite_wg_profile(profile: str, address: str, port: int) -> str:
    host = f"[{address}]" if ":" in address and not address.startswith("[") else address
    return _WG_ENDPOINT_RE.sub(lambda _m: f"Endpoint = {host}:{int(port)}", str(profile or ""), count=1)


def rewrite_profile(protocol: str, profile: str, address: str, port: int) -> str:
    if protocol == "openvpn":
        return rewrite_ovpn_profile(profile, address, port)
    if protocol == "wireguard":
        return rewrite_wg_profile(profile, address, port)
    return profile
