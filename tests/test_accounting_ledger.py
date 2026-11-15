import os
import sqlite3
import tempfile
import unittest
import accounting


class _DB:
    def __init__(self):
        self.path = tempfile.mktemp(suffix=".sqlite")
        self._conns = []
    def _get_conn(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        self._conns.append(conn)  # نگه‌داشتن برای بستن قبل از پاک‌کردن فایل (ویندوز قفل می‌کند)
        return conn
    def get_gateway_revenue_report(self):
        return []
    def close(self):
        for conn in self._conns:
            try:
                conn.close()
            except Exception:
                pass
        self._conns = []
        if os.path.exists(self.path):
            try:
                os.remove(self.path)
            except OSError:
                pass


class AccountingLedgerTest(unittest.TestCase):
    def setUp(self):
        self.db = _DB()

    def tearDown(self):
        self.db.close()

    def test_create_summary_update_delete(self):
        inc = accounting.create_ledger_entry(self.db, {
            "entry_type": "income", "title": "فروش تست", "amount": 250000,
            "category": "فروش نقدی", "entry_date": "2026-11-15"
        }, 7)
        accounting.create_ledger_entry(self.db, {
            "entry_type": "expense", "title": "هزینه سرور", "amount": 50000,
            "category": "هزینه سرور", "entry_date": "2026-11-15"
        }, 7)
        summary = accounting.ledger_summary(self.db, "2026-11-01", "2026-11-30")
        self.assertEqual(summary["income"], 250000)
        self.assertEqual(summary["expense"], 50000)
        self.assertEqual(summary["net"], 200000)
        updated = accounting.update_ledger_entry(self.db, inc["id"], {
            "entry_type": "income", "title": "فروش اصلاح‌شده", "amount": 300000,
            "category": "فروش نقدی", "entry_date": "2026-11-15"
        })
        self.assertEqual(updated["amount"], 300000)
        self.assertTrue(accounting.delete_ledger_entry(self.db, inc["id"]))
        self.assertEqual(accounting.ledger_summary(self.db)["income"], 0)

    def test_validation(self):
        with self.assertRaises(ValueError):
            accounting.create_ledger_entry(self.db, {
                "entry_type": "expense", "title": "نامعتبر", "amount": 0,
                "category": "سایر هزینه"
            })

    def test_csv_export(self):
        accounting.create_ledger_entry(self.db, {
            "entry_type": "income", "title": "CSV test", "amount": 123,
            "category": "سایر درآمد", "entry_date": "2026-11-15"
        })
        content = accounting.export_ledger_csv(self.db)
        self.assertIn("CSV test", content)
        self.assertIn("Amount (Toman)", content)


if __name__ == "__main__":
    unittest.main()
