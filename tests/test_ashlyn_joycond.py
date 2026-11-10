"""Evaluate the small scoped rule subset without touching the live udev database."""
from pathlib import Path
import fnmatch
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "hosts/kirax1/packages/ashlyn-joycond"
LEFT = "58:B0:3E:4B:7E:DD"
RIGHT = "58:B0:3E:4B:83:C2"


def evaluate(filename, properties):
    props = dict(properties)
    tags = {"uaccess"}
    for line in (PACKAGE / filename).read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        fields = re.findall(r'([\w{}\/]+)(==|!=|:=|\+=|-=|=)"([^"]*)"', line)
        matched = True
        for key, op, value in fields:
            if op in ("==", "!="):
                matches = any(fnmatch.fnmatchcase(props.get(key, ""), v)
                              for v in value.split("|"))
                if matches != (op == "=="):
                    matched = False
                    break
        if not matched:
            continue
        for key, op, value in fields:
            if key == "GOTO":
                return props, tags
            if key == "IMPORT{parent}":
                props[f"ENV{{{value}}}"] = props.get(f"PARENT{{{value}}}", "")
            elif key == "TAG":
                if op == "+=":
                    tags.add(value)
                elif op == "-=":
                    tags.discard(value)
            elif op in ("=", ":="):
                props[key] = value
    return props, tags


class Rules(unittest.TestCase):
    def input(self, mac, name="Joy-Con (L)", kernel="event25", action="add", vendor="057e"):
        return evaluate("72-joycond.rules", {
            "ACTION": action, "SUBSYSTEM": "input", "KERNEL": kernel,
            "ATTRS{id/vendor}": vendor, "ATTRS{uniq}": mac, "ATTRS{name}": name,
        })

    def raw(self, mac, action="add"):
        return evaluate("71-joycond-hidraw.rules", {
            "ACTION": action, "SUBSYSTEM": "hidraw", "KERNEL": "hidraw4",
            "PARENT{HID_UNIQ}": mac,
        })

    def test_both_halves_and_legacy_nodes_are_private(self):
        for mac in (LEFT, RIGHT):
            for action in ("add", "change"):
                for kernel in ("event25", "js2"):
                    props, tags = self.input(mac, kernel=kernel, action=action)
                    self.assertEqual(props["MODE"], "0600")
                    self.assertEqual(props["GROUP"], "root")
                    self.assertNotIn("uaccess", tags)
                    self.assertEqual("joycond" in tags, kernel.startswith("event"))

    def test_pro_controllers_other_joycons_imu_and_virtual_pair_are_untouched(self):
        for mac, name in (
            ("50:23:6D:8D:29:57", "Pro Controller"),
            ("98:B6:E9:7C:21:83", "Pro Controller"),
            ("AA:BB:CC:DD:EE:FF", "Joy-Con (L)"),
            (LEFT, "Joy-Con (L) (IMU)"),
            (RIGHT, "Joy-Con (R) (IMU)"),
            (LEFT + "+" + RIGHT, "Ashlyn's Joy Cons"),
        ):
            props, tags = self.input(mac, name)
            self.assertNotIn("MODE", props)
            self.assertEqual(tags, {"uaccess"})
        self.assertNotIn("MODE", self.input(LEFT, vendor="1234")[0])
        self.assertNotIn("MODE", self.input(LEFT, action="remove")[0])

    def test_only_exact_raw_halves_are_private(self):
        for mac in (LEFT, RIGHT):
            props, tags = self.raw(mac.lower())
            self.assertEqual(props["MODE"], "0600")
            self.assertNotIn("uaccess", tags)
        for mac in ("50:23:6d:8d:29:57", "98:b6:e9:7c:21:83", "", "aa:bb:cc:dd:ee:ff"):
            props, tags = self.raw(mac)
            self.assertNotIn("MODE", props)
            self.assertEqual(tags, {"uaccess"})

    def test_raw_access_removed_before_seat_late_can_queue_acl_grant(self):
        # The complete system's 73-seat-late rule schedules uaccess if the tag
        # exists at that point. Removing it later (e.g. at 89) is too late.
        self.assertLess("71-joycond-hidraw.rules", "73-seat-late.rules")
        for mac in (LEFT, RIGHT):
            _, tags = self.raw(mac.lower())
            scheduled_uaccess = "uaccess" in tags
            self.assertFalse(scheduled_uaccess)
        late = (PACKAGE / "89-joycond.rules").read_text()
        self.assertTrue(all(not line or line.startswith("#") for line in late.splitlines()))

    def test_package_replaces_both_stock_rules_and_names_pair(self):
        source = (PACKAGE / "default.nix").read_text()
        self.assertIn("installPhase = old.installPhase +", source)
        self.assertIn("runHook preInstallCheck", source)
        for name in ("71-joycond-hidraw.rules", "72-joycond.rules", "89-joycond.rules"):
            self.assertIn(f"install -m0644 ${{./{name}}} $out/etc/udev/rules.d/{name}", source)
            self.assertIn(f"cmp ${{./{name}}} $out/etc/udev/rules.d/{name}", source)
        self.assertIn("--replace-fail 'Nintendo Switch Combined Joy-Cons' \"Ashlyn's Joy Cons\"", source)
        gaming = (ROOT / "hosts/kirax1/modules/desktop/gaming.nix").read_text()
        self.assertIn("../../packages/ashlyn-joycond", gaming)


if __name__ == "__main__":
    unittest.main()
