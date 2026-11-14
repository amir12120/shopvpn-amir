# -*- coding: utf-8 -*-
"""عملیات کیف پول در ادمین: افزایش گروهی (باگ قبلی)، صفر کردن همه، تعیین مبلغ یک کاربر."""
import io
import os
import tempfile
import time
import unittest

os.environ.setdefault("BOT_TOKEN", "123:test")
os.environ.setdefault("OWNER_ID", "1")

import config  # noqa: E402

_TMP = tempfile.mkdtemp(prefix="wallet_admin_ops_test_")
config.DB_PATH = os.path.join(_TMP, "bot.db")

from database import Database  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class WalletAdminOpsTest(unittest.TestCase):
    def setUp(self):
        self.db = Database(os.path.join(_TMP, f"wallet{time.time_ns()}.db"))
        self.db.init_db(owner_id=1)
        self.rich = 1001
        self.poor = 1002
        self.debtor = 1003
        self.empty = 1004
        with self.db._get_conn() as conn:
            conn.executemany(
                "INSERT OR IGNORE INTO users(telegram_id, username, first_name, referral_credit) VALUES(?,?,?,?)",
                [
                    (self.rich, "RichUser", "Rich", 50000),
                    (self.poor, "poor_user", "Poor", 1200),
                    (self.debtor, "debtor", "Debtor", -3000),
                    (self.empty, "empty", "Empty", 0),
                ],
            )

    def _tx_kinds(self, uid):
        with self.db._get_conn() as conn:
            return [r["kind"] for r in conn.execute(
                "SELECT kind FROM wallet_transactions WHERE user_id=? ORDER BY id", (uid,)).fetchall()]

    # -------------------------------------------------- افزایش گروهی موجودی
    def test_bulk_credit_preview_and_apply_exist_and_work(self):
        # رگرسیون: این تابع‌ها نبودند و بات روی هر عدد مثبتی خطا می‌داد.
        self.assertTrue(hasattr(self.db, "preview_bulk_wallet_credit"))
        self.assertTrue(hasattr(self.db, "apply_bulk_wallet_credit"))

        rows = self.db.preview_bulk_wallet_credit("all", "all", 5000)
        by_id = {r["telegram_id"]: r for r in rows}
        self.assertEqual(len(rows), 4)
        self.assertEqual(by_id[self.rich]["balance_after"], 55000)
        self.assertEqual(by_id[self.debtor]["balance_after"], 2000)

        updated = self.db.apply_bulk_wallet_credit([r["telegram_id"] for r in rows], 5000, "تست")
        self.assertEqual(updated, 4)
        self.assertEqual(self.db.get_wallet_credit(self.rich), 55000)
        self.assertEqual(self.db.get_wallet_credit(self.debtor), 2000)
        self.assertIn("admin_bulk_credit", self._tx_kinds(self.rich))

    def test_bulk_credit_preview_respects_filters(self):
        with self.db._get_conn() as conn:
            conn.execute("UPDATE users SET is_blocked=1 WHERE telegram_id=?", (self.poor,))
        rows = self.db.preview_bulk_wallet_credit("blocked", "all", 100)
        self.assertEqual([r["telegram_id"] for r in rows], [self.poor])

    # ------------------------------------------------------ صفر کردن همه
    def test_zero_wallets_preview_skips_zero_balances(self):
        rows = self.db.preview_zero_wallets()
        ids = {r["telegram_id"] for r in rows}
        self.assertEqual(ids, {self.rich, self.poor, self.debtor})
        self.assertNotIn(self.empty, ids)
        self.assertTrue(all(r["balance_after"] == 0 for r in rows))

    def test_zero_wallets_applies_to_everyone(self):
        ids = [r["telegram_id"] for r in self.db.preview_zero_wallets()]
        updated = self.db.apply_zero_wallets(ids, "تست صفر کردن")
        self.assertEqual(updated, 3)
        for uid in (self.rich, self.poor, self.debtor, self.empty):
            self.assertEqual(self.db.get_wallet_credit(uid), 0)
        self.assertIn("admin_wallet_zero", self._tx_kinds(self.rich))

    def test_zero_wallets_is_idempotent(self):
        self.db.apply_zero_wallets([self.rich, self.poor, self.debtor], None)
        self.assertEqual(self.db.apply_zero_wallets([self.rich, self.poor, self.debtor], None), 0)

    # ------------------------------------------- تعیین مبلغ یک کاربر مشخص
    def test_find_user_by_numeric_id_and_username(self):
        by_id = self.db.find_admin_user(str(self.rich))
        self.assertEqual(by_id["telegram_id"], self.rich)
        self.assertEqual(by_id["balance"], 50000)
        self.assertEqual(self.db.find_admin_user("@richuser")["telegram_id"], self.rich)
        self.assertEqual(self.db.find_admin_user("poor_user")["telegram_id"], self.poor)
        self.assertIsNone(self.db.find_admin_user("no_such_user"))
        self.assertIsNone(self.db.find_admin_user(""))

    def test_set_wallet_balance_sets_an_absolute_amount(self):
        before, after = self.db.set_wallet_balance(self.rich, 7000, "تنظیم دستی")
        self.assertEqual((before, after), (50000, 7000))
        self.assertEqual(self.db.get_wallet_credit(self.rich), 7000)
        self.assertIn("admin_wallet_set", self._tx_kinds(self.rich))

        # کاهش موجودی هم مجاز است و مقدار مطلق جایگزین می‌شود
        self.db.set_wallet_balance(self.rich, 0, "صفر دستی")
        self.assertEqual(self.db.get_wallet_credit(self.rich), 0)

    def test_set_wallet_balance_unknown_user_or_negative(self):
        self.assertIsNone(self.db.set_wallet_balance(999999, 100, None))
        self.assertIsNone(self.db.set_wallet_balance(self.rich, -5, None))
        self.assertEqual(self.db.get_wallet_credit(self.rich), 50000)

    # ------------------------------------------------------------ وایرینگ UI
    def test_buttons_and_handlers_are_wired(self):
        kb_src = io.open(os.path.join(ROOT, "keyboards.py"), encoding="utf-8").read()
        admin_src = io.open(os.path.join(ROOT, "handlers_admin.py"), encoding="utf-8").read()
        self.assertIn('("adm_wallet_set", "💳 تعیین مبلغ کیف پول کاربر", "adm_wallet_set")', kb_src)
        self.assertIn('("adm_wallet_zero", "🧹 صفر کردن کیف پول همه کاربران", "adm_wallet_zero")', kb_src)
        self.assertIn('"adm_wallet_set", "adm_wallet_zero"', kb_src)
        self.assertIn('def admin_wallet_zero_confirm_kb', kb_src)
        self.assertIn('def admin_wallet_set_confirm_kb', kb_src)
        self.assertIn('F.data == "adm_wallet_zero"', admin_src)
        self.assertIn('F.data == "adm_wallet_set"', admin_src)
        self.assertIn('F.data == "adm_wz_confirm"', admin_src)
        self.assertIn('F.data == "adm_ws_confirm"', admin_src)
        self.assertIn('db.preview_bulk_wallet_credit', admin_src)


if __name__ == "__main__":
    unittest.main()
