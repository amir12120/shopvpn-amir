# -*- coding: utf-8 -*-
"""F139 — حذف دستی کانفیگ‌هایی که دیگر روی پنل وجود ندارند."""
import asyncio
import io
import os
import tempfile
import time
import unittest
from unittest import mock

os.environ.setdefault("BOT_TOKEN", "123:test")
os.environ.setdefault("OWNER_ID", "1")

import config  # noqa: E402

_TMP = tempfile.mkdtemp(prefix="config_audit_test_")
config.DB_PATH = os.path.join(_TMP, "bot.db")

import config_audit  # noqa: E402
from database import Database  # noqa: E402
from panel_providers.base import PanelError  # noqa: E402

USER_ID = 7701
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class FakeProvider:
    """provider پنل: فهرست کلاینت‌های پنل و/یا پرس‌وجوی تک‌تک."""

    def __init__(self, existing=None, inventory_error=None, error=None, has_inventory=True,
                 fail_once=()):
        self.existing = set(existing or ())
        self.inventory_error = inventory_error
        self.error = error
        self.has_inventory = has_inventory
        self.fail_once = set(fail_once)
        self.lookup_calls = []
        if has_inventory:
            self.list_client_usernames = self._inventory

    async def _inventory(self):
        if self.inventory_error:
            raise self.inventory_error
        return set(self.existing)

    async def get_user(self, username):
        self.lookup_calls.append(username)
        if self.error:
            raise self.error
        if username in self.fail_once:
            self.fail_once.discard(username)
            raise PanelError(f"کاربری با نام «{username}» روی پنل پیدا نشد.")
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

    def tearDown(self):
        config_audit.get_provider = self._orig

    def _config(self, username, volume_gb=10, days=30):
        return int(self.db.add_custom_config(USER_ID, self.server_id, username, volume_gb, days,
                                             "vless://" + username))

    def _collect(self):
        return asyncio.run(config_audit.collect_audit(self.db))

    def _apply(self, items):
        return asyncio.run(config_audit.apply_missing(self.db, items, admin_id=555))

    def _status(self, config_id):
        with self.db._get_conn() as conn:
            return conn.execute("SELECT status, enabled FROM custom_configs WHERE id=?",
                                (int(config_id),)).fetchone()

    def _visible_configs(self):
        rows = self.db.get_user_custom_configs(USER_ID)
        return [r for r in rows if (r["status"] or "active") != "deleted"]

    def _list_visible_configs(self):
        """همان چیزی که منوی «سفارش‌ها و کانفیگ‌های شما» می‌بیند."""
        return [r["username"] for r in self.db.get_custom_configs_for_user(USER_ID)]

    # ------------------------------------------------------- inventory path
    def test_config_missing_from_panel_inventory_is_reported_and_removed(self):
        kept = self._config("still_here")
        gone = self._config("deleted_on_panel")
        self.provider.existing = {"still_here"}
        result = self._collect()
        self.assertEqual(result["checked"], 2)
        self.assertEqual([m["username"] for m in result["missing"]], ["deleted_on_panel"])
        self.assertEqual(result["method"]["Panel A"], "inventory")
        # پیش‌نمایش چیزی را حذف نمی‌کند
        self.assertEqual(self._status(gone)["status"], "active")

        removed = self._apply(result["missing"])
        self.assertEqual(removed, 1)
        self.assertEqual(self._status(gone)["status"], "deleted")
        self.assertEqual(self._status(gone)["enabled"], 0)
        self.assertEqual(self._status(kept)["status"], "active")
        self.assertEqual([r["username"] for r in self._visible_configs()], ["still_here"])
        # منوی «سفارش‌ها و کانفیگ‌های شما» هم نباید کانفیگ حذف‌شده را نشان دهد
        self.assertEqual(self._list_visible_configs(), ["still_here"])
        self.assertEqual(len(self.db.get_custom_configs_for_user(USER_ID, include_deleted=True)), 2)
        self.assertEqual(len(self.db.get_user_custom_configs(USER_ID, include_deleted=True)), 2)
        history = self.db.get_custom_config_history(gone)
        self.assertIn("removed_from_panel", [h["event_type"] for h in history])

    def test_unreachable_panel_is_skipped_completely(self):
        self._config("a")
        self._config("b")
        self.provider.inventory_error = PanelError("خطا در اتصال به پنل: Cannot connect to host")
        result = self._collect()
        self.assertEqual(result["missing"], [])
        self.assertEqual(result["offline"], ["Panel A"])
        self.assertEqual(result["checked"], 0)
        self.assertEqual(len(self._visible_configs()), 2)

    def test_empty_inventory_for_a_populated_panel_is_suspicious(self):
        ids = [self._config(f"u{i}") for i in range(3)]
        self.provider.existing = set()
        result = self._collect()
        self.assertEqual(result["missing"], [])
        self.assertEqual(result["suspicious"], ["Panel A"])
        for cid in ids:
            self.assertEqual(self._status(cid)["status"], "active")

    def test_single_config_panel_is_still_cleaned(self):
        cid = self._config("only_one")
        self.provider.existing = set()
        result = self._collect()
        self.assertEqual([m["username"] for m in result["missing"]], ["only_one"])
        self._apply(result["missing"])
        self.assertEqual(self._status(cid)["status"], "deleted")

    # --------------------------------------------------------- lookup path
    def test_provider_without_inventory_uses_double_lookup(self):
        kept = self._config("here")
        gone = self._config("gone")
        self.provider = FakeProvider(existing={"here"}, has_inventory=False)
        config_audit.get_provider = lambda server: self.provider
        result = self._collect()
        self.assertEqual(result["method"]["Panel A"], "lookup")
        self.assertEqual([m["username"] for m in result["missing"]], ["gone"])
        self.assertEqual(self._status(kept)["status"], "active")

    def test_flaky_not_found_is_rechecked_before_reporting(self):
        cid = self._config("flaky")
        self._config("stays")
        self.provider = FakeProvider(existing={"flaky", "stays"}, has_inventory=False,
                                     fail_once={"flaky"})
        config_audit.get_provider = lambda server: self.provider
        result = self._collect()
        self.assertEqual(result["missing"], [])
        self.assertEqual(self._status(cid)["status"], "active")

    def test_lookup_connection_error_never_reports_missing(self):
        self._config("a")
        self.provider = FakeProvider(existing=set(), has_inventory=False,
                                     error=PanelError("خطا در اتصال به پنل: timeout"))
        config_audit.get_provider = lambda server: self.provider
        result = self._collect()
        self.assertEqual(result["missing"], [])
        self.assertEqual(result["failed"], 1)

    # ------------------------------------------------------------- misc
    def test_inactive_panel_is_not_audited(self):
        self._config("gone")
        with self.db._get_conn() as conn:
            conn.execute("UPDATE panel_servers SET is_active=0 WHERE id=?", (self.server_id,))
        result = self._collect()
        self.assertEqual(result["checked"], 0)
        self.assertEqual(result["missing"], [])

    def test_no_schedule_anymore_but_button_is_wired(self):
        cleanup_src = io.open(os.path.join(ROOT, "cleanup_loop.py"), encoding="utf-8").read()
        kb_src = io.open(os.path.join(ROOT, "keyboards.py"), encoding="utf-8").read()
        admin_src = io.open(os.path.join(ROOT, "handlers_admin.py"), encoding="utf-8").read()
        self.assertNotIn("config_audit.audit_configs_once", cleanup_src)
        self.assertIn('"adm_purge_missing_configs"', kb_src)
        self.assertIn('("پنل‌ها و نودها", ["adm_panel_servers", "adm_purge_missing_configs"', kb_src)
        self.assertIn('F.data == "adm_purge_missing_configs"', admin_src)
        self.assertIn('F.data == "adm_pmc_apply"', admin_src)
        self.assertIn('config_audit.collect_audit', admin_src)
        self.assertIn('config_audit.apply_missing', admin_src)


