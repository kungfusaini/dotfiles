"""Slay the Spire's guarded launcher and reversible Civ VI retirement."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "home/config/pegasus"


class SlayTheSpirePegasusTests(unittest.TestCase):
    def test_single_guarded_entry_with_full_artwork(self):
        text = (CONFIG / "steam.metadata.pegasus.txt").read_text()
        self.assertEqual(text.count("game: Slay the Spire\n"), 1)
        self.assertEqual(text.count("file: steam:646570\n"), 1)
        self.assertEqual(text.count("launch: tablet-game-launch -- steam-session 646570\n"), 1)
        stanza = text.split("game: Slay the Spire\n", 1)[1].split("\ngame:", 1)[0]
        self.assertIn("Touchscreen Mode", stanza)
        for name in ("boxFront.jpg", "background.jpg", "logo.png", "screenshot-1.jpg", "screenshot-2.jpg", "screenshot-3.jpg"):
            self.assertIn("/media/steam/slay-the-spire/" + name, stanza)
            self.assertTrue((CONFIG / "media/steam/slay-the-spire" / name).is_file())

    def test_civ_metadata_and_assets_retained_but_not_deployed_as_entry(self):
        active = (CONFIG / "steam.metadata.pegasus.txt").read_text()
        inactive = (CONFIG / "inactive/civilization-vi.metadata.pegasus.txt").read_text()
        self.assertNotIn("steam:289070", active)
        self.assertIn("launch: tablet-game-launch -- steam-session 289070\n", inactive)
        self.assertEqual(inactive.count("assets."), 6)
        self.assertEqual(len(list((CONFIG / "media/steam/civilization-vi").iterdir())), 6)
        module = (ROOT / "home/modules/pegasus.nix").read_text()
        self.assertNotIn("inactive", module)
        self.assertIn('"pegasus-frontend/metafiles/steam.metadata.pegasus.txt".source =', module)
        self.assertIn('"pegasus-frontend/media".source = pegasusArtwork;', module)


if __name__ == "__main__":
    unittest.main()
