"""Display-menu tests: fake launcher commands and real offscreen Quickshell UI."""
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "home/scripts/display/display-layout-open"
QML = ROOT / "home/config/quickshell/display-layout/shell.qml"


def executable(path, body):
    path.write_text(f"#!{sys.executable}\n" + body)
    path.chmod(0o755)
    return str(path)


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="display-menu.")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = dict(os.environ, PATH=str(self.root) + ":" + os.environ["PATH"],
                        MENU_RESULT=str(self.root / "result"), CALLS=str(self.root / "calls"))
        executable(self.root / "hyprctl", '''import json, os, sys
with open(os.environ["CALLS"], "a") as log: log.write(json.dumps(sys.argv[1:])+"\\n")
if sys.argv[1:]==["monitors", "all", "-j"]: print(os.environ["MONITORS"])
elif sys.argv[1:3]!=["keyword", "windowrule"]: raise SystemExit(9)
''')
        executable(self.root / "quickshell", '''import json, os, sys
keys=[k for k in os.environ if k.startswith("LAYOUT_") or k.startswith("DISPLAY_")]
with open(os.environ["MENU_RESULT"], "w") as file:
    json.dump({"env": {k: os.environ[k] for k in keys}, "args": sys.argv[1:]}, file)
''')
        executable(self.root / "gnome-network-displays", 'raise SystemExit("Must not launch while opening menu")\n')
        self.panel = dict(name="eDP-1", x=0, y=0, width=1920, height=1200, scale=1.25)
        self.external = dict(name="DP-3", x=1536, y=0, width=1920, height=1080, scale=1)

    def launch(self, outputs):
        self.env["MONITORS"] = outputs if isinstance(outputs, str) else json.dumps(outputs)
        result = subprocess.run(["bash", str(LAUNCHER)], env=self.env, capture_output=True,
                                text=True, timeout=10)
        return result

    def check_menu(self, outputs, available):
        result = self.launch(outputs)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads((self.root / "result").read_text())
        self.assertEqual(data["env"]["LAYOUT_AVAILABLE"], str(int(available)))
        self.assertEqual(data["env"]["DISPLAY_WIRELESS_OPEN"], str(self.root / "gnome-network-displays"))
        self.assertEqual(data["args"][:2], ["--no-duplicate", "--path"])
        for key, value in data["env"].items():
            if key.startswith("LAYOUT_") and key != "LAYOUT_EXTERNAL_NAME":
                self.assertTrue(math.isfinite(float(value)), key)
        calls = [json.loads(line) for line in (self.root / "calls").read_text().splitlines()]
        self.assertEqual(sum(args == ["monitors", "all", "-j"] for args in calls), 1)
        return data["env"]

    def test_laptop_only_offers_wireless(self):
        self.check_menu([self.panel], False)

    def test_external_only_offers_wireless_without_arranging_disabled_panel(self):
        self.panel["disabled"] = True
        self.check_menu([self.panel, self.external], False)

    def test_disabled_external_is_not_arrangeable(self):
        self.external["disabled"] = True
        self.check_menu([self.panel, self.external], False)

    def test_wired_pair_preserves_logical_geometry(self):
        env = self.check_menu([self.panel, self.external], True)
        factor = float(env["LAYOUT_FACTOR"])
        dx = (float(env["LAYOUT_EXTERNAL_X"]) - float(env["LAYOUT_INTERNAL_X"])) * factor
        self.assertAlmostEqual(dx, 1536)
        self.assertEqual(env["LAYOUT_EXTERNAL_NAME"], "DP-3")

    def test_bad_monitor_response_never_launches_broken_menu(self):
        result = self.launch("not json")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / "result").exists())


