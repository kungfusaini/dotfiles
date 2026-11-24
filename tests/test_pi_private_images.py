"""Private image policy and actual hidden-TUI tests. Use the packaged Pillow Python."""
import argparse
import base64
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

from PIL import Image, PngImagePlugin
from test_pi_private import load
from test_pi_private_native import Native, records
from test_pi_private_terminal import descendants, running

ROOT = Path(__file__).resolve().parents[1]
worker = load("private_image_worker", ROOT / "home/packages/pi-private/image.py")


class ImagePolicy(unittest.TestCase):
    def test_prompt_only_not_backend_configuration(self):
        self.assertEqual(worker.validate_prompt(" a red teapot "), "a red teapot")
        for prompt in [None, {}, "", " " * 3, "x" * 4001, "\x1b]52;c;no", "a\x00b",
                       '<sd_cpp_extra_args>{"width":8192}</sd_cpp_extra_args>',
                       "<SD_CPP_EXTRA_ARGS>anything"]:
            with self.subTest(prompt=repr(prompt)[:60]), self.assertRaises(ValueError):
                worker.validate_prompt(prompt)

    def test_fixed_local_backend_and_no_prompt_in_argv(self):
        argv = worker.server_command()
        self.assertEqual(argv[argv.index("--listen-ip") + 1], "127.0.0.1")
        self.assertEqual(argv[argv.index("--backend") + 1], "vulkan0")
        self.assertIn("--disable-image-metadata", argv)
        self.assertNotIn("--prompt", argv)
        self.assertNotIn("-p", argv)
        for preset, steps, sampler, scheduler in [("quality", "35", "dpm++2m", "karras"),
                                                   ("fast", "20", "euler", "discrete")]:
            argv = worker.server_command(preset)
            self.assertEqual(argv[argv.index("--steps") + 1], steps)
            self.assertEqual(argv[argv.index("--sampling-method") + 1], sampler)
            self.assertEqual(argv[argv.index("--scheduler") + 1], scheduler)
            if preset == "quality":
                self.assertIn("--vae-tiling", argv)
                self.assertEqual(argv[argv.index("--vae-tile-size") + 1], "64x64")
                self.assertEqual(argv[argv.index("--vae-tile-overlap") + 1], "0.5")
            else:
                self.assertNotIn("--vae-tiling", argv)
        self.assertEqual(worker.server_command(), worker.server_command("quality"))

    def test_only_bounded_named_presets(self):
        for preset in [None, {}, "unknown", "--width 8192", "quality; touch /images/no"]:
            with self.subTest(preset=preset), self.assertRaises(ValueError):
                worker.preset_config(preset)
        self.assertEqual(worker.preset_config("quality")["size"], 1024)
        self.assertEqual(worker.preset_config("fast")["size"], 512)

    def test_pixels_only_private_file_and_thumbnail(self):
        for preset in ["fast", "quality"]:
            with self.subTest(preset=preset):
                self.check_private_file(preset)

    def check_private_file(self, preset):
        size = worker.preset_config(preset)["size"]
        source = Image.new("RGB", (size, size), "red")
        buffer = io.BytesIO()
        info = PngImagePlugin.PngInfo()
        info.add_text("parameters", "SYNTHETIC_PROMPT_NOT_IMAGE_METADATA")
        source.save(buffer, format="PNG", pnginfo=info)
        response = json.dumps({"data": [{"b64_json": base64.b64encode(buffer.getvalue()).decode()}]}).encode()
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value.status = 200
        opener.open.return_value.__enter__.return_value.read.return_value = response
        server = MagicMock()
        server.poll.return_value = None
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model = root / "model"
            model.touch()
            images = root / "images"
            images.mkdir()
            with patch.object(worker, "MODEL", model), patch.object(worker, "OUTPUT", images), \
                 patch.object(worker.subprocess, "Popen", return_value=server), \
                 patch.object(worker.urllib.request, "build_opener", return_value=opener), \
                 patch.object(worker.signal, "signal"):
                result = worker.generate("a red teapot", preset)
            self.assertEqual((result["width"], result["height"]), (size, size))
            self.assertEqual(result["preset"], preset)
            request = opener.open.call_args_list[-1].args[0]
            payload = json.loads(request.data)
            self.assertEqual(payload["size"], f"{size}x{size}")
            self.assertEqual(opener.open.call_args.kwargs["timeout"], worker.preset_config(preset)["timeout"])
            self.assertEqual(len(base64.b64decode(result["preview"])), 64 * 64 * 3)
            path = images / result["filename"]
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with Image.open(path) as saved:
                self.assertEqual(saved.info, {})
                self.assertEqual(saved.getpixel((0, 0)), (255, 0, 0))
            self.assertEqual(list(images.iterdir()), [path])
            server.terminate.assert_called_once()
            server.wait.assert_called_once()

    def test_missing_model_never_launches_or_downloads(self):
        with patch.object(worker, "MODEL", Path("/nonexistent-private-image-weights")), \
             patch.object(worker.subprocess, "Popen") as start:
            with self.assertRaisesRegex(RuntimeError, "no download or cloud fallback"):
                worker.generate("a red teapot")
            start.assert_not_called()


