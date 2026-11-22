#!/usr/bin/env python3
"""Offline tests; synthetic artwork only, no image generation or private fixtures."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from PIL import Image, ImageDraw

SCRIPT = Path(__file__).resolve().parents[1] / "home/scripts/normalize-emoji.py"
spec = importlib.util.spec_from_file_location("normalize_emoji", SCRIPT)
normalizer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(normalizer)


class NormalizeEmojiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "raw.png"
        self.output = self.root / "normalized.png"

    def artwork(self, box=(35, 50, 64, 59)):
        image = Image.new("RGBA", (100, 100))
        ImageDraw.Draw(image).rectangle(box, fill=(200, 40, 20, 255))
        image.putpixel((0, 0), (255, 255, 255, 1))
        image.putpixel((99, 99), (255, 255, 255, 15))
        image.save(self.source)

    def test_noise_is_ignored_and_silhouette_centered_without_stretching(self):
        self.artwork()
        original = self.source.read_bytes()
        report = normalizer.normalize(self.source, self.output)
        with Image.open(self.output) as out:
            self.assertEqual(out.size, (1024, 1024))
            self.assertEqual(out.mode, "RGBA")
            self.assertEqual(out.getpixel((0, 0))[3], 0)
            left, top, right, bottom = normalizer.visible_bounds(out)
            self.assertLessEqual(abs((left + right) / 2 - 512), 0.5)
            self.assertLessEqual(abs((top + bottom) / 2 - 512), 0.5)
            opaque = out.getchannel("A").point(lambda a: 255 if a >= 128 else 0).getbbox()
            self.assertAlmostEqual((opaque[2] - opaque[0]) / (opaque[3] - opaque[1]), 3, delta=0.04)
            self.assertAlmostEqual(max(right-left, bottom-top)/1024, 0.90, delta=0.01)
        self.assertEqual(self.source.read_bytes(), original)
        self.assertEqual(report["sourceVisibleBounds"], [35, 50, 65, 60])
        self.assertEqual(report["sourceSha256"], hashlib.sha256(original).hexdigest())
        self.assertEqual(report["outputSha256"], hashlib.sha256(self.output.read_bytes()).hexdigest())

    def test_alpha_threshold_is_inclusive_and_soft_nearby_edges_are_retained(self):
        image = Image.new("RGBA", (100, 100))
        ImageDraw.Draw(image).rectangle((30, 30, 69, 69), fill=(10, 200, 80, 255))
        ImageDraw.Draw(image).rectangle((29, 30, 29, 69), fill=(10, 200, 80, 8))
        image.putpixel((70, 50), (10, 200, 80, 16))
        image.putpixel((0, 0), (10, 200, 80, 15))
        image.save(self.source)
        result = normalizer.normalize(self.source, self.output)
        self.assertEqual(result["sourceVisibleBounds"], [30, 30, 71, 70])
        with Image.open(self.output) as output:
            alpha = output.getchannel("A")
            self.assertGreater(sum(1 for v in alpha.tobytes() if 0 < v < 16), 0)

    def test_tiny_and_edge_touching_subjects_fit(self):
        for index, box in enumerate([(4, 4, 4, 4), (0, 0, 29, 49)]):
            image = Image.new("RGBA", (50, 50))
            ImageDraw.Draw(image).rectangle(box, fill=(120, 80, 40, 255))
            image.save(self.source)
            result = normalizer.normalize(self.source, self.root / f"tiny-{index}.png", 64)
            bounds = result["outputVisibleBounds"]
            self.assertTrue(all(0 <= p <= 64 for p in bounds))

    def test_rejects_opaque_and_invisible_input(self):
        for image in [Image.new("RGB", (10, 10), "white"), Image.new("RGBA", (10, 10)),
                      Image.new("RGBA", (10, 10), (0, 0, 0, 15))]:
            image.save(self.source)
            with self.assertRaises(ValueError):
                normalizer.normalize(self.source, self.output)
            self.assertFalse(self.output.exists())

    def test_rejects_animation(self):
        source = self.root / "animated.gif"
        a, b = Image.new("RGB", (10, 10), "red"), Image.new("RGB", (10, 10), "blue")
        a.save(source, save_all=True, append_images=[b], duration=100, loop=0)
        with self.assertRaisesRegex(ValueError, "Animated"):
            normalizer.normalize(source, self.output)

    def test_never_overwrites_input_existing_output_or_symlink_target(self):
        self.artwork()
        original = self.source.read_bytes()
        with self.assertRaises(ValueError):
            normalizer.normalize(self.source, self.source)
        self.output.write_bytes(b"existing")
        with self.assertRaises(FileExistsError):
            normalizer.normalize(self.source, self.output)
        self.assertEqual(self.output.read_bytes(), b"existing")
        link = self.root / "link.png"
        link.symlink_to(self.source)
        with self.assertRaises(ValueError):
            normalizer.normalize(self.source, link)
        self.assertEqual(self.source.read_bytes(), original)

    def test_png_only_and_size_limits(self):
        self.artwork()
        for size in [0, 31, 4097]:
            with self.assertRaises(ValueError):
                normalizer.normalize(self.source, self.output, size)
        with self.assertRaises(ValueError):
            normalizer.normalize(self.source, self.root / "out.webp")

    def test_cli_emits_machine_readable_provenance(self):
        self.artwork()
        result = subprocess.run([sys.executable, str(SCRIPT), str(self.source), str(self.output)],
                                capture_output=True, text=True, check=True)
        report = json.loads(result.stdout)
        self.assertEqual(report["algorithm"], "visible-alpha-v1")
        self.assertEqual(report["alphaThreshold"], 16)
        self.assertEqual(report["canvasSize"], [1024, 1024])
        repeat = subprocess.run([sys.executable, str(SCRIPT), str(self.source), str(self.output)],
                                capture_output=True, text=True)
        self.assertNotEqual(repeat.returncode, 0)
        self.assertIn("pi-normalize-emoji:", repeat.stderr)


if __name__ == "__main__":
    unittest.main()
