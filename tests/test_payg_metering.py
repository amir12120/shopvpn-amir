# -*- coding: utf-8 -*-
"""پرداخت به‌ازای مصرف: تحویل کانفیگ، کسر از کیف پول، قطع با کیف پول خالی و بازگشت پس از شارژ.

اجرا: python -m unittest tests.test_payg_metering -v
"""
import json
import os
import sys
import tempfile
import time
import types
import unittest
from unittest import mock

os.environ.setdefault("BOT_TOKEN", "123:test")
os.environ.setdefault("OWNER_ID", "1")


class _AnyModule(types.ModuleType):
    """جایگزین سبک aiogram تا تست در محیط بدون تلگرام هم اجرا شود."""

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        value = mock.MagicMock(name=name)
        setattr(self, name, value)
        return value


for _name in ("aiogram", "aiogram.filters", "aiogram.types", "aiogram.fsm",
              "aiogram.fsm.context", "aiogram.fsm.state", "aiogram.exceptions",
              "aiogram.enums", "aiogram.client", "aiogram.client.default",
              "aiogram.utils", "aiogram.utils.keyboard", "aiogram.dispatcher"):
    sys.modules.setdefault(_name, _AnyModule(_name))

import config  # noqa: E402

_TMP = tempfile.mkdtemp(prefix="payg_metering_test_")
config.DB_PATH = os.path.join(_TMP, "bot.db")

import payg  # noqa: E402
from database import Database  # noqa: E402
from quota_reconciler import QuotaReconciler  # noqa: E402

GIB = 1024 ** 3
USER_ID = 9001
RATES = {"gb_rate": 5000, "day_rate": 0, "user_rate": 0}


