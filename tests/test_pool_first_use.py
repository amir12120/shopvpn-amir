# -*- coding: utf-8 -*-
"""شروع زمان از اولین اتصال برای استخر سهمیه‌ی مشترک (چندپنلی/چندنودی).

Upstream ships this as `test_pool_first_use.py`, but it imports `test_multi_target`,
which this fork deleted on purpose (sync log 4.22.0).  This version exercises the
same shipping behaviour directly against the Database API instead of that harness.

اجرا: python -m pytest tests/test_pool_first_use.py -q
"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone

os.environ.setdefault("BOT_TOKEN", "123:test")
os.environ.setdefault("OWNER_ID", "1")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import config  # noqa: E402

_TMP = tempfile.mkdtemp(prefix="pool_first_use_")
config.DB_PATH = os.path.join(_TMP, "bot.db")

from database import Database  # noqa: E402


def make_db():
    db = Database(config.DB_PATH)
    db.init_db(owner_id=1)
    return db


class PoolFirstUseTests(unittest.TestCase):
    def setUp(self):
        self.db = make_db()

    def _pool(self, days=30, pending=True):
        pool_id = self.db.create_quota_pool(
            100, 100.0, label="test pool",
            metadata={"first_use_pending": pending, "first_use_days": float(days)},
        )
        return self.db.get_quota_pool(pool_id)

    def test_pending_pool_has_no_expiry(self):
        pool = self._pool()
        self.assertIsNone(pool["expires_at"])
        self.assertTrue(self.db.quota_pool_first_use_pending(pool))

    def test_activation_sets_expiry_and_clears_pending(self):
        pool = self._pool(days=30)
        started = self.db.activate_quota_pool_first_use(pool["id"])
        self.assertIsNotNone(started)
        after = self.db.get_quota_pool(pool["id"])
        self.assertEqual(after["expires_at"], started)
        self.assertFalse(self.db.quota_pool_first_use_pending(after))
        days = (datetime.fromisoformat(after["expires_at"])
                - datetime.now(timezone.utc)).total_seconds() / 86400
        self.assertTrue(29.9 < days <= 30.0, days)

    def test_activation_is_idempotent(self):
        pool = self._pool()
        self.db.activate_quota_pool_first_use(pool["id"])
        self.assertIsNone(self.db.activate_quota_pool_first_use(pool["id"]))

    def test_renewal_before_start_extends_stored_duration(self):
        pool = self._pool(days=30)
        self.assertTrue(self.db.add_quota_pool_first_use_days(pool["id"], 30))
        after = self.db.get_quota_pool(pool["id"])
        self.assertIsNone(after["expires_at"])
        self.assertEqual(json.loads(after["metadata_json"])["first_use_days"], 60.0)

    def test_add_days_ignored_once_started(self):
        pool = self._pool(days=30)
        self.db.activate_quota_pool_first_use(pool["id"])
        self.assertFalse(self.db.add_quota_pool_first_use_days(pool["id"], 30))

    def test_non_pending_pool_is_not_pending(self):
        pool = self._pool(pending=False)
        self.assertFalse(self.db.quota_pool_first_use_pending(pool))


if __name__ == "__main__":
    unittest.main()
