# -*- coding: utf-8 -*-
"""بررسی روزانهٔ وجود کانفیگ‌ها روی پنل (F139).

هر شب (پیش‌فرض: ساعت ۱۲ شب به وقت تهران) یک‌بار همهٔ کانفیگ‌های فعالی که روی
پنل ساخته شده‌اند با خود پنل مقایسه می‌شوند؛ اگر کاربر/کلاینت دیگر روی پنل
وجود نداشته باشد (ادمین یا کاربر از پنل پاکش کرده)، رکورد از لیست
«کانفیگ‌های من» کاربر حذف می‌شود.

اصل ایمنی: فقط پاسخ صریح «پیدا نشد» پنل باعث حذف می‌شود. خطای شبکه، timeout یا
احراز هویت هیچ‌وقت حذف نمی‌کند و اگر همهٔ کانفیگ‌های یک پنل «پیدا نشد»
برگردانند (احتمال پاسخ ناقص/خراب پنل)، برای آن پنل چیزی حذف نمی‌شود و فقط به
ادمین گزارش می‌شود.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from panel_providers import get_provider

logger = logging.getLogger(__name__)

SCHEDULE = (0, 0)          # ساعت اجرا به وقت تهران: ۱۲ شب
LAST_RUN_KEY = "config_audit_last_run"
NOT_FOUND_MARKERS = (
    "پیدا نشد", "not found", "notfound", "not_found", "does not exist", "non-existent",
)
# اگر همهٔ کانفیگ‌های یک پنل «پیدا نشد» برگردانند، احتمالاً پاسخ پنل ناقص است.
SUSPICIOUS_MIN_MISSING = 5


def _tehran_zone():
    try:
        return ZoneInfo("Asia/Tehran")
    except Exception:
        # سرورهایی که tzdata ندارند؛ ۱۲ شب تهران = ۲۰:۳۰ UTC
        return timezone(timedelta(hours=3, minutes=30))


def _tehran_now():
    return datetime.now(_tehran_zone())


def _utc_iso():
    return datetime.now(timezone.utc).isoformat()


def is_not_found_error(exc) -> bool:
    """آیا خطای پنل صراحتاً یعنی «کاربر روی پنل نیست»؟

    همه‌ی providerها برای کاربر ناموجود PanelError با متن «... پیدا نشد»
    پرتاب می‌کنند (همین قرارداد در delete_user آن‌ها هم استفاده شده است).
    """
    text = str(exc or "").strip().lower()
    return any(marker in text for marker in NOT_FOUND_MARKERS)


async def _audit_panel(server, rows):
    """(missing, unknown): missing = روی پنل نیست، unknown = قابل تشخیص نبود."""
    provider = get_provider(server)
    missing, unknown = [], 0
    for row in rows:
        try:
            await provider.get_user(row["username"])
        except Exception as exc:
            if is_not_found_error(exc):
                missing.append(row)
            else:
                unknown += 1
                logger.info(
                    "config-audit: بررسی %s روی پنل %s ممکن نبود: %s",
                    row["username"], server["id"] if "id" in server.keys() else "?",
                    str(exc)[:200],
                )
    return missing, unknown


async def _notify_admins(bot, db, text: str) -> None:
    if bot is None:
        return
    try:
        import report_router
        await report_router.report(bot, db, "service", text)
    except Exception:
        logger.warning("config-audit: ارسال گزارش به ادمین ناموفق بود.", exc_info=True)


async def audit_configs_once(bot, db, *, force: bool = False) -> dict:
    """یک دور بررسی. force=True برای تست/اجرای دستی، بدون توجه به زمان‌بندی."""
    now = _tehran_now()
    today = now.date().isoformat()
    last_run = str(await asyncio.to_thread(db.get_setting, LAST_RUN_KEY, "") or "")
    if not force:
        if (now.hour, now.minute) < SCHEDULE:
            return {"skipped": "before_schedule", "checked": 0, "removed": 0, "failed": 0}
        if last_run == today:
            return {"skipped": "already_ran", "checked": 0, "removed": 0, "failed": 0}
    await asyncio.to_thread(db.set_setting, LAST_RUN_KEY, today)

    rows = await asyncio.to_thread(db.get_custom_configs_for_panel_audit)
    by_server: dict[int, list] = {}
    for row in rows:
        by_server.setdefault(int(row["panel_server_id"]), []).append(row)

    checked = removed = failed = 0
    suspicious: list[str] = []
    for server_id, items in by_server.items():
        server = await asyncio.to_thread(db.get_panel_server, server_id)
        if not server or not server["is_active"]:
            continue
        missing, unknown = await _audit_panel(server, items)
        checked += len(items)
        failed += unknown
        if len(missing) >= SUSPICIOUS_MIN_MISSING and len(missing) == len(items):
            suspicious.append(server["name"])
            logger.warning(
                "config-audit: همهٔ %s کانفیگ پنل «%s» پیدا نشدند؛ برای احتیاط چیزی حذف نشد.",
                len(missing), server["name"],
            )
            continue
        for row in missing:
            if await asyncio.to_thread(db.mark_custom_config_removed_from_panel, int(row["id"])):
                removed += 1
                await asyncio.to_thread(
                    db.add_custom_config_history, int(row["id"]), "removed_from_panel",
                    "F139: این کاربر/کلاینت روی پنل وجود نداشت و از لیست کانفیگ‌های کاربر حذف شد",
                )
                logger.info("config-audit: کانفیگ #%s (%s) روی پنل نبود و از لیست حذف شد",
                            row["id"], row["username"])

    if removed or suspicious or failed:
        lines = ["🧾 F139 — بررسی روزانهٔ کانفیگ‌های حذف‌شده از پنل", ""]
        lines.append(f"🔍 بررسی‌شده: {checked} کانفیگ روی {len(by_server)} پنل")
        lines.append(f"🗑 حذف‌شده از لیست کاربران: {removed}")
        if failed:
            lines.append(f"⚠️ قابل بررسی نبود (خطای پنل): {failed}")
        if suspicious:
            lines.append(
                "🛑 برای احتیاط چیزی از این پنل‌ها حذف نشد (همهٔ کانفیگ‌ها پیدا نشدند): "
                + "، ".join(str(n) for n in suspicious)
            )
        await _notify_admins(bot, db, "\n".join(lines))

    return {"skipped": None, "checked": checked, "removed": removed, "failed": failed,
            "suspicious": suspicious, "run_at": _utc_iso()}