class FakeProvider:
    """حداقل رابط پنل: مصرف گزارش‌شده، سقف حجم و فعال/غیرفعال‌سازی."""

    supports_data_limit_sync = True

    def __init__(self, used=0, status="active"):
        self.used = used
        self.status = status
        self.limits = []
        self.enabled = []

    async def get_user_usage(self, username):
        return {"used_bytes": self.used, "data_limit_bytes": 0, "status": self.status,
                "reported_at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())}

    async def set_data_limit_bytes(self, username, limit_bytes, reenable=False):
        self.limits.append((int(limit_bytes), bool(reenable)))

    async def set_enabled(self, username, enabled):
        self.enabled.append((username, bool(enabled)))
        self.status = "active" if enabled else "disabled"


class PaygMeteringTest(unittest.TestCase):
    def setUp(self):
        self.db = Database(os.path.join(_TMP, f"payg{time.time_ns()}.db"))
        self.db.init_db(owner_id=1)
        payg.ensure_schema(self.db)
        self.db.set_setting("payg_panel_costs", json.dumps({"1": {"*": RATES}}))
        self.db.set_setting("payg_enabled", "1")
        self.server_id = self.db.add_panel_server("PayG panel", "3xui", "http://127.0.0.1:1", "u", "p")
        with self.db._get_conn() as conn:
            conn.execute("INSERT OR IGNORE INTO users(telegram_id, referral_credit) VALUES(?,?)",
                         (USER_ID, 100_000))
            conn.execute("UPDATE users SET referral_credit=? WHERE telegram_id=?", (100_000, USER_ID))
        self.config_id = self.db.add_custom_config(USER_ID, self.server_id, "payg_user", 0, 0, "vless://cfg")
        self.service_key = f"custom_config:{int(self.config_id)}"
        with self.db._get_conn() as conn:
            # همان نشانه‌ای که مسیر ساخت سرویس PayG ثبت می‌کند
            conn.execute("INSERT OR REPLACE INTO payg_provisioned_services(service_kind,service_id,user_id,created_at) "
                         "VALUES('vpn',?,?,?)", (self.service_key, USER_ID,
                                                   time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())))
        self._baseline(1 * GIB)
        # هر بار با تنظیمات تست، رویداد واقعی شارژ را بدون رشته‌ی پس‌زمینه اجرا می‌کنیم
        self._orig_kick = payg._kick_quota_enforcement
        payg._kick_quota_enforcement = lambda db: None

    def tearDown(self):
        payg._kick_quota_enforcement = self._orig_kick

    def _baseline(self, used):
        """ثبت اولین نمونه‌ی مصرف (مبنای صورتحساب، نه هزینه‌ی گذشته)."""
        self.db.record_usage_snapshot("vpn", self.service_key, int(used), uploaded_bytes=0, downloaded_bytes=0,
                                      source="panel:3xui", reported_at=time.strftime("%Y-%m-%dT%H:%M:%S+00:00",
                                                                                    time.gmtime()))

    def _activate(self):
        result = payg.activate_payg(self.db, USER_ID)
        self.assertTrue(result.get("ok"), result)
        with self.db._get_conn() as conn:
            account = dict(conn.execute("SELECT * FROM payg_accounts WHERE user_id=?", (USER_ID,)).fetchone())
        return account

    def _wallet(self):
        return int(self.db.get_wallet_credit(USER_ID) or 0)

    def _bill(self):
        return payg.PaygEngine(self.db, bot=None)._bill_once()

    def _transactions(self):
        with self.db._get_conn() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM payg_transactions WHERE user_id=? ORDER BY id", (USER_ID,)).fetchall()]

    # ------------------------------------------------------------------ wallet
    def test_usage_is_charged_to_the_wallet(self):
        account = self._activate()
        self._baseline(2 * GIB)
        self._bill()
        self.assertEqual(self._wallet(), 100_000 - 5_000)
        tx = self._transactions()
        self.assertEqual(len(tx), 1)
        self.assertEqual(int(tx[0]["used_bytes"]), 1 * GIB)
        self.assertEqual(int(tx[0]["amount"]), 5_000)
        with self.db._get_conn() as conn:
            row = conn.execute("SELECT month_used_bytes,month_cost FROM payg_accounts WHERE user_id=?",
                               (USER_ID,)).fetchone()
        self.assertEqual(int(row["month_used_bytes"]), 1 * GIB)
        self.assertEqual(int(row["month_cost"]), 5_000)
        self.assertEqual(int(account["initial_balance"]), 100_000)

    def test_unbillable_delta_is_preserved_not_partially_charged(self):
        self._activate()
        with self.db._get_conn() as conn:
            conn.execute("UPDATE users SET referral_credit=1000 WHERE telegram_id=?", (USER_ID,))
        self._baseline(2 * GIB)  # 1GB → 5000 تومان، بیشتر از موجودی
        self._bill()
        self.assertEqual(self._wallet(), 1000)          # هیچ کسر جزئی انجام نشد
        self.assertEqual(self._transactions(), [])
        with self.db._get_conn() as conn:
            service = conn.execute("SELECT last_billed_bytes FROM payg_services WHERE user_id=?",
                                   (USER_ID,)).fetchone()
        self.assertEqual(int(service["last_billed_bytes"]), 1 * GIB)  # مبنا جلو نرفت

    def test_empty_wallet_suspends_iterable_service_and_config_is_cut(self):
        self._activate()
        with self.db._get_conn() as conn:
            conn.execute("UPDATE users SET referral_credit=0 WHERE telegram_id=?", (USER_ID,))
        self._baseline(2 * GIB)
        self._bill()
        with self.db._get_conn() as conn:
            account = dict(conn.execute("SELECT * FROM payg_accounts WHERE user_id=?", (USER_ID,)).fetchone())
            pool = dict(conn.execute("SELECT * FROM quota_pools WHERE id=?", (int(account["quota_pool_id"]),)).fetchone())
        self.assertEqual(pool["status"], "exceeded")
        provider = FakeProvider(used=2 * GIB)
        reconciler = QuotaReconciler(self.db, vpn_provider_factory=lambda server: provider)
        asyncio_run(reconciler.reconcile_pool(pool))
        self.assertIn(("payg_user", False), provider.enabled)
        with self.db._get_conn() as conn:
            state = conn.execute("SELECT is_disabled,reason FROM quota_enforcement_state "
                                 "WHERE service_kind='vpn' AND service_id=?", (self.service_key,)).fetchone()
        self.assertIsNotNone(state)
        self.assertEqual(int(state["is_disabled"]), 1)
        self.assertEqual(state["reason"], "quota_exceeded")

    def test_top_up_raises_limit_and_restores_the_config_immediately(self):
        self._activate()
        with self.db._get_conn() as conn:
            conn.execute("UPDATE users SET referral_credit=0 WHERE telegram_id=?", (USER_ID,))
        self._baseline(2 * GIB)
        self._bill()
        with self.db._get_conn() as conn:
            account = dict(conn.execute("SELECT * FROM payg_accounts WHERE user_id=?", (USER_ID,)).fetchone())
        pool_id = int(account["quota_pool_id"])
        capped = int(self.db.get_quota_pool(pool_id)["limit_bytes"])
        provider = FakeProvider(used=2 * GIB)
        reconciler = QuotaReconciler(self.db, vpn_provider_factory=lambda server: provider)
        # حالت واقعی: کیف پول خالی شده و reconciler سرویس را غیرفعال کرده است
        asyncio_run(reconciler.reconcile_pool(self.db.get_quota_pool(pool_id)))
        self.assertIn(("payg_user", False), provider.enabled)
        self.db.add_wallet_credit(USER_ID, 50_000)
        refreshed = self.db.get_quota_pool(pool_id)
        self.assertGreater(int(refreshed["limit_bytes"]), capped)
        self.assertEqual(refreshed["status"], "active")
        asyncio_run(reconciler.reconcile_pool(refreshed))
        self.assertIn(("payg_user", True), provider.enabled)
        self.assertTrue(provider.limits)
        self.assertEqual(provider.limits[0][0], int(refreshed["limit_bytes"]))

    # ------------------------------------------------------------- rates/limits
    def test_missing_panel_tariff_falls_back_instead_of_unlimited(self):
        self.db.set_setting("payg_panel_costs", "{}")
        self._activate()
        rates, has_panel = payg._panel_traffic_rates(self.db, USER_ID)
        self.assertTrue(has_panel)
        self.assertTrue(any(rates), "fallback rates must not be all zero")
        limit = payg._affordable_payg_limit(self.db, USER_ID, 50_000,
                                           payg._billing_base_bytes(self.db, USER_ID), 0, payg.get_rates(self.db))
        self.assertGreater(limit, 0, "zero limit means unlimited in the quota API")

    def test_panel_tariff_is_used_for_the_allowance(self):
        self._activate()
        limit = payg._affordable_payg_limit(self.db, USER_ID, 10_000,
                                           payg._billing_base_bytes(self.db, USER_ID), 0, payg.get_rates(self.db))
        # ۱۰٬۰۰۰ تومان با نرخ ۵٬۰۰۰ تومان/گیگ ≈ ۲ گیگ
        self.assertGreaterEqual(limit, 2 * GIB)

    # ---------------------------------------------------------------- delivery
    def test_config_is_delivered_like_a_paid_order(self):
        try:
            import config_delivery
        except ModuleNotFoundError:
            # local venv without qrcode/Pillow: the CI job installs them, the stub only
            # lets this unit test exercise the call contract here.
            for _stub in ("qrcode", "PIL", "PIL.Image", "PIL.ImageDraw", "PIL.ImageFont"):
                sys.modules.setdefault(_stub, _AnyModule(_stub))
            import config_delivery

        captured = {}

        async def fake_deliver(bot, user_tg_id, product_name, links, **kwargs):
            captured["uid"] = user_tg_id
            captured["name"] = product_name
            captured["links"] = list(links)
            captured["kwargs"] = kwargs

        original = config_delivery.deliver_config_to_user
        config_delivery.deliver_config_to_user = fake_deliver
        try:
            delivered = asyncio_run(payg._deliver_payg_configs(object(), self.db, USER_ID,
                                                                ["vless://cfg"], header_text="h"))
        finally:
            config_delivery.deliver_config_to_user = original
        self.assertTrue(delivered)
        self.assertEqual(captured["uid"], USER_ID)
        self.assertEqual(captured["links"], ["vless://cfg"])
        self.assertIs(captured["kwargs"]["db"], self.db)
        self.assertEqual(captured["kwargs"]["final_price"], 0)

    def test_both_provisioning_flows_deliver_the_config(self):
        import io
        source = io.open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                      "payg.py"), encoding="utf-8").read()
        self.assertGreaterEqual(source.count("_deliver_payg_configs("), 3,
                                "both the single-panel and the multi-target flow must deliver the config")
        self.assertIn("deliver_config_to_user", source)

    def test_single_vpn_pool_carries_the_pool_ceiling_on_the_panel(self):
        self._activate()
        with self.db._get_conn() as conn:
            account = dict(conn.execute("SELECT * FROM payg_accounts WHERE user_id=?", (USER_ID,)).fetchone())
        pool = self.db.get_quota_pool(int(account["quota_pool_id"]))
        provider = FakeProvider(used=1 * GIB)
        reconciler = QuotaReconciler(self.db, vpn_provider_factory=lambda server: provider)
        asyncio_run(reconciler.reconcile_pool(pool))
        self.assertTrue(provider.limits, "single-member PAYG pool must set a panel volume limit")
        self.assertEqual(provider.limits[0][0], int(pool["limit_bytes"]))


def asyncio_run(coro):
    import asyncio
    return asyncio.run(coro)


if __name__ == "__main__":
    unittest.main()
