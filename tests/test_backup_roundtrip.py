# -*- coding: utf-8 -*-
"""بکاپ کامل قابل‌انتقال (manifest v2) و بازیابی آن روی نصب جدید.

این تست همان مسیری را می‌آزماید که از upstream 10.1.0 آمد: ساخت آرشیو با هش
هر دیتابیس، سپس بازیابی روی ماشینی که مسیر دیتابیس‌های نماینده‌اش عوض شده -
و مهم‌تر از همه این‌که دیتابیس نماینده‌ی غایب هرگز خالی ساخته نمی‌شود.
"""
import json
import os
import sys
import tempfile
import unittest
import zipfile

os.environ.setdefault("BOT_TOKEN", "123:test")
os.environ.setdefault("OWNER_ID", "1")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _aiogram_stub import install as _install_aiogram_stub  # noqa: E402

# backup -> database pulls handlers that import aiogram; the lean CI job has no
# aiogram, so install the fork's light stub first (real aiogram wins when present).
_install_aiogram_stub()

import backup  # noqa: E402
import config  # noqa: E402
from database import Database  # noqa: E402

_TMP_ROOT = tempfile.mkdtemp(prefix="full_backup_test_")
config.DB_PATH = os.path.join(_TMP_ROOT, "bot.db")


def _make_db(path: str, setting_value: str = "x") -> Database:
    db = Database(path)
    db.init_db(owner_id=1)
    db.set_setting("test_marker", setting_value)
    return db


class FullBackupRoundTripTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(dir=_TMP_ROOT)
        self.db = _make_db(os.path.join(self.root, "main.db"), "main")
        self.resellers = {}
        for rid in (1, 2):
            path = os.path.join(self.root, f"old_{rid}.db")
            rdb = _make_db(path, f"tenant-{rid}")
            rdb.close()
            self.resellers[rid] = path
        # نماینده‌ی سومی که دیتابیسش اصلاً وجود ندارد.
        self.db.register_reseller_bot("100:bot1", "b1", 11, "o1", self.resellers[1])
        self.db.register_reseller_bot("200:bot2", "b2", 22, "o2", self.resellers[2])
        self.db.register_reseller_bot("300:bot3", "b3", 33, "o3",
                                      os.path.join(self.root, "gone.db"))
        # فایل‌های نماینده را پیش از بکاپ حذف نمی‌کنیم؛ یکی را پاک می‌کنیم تا
        # «غایب» واقعاً غایب باشد.
        os.remove(os.path.join(self.root, "gone.db")) if os.path.exists(
            os.path.join(self.root, "gone.db")) else None
        self.out_dir = os.path.join(self.root, "backups")

    def tearDown(self):
        try:
            self.db.close()
        except Exception:
            pass

    def test_archive_is_complete_and_reports_missing_tenant(self):
        zip_path = backup.create_full_backup(self.db, self.db.db_path, self.out_dir, keep=5)
        self.assertIsNotNone(zip_path)
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
            manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
        self.assertEqual(manifest["format"], "shopvpn-full-backup")
        self.assertEqual(manifest["format_version"], 2)
        self.assertFalse(manifest["complete"], "a missing tenant DB must mark the archive incomplete")
        self.assertEqual([e["reason"] for e in manifest["errors"]], ["database_missing"])
        self.assertIn("main_bot.db", names)
        self.assertIn("reseller_1.db", names)
        self.assertIn("reseller_2.db", names)
        self.assertNotIn("reseller_3.db", names)
        for entry in manifest["entries"]:
            self.assertEqual(len(entry["sha256"]), 64)
            self.assertGreater(entry["size"], 0)
        # هیچ مسیر مطلق یا توکنی داخل manifest نیست.
        raw = json.dumps(manifest)
        self.assertNotIn(self.root.replace("\\", "\\\\"), raw)

    def test_restore_relocates_paths_and_never_creates_missing_tenant(self):
        zip_path = backup.create_full_backup(self.db, self.db.db_path, self.out_dir, keep=5)
        new_dir = os.path.join(self.root, "new_install_dbs")
        old_reseller_dir = config.RESELLER_DBS_DIR
        config.RESELLER_DBS_DIR = new_dir
        try:
            # مسیرهای قدیمی را عوض می‌کنیم تا بازیابی مجبور شود relocate کند.
            self.db.set_reseller_db_path(1, os.path.join(self.root, "moved", "r1.db"))
            self.db.set_reseller_db_path(2, os.path.join(self.root, "moved", "r2.db"))
            result = backup.restore_full_backup(self.db, self.db.db_path, zip_path)
        finally:
            config.RESELLER_DBS_DIR = old_reseller_dir

        self.assertTrue(result["main_restored"])
        self.assertFalse(result["complete"])
        self.assertEqual(sorted(r["id"] for r in result["resellers_restored"]), [1, 2])
        self.assertTrue(all(os.path.dirname(r["db_path"]) == new_dir for r in result["resellers_restored"]),
                        "restored tenant DBs must live inside this install's reseller_dbs/")
        skipped = {item["file"] for item in result["resellers_skipped"]}
        self.assertIn("reseller_3.db", skipped)
        self.assertFalse(os.path.exists(os.path.join(new_dir, "reseller_3.db")),
                         "a tenant DB missing from the archive must not be recreated empty")

        # داده‌ی هر نماینده از همان آرشیو برگشته است.
        for rid in (1, 2):
            restored = Database(os.path.join(new_dir, f"reseller_{rid}.db"))
            try:
                self.assertEqual(restored.get_setting("test_marker", ""), f"tenant-{rid}")
            finally:
                restored.close()
        self.assertEqual(self.db.get_setting("test_marker", ""), "main")

    def test_rejects_archive_with_unexpected_files(self):
        zip_path = backup.create_full_backup(self.db, self.db.db_path, self.out_dir, keep=5)
        tampered = zip_path + ".bad.zip"
        with zipfile.ZipFile(zip_path) as src, zipfile.ZipFile(tampered, "w") as dst:
            for info in src.infolist():
                dst.writestr(info.filename, src.read(info.filename))
            dst.writestr("../escape.txt", b"x")
        with self.assertRaises(ValueError):
            backup.restore_full_backup(self.db, self.db.db_path, tampered)

    def test_legacy_archive_without_manifest_still_restores(self):
        legacy = os.path.join(self.out_dir, "legacy.zip")
        os.makedirs(self.out_dir, exist_ok=True)
        src_main = os.path.join(self.root, "legacy_main.db")
        src_tenant = os.path.join(self.root, "legacy_tenant.db")
        m = _make_db(src_main, "legacy-main")
        # بکاپ‌های قدیمی manifest ندارند؛ اتصال فایل نماینده به ردیفش از روی
        # همان دیتابیس بازیابی‌شده انجام می‌شود.
        m.register_reseller_bot("400:bot4", "b4", 44, "o4", src_tenant)
        m.close()
        t = _make_db(src_tenant, "legacy-tenant")
        t.close()
        with zipfile.ZipFile(legacy, "w") as zf:
            zf.write(src_main, "main_bot.db")
            zf.write(src_tenant, "reseller_1.db")
        new_dir = os.path.join(self.root, "legacy_dbs")
        old_reseller_dir = config.RESELLER_DBS_DIR
        config.RESELLER_DBS_DIR = new_dir
        try:
            result = backup.restore_full_backup(self.db, self.db.db_path, legacy)
        finally:
            config.RESELLER_DBS_DIR = old_reseller_dir
        self.assertTrue(result["main_restored"])
        self.assertEqual(result["manifest"], {})
        self.assertEqual([r["id"] for r in result["resellers_restored"]], [1])
        restored = Database(os.path.join(new_dir, "reseller_1.db"))
        try:
            self.assertEqual(restored.get_setting("test_marker", ""), "legacy-tenant")
        finally:
            restored.close()


if __name__ == "__main__":
    unittest.main()
