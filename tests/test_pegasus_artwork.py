"""All curated artwork is permanent local input, with no remote build fetches."""
import hashlib
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "home/config/pegasus"


class PegasusArtworkTests(unittest.TestCase):
    def test_local_only_package(self):
        text = (ROOT / "home/packages/pegasus-artwork.nix").read_text()
        self.assertIn('cp -r ${../config/pegasus/media}/. "$out/"', text)
        for remote in ("fetchurl", "https://", "curl", "wget", "imagemagick"):
            self.assertNotIn(remote, text.lower())

    def test_checksums_cover_exact_asset_tree(self):
        expected = {}
        for line in (CONFIG / "artwork.SHA256SUMS").read_text().splitlines():
            digest, name = line.split("  ", 1)
            self.assertNotIn(name, expected)
            expected[name] = digest
        actual = {
            str(p.relative_to(CONFIG)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (CONFIG / "media").rglob("*") if p.is_file()
        }
        self.assertGreater(len(actual), 0)
        self.assertEqual(actual, expected)
        self.assertFalse(any(p.is_symlink() for p in (CONFIG / "media").rglob("*")))

    def test_every_curated_artwork_reference_exists(self):
        prefix = "/home/sumeet/.config/pegasus-frontend/media/"
        referenced = set()
        for metadata in CONFIG.glob("*.metadata.pegasus.txt"):
            for line in metadata.read_text().splitlines():
                if not line.startswith("assets."):
                    continue
                _, value = line.split(":", 1)
                value = value.strip()
                self.assertTrue(value.startswith(prefix), value)
                relative = value.removeprefix(prefix)
                self.assertNotIn("..", Path(relative).parts)
                self.assertTrue((CONFIG / "media" / relative).is_file(), value)
                referenced.add(relative)
        self.assertEqual(referenced, {
            str(p.relative_to(CONFIG / "media"))
            for p in (CONFIG / "media").rglob("*") if p.is_file()
        })


if __name__ == "__main__":
    unittest.main()
