"""Policy and real network-boundary checks for the packaged native private Pi."""
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


chat = load("private_chat", ROOT / "home/packages/pi-private/chat.py")
launcher = load("private_launcher", ROOT / "home/packages/pi-private/launcher.py")
PACKAGE = None
if __name__ == "__main__" and "--package" in sys.argv:
    index = sys.argv.index("--package")
    PACKAGE = Path(sys.argv[index + 1])
    del sys.argv[index:index + 2]


class Policy(unittest.TestCase):
    def test_abliterated_weights_and_display_name(self):
        self.assertEqual(launcher.MODEL_RELATIVE,
                         "matrix/models/LLM/Qwen3.5-4B-abliterated.Q4_K_M.gguf")
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"PI_CODING_AGENT_DIR": tmp}):
            chat.configure()
            models = json.loads((Path(tmp) / "models.json").read_text())
            model = models["providers"]["private-local"]["models"][0]
            self.assertEqual(model["id"], "private-qwen")  # Keep existing private history compatible.
            self.assertEqual(model["name"], "Private Qwen3.5-4B Abliterated")

    def test_native_tui_with_no_tools_or_discovery(self):
        argv = chat.pi_command("/pi")
        for option in ["--offline", "--no-builtin-tools", "--no-extensions", "--no-skills", "--no-context-files", "--no-approve"]:
            self.assertIn(option, argv)
        self.assertNotIn("rpc", argv)
        self.assertNotIn("--no-tools", argv)
        self.assertEqual(argv[argv.index("--tools") + 1], "generate_image")
        self.assertEqual(argv[argv.index("--tui-mode") + 1], "fullscreen")
        self.assertEqual(argv[argv.index("--session-dir") + 1], "/history")
        self.assertEqual(argv.count("--extension"), 1)
        self.assertEqual(argv[argv.index("--extension") + 1], "@imageExtension@")

    def test_native_exit_and_selection_defaults(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {"PI_CODING_AGENT_DIR": tmp}):
            chat.configure()
            settings = json.loads((Path(tmp) / "settings.json").read_text())
            self.assertFalse(settings["fullscreenCopyOnSelect"])
            self.assertEqual(settings["fullscreenExitOutput"], "resume-hint")

    def test_sandbox_has_no_host_mount_or_env_inheritance(self):
        argv = launcher.sandbox_command(Path("/private-history"), Path("/weights"))
        for option in ["--unshare-all", "--unshare-user", "--disable-userns", "--clearenv", "--new-session"]:
            self.assertIn(option, argv)
        self.assertNotIn("--share-net", argv)
        self.assertNotIn("/run/user", argv)
        self.assertNotIn(str(Path.home()), argv)
        self.assertIn("TERM", argv)

    def test_render_only_gpu_and_minimal_read_only_metadata(self):
        argv = launcher.sandbox_command(Path("/private-history"), Path("/weights"))
        triples = [argv[i:i + 3] for i in range(len(argv) - 2)]
        self.assertEqual([t for t in triples if t[0] == "--dev-bind"],
                         [["--dev-bind", "/dev/dri/renderD128", "/dev/dri/renderD128"]])
        gpu = "/sys/devices/pci0000:00/0000:00:02.0"
        sysfs = [t for t in triples if t[0] == "--ro-bind" and t[1].startswith("/sys")]
        self.assertEqual(sysfs, [["--ro-bind", gpu + "/" + a, gpu + "/" + a] for a in
                               ["uevent", "vendor", "device", "subsystem_vendor", "subsystem_device", "revision"]])
        self.assertIn(["--setenv", "VK_DRIVER_FILES", "@intelVulkanIcd@"], triples)
        self.assertNotIn("/dev/dri/card0", argv)
        self.assertNotIn("/sys", argv)
        self.assertNotIn("/run/opengl-driver", argv)

    def test_gpu_server_has_explicit_device_and_no_cloud_fallback(self):
        argv = chat.model_command("/llama-server")
        self.assertEqual(argv[argv.index("--device") + 1], "Vulkan0")
        self.assertEqual(argv[argv.index("--n-gpu-layers") + 1], "999")
        self.assertEqual(argv[argv.index("--ctx-size") + 1], "8192")
        self.assertIn("--log-disable", argv)

    def test_optional_image_mounts_are_narrow_and_weights_read_only(self):
        argv = launcher.sandbox_command(Path("/private-history"), Path("/weights"),
            images=Path("/private-images"), image_model=Path("/image-weights"))
        triples = [argv[i:i + 3] for i in range(len(argv) - 2)]
        self.assertIn(["--bind", "/private-images", "/images"], triples)
        self.assertIn(["--ro-bind", "/image-weights", "/image-model.safetensors"], triples)
        self.assertEqual([t for t in triples if t[0] == "--bind"],
                         [["--bind", "/private-history", "/history"], ["--bind", "/private-images", "/images"]])
        self.assertNotIn(str(Path.home()), argv)

    def test_symlink_storage_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "target").mkdir()
            (root / "link").symlink_to(root / "target")
            with self.assertRaises(RuntimeError):
                launcher.private_directory(root / "link")


@unittest.skipUnless(PACKAGE, "pass --package to test the built sandbox")
class Packaged(unittest.TestCase):
    def test_real_isolation(self):
        built = load("built_private_launcher", PACKAGE / "bin/pi-private")
        with tempfile.TemporaryDirectory(prefix="pi-private-test-") as tmp:
            history = Path(tmp) / "sessions"
            history.mkdir(mode=0o700)
            result = subprocess.run(built.sandbox_command(history, None, True),
                                    capture_output=True, text=True, timeout=30,
                                    env={**os.environ, "OPENAI_API_KEY": "synthetic-must-not-inherit"})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("PASS:", result.stdout)
            self.assertNotIn("Network namespace: " + os.readlink("/proc/self/ns/net"), result.stdout)

    def test_real_vulkan_device_in_sandbox(self):
        built = load("built_gpu_launcher", PACKAGE / "bin/pi-private")
        with tempfile.TemporaryDirectory(prefix="pi-private-gpu-test-") as tmp:
            argv = built.sandbox_command(Path(tmp), None)
            server = argv[-1]
            argv[-6:] = [server, "--list-devices"]
            result = subprocess.run(argv, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Vulkan0: Intel(R) Arc", result.stdout)


if __name__ == "__main__":
    unittest.main()
