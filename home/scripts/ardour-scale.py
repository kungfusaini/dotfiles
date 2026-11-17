"""Set Ardour's per-application scale without replacing its other preferences."""

import os
from pathlib import Path
import sys
import tempfile
import xml.etree.ElementTree as ET


def set_scale(path):
    path = Path(path)
    tree = ET.parse(path) if path.exists() else ET.ElementTree(ET.Element("Ardour"))
    root = tree.getroot()
    if root.tag != "Ardour":
        raise ValueError("Unexpected Ardour preferences format")
    ui = root.find("UI")
    if ui is None:
        ui = ET.SubElement(root, "UI")
    scale = ui.find("Option[@name='font-scale']")
    if scale is None:
        scale = ET.SubElement(ui, "Option", name="font-scale")
    if scale.get("value") == "128000":
        return
    scale.set("value", "128000")  # 125 percent * 1024
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".ui_config-")
    try:
        with os.fdopen(fd, "wb") as output:
            tree.write(output, encoding="UTF-8", xml_declaration=True)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


if __name__ == "__main__":
    set_scale(sys.argv[1])
