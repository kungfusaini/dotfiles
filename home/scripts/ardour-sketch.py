"""Seed an editable sketch session and initial layout, never reset existing work."""

from copy import deepcopy
from pathlib import Path
import os
import struct
import sys
import tempfile
import uuid
import xml.etree.ElementTree as ET


def write_xml(path, tree):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".sketch-")
    try:
        with os.fdopen(fd, "wb") as output:
            tree.write(output, encoding="UTF-8", xml_declaration=True)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def layout(config):
    marker = config / ".musical-sketch-layout-v1"
    if marker.exists():
        return
    ui_path = config / "ui_config"
    ui_tree = ET.parse(ui_path) if ui_path.exists() else ET.ElementTree(ET.Element("Ardour"))
    ui = ui_tree.getroot().find("UI")
    if ui is None:
        ui = ET.SubElement(ui_tree.getroot(), "UI")
    for name in ("show-toolbar-recpunch", "show-secondary-clock", "show-toolbar-selclock",
                 "show-toolbar-latency", "show-toolbar-cuectrl", "show-mini-timeline"):
        option = ui.find(f"Option[@name='{name}']")
        if option is None:
            option = ET.SubElement(ui, "Option", name=name)
        option.set("value", "0")
    instant_path = config / "instant.xml"
    instant = ET.parse(instant_path) if instant_path.exists() else ET.ElementTree(ET.Element("instant"))
    editor = instant.getroot().find("Editor")
    if editor is None:
        editor = ET.SubElement(instant.getroot(), "Editor")
    editor.attrib.update({"show-editor-mixer": "0", "show-editor-list": "0",
                          "show-editor-props": "0", "zoom": "512", "left-frame": "0",
                          "playhead": "0", "mouse-mode": "MouseDraw",
                          "grid-type": "GridTypeBeat", "snap-mode": "SnapNormal",
                          "internal-grid-type": "GridTypeBeat", "internal-snap-mode": "SnapNormal"})
    write_xml(ui_path, ui_tree)
    write_xml(instant_path, instant)
    marker.touch()


def starter(music, template, instant):
    directory = music / "Musical Sketch"
    if directory.exists():
        return
    tree = ET.parse(template)
    root = tree.getroot()
    root.attrib.update({"name": "Musical Sketch", "uuid": str(uuid.uuid4()),
                        "sample-rate": "48000", "session-range-is-free": "1",
                        "id-counter": "600"})
    root.remove(root.find("description"))
    ET.SubElement(root.find("Sources"), "Source", name="Sketch.mid", type="midi", id="500",
                  flags="Writable,CanRename", **{"take-id": "", "origin": ""})
    region = ET.SubElement(root.find("Regions"), "Region", {
        "name": "Your first idea", "id": "501", "type": "midi", "start": "b0",
        "position": "b0", "length": "b30720@b0", "whole-file": "1", "opaque": "0",
        "source-0": "500", "master-source-0": "500", "first-edit": "nothing"})
    placed = deepcopy(region)
    placed.set("id", "502")
    placed.set("whole-file", "0")
    root.find("Playlists/Playlist").append(placed)
    ET.SubElement(root.find("Locations"), "Location", id="503", name="session", start="b0",
                  end="b30720", flags="IsSessionRange", locked="0")
    # Standard MIDI file, format 0, 1920 ticks/quarter, empty end-of-track event.
    midi = b"MThd" + struct.pack(">IHHH", 6, 0, 1, 1920) + b"MTrk" + struct.pack(">I", 4) + b"\x00\xff\x2f\x00"
    directory.mkdir(parents=True)
    midi_path = directory / "interchange/Musical Sketch/midifiles/Sketch.mid"
    midi_path.parent.mkdir(parents=True)
    midi_path.write_bytes(midi)
    write_xml(directory / "instant.xml", ET.parse(instant))
    write_xml(directory / "Musical Sketch.ardour", tree)


if __name__ == "__main__":
    config, music, template = map(Path, sys.argv[1:])
    layout(config)
    starter(music, template, config / "instant.xml")
