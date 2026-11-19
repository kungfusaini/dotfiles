"""First-use VMPK/Ardour setup; never replace existing music or user keymaps."""

import configparser
import io
from pathlib import Path
import os
import sys
import tempfile
import xml.etree.ElementTree as ET

MIDI_SOURCE = "Midi-Bridge:VMPK Output:out (capture)"
FIXED_PIANO = "./Routes/Route[@name='Sketch Piano']/Processor[@unique-id='https://community.ardour.org/node/7596']"
SINGLE_CHANNEL = {
    "capture-channel-mode": "ForceChannel", "capture-channel-mask": "0x1",
    "playback-channel-mode": "ForceChannel", "playback-channel-mask": "0x1",
}


def atomic_write(path, data, exclusive=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if exclusive:
            try:
                os.link(temporary, path)
            except FileExistsError:
                pass
        else:
            temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def write_xml(path, tree):
    ET.indent(tree, space="  ")
    atomic_write(path, ET.tostring(tree.getroot(), encoding="UTF-8", xml_declaration=True))


def seed_vmpk(config):
    path = config / "vmpk.sourceforge.net/VMPK.conf"
    if path.exists():
        return
    settings = configparser.ConfigParser(interpolation=None)
    settings.optionxform = str
    settings["Connections"] = {
        "InputDriver": "ALSA", "OutputDriver": "ALSA",
        "InEnabled": "false", "ThruEnabled": "false",
    }
    settings["Preferences"] = {
        "BaseOctave": "4", "StartingKey": "0", "NumKeys": "44",
        "Channel": "0", "Velocity": "90",
        "EnableKeyboardInput": "true", "EnableMouseInput": "true",
        "EnableTouchInput": "true", "ShowStatusBar": "true",
    }
    settings["Keyboard"] = {
        "MapFile": str(config / "vmpk/home-row.xml"),
        "RawKeyboardMode": "false",
    }
    # Drumstick's ShowAlways=3 and OctaveC4=1: every piano key is labelled,
    # using the same octave convention as the companion typing-key guide.
    settings["TextSettings"] = {
        "namesVisibility": "3", "namesOctave": "1",
        "namesOrientation": "0", "namesFont": "DejaVu Sans,28",
    }
    stream = io.StringIO()
    settings.write(stream, space_around_delimiters=False)
    atomic_write(path, stream.getvalue().encode("UTF-8"), exclusive=True)


def configure_ardour(config):
    directory = config / "ardour9"
    marker = directory / ".laptop-instrument-jack-v1"
    if marker.exists():
        return
    path = directory / "config"
    tree = ET.parse(path) if path.exists() else ET.ElementTree(ET.Element("Ardour"))
    node = tree.getroot()
    for tag in ("Extra", "AudioMIDISetup", "EngineStates"):
        child = node.find(tag)
        if child is None:
            child = ET.SubElement(node, tag)
        node = child
    for state in node.findall("State"):
        state.set("active", "0")
    state = node.find("State[@backend='JACK/Pipewire']")
    if state is None:
        state = ET.SubElement(node, "State", {
            "backend": "JACK/Pipewire", "driver": "", "device": "",
            "input-device": "", "output-device": "", "sample-rate": "48000",
            "buffer-size": "256", "n-periods": "2", "input-latency": "0",
            "output-latency": "0", "use-buffered-io": "0", "midi-option": "",
        })
        ET.SubElement(state, "MIDIDevices")
    state.set("active", "1")
    state.set("lru", "1")
    backup = directory / "config.pre-laptop-instrument"
    if path.exists() and not backup.exists():
        atomic_write(backup, path.read_bytes(), exclusive=True)
    write_xml(path, tree)
    marker.touch()


def fluid_state(soundfont):
    # Lilv resolves atom:Path properties from file URIs when restoring state.
    return f'''@prefix lv2: <http://lv2plug.in/ns/lv2core#> .
@prefix pset: <http://lv2plug.in/ns/ext/presets#> .
@prefix state: <http://lv2plug.in/ns/ext/state#> .
<> a pset:Preset ;
   lv2:appliesTo <urn:ardour:a-fluidsynth> ;
   state:state [ <urn:ardour:a-fluidsynth:sf2file> <{soundfont.as_uri()}> ] .
'''.encode("UTF-8")


def replace_fixed_piano(tree, directory, soundfont):
    """Only migrate our known fixed piano; leave custom instruments alone."""
    processor = tree.find(FIXED_PIANO)
    if processor is None:
        return False
    plugin_dir = directory / "plugins" / processor.get("id")
    version = 1
    while (plugin_dir / f"state{version}").exists():
        version += 1
    state = plugin_dir / f"state{version}"
    atomic_write(state / "state.ttl", fluid_state(soundfont))
    processor.set("name", "ACE Fluid Synth")
    processor.set("unique-id", "urn:ardour:a-fluidsynth")
    old = processor.find("lv2")
    if old is not None:
        processor.remove(old)
    ET.SubElement(processor, "lv2", {
        "state-dir": state.name, "last-preset-uri": "", "last-preset-label": "",
        "parameter-changed-since-last-preset": "0",
    })
    return True


def upgrade_session(music, soundfont):
    directory = music / "Laptop Instrument"
    path = directory / "Laptop Instrument.ardour"
    if not path.is_file():
        return
    try:
        tree = ET.parse(path)
    except ET.ParseError:
        print("Laptop Instrument session is not valid XML; leaving it untouched.")
        return
    if tree.find(FIXED_PIANO) is None:
        return
    atomic_write(path.with_suffix(".ardour.pre-general-midi"), path.read_bytes(), exclusive=True)
    replace_fixed_piano(tree, directory, soundfont)
    write_xml(path, tree)


def configure_single_channel(music):
    directory = music / "Laptop Instrument"
    marker = directory / ".single-channel-v1"
    path = directory / "Laptop Instrument.ardour"
    if marker.exists() or not path.is_file():
        return
    try:
        tree = ET.parse(path)
    except ET.ParseError:
        return
    route = tree.find("./Routes/Route[@name='Sketch Piano']")
    if route is None:
        return
    if any(route.get(key) != value for key, value in SINGLE_CHANNEL.items()):
        atomic_write(path.with_suffix(".ardour.pre-single-channel"), path.read_bytes(), exclusive=True)
        route.attrib.update(SINGLE_CHANNEL)
        write_xml(path, tree)
    marker.touch()


def create_session(music, template, soundfont):
    directory = music / "Laptop Instrument"
    if directory.exists():
        return
    tree = ET.parse(template)
    root = tree.getroot()
    root.set("name", "Laptop Instrument")
    root.set("sample-rate", "48000")
    route = root.find("./Routes/Route[@default-type='midi']")
    route.attrib.update(SINGLE_CHANNEL)
    port = route.find("./IO[@direction='Input']/Port")
    ET.SubElement(port, "Connection", {"other": MIDI_SOURCE})
    monitor = route.find("Controllable[@name='monitor']")
    monitor.set("value", "1")
    monitor.set("monitoring", "MonitorInput")
    # A separate, immediately playable instrument: no tempo/grid decision,
    # transport, record arming or changes to the user's existing sketches.
    music.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".laptop-instrument-", dir=music) as tmp:
        staged = Path(tmp) / "Laptop Instrument"
        replace_fixed_piano(tree, staged, soundfont)
        write_xml(staged / "Laptop Instrument.ardour", tree)
        if not directory.exists():
            staged.rename(directory)


def setup(config, music, template, *, soundfont, vmpk_running=False, ardour_running=False):
    if vmpk_running:
        print("VMPK is running; skipping initial keyboard preferences.")
    else:
        seed_vmpk(config)
    if ardour_running:
        print("Ardour is running; skipping its JACK preference migration.")
    else:
        configure_ardour(config)
        upgrade_session(music, soundfont)
    create_session(music, template, soundfont)
    if not ardour_running:
        configure_single_channel(music)


if __name__ == "__main__":
    config, music, template = map(Path, sys.argv[1:4])
    setup(config, music, template, soundfont=Path(sys.argv[6]),
          vmpk_running=sys.argv[4] == "running",
          ardour_running=sys.argv[5] == "running")
