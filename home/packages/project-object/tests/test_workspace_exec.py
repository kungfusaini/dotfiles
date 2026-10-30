import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_EXEC = ROOT / "bin" / "project-workspace-exec"


class WorkspaceExecTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.calls = self.root / "calls.jsonl"
        self.clients = self.root / "clients.json"
        self.hyprctl = self.root / "hyprctl"
        self.hyprctl.write_text("""#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
arguments = sys.argv[1:]
with Path(os.environ['CALLS']).open('a') as stream:
    stream.write(json.dumps(arguments) + '\\n')
if arguments == ['clients', '-j']:
    print(Path(os.environ['CLIENTS']).read_text())
    raise SystemExit(0)
if arguments[:2] == ['dispatch', 'exec']:
    raise SystemExit(int(os.environ.get('DISPATCH_STATUS', '0')))
raise SystemExit(2)
""")
        self.hyprctl.chmod(0o755)

    def tearDown(self):
        self.temporary.cleanup()

    def environment(self):
        return {
            **os.environ,
            "PROJECT_PICKER_HYPRCTL": str(self.hyprctl),
            "CALLS": str(self.calls),
            "CLIENTS": str(self.clients),
        }

    def run_helper(self, *arguments, clients=None, extra_environment=None):
        self.clients.write_text(json.dumps([] if clients is None else clients))
        environment = self.environment()
        environment.pop("PROJECT_OBJECT_WORKSPACE_NAME", None)
        environment.update(extra_environment or {})
        return subprocess.run(
            [str(WORKSPACE_EXEC), *arguments],
            env=environment,
            text=True,
            capture_output=True,
        )

    def calls_value(self):
        return [json.loads(line) for line in self.calls.read_text().splitlines()]

    def test_launches_on_invoking_terminal_workspace_without_focusing_it(self):
        clients = [{
            "pid": os.getpid(),
            "workspace": {"id": -42, "name": "Command Center · Agents"},
        }]
        command = ["sample-app", "argument with spaces", "quote'argument"]
        result = self.run_helper(*command, clients=clients)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls_value(), [
            ["clients", "-j"],
            [
                "dispatch",
                "exec",
                f"[workspace name:Command Center · Agents silent] {shlex.join(command)}",
            ],
        ])

    def test_uses_recorded_project_workspace_when_client_ancestry_is_unavailable(self):
        result = self.run_helper(
            "sample-app",
            extra_environment={"PROJECT_OBJECT_WORKSPACE_NAME": "Command Center · Agents"},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("[workspace name:Command Center · Agents silent]", self.calls_value()[1][2])

    def test_refuses_to_guess_from_the_active_workspace(self):
        result = self.run_helper("sample-app")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("could not identify", result.stderr)
        self.assertEqual(self.calls_value(), [["clients", "-j"]])

    def test_rejects_workspace_rule_delimiters(self):
        result = self.run_helper(
            "sample-app",
            extra_environment={"PROJECT_OBJECT_WORKSPACE_NAME": "unsafe;float"},
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("cannot be represented safely", result.stderr)
        self.assertEqual(self.calls_value(), [["clients", "-j"]])

    def test_surfaces_dispatch_failure(self):
        clients = [{"pid": os.getpid(), "workspace": {"name": "Command Center · Agents"}}]
        result = self.run_helper(
            "sample-app",
            clients=clients,
            extra_environment={"DISPATCH_STATUS": "1"},
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Hyprland refused", result.stderr)


if __name__ == "__main__":
    unittest.main()
