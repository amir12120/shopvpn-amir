# -*- coding: utf-8 -*-
"""کلید و قیمت‌گذاری «پرداخت به‌ازای مصرف» از داخل ادمین بات (بخش فروش و محصولات)."""
import io
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

_TMP = tempfile.mkdtemp(prefix="payg_admin_settings_test_")
config.DB_PATH = os.path.join(_TMP, "bot.db")

import extra_settings_schema as xs  # noqa: E402
import payg  # noqa: E402
from database import Database  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class PaygAdminSettingsTest(unittest.TestCase):
    def setUp(self):
        self.db = Database(os.path.join(_TMP, f"paygset{time.time_ns()}.db"))
        self.db.init_db(owner_id=1)
        payg.ensure_schema(self.db)

    def _group(self):
        groups = [g for g in xs.groups_for("bot") if g["id"] == "payg"]
        self.assertEqual(len(groups), 1, "گروه payg باید در تنظیمات ادمین بات تعریف شده باشد")
        return groups[0]

    def test_bot_form_exposes_the_toggle_and_the_price(self):
        group = self._group()
        fields = {f["key"]: f for f in group["fields"]}
        self.assertEqual(set(fields), {"payg_enabled", "payg_rates"})
        self.assertEqual(fields["payg_enabled"]["type"], "bool")
        self.assertEqual(fields["payg_rates"]["type"], "number")
        self.assertEqual(fields["payg_rates"]["min"], 1)
        self.assertIn("payg_enabled", xs.allowed_keys("bot"))
        self.assertIn("payg_rates", xs.allowed_keys("bot"))

    def test_switch_and_price_are_saved_from_the_bot(self):
        xs.save_values(self.db, "bot", {"payg_enabled": "0", "payg_rates": "8,500"})
        self.assertEqual(self.db.get_setting("payg_enabled"), "0")
        self.assertEqual(payg.get_rates(self.db), [8500, 8500, 8500, 8500])
        xs.save_values(self.db, "bot", {"payg_enabled": "1"})
        self.assertEqual(self.db.get_setting("payg_enabled"), "1")
        self.assertEqual(payg.get_rates(self.db)[0], 8500, "قیمت نباید با روشن‌کردن کلید از دست برود")

    def test_price_rejects_non_numbers(self):
        with self.assertRaises(xs.SettingsValidationError):
            xs.save_values(self.db, "bot", {"payg_rates": "abc"})
        with self.assertRaises(xs.SettingsValidationError):
            xs.save_values(self.db, "bot", {"payg_rates": "0"})

    def test_rates_accept_legacy_json_and_plain_numbers(self):
        self.db.set_setting("payg_rates", json.dumps([7000, 6000, 5000, 4000]))
        self.assertEqual(payg.get_rates(self.db), [7000, 6000, 5000, 4000])
        self.db.set_setting("payg_rates", "9000")
        self.assertEqual(payg.get_rates(self.db), [9000] * 4)
        self.db.set_setting("payg_rates", "not-a-rate")
        self.assertEqual(payg.get_rates(self.db), list(payg.DEFAULT_RATES))

        # پنل وب هم همان مقدار را می‌خواند (rate اولین پله است)
        self.db.set_setting("payg_rates", "12000")
        self.assertEqual(payg.get_rates(self.db)[0], 12000)

    def test_admin_button_lives_in_the_products_hub(self):
        source = io.open(os.path.join(ROOT, "keyboards.py"), encoding="utf-8").read()
        self.assertIn('"adm_payg_settings", "💳 پرداخت به‌ازای مصرف (قیمت/خاموش-روشن)", "adm_xs_g:payg"', source)
        self.assertIn('("قیمت و تخفیف", ["adm_discounts_menu", "adm_payg_settings"])', source)
        self.assertIn('"payg": "adm_payg_settings"', source)
        self.assertIn('if key == "adm_payg_settings":', source)


if __name__ == "__main__":
    unittest.main()
