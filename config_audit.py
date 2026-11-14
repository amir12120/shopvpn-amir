# -*- coding: utf-8 -*-
"""حذف کانفیگ‌هایی که دیگر روی پنل وجود ندارند (F139).

روش کار (بازطراحی‌شده): به‌جای زمان‌بندی شبانه، ادمین از مسیر
«سرور و سرویس → حذف کانفیگ‌های بدون پنل» خودش اجرا می‌کند.

تشخیص «روشن بودن پنل» عوض شده است: به‌جای تست اتصال/احراز هویت، **فهرست
واقعی کلاینت‌های پنل** خوانده می‌شود (برای 3x-ui از همان endpoint لیست
inboundها). اگر این خواندن موفق شود، یعنی پنل روشن و قابل خواندن است و همان
فهرست، مرجع قطعی «وجود/عدم‌وجود» هر کانفیگ است:

- کانفیگی که نامش در فهرست پنل نیست = از پنل حذف شده → قابل حذف از حساب کاربر.
- هر خطای شبکه/timeout/401/403 = پنل در دسترس نیست → برای آن پنل هیچ حذفی
  انجام نمی‌شود (فقط گزارش می‌شود).
- اگر همهٔ کانفیگ‌های یک پنل «موجود نبودند» ولی تعدادشان بیشتر از یکی است،
  پاسخ پنل ناقص فرض می‌شود و برای احتیاط چیزی حذف نمی‌شود.
- برای providerهایی که فهرست کلاینت ندارند، همان روش قبلی (تأیید دوبارِ
  get_user) استفاده می‌شود و خطای ارتباطی هرگز حذف نمی‌کند.

حذف به‌صورت «حذف منطقی» است (status='deleted' + رکورد تاریخچه)، پس کانفیگ از
لیست «کانفیگ‌های من» کاربر و از آمار فعال خارج می‌شود ولی گزارش‌ها می‌مانند.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from panel_providers import get_provider

logger = logging.getLogger(__name__)

NOT_FOUND_MARKERS = (
    "پیدا نشد", "not found", "notfound", "not_found", "does not exist", "non-existent",
)
# اگر همهٔ کانفیگ‌های یک پنل «موجود نبودند» و تعدادشان از این کمتر نبود،
# احتمالاً فهرست پنل ناقص خوانده شده است.
SUSPICIOUS_MIN_TOTAL = 2


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_not_found_error(exc) -> bool:
    """آیا خطای پنل صراحتاً یعنی «کاربر روی پنل نیست»؟"""
    text = str(exc or "").strip().lower()
    return any(marker in text for marker in NOT_FOUND_MARKERS)


def supports_inventory(provider) -> bool:
    """آیا این provider می‌تواند فهرست کلاینت‌های پنل را بدهد؟"""
    return callable(getattr(provider, "list_client_usernames", None))


async def _confirm_by_lookup(provider, rows):
    """مسیر جایگزین: پرسیدن تک‌تک کلاینت‌ها با تأیید دوباره. (missing, unknown)"""
    missing, unknown = [], 0
    for row in rows:
        username = row["username"]
        try:
            await provider.get_user(username)
            continue
        except Exception as exc:
            if not is_not_found_error(exc):
                unknown += 1
                logger.info("config-audit: بررسی %s ممکن نبود: %s", username, str(exc)[:200])
                continue
        try:
            await provider.get_user(username)
            logger.warning("config-audit: %s بار اول پیدا نشد و بار دوم پیدا شد؛ حذف نشد.", username)
        except Exception as exc:
            if is_not_found_error(exc):
                missing.append(row)
            else:
                unknown += 1
                logger.info("config-audit: تأیید نبودِ %s ممکن نبود: %s", username, str(exc)[:200])
    return missing, unknown


async def collect_audit(db) -> dict:
    """بدون تغییر چیزی: کانفیگ‌های موجود روی پنل را پیدا می‌کند.

    خروجی:
      missing     ردیف‌های {id,username,user_id,panel} که باید حذف شوند
      checked     تعداد کانفیگ بررسی‌شده
      failed      تعداد کانفیگی که بررسی‌شان ممکن نبود
      offline     نام پنل‌هایی که در دسترس نبودند (هیچ حذفی برایشان انجام نشد)
      suspicious  نام پنل‌هایی که به‌احتیاط بررسی نشدند
    """
    rows = await _to_thread(db.get_custom_configs_for_panel_audit)
    by_server: dict[int, list] = {}
    for row in rows:
        by_server.setdefault(int(row["panel_server_id"]), []).append(row)

    missing: list[dict] = []
    checked = failed = 0
    offline: list[str] = []
    suspicious: list[str] = []
    method: dict[str, str] = {}

    for server_id, items in by_server.items():
        server = await _to_thread(db.get_panel_server, server_id)
        if not server or not server["is_active"]:
            continue
        name = str(server["name"])
        try:
            provider = get_provider(server)
        except Exception as exc:
            logger.warning("config-audit: ساخت provider پنل «%s» ناموفق بود: %s", name, str(exc)[:200])
            offline.append(name)
            continue

        if supports_inventory(provider):
            # خواندن فهرست کلاینت‌ها هم‌زمان «تست روشن بودن پنل» است: اگر این
            # درخواست شکست بخورد یعنی پنل در دسترس نیست و هیچ حذفی نمی‌کنیم.
            try:
                names = await provider.list_client_usernames()
            except Exception as exc:
                logger.warning("config-audit: فهرست کلاینت‌های پنل «%s» خوانده نشد: %s",
                               name, str(exc)[:200])
                offline.append(name)
                continue
            inventory = {str(n) for n in (names or ())}
            missing_rows = [r for r in items if str(r["username"]) not in inventory]
            unknown = 0
            method[name] = "inventory"
            logger.info("config-audit: پنل «%s» فهرست %s کلاینت را داد؛ %s کانفیگ موجود نیست.",
                        name, len(inventory), len(missing_rows))
        else:
            missing_rows, unknown = await _confirm_by_lookup(provider, items)
            method[name] = "lookup"
        checked += len(items)
        failed += unknown

        if not missing_rows:
            continue
        if len(missing_rows) == len(items) and len(items) >= SUSPICIOUS_MIN_TOTAL:
            suspicious.append(name)
            logger.warning(
                "config-audit: همهٔ %s کانفیگ پنل «%s» موجود نبودند؛ برای احتیاط چیزی حذف نشد.",
                len(items), name,
            )
            continue
        for row in missing_rows:
            missing.append({
                "id": int(row["id"]), "username": row["username"],
                "user_id": row["user_id"], "panel": name,
            })

    return {
        "missing": missing, "checked": checked, "failed": failed,
        "offline": offline, "suspicious": suspicious, "method": method,
        "panels": len(by_server), "run_at": _utc_iso(),
    }


async def apply_missing(db, items: list, admin_id=None) -> int:
    """حذف منطقی کانفیگ‌های تأییدشده از حساب کاربر؛ تعداد حذف‌شده."""
    removed = 0
    for item in items or []:
        config_id = int(item["id"])
        if not await _to_thread(db.mark_custom_config_removed_from_panel, config_id):
            continue
        removed += 1
        detail = "F139: این کاربر/کلاینت روی پنل وجود نداشت و از لیست کانفیگ‌های کاربر حذف شد"
        if admin_id:
            detail += f" (اجرای دستی ادمین {admin_id})"
        await _to_thread(db.add_custom_config_history, config_id, "removed_from_panel", detail)
        logger.info("config-audit: کانفیگ #%s (%s) از پنل «%s» نبود و حذف شد",
                    config_id, item.get("username"), item.get("panel"))
    return removed


async def _to_thread(fn, *args):
    import asyncio
    return await asyncio.to_thread(fn, *args)
