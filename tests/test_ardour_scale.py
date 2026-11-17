"""Exercise Ardour scaling against temporary preferences, never live sessions."""
import importlib.util
from pathlib import Path
import tempfile
import subprocess
import unittest
import xml.etree.ElementTree as ET

SOURCE = Path(__file__).resolve().parents[1] / "home/scripts/ardour-scale.py"
spec = importlib.util.spec_from_file_location("ardour_scale", SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ArdourScaleTests(unittest.TestCase):
    def test_new_preferences(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ardour9/ui_config"
            module.set_scale(path)
            self.assertEqual(ET.parse(path).find("UI/Option").get("value"), "128000")

    def test_preserve_other_preferences_and_idempotence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ui_config"
            path.write_text('<Ardour><UI><Option name="font-scale" value="102400"/>'
                            '<Option name="other" value="keep"/></UI>'
                            '<Canvas><Option name="normal font" value="8"/></Canvas></Ardour>')
            module.set_scale(path)
            tree = ET.parse(path)
            self.assertEqual(tree.find("UI/Option[@name='font-scale']").get("value"), "128000")
            self.assertEqual(tree.find("UI/Option[@name='other']").get("value"), "keep")
            self.assertIsNotNone(tree.find("Canvas/Option"))
            before = path.stat().st_mtime_ns
            module.set_scale(path)
            self.assertEqual(path.stat().st_mtime_ns, before)

    def test_activation_honors_dry_run(self):
        source = (SOURCE.parents[1] / "sumeet.nix").read_text()
        activation = source.split('home.activation.ardourScale =', 1)[1].split("''", 2)[1]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ardour9/ui_config"
            activation = (activation.replace('${pkgs.procps}/bin/pgrep', 'false')
                          .replace('${pkgs.python3}/bin/python3', 'python3')
                          .replace('${./scripts/ardour-scale.py}', str(SOURCE))
                          .replace('${config.xdg.configHome}', directory)
                          .replace('${./scripts/ardour-sketch.py}', str(SOURCE.with_name('ardour-sketch.py')))
                          .replace('${config.home.homeDirectory}', directory)
                          .replace('${./config/ardour/musical-sketch.template}', 'unused-template'))
            # Home Manager's run helper logs commands instead of running them
            # in dry-run mode. A direct invocation would create the file here.
            result = subprocess.run(['bash', '-eu', '-c',
                                     'run() { printf "dry run: %s\\n" "$*"; };\n' + activation],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('dry run:', result.stdout)
            self.assertFalse(path.exists())

    def test_malformed_preferences_are_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ui_config"
            path.write_text("<broken")
            with self.assertRaises(ET.ParseError):
                module.set_scale(path)
            self.assertEqual(path.read_text(), "<broken")


if __name__ == "__main__":
    unittest.main()