class _FakeResp:
    def __init__(self, status, payload):
        self.status = status
        self.payload = payload

    async def json(self):
        return self.payload

    async def text(self):
        return str(self.payload)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeSession:
    def __init__(self, resp):
        self._resp = resp

    def get(self, url):
        return self._resp

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class ThreeXuiInventoryTest(unittest.TestCase):
    """متد جدید 3x-ui که «روشن بودن پنل» و فهرست کلاینت‌ها را یک‌جا می‌دهد."""

    def _provider(self, status, payload):
        from panel_providers.threexui_provider import ThreeXUIProvider
        provider = ThreeXUIProvider({"api_url": "http://panel", "api_username": "u",
                                     "api_password": "p", "xui_sub_base_url": "http://sub"})
        provider._session = lambda: _FakeSession(_FakeResp(status, payload))
        return provider

    def test_reads_emails_from_every_inbound(self):
        import json as _json
        payload = {"success": True, "obj": [
            {"settings": _json.dumps({"clients": [{"email": "u1"}, {"email": "u2"}]})},
            {"settings": {"clients": [{"email": "u3"}, {"email": None}]}},
            {"settings": "not-json"},
        ]}
        provider = self._provider(200, payload)
        self.assertEqual(asyncio.run(provider.list_client_usernames()), {"u1", "u2", "u3"})

    def test_empty_panel_returns_empty_set(self):
        provider = self._provider(200, {"success": True, "obj": []})
        self.assertEqual(asyncio.run(provider.list_client_usernames()), set())

    def test_auth_error_raises_so_the_panel_is_treated_as_down(self):
        provider = self._provider(401, {})
        with self.assertRaises(PanelError):
            asyncio.run(provider.list_client_usernames())

    def test_unsuccessful_answer_raises(self):
        provider = self._provider(200, {"success": False, "msg": "boom"})
        with self.assertRaises(PanelError):
            asyncio.run(provider.list_client_usernames())


if __name__ == "__main__":
    unittest.main()
