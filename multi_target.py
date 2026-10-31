# -*- coding: utf-8 -*-
"""همگام‌سازی پنل‌های اضافه‌ی یک سرویس چندپنلی با عملیات روی سرویس اصلی (حذف/قطع)."""

import asyncio
import logging

from panel_providers import get_provider

logger = logging.getLogger(__name__)


async def delete_linked_panel_users(db, custom_config_id) -> None:
    """کاربران پنل‌های اضافه‌ی سرویس را از پنل‌ها و رکوردهای محلی پاک می‌کند (بدون پرتاب خطا)."""
    try:
        links = await asyncio.to_thread(db.delete_config_panel_links, int(custom_config_id))
    except Exception:
        logger.exception("panel links lookup failed for config %s", custom_config_id)
        return
    for link in links:
        try:
            server = await asyncio.to_thread(db.get_panel_server, link["panel_server_id"])
            if server:
                await get_provider(server).delete_user(link["username"])
        except Exception:
            logger.exception("extra panel user delete failed (config=%s, link=%s)", custom_config_id, link["id"])


async def set_linked_panel_users_enabled(db, custom_config_id, enabled: bool) -> None:
    try:
        links = await asyncio.to_thread(db.panel_links_for_config, int(custom_config_id))
    except Exception:
        return
    for link in links:
        try:
            server = await asyncio.to_thread(db.get_panel_server, link["panel_server_id"])
            if server:
                await get_provider(server).set_enabled(link["username"], bool(enabled))
        except Exception:
            logger.exception("extra panel user toggle failed (config=%s, link=%s)", custom_config_id, link["id"])
