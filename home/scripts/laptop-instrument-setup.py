"""First-use VMPK/Ardour setup; never replace existing music or user keymaps."""

import configparser
import io
from pathlib import Path
import os
import sys
import tempfile
import xml.etree.ElementTree as ET

MIDI_SOURCE = "Midi-Bridge:VMPK Output:out (capture)"


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
        "BaseOctave": "4", "StartingKey": "0", "NumKeys": "61",
        "Channel": "0", "Velocity": "90",
        "EnableKeyboardInput": "true", "EnableMouseInput": "true",
        "EnableTouchInput": "true", "ShowStatusBar": "true",
    }
    settings["Keyboard"] = {
        "MapFile": str(config / "vmpk/home-row.xml"),
        "RawKeyboardMode": "false",
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


def create_session(music, template):
    directory = music / "Laptop Instrument"
    if directory.exists():
        return
    tree = ET.parse(template)
    root = tree.getroot()
    root.set("name", "Laptop Instrument")
    root.set("sample-rate", "48000")
    route = root.find("./Routes/Route[@default-type='midi']")
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
        write_xml(staged / "Laptop Instrument.ardour", tree)
        if not directory.exists():
            staged.rename(directory)


def setup(config, music, template, vmpk_running=False, ardour_running=False):
    if vmpk_running:
        print("VMPK is running; skipping initial keyboard preferences.")
    else:
        seed_vmpk(config)
    if ardour_running:
        print("Ardour is running; skipping its JACK preference migration.")
    else:
        configure_ardour(config)
    create_session(music, template)


if __name__ == "__main__":
    config, music, template = map(Path, sys.argv[1:4])
    setup(config, music, template,
          vmpk_running=sys.argv[4] == "running",
          ardour_running=sys.argv[5] == "running")
