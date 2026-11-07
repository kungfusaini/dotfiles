#!/usr/bin/env python3
"""Test packaged capture/codecs without a GUI, device discovery or real media."""
import argparse
import os
from pathlib import Path
import re
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--gstreamer", type=Path, required=True)
    args = parser.parse_args()
    app = args.package / "bin/gnome-network-displays"
    result = subprocess.run([str(app), "--help"], capture_output=True, text=True,
                            check=True, timeout=10)
    assert "Usage:" in result.stdout
    desktop = args.package / "share/applications/org.gnome.NetworkDisplays.desktop"
    assert "Exec=gnome-network-displays" in desktop.read_text()

    # Nix's compiled wrapper embeds its makeCWrapper invocation. Test the
    # application's exact plugin search path, not an unrelated global plugin set.
    metadata = app.read_bytes().decode("utf-8", errors="ignore")
    match = re.search(r"--prefix 'GST_PLUGIN_SYSTEM_PATH_1_0' ':' '([^']+)'", metadata)
    assert match, "Cannot identify the packaged GStreamer plugin environment"
    with tempfile.TemporaryDirectory(prefix="gnd-smoke.") as directory:
        env = dict(os.environ, GST_PLUGIN_SYSTEM_PATH_1_0=match.group(1),
                   GST_PLUGIN_PATH="", GST_PLUGIN_PATH_1_0="",
                   GST_REGISTRY_1_0=directory + "/registry.bin")

        def run(tool, *arguments):
            return subprocess.run([str(args.gstreamer / "bin" / tool), *arguments],
                                  env=env, capture_output=True, text=True, timeout=30)

        def available(element):
            return run("gst-inspect-1.0", element).returncode == 0

        for element in ("pipewiresrc", "videoconvert", "h264parse", "aacparse", "mpegtsmux"):
            assert available(element), f"Missing packaged element: {element}"
        # Software fallbacks work independently of the host GPU or render node.
        assert available("x264enc"), "Missing software H.264 encoder"
        audio = next((name for name in ("fdkaacenc", "avenc_aac", "faac") if available(name)), None)
        assert audio, "Missing AAC audio encoder"
        pipelines = [
            ["videotestsrc", "num-buffers=10", "!", "video/x-raw,width=320,height=180,framerate=30/1",
             "!", "videoconvert", "!", "x264enc", "tune=zerolatency", "!", "h264parse", "!", "fakesink"],
            ["audiotestsrc", "num-buffers=10", "!", "audioconvert", "!",
             "audio/x-raw,format=S16LE,rate=48000,channels=2", "!", audio, "!", "aacparse", "!", "fakesink"],
        ]
        for pipeline in pipelines:
            result = run("gst-launch-1.0", "-q", *pipeline)
            assert result.returncode == 0, result.stderr
        print(f"PASS: launcher, desktop entry, PipeWire source, H.264 and {audio} synthetic encoding")
        print("Receiver discovery, permission selection and end-to-end casting are not tested.")


if __name__ == "__main__":
    main()
