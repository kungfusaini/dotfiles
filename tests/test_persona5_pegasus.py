"""Contract checks for the installed Steam edition of Persona 5 Royal."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class Persona5PegasusTests(unittest.TestCase):
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
                active = value == "Persona 5 Royal"
            if active:
                self.fields.setdefault(key, []).append(value)

    def test_steam_collection_and_single_exact_launch_entry(self):
        self.assertIn("collection: Steam\nshortname: steam\n", self.text)
        self.assertEqual(self.text.count("game: Persona 5 Royal\n"), 1)
        self.assertEqual(self.fields["file"], ["steam:1687950"])
        self.assertEqual(self.fields["launch"], ["steam-session 1687950"])
        self.assertNotIn("launch: steam steam://", self.text)
        for appid in (1687950, 242550, 289070):
            self.assertIn(f"launch: steam-session {appid}\n", self.text)
        module = (ROOT / "home/modules/pegasus.nix").read_text()
        self.assertIn("(pkgs.callPackage ../packages/steam-session { })", module)
        self.assertIn("workspace special:steam-hidden silent", module)
        self.assertIn("no_initial_focus on", module)
        self.assertEqual(self.fields["players"], ["1"])
        self.assertEqual(self.fields["release"], ["2022-10-20"])

    def test_artwork_is_built_and_deployed(self):
        artwork = (ROOT / "home/packages/pegasus-artwork.nix").read_text()
        module = (ROOT / "home/modules/pegasus.nix").read_text()
        prefix = "/home/sumeet/.config/pegasus-frontend/media/"
        for field in ("assets.box_front", "assets.background", "assets.logo"):
            path, = self.fields[field]
            self.assertTrue(path.startswith(prefix + "steam/persona-5-royal/"))
            self.assertIn(f'"$out/{path.removeprefix(prefix)}"', artwork)
        self.assertIn('"pegasus-frontend/media".source = pegasusArtwork;', module)
        self.assertIn('../config/pegasus/steam.metadata.pegasus.txt;', module)
        for asset in ("library_600x900.jpg", "library_hero.jpg", "logo.png"):
            self.assertIn(f"steam/apps/1687950/{asset}", artwork)

    def test_existing_curated_games_and_provider_policy_preserved(self):
        self.assertIn("game: Rayman Legends\nfile: steam:242550\n", self.text)
        self.assertIn("game: Sid Meier's Civilization VI\nfile: steam:289070\n", self.text)
        settings = (ROOT / "home/config/pegasus/settings.txt").read_text()
        self.assertIn("providers.steam.enabled: false", settings)


if __name__ == "__main__":
    unittest.main()
