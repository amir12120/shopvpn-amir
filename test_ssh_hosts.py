# -*- coding: utf-8 -*-
import asyncio
import json
import os
import tempfile
import unittest

import ssh_hosts
import ssh_service

OVPN = ("client\ndev tun\nproto udp\nremote 203.0.113.10 1194\nnobind\n<ca>\nCA\n</ca>\n<key>\nK\n</key>\n")
WG = ("[Interface]\nPrivateKey = abc\nAddress = 10.8.0.2/32\n\n[Peer]\nPublicKey = pub\n"
      "Endpoint = 203.0.113.10:51820\nAllowedIPs = 0.0.0.0/0\n")


def node(hosts=None, **extra):
    cfg = {"protocols": ["ssh", "openvpn", "wireguard"], "ovpn_port": 1194, "wg_port": 51820}
    if hosts is not None:
        cfg["hosts"] = hosts
    cfg.update(extra)
    return {"id": 1, "name": "N1", "host": "203.0.113.10", "port": 22, "node_type": "linux",
            "config_json": json.dumps(cfg)}


class FakeDb:
    def __init__(self, n):
        self.n = dict(n)

    def get_ssh_node(self, node_id):
        return dict(self.n) if int(node_id) == int(self.n["id"]) else None

    def list_ssh_nodes(self, active_only=False):
        return [dict(self.n)]

    def merge_ssh_node_config(self, node_id, updates):
        cfg = json.loads(self.n["config_json"]); cfg.update(updates); self.n["config_json"] = json.dumps(cfg); return True

    def replace_ssh_node_config_keys(self, node_id, updates, remove=()):
        cfg = json.loads(self.n["config_json"])
        for k in remove:
            cfg.pop(k, None)
        cfg.update(updates); self.n["config_json"] = json.dumps(cfg); return True


class HostsModuleTests(unittest.TestCase):
    def test_no_hosts_returns_real_address(self):
        eps = ssh_hosts.endpoints(node(), "openvpn", "203.0.113.10", 1194)
        self.assertEqual([(e["address"], e["port"]) for e in eps], [("203.0.113.10", 1194)])

    def test_openvpn_host_overrides_address_and_port(self):
        n = node([{"protocol": "openvpn", "address": "tun.example.com", "port": 443, "remark": "A"}])
        eps = ssh_hosts.endpoints(n, "openvpn", "203.0.113.10", 1194)
        self.assertEqual((eps[0]["address"], eps[0]["port"], eps[0]["remark"]), ("tun.example.com", 443, "A"))
        # پروتکل‌های دیگر دست‌نخورده‌اند
        self.assertEqual(ssh_hosts.endpoints(n, "wireguard", "203.0.113.10", 51820)[0]["address"], "203.0.113.10")

    def test_empty_port_keeps_account_port(self):
        n = node([{"protocol": "wireguard", "address": "wg.example.com"}])
        self.assertEqual(ssh_hosts.endpoints(n, "wireguard", "203.0.113.10", 51820)[0]["port"], 51820)

    def test_ssh_host_changes_address_but_keeps_per_account_port(self):
        n = node([{"protocol": "ssh", "address": "relay.example.com"}])
        ep = ssh_hosts.endpoints(n, "ssh", "203.0.113.10", 24720)[0]
        self.assertEqual((ep["address"], ep["port"]), ("relay.example.com", 24720))

    def test_ssh_host_with_port_is_rejected(self):
        with self.assertRaises(ssh_hosts.HostConfigError):
            ssh_hosts.normalize_host({"protocol": "ssh", "address": "relay.example.com", "port": 443})

    def test_disabled_host_ignored_and_multiple_hosts_expand(self):
        n = node([{"protocol": "openvpn", "address": "a.example.com", "enabled": False},
                  {"protocol": "openvpn", "address": "b.example.com", "port": 8443},
                  {"protocol": "openvpn", "address": "c.example.com"}])
        eps = ssh_hosts.endpoints(n, "openvpn", "203.0.113.10", 1194)
        self.assertEqual([(e["address"], e["port"]) for e in eps], [("b.example.com", 8443), ("c.example.com", 1194)])

    def test_invalid_input(self):
        for bad in ({"protocol": "x", "address": "a.example.com"},
                    {"protocol": "openvpn", "address": "http://a.example.com"},
                    {"protocol": "openvpn", "address": "a.example.com", "port": 70000},
                    {"protocol": "openvpn", "address": "a b"}):
            with self.assertRaises(ssh_hosts.HostConfigError):
                ssh_hosts.normalize_host(bad)

    def test_corrupt_stored_host_does_not_break_output(self):
        n = node([{"protocol": "openvpn", "address": "bad address"}])
        self.assertEqual(ssh_hosts.endpoints(n, "openvpn", "203.0.113.10", 1194)[0]["address"], "203.0.113.10")

    def test_rewrite_profiles(self):
        out = ssh_hosts.rewrite_ovpn_profile(OVPN, "tun.example.com", 443)
        self.assertIn("\nremote tun.example.com 443\n", out)
        self.assertIn("<ca>\nCA\n</ca>", out)
        self.assertNotIn("203.0.113.10", out)
        wg = ssh_hosts.rewrite_wg_profile(WG, "2001:db8::1", 4500)
        self.assertIn("Endpoint = [2001:db8::1]:4500", wg)
        self.assertIn("PrivateKey = abc", wg)

    def test_ssh_port_range_defaults_and_validation(self):
        self.assertEqual(ssh_hosts.ssh_port_range(node()), (20000, 39999))
        self.assertEqual(ssh_hosts.ssh_port_range(node(ssh_port_min=30000, ssh_port_max=30010)), (30000, 30010))
        self.assertEqual(ssh_hosts.validate_ssh_port_range(30000, 30000), (30000, 30000))
        for lo, hi in ((500, 600), (30010, 30000), (1024, 70000), ("a", 5000)):
            with self.assertRaises(ssh_hosts.HostConfigError):
                ssh_hosts.validate_ssh_port_range(lo, hi)


