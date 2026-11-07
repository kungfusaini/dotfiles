import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("voyee", ROOT / "home/packages/voyee-controller/setup.py")
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)


class Profiles(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.config = self.root / "config"
        self.data = self.root / "data"
        self.state = self.root / "state"
        self.ps2 = self.config / "PCSX2/inis/PCSX2.ini"
        self.sym = self.data / "games/symphony-recomp/settings.json"
        self.ryu = self.config / "Ryujinx/Config.json"
        self.keyboard = {"backend": "WindowKeyboard", "player_index": "Player1", "id": "0",
                         "right_joycon": {"button_a": "Z"}}
        for p, value in [
            (self.ps2, "[UI]\nTheme = untouched\n\n[InputSources]\nKeyboard = true\nSDL = false\n\n[Pad1]\nCross = Keyboard/K\nSquare = Keyboard/J\nSquare = Keyboard/Space\nL1 = Keyboard/Q & Keyboard/Shift\n\n[Pad2]\nType = None\n"),
            (self.sym, json.dumps({"system": {"discPath": "read-only.cue", "cardA": {"path": "save.sav"},
                "input": {"ports": [{"kind": "analog", "device": "", "keys": {"cross": "Z"},
                                      "analog": {}, "digital": {}}, {"kind": "digital"}]}},
                                  "options": {"notices": True}})),
            (self.ryu, json.dumps({"input_config": [self.keyboard, {"player_index": "Player2", "id": "other"}],
                                   "graphics_backend": "Vulkan"})),
        ]:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(value)

    def test_position_and_label_policy(self):
        self.assertEqual(v.PS2["Cross"], "FaceSouth")
        self.assertEqual(v.PS1["cross"], [1])  # SDL2 B: physical bottom
        self.assertEqual(v.PS1["square"], [3])  # SDL2 Y: physical left
        p = v.nintendo_profile()
        for key in "abxy":
            self.assertEqual(p["right_joycon"]["button_" + key], key.upper())
        self.assertEqual(p["id"], "0-00000005-057e-0000-0920-000001800000")

    def test_preserves_keyboard_and_unrelated_settings(self):
        changes = v.plan(self.config, self.data)
        ps2 = changes[self.ps2]
        self.assertEqual(v.ini_values(ps2, "Pad1")["Cross"], ["Keyboard/K", "SDL-0/FaceSouth"])
        self.assertEqual(v.ini_values(ps2, "Pad1")["Square"], ["Keyboard/J", "Keyboard/Space", "SDL-0/FaceWest"])
        self.assertEqual(v.ini_values(ps2, "Pad1")["L1"][0], "Keyboard/Q & Keyboard/Shift")
        self.assertIn("[UI]\nTheme = untouched\n", ps2)
        self.assertIn("[Pad2]\nType = None\n", ps2)
        sym = json.loads(changes[self.sym])
        self.assertEqual(sym["system"]["cardA"]["path"], "save.sav")
        self.assertEqual(sym["system"]["input"]["ports"][0]["keys"], {"cross": "Z"})
        self.assertEqual(sym["system"]["input"]["ports"][1], {"kind": "digital"})
        ryu = json.loads(changes[self.ryu])
        self.assertEqual(ryu["graphics_backend"], "Vulkan")
        self.assertEqual(ryu["input_config"][1], {"player_index": "Player2", "id": "other"})
        keyboard = self.config / "Ryujinx/profiles/keyboard/Before VOYEE.json"
        self.assertEqual(json.loads(changes[keyboard]), self.keyboard)

    def test_apply_backups_and_idempotency(self):
        before = self.ps2.read_bytes()
        v.apply(v.plan(self.config, self.data), self.state)
        self.assertIn(before, [p.read_bytes() for p in self.state.iterdir()])
        self.assertEqual(v.plan(self.config, self.data), {})
        self.assertEqual(self.ps2.stat().st_mode & 0o777, 0o600)

    def test_invalid_config_does_not_write(self):
        original = self.ps2.read_bytes()
        self.ryu.write_text("not json")
        with self.assertRaises(json.JSONDecodeError):
            v.plan(self.config, self.data)
        self.assertEqual(self.ps2.read_bytes(), original)

    def test_symlink_refused_before_any_write(self):
        target = self.root / "managed"
        target.write_text("unchanged")
        link = self.root / "link"
        link.symlink_to(target)
        with self.assertRaises(RuntimeError):
            v.apply({self.ps2: "wrong", link: "wrong"}, self.state)
        self.assertEqual(target.read_text(), "unchanged")
        self.assertIn("Keyboard/K", self.ps2.read_text())


if __name__ == "__main__":
    unittest.main()
