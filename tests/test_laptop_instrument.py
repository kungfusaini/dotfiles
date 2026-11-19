import configparser
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "laptop_instrument", ROOT / "home/scripts/laptop-instrument-setup.py")
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)
TEMPLATE = ROOT / "home/config/ardour/musical-sketch.template"
FONT = Path("/test/soundfonts/General MIDI.sf2")
guide_spec = importlib.util.spec_from_file_location(
    "laptop_keyboard_guide", ROOT / "home/scripts/laptop-keyboard-guide.py")
guide = importlib.util.module_from_spec(guide_spec)
guide_spec.loader.exec_module(guide)


class LaptopInstrumentTests(unittest.TestCase):
    def test_home_row_and_no_shortcut_collisions(self):
        entries = ET.parse(ROOT / "home/config/vmpk/home-row.xml").findall("mapping")
        mapping = {entry.get("key"): int(entry.get("note")) for entry in entries}
        self.assertEqual(len(entries), len(mapping))
        self.assertEqual(len(mapping), 43)
        self.assertEqual([mapping[k] for k in "ASDFGHJKL;'"],
                         [12, 14, 16, 17, 19, 21, 23, 24, 26, 28, 29])
        self.assertEqual([mapping[k] for k in "WETYU"], [13, 15, 18, 20, 22])
        self.assertEqual(mapping["Z"], 0)
        self.assertEqual(mapping["="], 43)
        self.assertTrue(all(0 <= note < 44 for note in mapping.values()))
        self.assertFalse(set(mapping) & {"Left", "Right", "PgUp", "PgDown", "Esc"})

    def test_visual_guide_matches_every_managed_mapping(self):
        path = ROOT / "home/config/vmpk/home-row.xml"
        svg = guide.render(path).getroot()
        caps = {g.get("data-key"): g.get("data-midi")
                for g in svg.findall(f"{{{guide.SVG}}}g")}
        mapping = {m.get("key"): str(48 + int(m.get("note")))
                   for m in ET.parse(path).findall("mapping")}
        self.assertEqual({k: v for k, v in caps.items() if v}, mapping)
        self.assertEqual(caps["A"], "60")
        self.assertEqual(caps["W"], "61")
        self.assertEqual(caps["Q"], "")
        text = " ".join(svg.itertext())
        self.assertIn("A = middle C", text)
        self.assertIn("C4", text)
        self.assertIn("G6", text)
        self.assertIn("This guide is static", text)

    def test_visual_guide_tracks_changes_instead_of_duplicating_the_map(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "map.xml"
            path.write_text('<keyboardmap><mapping key="A" note="14"/></keyboardmap>')
            svg = guide.render(path).getroot()
            cap = next(g for g in svg.findall(f"{{{guide.SVG}}}g") if g.get("data-key") == "A")
            self.assertEqual(cap.get("data-midi"), "62")
        self.assertEqual(guide.note_name(60), "C4")
        self.assertEqual(guide.note_name(61), "C#4")

    def test_initial_setup_is_playable_and_preserves_other_preferences(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config, music = root / "config", root / "music"
            ardour = config / "ardour9/config"
            ardour.parent.mkdir(parents=True)
            original = b'<Ardour><Config><Option name="unrelated" value="keep"/></Config><Extra><AudioMIDISetup><EngineStates><State backend="PulseAudio" active="1"/></EngineStates></AudioMIDISetup></Extra></Ardour>'
            ardour.write_bytes(original)
            setup.setup(config, music, TEMPLATE, soundfont=FONT)
            states = ET.parse(ardour).findall(".//EngineStates/State")
            self.assertEqual([s.get("backend") for s in states if s.get("active") == "1"],
                             ["JACK/Pipewire"])
            self.assertEqual(ET.parse(ardour).find(".//Option").get("value"), "keep")
            self.assertEqual(ardour.with_name("config.pre-laptop-instrument").read_bytes(), original)
            session = music / "Laptop Instrument/Laptop Instrument.ardour"
            route = ET.parse(session).find("./Routes/Route[@default-type='midi']")
            self.assertEqual(route.find("Controllable[@name='monitor']").get("value"), "1")
            self.assertIn(setup.MIDI_SOURCE, [c.get("other") for c in route.findall("./IO[@direction='Input']/Port/Connection")])
            fluid = route.find("Processor[@unique-id='urn:ardour:a-fluidsynth']")
            self.assertIsNotNone(fluid)
            state = session.parent / "plugins" / fluid.get("id") / fluid.find("lv2").get("state-dir") / "state.ttl"
            self.assertIn(FONT.as_uri(), state.read_text())
            self.assertNotIn(" ", FONT.as_uri())
            prefs = configparser.ConfigParser()
            prefs.read(config / "vmpk.sourceforge.net/VMPK.conf")
            self.assertEqual(prefs["Keyboard"]["MapFile"], str(config / "vmpk/home-row.xml"))
            self.assertEqual(prefs["Connections"]["ThruEnabled"], "false")
            self.assertEqual(prefs["Preferences"]["BaseOctave"], "4")
            self.assertEqual(prefs["Preferences"]["NumKeys"], "44")
            self.assertEqual(prefs["TextSettings"]["namesVisibility"], "3")
            self.assertEqual(prefs["TextSettings"]["namesOctave"], "1")

    def test_repeated_activation_never_replaces_preferences_or_music(self):
        with tempfile.TemporaryDirectory() as tmp:
            config, music = Path(tmp) / "config", Path(tmp) / "music"
            setup.setup(config, music, TEMPLATE, soundfont=FONT)
            prefs = config / "vmpk.sourceforge.net/VMPK.conf"
            prefs.write_text("my custom map and shortcuts")
            ardour = config / "ardour9/config"
            ardour.write_text("my later audio preferences")
            session = music / "Laptop Instrument/Laptop Instrument.ardour"
            session.write_text("my music")
            setup.setup(config, music, TEMPLATE, soundfont=FONT)
            self.assertEqual(prefs.read_text(), "my custom map and shortcuts")
            self.assertEqual(ardour.read_text(), "my later audio preferences")
            self.assertEqual(session.read_text(), "my music")

    def test_failed_preferences_write_preserves_original_and_retries(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp)
            path = config / "ardour9/config"
            path.parent.mkdir()
            original = b'<Ardour><Config/></Ardour>'
            path.write_bytes(original)
            with mock.patch.object(Path, "replace", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    setup.configure_ardour(config)
            self.assertEqual(path.read_bytes(), original)
            self.assertFalse((path.parent / ".laptop-instrument-jack-v1").exists())
            self.assertEqual({p.name for p in path.parent.iterdir()},
                             {"config", "config.pre-laptop-instrument"})
            setup.configure_ardour(config)
            self.assertIsNotNone(ET.parse(path).find(".//State[@backend='JACK/Pipewire']"))

    def test_failed_backup_is_not_published_and_retry_preserves_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp)
            path = config / "ardour9/config"
            path.parent.mkdir()
            original = b'<Ardour><Config/></Ardour>'
            path.write_bytes(original)
            backup = path.with_name("config.pre-laptop-instrument")
            with mock.patch.object(setup.os, "fsync", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    setup.configure_ardour(config)
            self.assertEqual(path.read_bytes(), original)
            self.assertFalse(backup.exists())
            self.assertEqual(list(path.parent.iterdir()), [path])
            setup.configure_ardour(config)
            self.assertEqual(backup.read_bytes(), original)
            self.assertIsNotNone(ET.parse(path).find(".//State[@backend='JACK/Pipewire']"))

    def test_failed_session_creation_leaves_no_partial_session_and_retries(self):
        with tempfile.TemporaryDirectory() as tmp:
            music = Path(tmp)
            with mock.patch.object(setup, "atomic_write", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    setup.create_session(music, TEMPLATE, FONT)
            self.assertEqual(list(music.iterdir()), [])
            setup.create_session(music, TEMPLATE, FONT)
            self.assertTrue((music / "Laptop Instrument/Laptop Instrument.ardour").exists())

    def test_atomic_create_never_overwrites_existing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings"
            path.write_bytes(b"original")
            setup.atomic_write(path, b"replacement", exclusive=True)
            self.assertEqual(path.read_bytes(), b"original")
            self.assertEqual(list(Path(tmp).iterdir()), [path])

    def test_existing_fixed_piano_upgrade_preserves_music_and_headphone_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            music = Path(tmp)
            path = music / "Laptop Instrument/Laptop Instrument.ardour"
            path.parent.mkdir()
            tree = ET.parse(TEMPLATE)
            ET.SubElement(tree.find("Sources"), "Source", {"name": "my-performance.mid", "id": "999"})
            output = tree.find("./Routes/Route[@name='Master']/IO[@direction='Output']/Port/Connection")
            output.set("other", "my-headphones:playback_FL")
            setup.write_xml(path, tree)
            original = path.read_bytes()
            setup.upgrade_session(music, FONT)
            new = ET.parse(path)
            self.assertIsNone(new.find(setup.FIXED_PIANO))
            self.assertIsNotNone(new.find(".//Processor[@unique-id='urn:ardour:a-fluidsynth']"))
            self.assertEqual(new.find("Sources/Source").get("name"), "my-performance.mid")
            self.assertEqual(new.find("./Routes/Route[@name='Master']/IO[@direction='Output']/Port/Connection").get("other"), "my-headphones:playback_FL")
            self.assertEqual(path.with_suffix(".ardour.pre-general-midi").read_bytes(), original)
            first = path.read_bytes()
            setup.upgrade_session(music, FONT)
            self.assertEqual(path.read_bytes(), first)

    def test_custom_instrument_is_not_replaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            music = Path(tmp)
            path = music / "Laptop Instrument/Laptop Instrument.ardour"
            tree = ET.parse(TEMPLATE)
            tree.find(setup.FIXED_PIANO).set("unique-id", "urn:my-custom-synth")
            setup.write_xml(path, tree)
            original = path.read_bytes()
            setup.upgrade_session(music, FONT)
            self.assertEqual(path.read_bytes(), original)
            self.assertFalse((path.parent / "plugins").exists())
            self.assertFalse(path.with_suffix(".ardour.pre-general-midi").exists())

    def test_running_session_is_not_upgraded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "music/Laptop Instrument/Laptop Instrument.ardour"
            setup.write_xml(path, ET.parse(TEMPLATE))
            original = path.read_bytes()
            setup.setup(root / "config", root / "music", TEMPLATE, soundfont=FONT, ardour_running=True)
            self.assertEqual(path.read_bytes(), original)
            self.assertFalse((path.parent / "plugins").exists())

    def test_failed_upgrade_keeps_snapshot_and_can_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            music = Path(tmp)
            path = music / "Laptop Instrument/Laptop Instrument.ardour"
            setup.write_xml(path, ET.parse(TEMPLATE))
            original = path.read_bytes()
            with mock.patch.object(setup, "write_xml", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    setup.upgrade_session(music, FONT)
            self.assertEqual(path.read_bytes(), original)
            setup.upgrade_session(music, FONT)
            self.assertIsNone(ET.parse(path).find(setup.FIXED_PIANO))
            self.assertEqual(path.with_suffix(".ardour.pre-general-midi").read_bytes(), original)

    def test_running_applications_are_not_reconfigured(self):
        with tempfile.TemporaryDirectory() as tmp:
            config, music = Path(tmp) / "config", Path(tmp) / "music"
            setup.setup(config, music, TEMPLATE, soundfont=FONT, vmpk_running=True, ardour_running=True)
            self.assertFalse((config / "ardour9/config").exists())
            self.assertFalse((config / "vmpk.sourceforge.net/VMPK.conf").exists())
            self.assertTrue((music / "Laptop Instrument/Laptop Instrument.ardour").exists())


if __name__ == "__main__":
    unittest.main()
