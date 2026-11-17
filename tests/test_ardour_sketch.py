"""Sketch initialization tests use only temporary preferences and music folders."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "home/config/ardour/musical-sketch.template"
spec = importlib.util.spec_from_file_location("sketch", ROOT / "home/scripts/ardour-sketch.py")
sketch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sketch)


class SketchTests(unittest.TestCase):
    def test_layout_preserves_scale_and_can_grow_after_first_run(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory)
            (config / "ui_config").write_text('<Ardour><UI><Option name="font-scale" value="128000"/></UI></Ardour>')
            (config / "instant.xml").write_text('<instant><Other keep="yes"/></instant>')
            sketch.layout(config)
            ui = ET.parse(config / "ui_config")
            self.assertEqual(ui.find("UI/Option[@name='font-scale']").get("value"), "128000")
            instant = ET.parse(config / "instant.xml")
            self.assertEqual(instant.find("Editor").get("show-editor-mixer"), "0")
            self.assertEqual(instant.find("Other").get("keep"), "yes")
            instant.find("Editor").set("show-editor-mixer", "1")
            instant.write(config / "instant.xml")
            sketch.layout(config)
            self.assertEqual(ET.parse(config / "instant.xml").find("Editor").get("show-editor-mixer"), "1")

    def test_starter_is_blank_routed_and_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "config"
            sketch.layout(config)
            sketch.starter(root / "music", TEMPLATE, config / "instant.xml")
            session = root / "music/Musical Sketch/Musical Sketch.ardour"
            tree = ET.parse(session)
            routes = tree.findall("Routes/Route")
            self.assertEqual(len(routes), 2)
            self.assertEqual([r.get("name") for r in routes], ["Master", "Sketch Piano"])
            self.assertIsNotNone(tree.find("Routes/Route/Processor[@type='lv2']"))
            self.assertEqual(len(tree.findall("Locations/Location")), 1)
            self.assertEqual(tree.find("Playlists/Playlist/Region").get("length"), "b30720@b0")
            self.assertIsNotNone(tree.find("Config/Option[@name='native-file-data-format']"))
            midi = root / "music/Musical Sketch/interchange/Musical Sketch/midifiles/Sketch.mid"
            self.assertEqual(midi.read_bytes()[-4:], b"\x00\xff\x2f\x00")
            session.write_text("user's work")
            sketch.starter(root / "music", TEMPLATE, config / "instant.xml")
            self.assertEqual(session.read_text(), "user's work")

    def test_template_has_no_machine_or_audio_device_state(self):
        tree = ET.parse(TEMPLATE)
        self.assertIsNone(tree.find("EngineHints"))
        self.assertIsNone(tree.find("EngineState"))
        self.assertEqual(len(tree.findall("Sources/Source")), 0)
        self.assertEqual(len(tree.findall("Locations/Location")), 0)
        self.assertEqual(tree.find("Extra/RulerVisibility").get("bbt"), "1")
        self.assertEqual(tree.find("Extra/UI/GUIObjectState/Object[@id='rtav 119']").get("height"), "580")
        self.assertNotIn("/home/", TEMPLATE.read_text())
        self.assertNotIn("/tmp/", TEMPLATE.read_text())


if __name__ == "__main__":
    unittest.main()