class ServiceTests(unittest.TestCase):
    def test_set_and_get_hosts_roundtrip(self):
        db = FakeDb(node())
        ssh_service.set_node_hosts(db, 1, [{"protocol": "openvpn", "address": "tun.example.com", "port": 443}])
        got = ssh_service.get_node_hosts(db, 1)
        self.assertEqual(got["hosts"][0]["address"], "tun.example.com")
        self.assertEqual((got["ssh_port_min"], got["ssh_port_max"]), (20000, 39999))

    def test_host_for_uninstalled_protocol_rejected(self):
        n = node(); cfg = json.loads(n["config_json"]); cfg["protocols"] = ["ssh"]; n["config_json"] = json.dumps(cfg)
        with self.assertRaises(ssh_service.SSHServiceError):
            ssh_service.set_node_hosts(FakeDb(n), 1, [{"protocol": "wireguard", "address": "wg.example.com"}])

    def test_other_config_keys_survive_hosts_save(self):
        db = FakeDb(node(cert_sha256="abc", agent_url="https://x:8765"))
        ssh_service.set_node_hosts(db, 1, [])
        cfg = json.loads(db.n["config_json"])
        self.assertEqual(cfg["cert_sha256"], "abc")
        self.assertEqual(cfg["agent_url"], "https://x:8765")

    def test_reset_range_removes_keys(self):
        db = FakeDb(node(ssh_port_min=30000, ssh_port_max=31000))
        r = asyncio.run(ssh_service.set_ssh_port_range(db, 1, None, None))
        self.assertFalse(r["ssh_port_custom"])
        self.assertNotIn("ssh_port_min", json.loads(db.n["config_json"]))

    def test_user_endpoints_rewrites_profile_for_each_host(self):
        n = node([{"protocol": "openvpn", "address": "a.example.com", "port": 443},
                  {"protocol": "openvpn", "address": "b.example.com"}])
        eps = ssh_service.user_endpoints(n, {"protocol": "openvpn", "host": "203.0.113.10", "port": 1194}, OVPN)
        self.assertIn("remote a.example.com 443", eps[0]["profile"])
        self.assertIn("remote b.example.com 1194", eps[1]["profile"])


