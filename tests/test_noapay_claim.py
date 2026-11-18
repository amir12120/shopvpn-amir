# -*- coding: utf-8 -*-
"""رگرسیون: تأیید فاکتور NoapayBot باید یک‌بارمصرف و اتمیک باشد.

قبلاً ``try_verify_and_finalize`` بعد از تأیید وضعیت از API، فقط
``update_noapay_invoice_status(token, 'completed')`` می‌زد - بدون هیچ claim
اتمیک. اگر وب‌هوک و دکمه‌ی «بررسی وضعیت» هم‌زمان اجرا می‌شدند یا بررسی دوباره
انجام می‌شد، هر دو ``verified_now`` می‌گرفتند و سفارش/شارژ کیف پول دو بار
تحویل داده می‌شد (پول/سرویس رایگان).

همچنین لاگ عدم تطابق هش ``miniapp/auth.py`` نباید هیچ بخشی از bot_token را
(که کلید امضای initData است) در خود داشته باشد.
"""
import asyncio
import os
import tempfile
import time
import types
import unittest
from unittest import mock

os.environ.setdefault("BOT_TOKEN", "123:test")
os.environ.setdefault("OWNER_ID", "1")

# جایگزین سبک aiogram برای محیطی که aiogram نصب نیست (مثل تست‌های دیگر این پوشه).
import sys  # noqa: E402

def _stub_module(name):
    if name in sys.modules:
        return
    mod = types.ModuleType(name)

    def _getattr(attr, _mod=mod):
        if attr.startswith("__"):
            raise AttributeError(attr)
        value = mock.MagicMock(name=attr)
        setattr(_mod, attr, value)
        return value

    mod.__getattr__ = _getattr
    sys.modules[name] = mod


for _name in ("aiogram", "aiogram.filters", "aiogram.types", "aiogram.fsm",
              "aiogram.fsm.context", "aiogram.fsm.state", "aiogram.exceptions",
              "aiogram.enums", "aiogram.client", "aiogram.client.default",
              "aiogram.utils", "aiogram.utils.keyboard", "aiogram.dispatcher",
              # noapay_payment -> config_delivery -> qrcode (در محیط تست نصب نیست).
              "qrcode"):
    _stub_module(_name)

import config  # noqa: E402

_TMP = tempfile.mkdtemp(prefix="noapay_claim_test_")
config.DB_PATH = os.path.join(_TMP, "bot.db")

import noapay_payment  # noqa: E402
from database import Database  # noqa: E402
from miniapp.auth import validate_init_data  # noqa: E402

USER_ID = 8801
TOKEN = "np-claim-token"


class NoapayClaimTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.db = Database(os.path.join(_TMP, f"noapay{time.time_ns()}.db"))
        self.db.init_db(owner_id=1)
        with self.db._get_conn() as conn:
            conn.execute("INSERT OR IGNORE INTO users(telegram_id, first_name) VALUES(?,?)",
                         (USER_ID, "Noapay"))
        self.db.create_noapay_invoice(
            invoice_token=TOKEN, kind="wallet_topup", ref_id=1, user_id=USER_ID,
            amount_toman=50_000, stars_count=100,
        )

    def _patches(self):
        """API تأییدشده برمی‌گرداند تا مسیر «پرداخت شد» واقعاً اجرا شود."""
        async def fake_get_invoice(api_key, token):
            return {"status": "completed"}

        return (
            mock.patch.object(noapay_payment, "resolve_api_key", return_value="test-key"),
            mock.patch.object(noapay_payment.noapay_client, "get_invoice", fake_get_invoice),
        )

    async def test_second_verification_is_already_delivered(self):
        row = self.db.get_noapay_invoice_by_token(TOKEN)
        p1, p2 = self._patches()
        with p1, p2:
            first = await noapay_payment.try_verify_and_finalize(self.db, row)
            second = await noapay_payment.try_verify_and_finalize(
                self.db, self.db.get_noapay_invoice_by_token(TOKEN))
        self.assertEqual(first, "verified_now")
        self.assertEqual(second, "already_delivered")
        self.assertEqual(self.db.get_noapay_invoice_by_token(TOKEN)["status"], "completed")

    async def test_concurrent_verification_delivers_once(self):
        """وب‌هوک و بررسی دستی هم‌زمان: فقط یکی باید verified_now بگیرد."""
        row = self.db.get_noapay_invoice_by_token(TOKEN)
        p1, p2 = self._patches()
        with p1, p2:
            results = await asyncio.gather(
                noapay_payment.try_verify_and_finalize(self.db, row),
                noapay_payment.try_verify_and_finalize(self.db, row),
            )
        self.assertEqual(sorted(results), ["already_delivered", "verified_now"])

    def test_claim_is_one_shot(self):
        self.assertTrue(self.db.claim_noapay_invoice(TOKEN))
        self.assertFalse(self.db.claim_noapay_invoice(TOKEN))


class InitDataLoggingTest(unittest.TestCase):
    def test_failed_validation_does_not_log_bot_token(self):
        bot_token = "123456789:SECRET-TOKEN"
        init_data = "auth_date=1&user=%7B%7D&hash=deadbeef"
        with self.assertLogs("miniapp.auth", level="WARNING") as captured:
            self.assertIsNone(validate_init_data(init_data, bot_token))
        output = "\n".join(captured.output)
        self.assertNotIn(bot_token[-6:], output)
        self.assertNotIn(bot_token, output)


if __name__ == "__main__":
    unittest.main()
