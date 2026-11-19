"""Render the managed VMPK keymap as a static, beginner-facing SVG reference."""

from pathlib import Path
import sys
import xml.etree.ElementTree as ET

SVG = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG)
NOTES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
ROWS = ("1234567890-=", "QWERTYUIOP[]\\", "ASDFGHJKL;'", "ZXCVBNM,./")
COLORS = ("#f6c66c", "#c9a9ff", "#8ee5cd", "#8cc7ff")


def note_name(midi):
    return f"{NOTES[midi % 12]}{midi // 12 - 1}"


def render(keymap, base_octave=4):
    mapping = {m.get("key"): base_octave * 12 + int(m.get("note"))
               for m in ET.parse(keymap).findall("mapping")}
    root = ET.Element(f"{{{SVG}}}svg", {"width": "1500", "height": "1020",
                                           "viewBox": "0 0 1500 1020"})
    ET.SubElement(root, f"{{{SVG}}}title").text = "Laptop piano: typing keys and notes"
    ET.SubElement(root, f"{{{SVG}}}desc").text = (
        "Static reference for the managed VMPK home-row layout. "
        "Play in VMPK to see live note highlighting; this image does not play notes.")

    def element(tag, **attrs):
        return ET.SubElement(root, f"{{{SVG}}}{tag}",
                             {k.replace("_", "-"): str(v) for k, v in attrs.items()})

    def text(x, y, value, size=22, color="#b7c4d8", anchor="start", weight="normal"):
        element("text", x=x, y=y, font_family="DejaVu Sans", font_size=size,
                fill=color, text_anchor=anchor, font_weight=weight).text = value

    def rect(x, y, width, height, fill, stroke="none", rx=0):
        return element("rect", x=x, y=y, width=width, height=height,
                       fill=fill, stroke=stroke, rx=rx)

    rect(0, 0, 1500, 1020, "#101925")
    text(60, 66, "Play from your home row", 38, "#f0f5fc", weight="bold")
    text(60, 103, "Large letters = laptop keys     Smaller labels = musical notes", 23)
    text(1440, 64, "VMPK  /  STARTING LAYOUT", 18, "#8ee5cd", "end", "bold")
    text(1440, 99, f"Base Octave {base_octave}  ·  Transpose 0", 18, anchor="end")

    # Two piano octaves: the home row plus its higher continuation.
    start = (base_octave + 1) * 12
    whites = [n for n in range(start, start + 24) if "#" not in NOTES[n % 12]]
    width, x0, y0 = 96, 78, 150
    for index, midi in enumerate(whites):
        x = x0 + index * width
        rect(x, y0, width - 2, 245, "#f1f5f4", rx=5)
        # Main fingering, without crowding the piano with duplicate aliases.
        keys = [key for key in ROWS[2] if mapping.get(key) == midi]
        if not keys:
            keys = [key for key in ROWS[0] if mapping.get(key) == midi]
        text(x + width / 2, y0 + 183, " / ".join(keys), 33, "#142c2b", "middle", "bold")
        text(x + width / 2, y0 + 220, note_name(midi), 22, "#4b6262", "middle")
    for index, midi in enumerate(whites[:-1]):
        if midi + 1 == whites[index + 1]:
            continue
        black = midi + 1
        x = x0 + (index + 1) * width - 30
        rect(x, y0, 60, 143, "#283344", "#101925", 4)
        keys = [key for key in ROWS[1] if mapping.get(key) == black]
        text(x + 30, y0 + 79, " / ".join(keys), 25, "#dfcaff", "middle", "bold")
        text(x + 30, y0 + 117, note_name(black), 16, "#c6b5df", "middle")
    anchor_note = "A = middle C" if mapping.get("A") == 60 else "Typing keys → piano notes"
    text(78, 432, anchor_note, 23, "#8ee5cd", weight="bold")
    text(1422, 432, f"The laptop rows below show all {len(mapping)} mapped keys, including duplicates.", 20, anchor="end")

    # Physical typing rows, staggered like a laptop keyboard.
    for row_index, row in enumerate(ROWS):
        y = 489 + row_index * 105
        x_start = 84 + (0, 25, 52, 104)[row_index]
        for index, key in enumerate(row):
            x, midi = x_start + index * 99, mapping.get(key)
            group = element("g", data_key=key, data_midi=midi if midi is not None else "")
            color = COLORS[row_index] if midi is not None else "#586475"
            cap = rect(x, y, 91, 88, "#1d2a3b", color, 9)
            root.remove(cap)
            group.append(cap)
            text(x + 45.5, y + 37, key, 29, color, "middle", "bold")
            text(x + 45.5, y + 69, note_name(midi) if midi is not None else "—",
                 19, "#e3ebf5" if midi is not None else "#586475", "middle")

    text(60, 952, "← / →  Octave   ·   Home / End  Softer / louder   ·   Esc  Stop notes   ·   Choose sounds and sustain in Ardour", 22, "#f0f5fc")
    text(60, 990, "Keep VMPK focused to play and see notes light up. This guide is static; octave shifts or edited mappings change the notes.", 19)
    return ET.ElementTree(root)


if __name__ == "__main__":
    render(Path(sys.argv[1])).write(sys.argv[2], encoding="UTF-8", xml_declaration=True)
