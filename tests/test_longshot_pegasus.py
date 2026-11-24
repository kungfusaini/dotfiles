"""Contracts for direct Longshot launch and opt-in update management."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class LongshotPegasusTests(unittest.TestCase):
    def test_game_gate_and_direct_launch(self):
        text = (ROOT / "home/config/pegasus/longshot.metadata.pegasus.txt").read_text()
        self.assertIn("collection: PC\nshortname: pc", text)
        self.assertIn("file: /home/sumeet/matrix/projects/longshot/game/bin/longshot", text)
        self.assertIn("launch: tablet-game-launch -- longshot-play", text)
        self.assertNotIn("launch: longshot-launcher", text)

    def test_notification_is_launch_triggered_not_scheduled(self):
        module = (ROOT / "home/modules/pegasus.nix").read_text()
        package = (ROOT / "home/packages/longshot/default.nix").read_text()
        self.assertIn('"pegasus-frontend/metafiles/longshot.metadata.pegasus.txt".source', module)
        self.assertIn("systemd.user.services.longshot-update-check", module)
        self.assertNotIn("systemd.user.timers.longshot", module)
        self.assertIn("start --no-block longshot-update-check.service", package)
        self.assertIn('exec appimage-run ${builder} --play "$game"', package)
        self.assertIn("xdg.desktopEntries.longshot-launcher", module)


if __name__ == "__main__":
    unittest.main()
