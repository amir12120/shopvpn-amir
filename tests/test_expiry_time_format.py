# -*- coding: utf-8 -*-
"""رگرسیون: قالب cutoff باید با created_at (CURRENT_TIMESTAMP، با فاصله) یکی باشد.

قبلاً cutoff با ``.isoformat()`` ساخته می‌شد و یک 'T' داشت. در مقایسهٔ رشته‌ای
SQLite، ``'2026-11-18 08:00:00' < '2026-11-18T07:27:00'`` درست است (چون
کد ۳۲ ' ' کوچک‌تر از 'T' است)، پس همهٔ ردیف‌های تازه هم «قدیمی‌تر از cutoff»
دیده می‌شدند و بلافاصله منقضی می‌شدند.
"""
import os
import tempfile
import time
import unittest
from datetime import datetime, timedelta

os.environ.setdefault("BOT_TOKEN", "123:test")
os.environ.setdefault("OWNER_ID", "1")

import config  # noqa: E402

_TMP = tempfile.mkdtemp(prefix="expiry_time_format_test_")
config.DB_PATH = os.path.join(_TMP, "bot.db")

from database import Database  # noqa: E402

USER_ID = 7101
LONG_AGO = (datetime.utcnow() - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M:%S")


class ExpiryTimeFormatTest(unittest.TestCase):
    def setUp(self):
        self.db = Database(os.path.join(_TMP, f"expiry{time.time_ns()}.db"))
        self.db.init_db(owner_id=1)
        with self.db._get_conn() as conn:
            conn.execute("INSERT OR IGNORE INTO users(telegram_id, first_name) VALUES(?,?)",
                         (USER_ID, "Expiry"))
            conn.execute("INSERT OR IGNORE INTO discount_codes(code, percent, max_uses, used_count) "
                         "VALUES('EXPIRY10', 10, 0, 0)")
            self.code_id = conn.execute(
                "SELECT id FROM discount_codes WHERE code='EXPIRY10'").fetchone()["id"]

    # ------------------------------------------------------------------ #
    # سفارش تخفیف‌دار (db/orders.py :: expire_stale_discount_orders)
    # ------------------------------------------------------------------ #
    def _add_order(self, created_at=None):
        discount_id = self.code_id
        if created_at is None:
            with self.db._get_conn() as conn:
                cur = conn.execute(
                    "INSERT INTO orders(user_id, product_id, status, discount_code_id, base_price, final_price) "
                    "VALUES(?,?, 'pending', ?, 1000, 900)",
                    (USER_ID, 1, discount_id),
                )
                return cur.lastrowid
        with self.db._get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO orders(user_id, product_id, status, discount_code_id, base_price, final_price, created_at) "
                "VALUES(?,?, 'pending', ?, 1000, 900, ?)",
                (USER_ID, 1, discount_id, created_at),
            )
            return cur.lastrowid

    def test_fresh_discount_order_is_not_expired(self):
        order_id = self._add_order()
        expired = self.db.expire_stale_discount_orders(60)
        self.assertNotIn(order_id, expired)
        self.assertEqual(self.db.get_order(order_id)["status"], "pending")

    def test_stale_discount_order_is_expired(self):
        order_id = self._add_order(created_at=LONG_AGO)
        expired = self.db.expire_stale_discount_orders(60)
        self.assertIn(order_id, expired)
        self.assertEqual(self.db.get_order(order_id)["status"], "expired")

    # ------------------------------------------------------------------ #
    # بلوپال (db/payments.py :: expire_stale_blupal_invoices)
    # ------------------------------------------------------------------ #
    def _add_blupal(self, token, created_at=None):
        with self.db._get_conn() as conn:
            if created_at is None:
                cur = conn.execute(
                    "INSERT INTO blupal_invoices(invoice_id, kind, ref_id, user_id, amount_toman, amount_rial) "
                    "VALUES(?, 'order', 1, ?, 1000, 10000)",
                    (token, USER_ID),
                )
            else:
                cur = conn.execute(
                    "INSERT INTO blupal_invoices(invoice_id, kind, ref_id, user_id, amount_toman, amount_rial, created_at) "
                    "VALUES(?, 'order', 1, ?, 1000, 10000, ?)",
                    (token, USER_ID, created_at),
                )
            return cur.lastrowid

    def _status(self, table, row_id):
        with self.db._get_conn() as conn:
            return conn.execute(f"SELECT status FROM {table} WHERE id=?", (row_id,)).fetchone()["status"]

    def test_fresh_blupal_invoice_is_not_expired(self):
        row_id = self._add_blupal("blupal-fresh")
        self.db.expire_stale_blupal_invoices(hours=1)
        self.assertEqual(self._status("blupal_invoices", row_id), "new")

    def test_stale_blupal_invoice_is_expired(self):
        row_id = self._add_blupal("blupal-stale", created_at=LONG_AGO)
        self.db.expire_stale_blupal_invoices(hours=1)
        self.assertEqual(self._status("blupal_invoices", row_id), "expired")

    # ------------------------------------------------------------------ #
    # Noapay (db/payments.py :: expire_stale_noapay_invoices)
    # ------------------------------------------------------------------ #
    def _add_noapay(self, token, created_at=None):
        with self.db._get_conn() as conn:
            if created_at is None:
                cur = conn.execute(
                    "INSERT INTO noapay_invoices(invoice_token, kind, ref_id, user_id, amount_toman, stars_count) "
                    "VALUES(?, 'order', 1, ?, 1000, 100)",
                    (token, USER_ID),
                )
            else:
                cur = conn.execute(
                    "INSERT INTO noapay_invoices(invoice_token, kind, ref_id, user_id, amount_toman, stars_count, created_at) "
                    "VALUES(?, 'order', 1, ?, 1000, 100, ?)",
                    (token, USER_ID, created_at),
                )
            return cur.lastrowid

    def test_fresh_noapay_invoice_is_not_expired(self):
        row_id = self._add_noapay("noapay-fresh")
        self.db.expire_stale_noapay_invoices()
        self.assertEqual(self._status("noapay_invoices", row_id), "new")

    def test_stale_noapay_invoice_is_expired(self):
        row_id = self._add_noapay("noapay-stale", created_at=LONG_AGO)
        self.db.expire_stale_noapay_invoices()
        self.assertEqual(self._status("noapay_invoices", row_id), "expired")


if __name__ == "__main__":
    unittest.main()
