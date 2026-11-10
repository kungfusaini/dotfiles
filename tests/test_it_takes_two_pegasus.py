"""Contract checks for the curated Steam edition of It Takes Two."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ItTakesTwoPegasusTests(unittest.TestCase):
    def setUp(self):
        self.text = (ROOT / "home/config/pegasus/steam.metadata.pegasus.txt").read_text()
        self.fields = {}
        active = False
        for line in self.text.splitlines():
            if not line or line.startswith("#"):
                continue
            key, value = line.split(":", 1)
            value = value.strip()
            if key == "game":
                active = value == "It Takes Two"
            if active:
                self.fields.setdefault(key, []).append(value)

    def test_exact_entry_uses_managed_launcher(self):
        self.assertEqual(self.text.count("game: It Takes Two\n"), 1)
        self.assertEqual(self.fields["file"], ["steam:1426210"])
        self.assertEqual(self.fields["launch"], ["steam-session 1426210"])
        self.assertEqual(self.fields["players"], ["2"])
        self.assertEqual(self.fields["release"], ["2021-03-25"])
        for appid in (1687950, 242550, 289070):
            self.assertIn(f"launch: steam-session {appid}\n", self.text)

    def test_all_artwork_is_packaged(self):
        artwork = (ROOT / "home/packages/pegasus-artwork.nix").read_text()
        prefix = "/home/sumeet/.config/pegasus-frontend/media/"
        for field in ("assets.box_front", "assets.background", "assets.logo", "assets.screenshot"):
            for path in self.fields[field]:
                self.assertTrue(path.startswith(prefix + "steam/it-takes-two/"))
                self.assertTrue((ROOT / "home/config/pegasus/media" / path.removeprefix(prefix)).is_file())
        self.assertEqual(len(self.fields["assets.screenshot"]), 3)
        self.assertIn("${../config/pegasus/media}", artwork)
        module = (ROOT / "home/modules/pegasus.nix").read_text()
        self.assertIn('"pegasus-frontend/media".source = pegasusArtwork;', module)
        self.assertIn('../config/pegasus/steam.metadata.pegasus.txt;', module)
        settings = (ROOT / "home/config/pegasus/settings.txt").read_text()
        self.assertIn("providers.steam.enabled: false", settings)


if __name__ == "__main__":
    unittest.main()
