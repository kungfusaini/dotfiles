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
        for option in ["--offline", "--no-tools", "--no-extensions", "--no-skills", "--no-context-files", "--no-approve"]:
            self.assertIn(option, argv)
        self.assertNotIn("rpc", argv)
        self.assertEqual(argv[argv.index("--tui-mode") + 1], "fullscreen")
        self.assertEqual(argv[argv.index("--session-dir") + 1], "/history")

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


if __name__ == "__main__":
    unittest.main()
