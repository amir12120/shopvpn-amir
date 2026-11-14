# -*- coding: utf-8 -*-
"""F139 — بررسی روزانهٔ وجود کانفیگ‌ها روی پنل و حذف رکوردهای پاک‌شده از پنل."""
import asyncio
import os
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

os.environ.setdefault("BOT_TOKEN", "123:test")
os.environ.setdefault("OWNER_ID", "1")

import config  # noqa: E402

_TMP = tempfile.mkdtemp(prefix="config_audit_test_")
config.DB_PATH = os.path.join(_TMP, "bot.db")

import config_audit  # noqa: E402
from database import Database  # noqa: E402
from panel_providers.base import PanelError  # noqa: E402

TEHRAN = timezone(timedelta(hours=3, minutes=30))
USER_ID = 7701


class FakeProvider:
    """get_user فقط برای نام‌هایی که روی «پنل» هستن��د موفق است."""

    def __init__(self, existing, error=None):
        self.existing = set(existing)
        self.error = error
        self.checked = []

    async def get_user(self, username):
        self.checked.append(username)
        if self.error:
            raise self.error
        if username not in self.existing:
            raise PanelError(f"کاربری با نام «{username}» روی پنل پیدا نشد.")
        return mock.Mock(username=username, subscription_url="http://sub/" + username)


class ConfigAuditTest(unittest.TestCase):
    def setUp(self):
        self.db = Database(os.path.join(_TMP, f"audit{time.time_ns()}.db"))
        self.db.init_db(owner_id=1)
        self.server_id = self.db.add_panel_server("Panel A", "3xui", "http://127.0.0.1:1", "u", "p")
        with self.db._get_conn() as conn:
            conn.execute("INSERT OR IGNORE INTO users(telegram_id) VALUES(?)", (USER_ID,))
        self.provider = FakeProvider(existing=set())
        self._orig = config_audit.get_provider
        config_audit.get_provider = lambda server: self.provider
        self._orig_now = config_audit._tehran_now
        config_audit._tehran_now = lambda: datetime(2026, 11, 15, 0, 5, tzinfo=TEHRAN)

    def tearDown(self):
        config_audit.get_provider = self._orig
        config_audit._tehran_now = self._orig_now

    def _config(self, username, volume_gb=10, days=30):
        return int(self.db.add_custom_config(USER_ID, self.server_id, username, volume_gb, days,
                                             "vless://" + username))

    def _run(self, **kwargs):
        return asyncio.run(config_audit.audit_configs_once(None, self.db, **kwargs))

    def _status(self, config_id):
        with self.db._get_conn() as conn:
            return conn.execute("SELECT status, enabled FROM custom_configs WHERE id=?",
                                (int(config_id),)).fetchone()

    def _visible_configs(self):
        rows = self.db.get_user_custom_configs(USER_ID)
        return [r for r in rows if (r["status"] or "active") != "deleted"]

    # ------------------------------------------------------------------ basics
    def test_config_deleted_from_panel_is_removed_from_the_user_list(self):
        kept = self._config("still_here")
        gone = self._config("deleted_on_panel")
        self.provider.existing = {"still_here"}
        result = self._run(force=True)
        self.assertEqual(result["removed"], 1)
        self.assertEqual(result["checked"], 2)
        self.assertEqual(self._status(gone)["status"], "deleted")
        self.assertEqual(self._status(gone)["enabled"], 0)
        self.assertEqual(self._status(kept)["status"], "active")
        self.assertEqual([r["username"] for r in self._visible_configs()], ["still_here"])
        history = self.db.get_custom_config_history(gone)
        self.assertIn("removed_from_panel", [h["event_type"] for h in history])

    def test_panel_connection_error_never_deletes(self):
        self._config("a")
        self._config("b")
        self.provider.error = PanelError("خطا در اتصال به پنل: timeout")
        result = self._run(force=True)
        self.assertEqual(result["removed"], 0)
        self.assertEqual(result["failed"], 2)
        self.assertEqual(len(self._visible_configs()), 2)

    def test_all_configs_missing_looks_like_a_broken_panel_response(self):
        ids = [self._config(f"u{i}") for i in range(5)]
        self.provider.existing = set()
        result = self._run(force=True)
        self.assertEqual(result["removed"], 0)
        self.assertEqual(result["suspicious"], ["Panel A"])
        for cid in ids:
            self.assertEqual(self._status(cid)["status"], "active")

    def test_one_missing_below_the_guard_is_removed(self):
        ids = [self._config(f"u{i}") for i in range(4)]
        self.provider.existing = {f"u{i}" for i in range(1, 4)}
        result = self._run(force=True)
        self.assertEqual(result["removed"], 1)
        self.assertEqual(self._status(ids[0])["status"], "deleted")

    # --------------------------------------------------------------- schedule
    def test_runs_at_most_once_a_day(self):
        self._config("gone")
        first = self._run()
        self.assertIsNone(first["skipped"])
        self.assertEqual(first["removed"], 1)
        second = self._run()
        self.assertEqual(second["skipped"], "already_ran")

    def test_schedule_guard_holds_until_the_configured_hour(self):
        config_audit._tehran_now = lambda: datetime(2026, 11, 14, 23, 40, tzinfo=TEHRAN)
        self._config("gone")
        original_schedule = config_audit.SCHEDULE
        config_audit.SCHEDULE = (23, 50)
        try:
            result = self._run()
        finally:
            config_audit.SCHEDULE = original_schedule
        self.assertEqual(result["skipped"], "before_schedule")
        self.assertEqual(result["removed"], 0)
        self.assertEqual(len(self._visible_configs()), 1)

    def test_inactive_panel_is_not_audited(self):
        self._config("gone")
        with self.db._get_conn() as conn:
            conn.execute("UPDATE panel_servers SET is_active=0 WHERE id=?", (self.server_id,))
        result = self._run(force=True)
        self.assertEqual(result["removed"], 0)
        self.assertEqual(result["checked"], 0)


if __name__ == "__main__":
    unittest.main()
