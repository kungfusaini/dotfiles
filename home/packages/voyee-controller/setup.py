"""Apply the captured Bluetooth VOYEE S08 layout to existing emulator settings.

No global SDL overrides: PCSX2/SDL3 uses positions, bundled SDL2 uses labels.
Explicit opt-in only; never run during activation or while an emulator is open.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import re
import tempfile

# Ryubing SDL2GamepadDriver: .NET GUID byte order, CRC prefix zeroed.
RYU_ID = "0-00000005-057e-0000-0920-000001800000"
PS2 = {
    "Cross": "FaceSouth", "Circle": "FaceEast",
    "Square": "FaceWest", "Triangle": "FaceNorth",
    "Up": "DPadUp", "Down": "DPadDown", "Left": "DPadLeft", "Right": "DPadRight",
    "L1": "LeftShoulder", "R1": "RightShoulder",
    "L2": "+LeftTrigger", "R2": "+RightTrigger",
    "L3": "LeftStick", "R3": "RightStick", "Select": "Back", "Start": "Start",
    "LLeft": "-LeftX", "LRight": "+LeftX", "LUp": "-LeftY", "LDown": "+LeftY",
    "RLeft": "-RightX", "RRight": "+RightX", "RUp": "-RightY", "RDown": "+RightY",
}
# The shipped Symphony SDL2 reports Nintendo face labels, not Xbox positions.
PS1 = {"cross": [1], "circle": [0], "square": [3], "triangle": [2],
       "l1": [9], "r1": [10], "l2": [100], "r2": [101],
       "l3": [7], "r3": [8], "select": [4], "start": [6],
       "up": [11], "down": [12], "left": [13], "right": [14],
       "leftStickX": 0, "leftStickY": 1, "rightStickX": 2, "rightStickY": 3}


def nintendo_profile():
    def stick(side):
        return {"joystick": side, "stick_button": side + "Stick",
                "invert_stick_x": False, "invert_stick_y": False, "rotate90_cw": False}
    return {
        "version": 1, "backend": "GamepadSDL2", "id": RYU_ID,
        "name": "Nintendo Switch Pro Controller", "controller_type": "ProController",
        "player_index": "Player1", "deadzone_left": 0.1, "deadzone_right": 0.1,
        "range_left": 1.0, "range_right": 1.0, "trigger_threshold": 0.5,
        "left_joycon_stick": stick("Left"), "right_joycon_stick": stick("Right"),
        "left_joycon": {"dpad_up": "DpadUp", "dpad_down": "DpadDown",
                        "dpad_left": "DpadLeft", "dpad_right": "DpadRight",
                        "button_minus": "Minus", "button_l": "LeftShoulder",
                        "button_zl": "LeftTrigger", "button_sl": "Unbound", "button_sr": "Unbound"},
        "right_joycon": {"button_a": "A", "button_b": "B", "button_x": "X", "button_y": "Y",
                         "button_plus": "Plus", "button_r": "RightShoulder",
                         "button_zr": "RightTrigger", "button_sl": "Unbound", "button_sr": "Unbound"},
        "motion": {"motion_backend": "GamepadDriver", "enable_motion": False,
                   "sensitivity": 100, "gyro_deadzone": 1},
        "rumble": {"enable_rumble": False, "strong_rumble": 1.0, "weak_rumble": 1.0},
    }


def ini_values(text, section):
    result = {}
    active = False
    for line in text.splitlines():
        if line.startswith("["):
            active = line.strip() == f"[{section}]"
        elif active and "=" in line and not line.lstrip().startswith(("#", ";")):
            key, value = line.split("=", 1)
            result.setdefault(key.strip(), []).append(value.strip())
    return result


def patch_ini(text, updates):
    """SimpleIni represents alternatives as repeated keys, NOT '&' chords."""
    for section, values in updates.items():
        pattern = re.compile(r"(?ms)^\[" + re.escape(section) + r"\][^\n]*\n(.*?)(?=^\[|\Z)")
        match = pattern.search(text)
        block = match.group(1) if match else ""
        kept = [line for line in block.splitlines(keepends=True)
                if not ("=" in line and line.split("=", 1)[0].strip() in values)]
        body = "".join(kept).rstrip("\n") + "\n"
        body += "".join(f"{key} = {v}\n" for key, items in values.items() for v in items)
        replacement = f"[{section}]\n" + body + "\n"
        if match:
            text = text[:match.start()] + replacement + text[match.end():]
        else:
            text = text.rstrip("\n") + "\n\n" + replacement
    return text


def js(value):
    return json.dumps(value, indent=2, ensure_ascii=False) + "\n"


def plan(config, data):
    """Read/validate all inputs before returning any proposed writes."""
    changes = {}
    ps2path = config / "PCSX2/inis/PCSX2.ini"
    original = ps2path.read_text()
    old_pad = ini_values(original, "Pad1")
    pad = {"Type": ["DualShock2"], "Deadzone": ["0.10"], "AxisScale": ["1.0"]}
    for key, value in PS2.items():
        pad[key] = [x for x in old_pad.get(key, []) if not x.startswith("SDL-0/")]
        pad[key].append("SDL-0/" + value)
    merged = patch_ini(original, {"InputSources": {"SDL": ["true"]}, "Pad1": pad})
    changes[ps2path] = merged
    changes[config / "PCSX2/inputprofiles/VOYEE S08.ini"] = patch_ini("", {
        "InputSources": ini_values(merged, "InputSources"), "Pad1": ini_values(merged, "Pad1")})

    sympath = data / "games/symphony-recomp/settings.json"
    sym = json.loads(sympath.read_text())
    port = sym["system"]["input"]["ports"][0]
    port["kind"] = "analog"
    for mode in ("analog", "digital"):
        port.setdefault(mode, {}).update(PS1)
    # Digital pad mode also allows the left stick to act as the D-pad.
    for key, extra in {"up": 104, "down": 105, "left": 102, "right": 103}.items():
        port["digital"][key] = PS1[key] + [extra]
    changes[sympath] = js(sym)

    ryupath = config / "Ryujinx/Config.json"
    ryu = json.loads(ryupath.read_text())
    inputs = ryu["input_config"]
    for item in inputs:
        if item.get("player_index") == "Player1" and item.get("backend") == "WindowKeyboard":
            # Ryubing supports only one device per player. Keep keyboard usable
            # as a named profile, not a duplicate Player1 or phantom Player2.
            changes[config / "Ryujinx/profiles/keyboard/Before VOYEE.json"] = js(item)
    controller = nintendo_profile()
    for item in inputs:
        if (item.get("player_index") == "Player1" and item.get("backend") == "GamepadSDL2"
                and "057e-0000-0920" in item.get("id", "")):
            for key in ("motion", "rumble", "led"):
                if key in item:
                    controller[key] = item[key]
    ryu["input_config"] = [controller] + [
        x for x in inputs if x.get("player_index") != "Player1"]
    changes[ryupath] = js(ryu)
    changes[config / "Ryujinx/profiles/controller/VOYEE S08.json"] = js(controller)
    return {p: t for p, t in changes.items() if not p.exists() or p.read_text() != t}


def check_idle():
    for proc in Path("/proc").iterdir():
        if not proc.name.isdecimal():
            continue
        try:
            args = (proc / "cmdline").read_bytes().split(b"\0")
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
        if any(Path(os.fsdecode(a)).name in {"pcsx2-qt", ".pcsx2-qt-wrapped", "Ryujinx", "sotn.dll"}
               for a in args if a):
            raise RuntimeError("Close PCSX2, Ryubing and SymphonyRecomp before applying profiles")


def apply(changes, state):
    for path, text in changes.items():
        if path.is_symlink():
            raise RuntimeError(f"Refusing managed/symlink settings: {path}")
    for path, text in changes.items():
        if path.exists():
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            backup = state / (hashlib.sha256(str(path).encode()).hexdigest()[:16] + "-" + digest)
            backup.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            if not backup.exists():
                shutil.copyfile(path, backup)
                backup.chmod(0o600)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=".voyee-", dir=path.parent)
        try:
            with os.fdopen(fd, "w") as out:
                out.write(text)
            os.replace(name, path)
        finally:
            if os.path.exists(name):
                os.unlink(name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="back up and apply; default is preview only")
    args = parser.parse_args()
    home = Path.home()
    config = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config"))
    state = Path(os.environ.get("XDG_STATE_HOME", home / ".local/state")) / "voyee-controller/backups"
    data = home / "matrix/data/emulation"
    check_idle()
    changes = plan(config, data)
    for path in changes:
        print(("Update " if args.apply else "Would update ") + str(path))
    if args.apply:
        apply(changes, state)
    print(f"{len(changes)} changed files. Pegasus keeps its positional SDL defaults (bottom=select).")


if __name__ == "__main__":
    main()
