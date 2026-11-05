"""Headless launcher regressions; no game code, display, or real saves are used."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class SymphonyLauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "data with spaces"
        self.state = self.root / "games/symphony-recomp"
        self.app = self.base / "app"
        (self.app / "mods/shaders").mkdir(parents=True)
        (self.app / "mods/shaders/mod.json").write_text("{}")
        self.dotnet = self.base / "dotnet"
        self.dotnet.write_text('#!/bin/sh\nprintf "%s\\n" "$PWD" "$@"\n')
        self.dotnet.chmod(0o755)
        source = (Path(__file__).resolve().parents[1]
                  / "home/packages/symphony-recomp/launch.sh").read_text()
        for key, value in {
            "shell": shutil.which("bash"), "jq": shutil.which("jq"),
            "app": str(self.app), "dotnet": str(self.dotnet),
        }.items():
            self.assertIsNotNone(value, f"Missing test dependency: {key}")
            source = source.replace(f"@{key}@", value)
        self.launcher = self.base / "launch"
        self.launcher.write_text(source)
        self.launcher.chmod(0o755)
        self.env = dict(os.environ, SYMPHONY_RECOMP_DATA_ROOT=str(self.root))

    def disc(self):
        disc = (self.root / "roms/ps1/Castlevania - Symphony of the Night (USA)"
                / "Castlevania - Symphony of the Night (USA).cue")
        disc.parent.mkdir(parents=True)
        disc.touch()
        return disc

    def run_launcher(self, *args):
        return subprocess.run([str(self.launcher), *args], env=self.env,
                              capture_output=True, text=True)

    def test_missing_disc_fails_without_creating_state(self):
        result = self.run_launcher()
        self.assertEqual(result.returncode, 1)
        self.assertIn("requires your USA PS1", result.stderr)
        self.assertFalse(self.state.exists())

    def test_first_run_seeds_private_state_and_forwards_arguments(self):
        disc = self.disc()
        result = self.run_launcher("argument with spaces")
        self.assertEqual(result.returncode, 0, result.stderr)
        settings = json.loads((self.state / "settings.json").read_text())
        self.assertEqual(settings["system"]["discPath"], str(disc))
        self.assertFalse(settings["options"]["updates.check_on_startup"])
        self.assertEqual(settings["system"]["cardA"]["path"],
                         str(self.root / "saves/symphony-recomp/carda.sav"))
        self.assertEqual(result.stdout.splitlines(), [str(self.state),
                         str(self.app / "sotn.dll"), "argument with spaces"])
        self.assertEqual((self.state / "settings.json").stat().st_mode & 0o777, 0o600)
        self.assertFalse((self.state / "mods").is_symlink())
        self.assertTrue((self.state / "mods/shaders").is_symlink())
        (self.state / "mods/.cache").mkdir()

    def test_repeat_run_preserves_settings_cards_and_custom_mods(self):
        self.disc()
        self.assertEqual(self.run_launcher().returncode, 0)
        settings = self.state / "settings.json"
        settings.write_text('{"custom": "player setting"}')
        card = self.root / "saves/symphony-recomp/carda.sav"
        card.write_bytes(b"player save")
        mod = self.state / "mods/shaders"
        mod.unlink()
        mod.mkdir()
        (mod / "custom").write_text("player mod")
        self.assertEqual(self.run_launcher().returncode, 0)
        self.assertEqual(settings.read_text(), '{"custom": "player setting"}')
        self.assertEqual(card.read_bytes(), b"player save")
        self.assertEqual((mod / "custom").read_text(), "player mod")


if __name__ == "__main__":
    unittest.main()
