"""Unprivileged deployment orchestration tests; no real rebuild or sudo."""
import os
from pathlib import Path
import subprocess
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "hosts/kirax1/scripts/system/deploy-kirax1"


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.git("init", "-b", "main")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "Test")
        (self.repo / "config").write_text("committed\n")
        self.git("add", ".")
        self.git("commit", "-m", "snapshot")
        self.rev = self.git("rev-parse", "HEAD").strip()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.log = self.root / "calls"
        self.tool("runuser", 'shift 3\nexec "$@"')
        self.tool("logger", ':')
        self.tool("nix", 'printf "build %s\\n" "$*" >> "$CALLS"\nexit "${BUILD_EXIT:-0}"')
        self.tool("nixos-rebuild", 'printf "switch %s\\n" "$*" >> "$CALLS"')
        source = SCRIPT.read_text()
        source = source.replace("repo=/home/sumeet/.config/nixos", f"repo={self.repo}")
        source = source.replace("if (( EUID != 0 )); then", "if false; then")
        source = source.replace("/run/lock/deploy-kirax1.lock", str(self.root / "lock"))
        source = source.replace("/run/current-system/sw/bin/nixos-rebuild", "nixos-rebuild")
        source = source.replace("/run/current-system/sw/bin/nix build", "nix build")
        self.script = self.root / "deploy"
        self.script.write_text("set -euo pipefail\n" + source)

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.repo), *args], text=True, stderr=subprocess.DEVNULL)

    def tool(self, name, body):
        path = self.bin / name
        path.write_text("#!/usr/bin/env bash\nset -eu\n" + body + "\n")
        path.chmod(0o755)

    def run_deploy(self, *args, **env):
        return subprocess.run(["bash", str(self.script), *args], env={**os.environ,
            "PATH": f"{self.bin}:{os.environ['PATH']}", "CALLS": str(self.log),
            "SUDO_USER": "sumeet", **env}, capture_output=True, text=True)

    def test_dirty_files_are_preserved_and_same_revision_built_and_switched(self):
        (self.repo / "config").write_text("staged\n")
        self.git("add", "config")
        (self.repo / "config").write_text("unstaged\n")
        (self.repo / "untracked").write_text("untracked\n")
        before = self.git("status", "--porcelain")
        index = self.git("show", ":config")
        result = self.run_deploy()
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.log.read_text().splitlines()
        self.assertEqual(len(calls), 2)
        source = f"git+file://{self.repo}?ref=refs/heads/main&rev={self.rev}"
        self.assertIn(source + "#nixosConfigurations.kirax1.config.system.build.toplevel", calls[0])
        self.assertIn(source + "#kirax1", calls[1])
        self.assertEqual(before, self.git("status", "--porcelain"))
        self.assertEqual(index, self.git("show", ":config"))
        self.assertEqual((self.repo / "config").read_text(), "unstaged\n")
        self.assertEqual((self.repo / "untracked").read_text(), "untracked\n")

    @unittest.skipUnless(shutil.which("nix"), "Nix unavailable")
    def test_real_nix_reads_commit_not_dirty_index_or_worktree(self):
        (self.repo / "flake.nix").write_text(
            '{ outputs = { self }: { marker = builtins.readFile ./config; }; }\n')
        self.git("add", "flake.nix")
        self.git("commit", "-m", "test flake")
        rev = self.git("rev-parse", "HEAD").strip()
        (self.repo / "config").write_text("staged\n")
        self.git("add", "config")
        (self.repo / "config").write_text("unstaged\n")
        (self.repo / "flake.nix").write_text("invalid dirty flake\n")
        source = f"git+file://{self.repo}?ref=refs/heads/main&rev={rev}#marker"
        result = subprocess.run(["nix", "eval", "--raw", source], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "committed\n")

    def test_build_failure_prevents_switch(self):
        result = self.run_deploy(BUILD_EXIT="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("build", self.log.read_text())
        self.assertNotIn("switch", self.log.read_text())

    def test_other_branch_rejected(self):
        self.git("checkout", "-b", "unfinished")
        self.assertNotEqual(self.run_deploy().returncode, 0)
        self.assertFalse(self.log.exists())

    def test_detached_head_rejected(self):
        self.git("checkout", "--detach")
        self.assertNotEqual(self.run_deploy().returncode, 0)
        self.assertFalse(self.log.exists())

    def test_arguments_rejected(self):
        self.assertEqual(self.run_deploy("--anything").returncode, 64)
        self.assertFalse(self.log.exists())

    def test_wrong_actor_rejected(self):
        self.assertEqual(self.run_deploy(SUDO_USER="other").returncode, 77)
        self.assertFalse(self.log.exists())


if __name__ == "__main__":
    unittest.main()
