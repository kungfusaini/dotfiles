"""No network or privileged commands: exercise the packaged policy decision."""
import importlib.util
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "hosts/kirax1/scripts/system/wifi-dns-policy.py"
spec = importlib.util.spec_from_file_location("wifi_dns_policy", SOURCE)
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


class WifiDnsPolicyTests(unittest.TestCase):
    def exercise(self, *, dhcp=None, current=None, state="full", route=None, interface="", action="connectivity-change", separator=" | "):
        dhcp = dhcp if dhcp is not None else sorted(policy.UNRELIABLE)
        current = current if current is not None else dhcp
        commands = []
        def output(*args):
            commands.append(args)
            if args[0] == "nmcli":
                return state if "CONNECTIVITY" in args else separator.join(dhcp)
            if args[:3] == ("resolvectl", "--json=short", "dns"):
                return json.dumps([{"ifname": policy.DEVICE, "servers": [{"addressString": ip} for ip in current]}])
            if args[0] == "ip":
                if isinstance(route, Exception):
                    raise route
                return json.dumps([{"dev": route or policy.DEVICE}])
            return ""
        with patch.object(policy, "output", side_effect=output):
            changed = policy.apply(interface, action)
        writes = [c for c in commands if c[:2] == ("resolvectl", "dns")]
        return changed, commands, writes

    def test_full_known_network_uses_reachable_public_resolvers_only_on_wifi(self):
        changed, commands, writes = self.exercise()
        self.assertTrue(changed)
        self.assertEqual(writes, [("resolvectl", "dns", policy.DEVICE, *policy.REPLACEMENTS)])
        self.assertFalse(any("domain" in c or "modify" in c or "reapply" in c for c in commands))

    def test_real_nmcli_array_output_and_legacy_multiline_are_both_parsed(self):
        for separator in (" | ", "\n"):
            with self.subTest(separator=separator):
                self.assertTrue(self.exercise(separator=separator)[0])

    def test_other_dhcp_servers_or_interfaces_are_not_modified(self):
        for opts in ({"dhcp": ["192.168.1.1"]}, {"dhcp": ["18.135.144.127", "192.168.1.1"]},
                     {"interface": "tailscale0"}, {"interface": "nordlynx"}, {"action": "down"}):
            with self.subTest(opts=opts):
                self.assertFalse(self.exercise(**opts)[0])
                self.assertEqual(self.exercise(**opts)[2], [])

    def test_portal_limited_unknown_or_offline_restores_original_dns(self):
        for state in ("portal", "limited", "unknown", "none"):
            with self.subTest(state=state):
                changed, _, writes = self.exercise(state=state, current=policy.REPLACEMENTS)
                self.assertTrue(changed)
                self.assertEqual(list(writes[0][3:]), sorted(policy.UNRELIABLE))

    def test_vpn_exit_route_or_failed_route_read_restores_dhcp(self):
        for route in ("tailscale0", "nordlynx", subprocess.TimeoutExpired("ip", 3)):
            with self.subTest(route=str(route)):
                self.assertTrue(self.exercise(route=route, current=policy.REPLACEMENTS)[0])
                self.assertEqual(list(self.exercise(route=route, current=policy.REPLACEMENTS)[2][0][3:]), sorted(policy.UNRELIABLE))

    def test_vpn_events_reconcile_wifi_even_when_event_interface_is_vpn(self):
        for action in ("vpn-up", "vpn-down"):
            self.assertTrue(self.exercise(action=action, interface="nordlynx", route="nordlynx", current=policy.REPLACEMENTS)[0])

    def test_periodic_reconcile_handles_exit_node_with_unchanged_full_connectivity(self):
        self.assertTrue(self.exercise(state="full")[0])
        _, _, writes = self.exercise(state="full", current=policy.REPLACEMENTS, route="tailscale0")
        self.assertEqual(list(writes[0][3:]), sorted(policy.UNRELIABLE))

    def test_foreign_resolved_override_is_not_clobbered(self):
        self.assertEqual(self.exercise(current=["100.100.100.100"])[2], [])

    def test_repeated_events_are_idempotent(self):
        self.assertEqual(self.exercise(current=policy.REPLACEMENTS)[2], [])
        self.assertEqual(self.exercise(state="portal")[2], [])

    def test_invalid_dhcp_data_fails_before_any_write(self):
        with self.assertRaises(ValueError):
            self.exercise(dhcp=["not-an-address"])


if __name__ == "__main__":
    unittest.main()