def image_servers(native):
    result = []
    for pid in descendants(native.pid):
        try:
            argv = Path(f"/proc/{pid}/cmdline").read_bytes()
        except FileNotFoundError:
            continue
        assert b"PRIVATE_IMAGE_ARGV_SENTINEL" not in argv, "Image prompt leaked to process arguments"
        if b"/bin/sd-server" in argv:
            result.append(pid)
    return result


def real_tui(package, preset="quality", artifact_dir=None):
    built = load("image_native_launcher", package / "bin/pi-private")
    with tempfile.TemporaryDirectory(prefix="pi-private-images-") as tmp:
        root = Path(tmp)
        history, images = root / "sessions", root / "images"
        history.mkdir(mode=0o700)
        images.mkdir(mode=0o700)
        command = built.sandbox_command(history, Path.home() / built.MODEL_RELATIVE,
            images=images, image_model=Path.home() / built.IMAGE_MODEL_RELATIVE)
        native = Native(command)
        try:
            native.send("/name Private image fixture\r")
            native.wait("Session name set")
            native.send("/image\r")
            native.wait("Usage: /image")
            assert not list(images.iterdir())
            prompt = "Candid photograph of an adult woman in her thirties wearing a blue linen shirt, soft natural window light, realistic skin texture, subtle imperfections, neutral colors. PRIVATE_IMAGE_ARGV_SENTINEL"
            prefix = "/image --fast " if preset == "fast" else "/image "
            native.send(prefix + prompt + "\r")
            native.wait("Generating private local image")
            native.poll_until(lambda: bool(image_servers(native)), timeout=30)
            servers = image_servers(native)
            def completed():
                if b"Image cancelled or unavailable" in native.output:
                    raise AssertionError("Synthetic image request failed before saving a PNG")
                return any(r.get("type") == "custom_message" and r.get("customType") == "private-image"
                           for r in records(history))
            native.poll_until(completed, timeout=720)
            native.poll_until(lambda: b"Saved:" in native.output, timeout=20)
            saved = next(r for r in records(history) if r.get("type") == "custom_message" and r.get("customType") == "private-image")
            data = saved["details"]
            file = images / data["filename"]
            assert file.stat().st_mode & 0o077 == 0
            with Image.open(file) as png:
                size = worker.preset_config(preset)["size"]
                assert png.size == (size, size) and png.info == {}
            assert data["preset"] == preset
            print(f"BENCHMARK: {preset} {size}x{size} completed in {data['seconds']} seconds", flush=True)
            if artifact_dir:
                artifact_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
                artifact = artifact_dir / f"{preset}-{time.time_ns()}.png"
                with artifact.open("xb") as target:
                    os.chmod(artifact, 0o600)
                    target.write(file.read_bytes())
                print(f"Synthetic image retained: {artifact}", flush=True)
            assert len(list(images.iterdir())) == 1
            assert all(not running(pid) for pid in servers), "Idle image server retained after request"
            assert b"\x1b[38;2;" in native.output, "Missing local pixel preview"
            assert not any(r.get("type") == "message" and r["message"].get("role") == "assistant"
                           for r in records(history)), "Image command unexpectedly called the chat model"
            native.send('/image <sd_cpp_extra_args>{"width":8192}</sd_cpp_extra_args>\r')
            native.wait("Image cancelled or unavailable")
            assert len(list(images.iterdir())) == 1
            native.send("/image --quality A blue ceramic cup. PRIVATE_IMAGE_ARGV_SENTINEL\r")
            native.wait("Generating private local image")
            native.poll_until(lambda: bool(image_servers(native)), timeout=30)
            servers = image_servers(native)
            native.send("\x1b")
            native.wait("Image cancelled or unavailable")
            assert all(not running(pid) for pid in servers), "Cancelled image server survived"
            assert len(list(images.iterdir())) == 1
            native.quit()
        finally:
            native.cleanup()
        reopened = Native(command)
        try:
            reopened.send("/resume\r")
            reopened.wait("Resume Session")
            reopened.send("Private image fixture")
            time.sleep(0.2)
            reopened.send("\r")
            reopened.wait("Resumed session")
            reopened.poll_until(lambda: b"Saved:" in reopened.output, timeout=20)
            assert b"\x1b[38;2;" in reopened.output, "Saved thumbnail did not reopen"
            reopened.send("/image A green teapot. PRIVATE_IMAGE_ARGV_SENTINEL\r")
            reopened.wait("Generating private local image")
            reopened.poll_until(lambda: bool(image_servers(reopened)), timeout=30)
            children = descendants(reopened.pid)
            reopened.cleanup()
            deadline = time.monotonic() + 15
            while any(running(pid) for pid in children) and time.monotonic() < deadline:
                time.sleep(0.1)
            assert all(not running(pid) for pid in children), "Image processes survived sandbox termination"
            assert len(list(images.iterdir())) == 1
        finally:
            reopened.cleanup()
        print("PASS: actual /image, private PNG/preview, no chat turn, backend-tag rejection, Escape reaps server, history reopening and sandbox-death cleanup")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--unit-only", action="store_true")
    parser.add_argument("--preset", choices=["quality", "fast"], default="quality")
    parser.add_argument("--artifact-dir", type=Path)
    args = parser.parse_args()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ImagePolicy)
    if not unittest.TextTestRunner().run(suite).wasSuccessful():
        raise SystemExit(1)
    if not args.unit_only:
        real_tui(args.package, args.preset, args.artifact_dir)
