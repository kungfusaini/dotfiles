#!/usr/bin/env python3
"""Compile the patched production callbacks against deterministic GLib fakes.

No GTK display, bus, receiver, permission UI, PipeWire or real media is accessed.
The entire application is also compiled by its ordinary Nix/Meson build.
"""
import argparse
from pathlib import Path
import os
import re
import shlex
import subprocess
import tempfile


FUNCTIONS = [
    "nd_window_close_session", "nd_window_clear_pending_sink",
    "nd_window_close_requested_cb", "nd_screencast_started_cb",
    "session_closed_cb", "nd_screencast_init_cb",
    "find_sink_list_row_activated_cb", "nd_window_start_selected_sink",
    "nd_pulseaudio_init_async_cb", "gnome_nd_window_finalize",
]


def function(source, name):
    match = re.search(r"^static (?:void|gboolean)\n" + re.escape(name) + r" \([^;]*?\)\n\{", source, re.M)
    assert match, f"Production function not found: {name}"
    # These selected functions contain no braces inside string/comment literals.
    depth = 1
    index = match.end()
    while depth:
        depth += (source[index] == "{") - (source[index] == "}")
        index += 1
    return source[match.start():index]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--probe", type=Path, required=True)
    args = parser.parse_args()
    source = args.source.read_text()
    startup = function(source, "gnome_nd_window_init")
    assert "xdp_portal_create_screencast_session" not in startup, "Startup must not request screen access"
    assert "xdp_session_start" not in startup, "Startup must not show the picker"
    assert "use_x11 = TRUE" not in source, "Portal failure/cancel must never silently capture X11"
    assert source.count("self->cancellable = g_cancellable_new ()") == 1
    assert '"close-request"' in startup
    production = "\n\n".join(function(source, name) for name in FUNCTIONS)
    probe = args.probe.read_text().replace("/* PRODUCTION_CALLBACKS */", production)
    with tempfile.TemporaryDirectory(prefix="receiver-first.") as directory:
        root = Path(directory)
        (root / "probe.c").write_text(probe)
        flags = shlex.split(subprocess.check_output(["pkg-config", "--cflags", "--libs", "gio-2.0"], text=True))
        compiler = shlex.split(os.environ.get("CC", "cc"))
        subprocess.run([*compiler, "-std=gnu11", "-Werror=implicit-function-declaration",
                        str(root / "probe.c"), "-o", str(root / "probe"), *flags], check=True)
        subprocess.run([str(root / "probe")], check=True, timeout=30)
    print("PASS: startup requests no screen access; compiled production callback tests passed")


if __name__ == "__main__":
    main()