class DedicatedSubTests(unittest.TestCase):
    def setUp(self):
        # کلید موقت تا فایل .ssh_credential_key کنار پروژه ساخته نشود
        from cryptography.fernet import Fernet
        os.environ["SHOPVPN_SSH_CREDENTIAL_KEY"] = Fernet.generate_key().decode()

    def _rows(self, protocol, secret, port):
        import ssh_credentials
        try:
            enc = ssh_credentials.encrypt_credential(secret)
        except Exception as exc:  # pragma: no cover - بدون کلید رمزنگاری قابل تست نیست
            self.skipTest(f"credential encryption unavailable: {exc}")
        return [{"account_id": "a1", "username": "u1", "host": "203.0.113.10", "port": port, "credential_enc": enc,
                 "node_name": "N1", "node_config_json": node([
                     {"protocol": protocol, "address": "tun.example.com", "port": None if protocol == "ssh" else 443, "remark": "T"}
                 ])["config_json"]}]

    def test_ovpn_and_ssh_outputs(self):
        import dedicated_sub

        class Db:
            def __init__(self, rows): self.rows = rows
            def ssh_accounts_for_config(self, cid, protocol="ssh"): return self.rows

        files = dedicated_sub.ovpn_files_for_config(Db(self._rows("openvpn", OVPN, 1194)), 1)
        self.assertIn("remote tun.example.com 443", files[0]["profile"])
        uris = dedicated_sub.ssh_uris_for_config(Db(self._rows("ssh", "p" * 20, 24720)), 1)
        self.assertTrue(uris[0].startswith("ssh://") and "@tun.example.com:24720#" in uris[0])


def _import_agent(case):
    """Agent به aiohttp نیاز دارد؛ فقط برای تست تخصیص پورت در صورت نبودنش یک stub ساده می‌گذاریم."""
    import sys
    import types
    try:
        import aiohttp  # noqa: F401
    except ImportError:
        stub = types.ModuleType("aiohttp")
        stub.web = types.SimpleNamespace()
        sys.modules["aiohttp"] = stub
    try:
        import ssh_node_agent
    except Exception as exc:
        case.skipTest(f"agent import failed: {exc}")
    return ssh_node_agent


class AgentPortTests(unittest.TestCase):
    def test_allocation_respects_range_and_reserved(self):
        ssh_node_agent = _import_agent(self)
        with tempfile.TemporaryDirectory() as tmp:
            agent = ssh_node_agent.Agent("t" * 40, os.path.join(tmp, "a.db"), nft_accounting=False)
            for _ in range(25):
                self.assertTrue(41000 <= agent._allocate_ssh_port(41000, 41010) <= 41010)
            with agent._conn() as db:
                for port in range(41000, 41010):
                    db.execute("INSERT INTO accounts(account_id,username,ssh_port,status,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                               (f"id{port}", f"u{port}", port, "active", "x", "x"))
            self.assertEqual(agent._allocate_ssh_port(41000, 41010), 41010)  # تنها پورت آزاد
            with agent._conn() as db:
                db.execute("INSERT INTO accounts(account_id,username,ssh_port,status,created_at,updated_at) VALUES('idz','uz',41010,'active','x','x')")
            with self.assertRaises(RuntimeError):
                agent._allocate_ssh_port(41000, 41010)

    def test_agent_default_range(self):
        ssh_node_agent = _import_agent(self)
        self.assertEqual(ssh_node_agent.Agent._default_ssh_port_range(), (20000, 39999))


class ProviderTests(unittest.TestCase):
    def _provider(self, n, reply_port):
        from ssh_providers import LinuxAgentSSHProvider
        calls = []

        class P(LinuxAgentSSHProvider):
            async def _request(self, method, path, payload=None):
                calls.append((method, path, payload))
                if path == "/v1/accounts":
                    return {"username": payload["username"], "port": reply_port}
                return {}

        return P(n), calls

    def test_range_is_sent_to_agent_and_accepted(self):
        provider, calls = self._provider(node(ssh_port_min=30000, ssh_port_max=30100), 30050)
        result = asyncio.run(provider.create_account("u1", 0, None, protocol="ssh"))
        self.assertEqual(result.port, 30050)
        self.assertEqual((calls[0][2]["port_min"], calls[0][2]["port_max"]), (30000, 30100))

    def test_default_range_is_not_sent(self):
        provider, calls = self._provider(node(), 24000)
        asyncio.run(provider.create_account("u1", 0, None, protocol="ssh"))
        self.assertNotIn("port_min", calls[0][2])

    def test_old_agent_ignoring_range_is_rolled_back(self):
        from ssh_providers import SSHProviderError
        provider, calls = self._provider(node(ssh_port_min=30000, ssh_port_max=30100), 24000)
        with self.assertRaises(SSHProviderError):
            asyncio.run(provider.create_account("u1", 0, None, protocol="ssh"))
        self.assertTrue(any(c[1].endswith("/delete") for c in calls))


if __name__ == "__main__":
    unittest.main()
