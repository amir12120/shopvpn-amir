# -*- coding: utf-8 -*-
"""بررسی روزانهٔ وجود کانفیگ‌ها روی پنل (F139).

هر شب (پیش‌فرض: ساعت ۱۲ شب به وقت تهران) یک‌بار همهٔ کانفیگ‌های فعالی که روی
پنل ساخته شده‌اند با خود پنل مقایسه می‌شوند؛ اگر کاربر/کلاینت دیگر روی پنل
وجود نداشته باشد (ادمین یا خود کاربر از پنل پاکش کرده)، رکورد از لیست
«کانفیگ‌های من» کاربر حذف می‌شود.

اصل ایمنی (مهم): حذف فقط وقتی انجام می‌شود که «اطمینان کامل» داشته باشیم پنل
در دسترس است و کاربر واقعاً پاک شده است. برای همین:

۱) قبل از بررسی، سلامت پنل با test_connection (اتصال + احراز هویت) چک می‌شود؛
   پنل خاموش/در دسترس نبودنِ پنل یعنی «هیچ حذفی» برای آن پنل.
۲) هر کانفیگی که «پیدا نشد» می‌دهد بلافاصله حذف نمی‌شود؛ یک‌بار دیگر هم
   مستقیم از پنل پرسیده می‌شود و فقط اگر بار دوم هم صریحاً نبود، حذف می‌شود.
۳) اگر همهٔ کانفیگ‌های یک پنل (وقتی بیشتر از یکی دارند) «پیدا نشد»
   برگردانند (پاسخ ناقص/خراب پنل)، هیچ‌چیز حذف نمی‌شود.
۴) درست قبل از ثبت حذف، سلامت پنل دوباره چک می‌شود؛ اگر پنل در همین فاصله از
   دسترس خارج شده باشد، حذف انجام نمی‌شود.

خطای شبکه، timeout، 401/403 و هر خطای نامشخص فقط «failed» شمرده می‌شود و هرگز
باعث حذف نیست.
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
    هر خطای دیگری (اتصال، timeout، احراز هویت، پاسخ نامعتبر) «نامشخص» است.
    """
    text = str(exc or "").strip().lower()
    return any(marker in text for marker in NOT_FOUND_MARKERS)


async def _panel_reachable(provider) -> bool:
    """اتصال و احراز هویت پنل در همین لحظه سالم است؟ (هر خطایی = خیر)"""
    try:
        return bool(await provider.test_connection())
    except Exception as exc:
        logger.info("config-audit: پنل در دسترس نیست: %s", str(exc)[:200])
        return False


async def _audit_panel(provider, rows):
    """(missing, unknown)

    missing = پنل دو بار پشت‌سرهم و صریح گفت وجود ندارد
    unknown = قابل تشخیص نبود (خطای پنل) و هرگز حذف نمی‌شود
    """
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
        # تأیید دوباره: اگر بار دوم پیدا شد یا خطای دیگری داد، چیزی حذف نمی‌شود.
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
    offline: list[str] = []
    suspicious: list[str] = []
    for server_id, items in by_server.items():
        server = await asyncio.to_thread(db.get_panel_server, server_id)
        if not server or not server["is_active"]:
            continue
        try:
            provider = get_provider(server)
        except Exception:
            logger.exception("config-audit: ساخت provider برای پنل #%s ناموفق بود", server_id)
            offline.append(str(server["name"]))
            continue
        if not await _panel_reachable(provider):
            offline.append(str(server["name"]))
            logger.warning(
                "config-audit: پنل «%s» در دسترس نیست؛ %s کانفیگ آن بررسی و حذف نشد.",
                server["name"], len(items),
            )
            continue

        missing, unknown = await _audit_panel(provider, items)
        checked += len(items)
        failed += unknown
        if not missing:
            continue
        if len(missing) == len(items) and len(items) >= 2:
            suspicious.append(str(server["name"]))
            logger.warning(
                "config-audit: هیچ‌کدام از %s کانفیگ پنل «%s» روی پنل پیدا نشد؛ برای احتیاط چیزی حذف نشد.",
                len(items), server["name"],
            )
            continue
        # آخرین دروازه: اگر پنل در همین فاصله از دسترس خارج شده، حذف نکن.
        if not await _panel_reachable(provider):
            offline.append(str(server["name"]))
            logger.warning(
                "config-audit: پنل «%s» حین بررسی قطع شد؛ %s کانفیگ ناموجود حذف نشد.",
                server["name"], len(missing),
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

    if removed or suspicious or offline or failed:
        lines = ["🧾 F139 — بررسی روزانهٔ کانفیگ‌های حذف‌شده از پنل", ""]
        lines.append(f"🔍 بررسی‌شده: {checked} کانفیگ روی {len(by_server)} پنل")
        lines.append(f"🗑 حذف‌شده از لیست کاربران: {removed}")
        if failed:
            lines.append(f"⚠️ قابل بررسی نبود (خطای پنل): {failed}")
        if offline:
            lines.append("🔌 پنل در دسترس نبود و بررسی نشد (هیچ حذفی انجام نشد): "
                         + "، ".join(offline))
        if suspicious:
            lines.append("🛑 برای احتیاط چیزی از این پنل‌ها حذف نشد (هیچ کانفیگی روی پنل پیدا نشد): "
                         + "، ".join(suspicious))
        await _notify_admins(bot, db, "\n".join(lines))

    return {"skipped": None, "checked": checked, "removed": removed, "failed": failed,
            "offline": offline, "suspicious": suspicious, "run_at": _utc_iso()}