@unittest.skipUnless(os.environ.get("DISPLAY_MENU_QUICKSHELL"), "Set DISPLAY_MENU_QUICKSHELL for offscreen UI tests")
class MenuUiTests(unittest.TestCase):
    def run_ui(self, available, action, overlap=False, command=True):
        with tempfile.TemporaryDirectory(prefix="display menu.") as directory:
            root = Path(directory)
            runtime = root / "runtime"
            runtime.mkdir(mode=0o700)
            calls = root / "wireless-calls"
            apply_calls = root / "apply-calls"
            wireless = executable(root / "wireless fake", f'from pathlib import Path\nPath({str(calls)!r}).write_text("launched")\n')
            apply = executable(root / "apply fake", f'import json, sys\nfrom pathlib import Path\nPath({str(apply_calls)!r}).write_text(json.dumps(sys.argv[1:]))\n')
            env = dict(os.environ, QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software",
                       QT_QUICK_CONTROLS_STYLE="Basic", XDG_RUNTIME_DIR=str(runtime),
                       XDG_CONFIG_HOME=str(root / "config"), XDG_CACHE_HOME=str(root / "cache"),
                       XDG_STATE_HOME=str(root / "state"), HOME=str(root),
                       LAYOUT_AVAILABLE=str(int(available)), LAYOUT_FACTOR="2",
                       LAYOUT_INTERNAL_X="100", LAYOUT_INTERNAL_Y="100", LAYOUT_INTERNAL_W="200", LAYOUT_INTERNAL_H="120",
                       LAYOUT_EXTERNAL_X="100" if overlap else "300", LAYOUT_EXTERNAL_Y="100",
                       LAYOUT_EXTERNAL_W="150", LAYOUT_EXTERNAL_H="100", LAYOUT_EXTERNAL_NAME="DP-3",
                       DISPLAY_WIRELESS_OPEN=wireless if command else "", DISPLAY_LAYOUT_APPLY=apply)
            for key in ("DISPLAY", "WAYLAND_DISPLAY", "WAYLAND_SOCKET", "HYPRLAND_INSTANCE_SIGNATURE", "DBUS_SESSION_BUS_ADDRESS"):
                env.pop(key, None)
            checks = f'''
        if (shell.layoutAvailable !== {str(available).lower()}) throw new Error("availability");
        if (applyButton.enabled !== {str(available and not overlap).lower()}) throw new Error("apply enabled");
        if (wirelessButton.enabled !== {str(command).lower()}) throw new Error("wireless enabled");
        if (wirelessButton.x + wirelessButton.width >= cancelButton.x) throw new Error("buttons overlap");
'''
            if action == "wireless":
                if not available:
                    checks += 'shell.applyLayout(); if (runner.running) throw new Error("disabled layout ran");\n'
                checks += "wirelessButton.clicked();"
            elif action == "apply":
                checks += "shell.applyLayout();"
            elif action == "escape":
                checks += "wirelessButton.forceActiveFocus(); escapeShortcut.activated();"
            else:
                checks += "shell.openWireless(); Qt.quit();"
            timer = '''
    Timer {
        interval: 200; running: true
        onTriggered: {
            try { CHECKS }
            catch (error) { console.error("UI ASSERTION: " + error); Qt.exit(1) }
        }
    }
'''.replace("CHECKS", checks)
            source, end = QML.read_text().rsplit("}", 1)
            (root / "shell.qml").write_text(source + timer + "}" + end)
            result = subprocess.run([os.environ["DISPLAY_MENU_QUICKSHELL"], "--path", str(root / "shell.qml")],
                                    env=env, capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn("UI ASSERTION:", result.stderr)
            if action == "wireless":
                deadline = time.monotonic() + 3
                while not calls.exists() and time.monotonic() < deadline:
                    time.sleep(.02)
                self.assertTrue(calls.exists(), result.stdout + result.stderr)
                self.assertFalse(apply_calls.exists())
            elif action == "apply":
                self.assertEqual(json.loads(apply_calls.read_text()), ["custom", "200", "0", "2"])
                self.assertFalse(calls.exists())
            else:
                self.assertFalse(calls.exists())
                self.assertFalse(apply_calls.exists())

    def test_laptop_only_wireless_button_launches_without_layout_mutation(self):
        self.run_ui(False, "wireless")

    def test_wired_wireless_button_launches_without_layout_mutation(self):
        self.run_ui(True, "wireless")

    def test_wired_apply_keeps_existing_geometry_arguments(self):
        self.run_ui(True, "apply")

    def test_overlapping_wired_layout_keeps_apply_disabled(self):
        self.run_ui(True, "wireless", overlap=True)

    def test_escape_closes_with_wireless_button_focused(self):
        self.run_ui(False, "escape")

    def test_missing_wireless_command_disables_button(self):
        self.run_ui(False, "none", command=False)


if __name__ == "__main__":
    unittest.main()
