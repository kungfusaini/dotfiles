"""Contract checks for SymphonyRecomp's declarative Pegasus registration."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SymphonyPegasusTests(unittest.TestCase):
    def setUp(self):
        text = (ROOT / "home/config/pegasus/custom.metadata.pegasus.txt").read_text()
        self.fields = {}
        self.collection = None
        active = False
        for line in text.splitlines():
            if not line or line.startswith("#"):
                continue
            key, value = line.split(":", 1)
            value = value.strip()
            if key == "collection":
                self.collection = value
            if key == "game":
                active = value == "Castlevania: Symphony of the Night"
            if active:
                self.fields.setdefault(key, []).append(value)

    def test_native_command_and_disc_gate(self):
        self.assertEqual(self.collection, "PC")
        self.assertEqual(self.fields["launch"], ["symphony-recomp"])
        self.assertEqual(self.fields["file"], [
            "/home/sumeet/matrix/data/emulation/roms/ps1/"
            "Castlevania - Symphony of the Night (USA)/"
            "Castlevania - Symphony of the Night (USA).cue"
        ])
        self.assertIn("beta", self.fields["summary"][0])

    def test_artwork_paths_are_built_and_deployed(self):
        artwork = (ROOT / "home/packages/pegasus-artwork.nix").read_text()
        module = (ROOT / "home/modules/pegasus.nix").read_text()
        prefix = "/home/sumeet/.config/pegasus-frontend/media/"
        for key in ("assets.box_front", "assets.background", "assets.logo"):
            path, = self.fields[key]
            self.assertTrue(path.startswith(prefix))
            relative = path.removeprefix(prefix)
            self.assertIn(f'"$out/{relative}"', artwork)
        self.assertIn('"pegasus-frontend/media".source = pegasusArtwork;', module)
        self.assertIn('../config/pegasus/custom.metadata.pegasus.txt;', module)

    def test_no_desktop_application_entry(self):
        package = (ROOT / "home/packages/symphony-recomp/default.nix").read_text()
        self.assertNotIn("makeDesktopItem", package)
        self.assertNotIn("copyDesktopItems", package)
        self.assertIn('mainProgram = pname;', package)


if __name__ == "__main__":
    unittest.main()
