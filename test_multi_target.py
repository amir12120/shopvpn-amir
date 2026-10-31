# -*- coding: utf-8 -*-
"""تست محصول چندمقصدی (چند پنل VPN با سهمیه مشترک) و قفل ساب اختصاصی.

اجرا: python -m unittest test_multi_target -v
"""

import asyncio
import os
import sys
import tempfile
import time
import types
import unittest

os.environ.setdefault("BOT_TOKEN", "123:test")
os.environ.setdefault("OWNER_ID", "1")

try:
    import aiohttp  # noqa: F401
except ImportError:
    from unittest import mock
    sys.modules["aiohttp"] = mock.MagicMock()

import config  # noqa: E402

_TMP = tempfile.mkdtemp(prefix="multi_target_test_")
config.DB_PATH = os.path.join(_TMP, "bot.db")

import direct_panel_provision as dpp  # noqa: E402
from database import Database  # noqa: E402
from panel_providers import PanelError  # noqa: E402
from quota_reconciler import QuotaReconciler  # noqa: E402


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class FakePanel:
    supports_user_limit = False
    supports_data_limit_sync = False

    def __init__(self, name, fail=False):
        self.name, self.fail = name, fail
        self.created, self.deleted = [], []

    async def create_user(self, username, volume_gb, duration_days, **kwargs):
        if self.fail:
            raise PanelError("boom")
        self.created.append((username, volume_gb))
        return types.SimpleNamespace(username=username,
                                     subscription_url=f"https://{self.name}.example.com/sub/{username}")

    async def delete_user(self, username):
        self.deleted.append(username)
        return True

    async def get_user_usage(self, username):
        return {"used_bytes": 0, "data_limit_bytes": 0, "status": "active"}

    async def set_enabled(self, username, enabled):
        return True


def make_world(dsub=True, panels=3, fail_last=False):
    db = Database(os.path.join(_TMP, f"t{time.time_ns()}.db"))
    db.init_db(owner_id=1)
    if dsub:
        db.set_setting("dsub_enabled", "1")
        db.set_setting("dsub_base_url", "https://sub.example.com")
    ids, fakes = [], {}
    for i in range(panels):
        sid = db.add_panel_server(f"P{i + 1}", "pasarguard", f"https://p{i + 1}.example.com", "u", "p")
        ids.append(sid)
        fakes[sid] = FakePanel(f"p{i + 1}", fail=(fail_last and i == panels - 1))
    dpp.get_provider = lambda server: fakes[int(server["id"])]
    cat = db.add_category("C")
    pid = db.add_product(cat, "Multi", 1000, "", 30, True, 10, ids[0])
    return db, ids, fakes, db.get_product(pid)


class MultiTargetTests(unittest.TestCase):
    def test_extra_targets_roundtrip_and_counts(self):
        db, ids, _, product = make_world()
        db.set_product_extra_targets(product["id"], [ids[1], ids[2], ids[1]], [])
        self.assertEqual(db.get_product_extra_targets(product["id"]), {"panels": [ids[1], ids[2]], "ssh": []})
        counts = db.product_target_counts(db.get_product(product["id"]))
        self.assertEqual(counts["panels"], ids)
        db.edit_product(product["id"], provision_server_id=ids[0])
        self.assertEqual(db.get_product_extra_targets(product["id"]), {"panels": [], "ssh": []})

    def test_multi_panel_blocked_without_dsub(self):
        db, ids, fakes, product = make_world(dsub=False)
        db.set_product_extra_targets(product["id"], [ids[1]], [])
        with self.assertRaises(dpp.ProvisionError):
            run(dpp.provision_direct(db, db.get_product(product["id"]), 1, user_id=100, order_id=None))
        self.assertTrue(all(not f.created for f in fakes.values()))

    def test_multi_panel_provision_links_and_shared_pool(self):
        db, ids, fakes, product = make_world()
        db.set_product_extra_targets(product["id"], [ids[1], ids[2]], [])
        items = run(dpp.provision_direct(db, db.get_product(product["id"]), 1, user_id=100, order_id=None))
        self.assertEqual(len(items), 1)
        cc_id = items[0]["custom_config_id"]
        links = db.panel_links_for_config(cc_id)
        self.assertEqual([l["panel_server_id"] for l in links], [ids[1], ids[2]])
        self.assertTrue(all(l["subscription_url"].startswith("https://p") for l in links))
        pool = db.quota_pool_for_custom_config(cc_id)
        usage = db.get_quota_usage(pool["id"])
        members = sorted(s["service_id"] for s in usage["services"])
        self.assertEqual(members, sorted([f"custom_config:{cc_id}"] + [f"panel_link:{l['id']}" for l in links]))
        self.assertEqual(int(pool["limit_bytes"]), 10 * 1024 ** 3)
        for sid in ids:
            self.assertEqual(fakes[sid].created[0][1], 0)

    def test_failure_rolls_everything_back(self):
        db, ids, fakes, product = make_world(fail_last=True)
        db.set_product_extra_targets(product["id"], [ids[1], ids[2]], [])
        with self.assertRaises(dpp.ProvisionError):
            run(dpp.provision_direct(db, db.get_product(product["id"]), 1, user_id=100, order_id=None))
        with db._get_conn() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) c FROM custom_configs").fetchone()["c"], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) c FROM config_panel_links").fetchone()["c"], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) c FROM quota_pools").fetchone()["c"], 0)
        self.assertEqual(len(fakes[ids[0]].deleted), 1)
        self.assertEqual(len(fakes[ids[1]].deleted), 1)

    def test_reconciler_resolves_panel_link_member(self):
        db, ids, fakes, product = make_world()
        db.set_product_extra_targets(product["id"], [ids[1]], [])
        items = run(dpp.provision_direct(db, db.get_product(product["id"]), 1, user_id=100, order_id=None))
        link = db.panel_links_for_config(items[0]["custom_config_id"])[0]
        rec = QuotaReconciler(db, vpn_provider_factory=lambda server: fakes[int(server["id"])])
        record, server = rec._vpn_member(f"panel_link:{link['id']}")
        self.assertEqual(record["username"], link["username"])
        self.assertEqual(int(server["id"]), ids[1])
        res = run(rec._poll_vpn(f"panel_link:{link['id']}"))
        self.assertTrue(res["ok"])

    def test_delete_linked_users(self):
        import multi_target
        db, ids, fakes, product = make_world()
        db.set_product_extra_targets(product["id"], [ids[1]], [])
        items = run(dpp.provision_direct(db, db.get_product(product["id"]), 1, user_id=100, order_id=None))
        cc_id = items[0]["custom_config_id"]
        link = db.panel_links_for_config(cc_id)[0]
        multi_target.get_provider = lambda server: fakes[int(server["id"])]
        run(multi_target.delete_linked_panel_users(db, cc_id))
        self.assertEqual(fakes[ids[1]].deleted, [link["username"]])
        self.assertEqual(db.panel_links_for_config(cc_id, active_only=False), [])


if __name__ == "__main__":
    unittest.main()
