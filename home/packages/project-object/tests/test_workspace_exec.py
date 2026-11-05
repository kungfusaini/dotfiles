import contextlib
import importlib.machinery
import importlib.util
import io
import os
from pathlib import Path
import shlex
import subprocess
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
LOADER = importlib.machinery.SourceFileLoader("workspace_exec", str(ROOT / "bin" / "project-workspace-exec"))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
workspace_exec = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(workspace_exec)


def client(workspace="Command Center · Agents", pid=123, address="0xabc", **extra):
    return {"pid": pid, "address": address, "mapped": True, "workspace": {"name": workspace}, **extra}


class WorkspaceExecTests(unittest.TestCase):
    def setUp(self):
        self.environment = mock.patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_uses_ancestry_before_recorded_workspace(self):
        with mock.patch.object(workspace_exec, "ancestor_pids", return_value=[3, 2]), \
                mock.patch.dict(os.environ, {workspace_exec.WORKSPACE_ENV: "old"}):
            self.assertEqual(workspace_exec.invoking_workspace([client(pid=2)]), "Command Center · Agents")

    def test_ambiguous_terminal_server_uses_recorded_workspace_not_first_client(self):
        with mock.patch.object(workspace_exec, "ancestor_pids", return_value=[3, 2]), \
                mock.patch.dict(os.environ, {workspace_exec.WORKSPACE_ENV: "Recorded"}):
            self.assertEqual(workspace_exec.invoking_workspace([client("One", pid=2), client("Two", pid=2)]), "Recorded")

    def test_ambiguous_terminal_server_without_recorded_workspace_fails_closed(self):
        with mock.patch.object(workspace_exec, "ancestor_pids", return_value=[3, 2]):
            self.assertIsNone(workspace_exec.invoking_workspace([client("One", pid=2), client("Two", pid=2)]))

    def test_refuses_to_guess_from_active_workspace(self):
        with mock.patch.object(workspace_exec, "ancestor_pids", return_value=[3]):
            self.assertIsNone(workspace_exec.invoking_workspace([client("Focused", pid=999)]))

    def test_launches_with_marker_and_verifies_before_success(self):
        command = ["sample-app", "argument with spaces", "quote'argument"]
        with mock.patch.object(workspace_exec, "hypr_clients", return_value=[client(pid=os.getpid())]), \
                mock.patch.object(workspace_exec.secrets, "token_hex", return_value="unique"), \
                mock.patch.object(workspace_exec.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "ok\n", "")) as run, \
                mock.patch.object(workspace_exec, "verify_window") as verify, \
                mock.patch.object(workspace_exec.sys, "argv", ["helper", *command]), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            workspace_exec.main()
        payload = run.call_args.args[0][-1]
        self.assertEqual(payload, "[workspace name:Command Center · Agents silent] " + shlex.join([
            "env", "PROJECT_OBJECT_LAUNCH_WORKSPACE_NAME=Command Center · Agents", "PROJECT_OBJECT_LAUNCH_ID=unique", *command,
        ]))
        verify.assert_called_once_with("Command Center · Agents", "unique", {"0xabc"})
        self.assertIn("verified new window", output.getvalue())

    def test_browser_delegates_synchronously_without_competing_exec_rule(self):
        with mock.patch.object(workspace_exec, "hypr_clients", return_value=[client(pid=os.getpid())]), \
                mock.patch.object(workspace_exec.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as run, \
                mock.patch.object(workspace_exec, "verify_window") as verify, \
                mock.patch.object(workspace_exec.sys, "argv", ["helper", "/package/bin/project-browser", "open", "--mode", "project", "https://example.com"]), \
                contextlib.redirect_stdout(io.StringIO()):
            workspace_exec.main()
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0][0], "/package/bin/project-browser")
        self.assertEqual(run.call_args.kwargs["env"][workspace_exec.LAUNCH_WORKSPACE_ENV], "Command Center · Agents")
        verify.assert_not_called()

    def test_browser_failure_is_propagated(self):
        with mock.patch.object(workspace_exec, "hypr_clients", return_value=[client(pid=os.getpid())]), \
                mock.patch.object(workspace_exec.subprocess, "run", return_value=subprocess.CompletedProcess([], 5)), \
                mock.patch.object(workspace_exec.sys, "argv", ["helper", "project-browser", "open", "https://example.com"]), \
                self.assertRaises(SystemExit) as error:
            workspace_exec.main()
        self.assertEqual(error.exception.code, 5)

    def test_app_handoff_matches_class_without_process_environment(self):
        identity = "a" * 32
        window = client(**{"class": "vivaldi-127.0.0.1__poagent" + identity + "b" * 16 + "-Default"})
        with mock.patch.object(workspace_exec, "hypr_clients", return_value=[window]), \
                mock.patch.object(workspace_exec, "process_has_launch_id", return_value=False):
            workspace_exec.verify_window("Command Center · Agents", identity, set())

    def test_selected_address_survives_parent_exit_after_move(self):
        with mock.patch.object(workspace_exec, "hypr_clients", side_effect=[[client("Wrong")], [client()]]), \
                mock.patch.object(workspace_exec, "process_has_launch_id", side_effect=[True, False]) as marker, \
                mock.patch.object(workspace_exec.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "ok")), \
                mock.patch.object(workspace_exec.time, "sleep"):
            workspace_exec.verify_window("Command Center · Agents", "marker", set())
        self.assertEqual(marker.call_count, 1)

    def test_help_does_not_contact_compositor(self):
        with mock.patch.object(workspace_exec.sys, "argv", ["helper", "--help"]), \
                mock.patch.object(workspace_exec, "hypr_clients") as clients, \
                contextlib.redirect_stdout(io.StringIO()):
            workspace_exec.main()
        clients.assert_not_called()

    def test_rejects_rule_and_dispatch_delimiters(self):
        for character in ";[],\r\n\0":
            with self.subTest(character=character), self.assertRaises(RuntimeError):
                workspace_exec.validate_workspace_rule("unsafe" + character + "name")

    def test_surfaces_dispatch_failure_even_when_hyprctl_exits_zero(self):
        for status, text in [(1, ""), (0, "Invalid dispatcher")]:
            with self.subTest(status=status), \
                    mock.patch.object(workspace_exec, "hypr_clients", return_value=[client(pid=os.getpid())]), \
                    mock.patch.object(workspace_exec.subprocess, "run", return_value=subprocess.CompletedProcess([], status, text, "")), \
                    mock.patch.object(workspace_exec, "verify_window") as verify, \
                    mock.patch.object(workspace_exec.sys, "argv", ["helper", "app"]), \
                    self.assertRaisesRegex(SystemExit, "refused"):
                workspace_exec.main()
            verify.assert_not_called()

    def test_verifies_correct_window_without_moving(self):
        with mock.patch.object(workspace_exec, "hypr_clients", return_value=[client()]), \
                mock.patch.object(workspace_exec, "process_has_launch_id", return_value=True), \
                mock.patch.object(workspace_exec.subprocess, "run") as run:
            workspace_exec.verify_window("Command Center · Agents", "marker", set())
        run.assert_not_called()

    def test_corrects_only_marked_new_window_and_checks_actual_result(self):
        unrelated = client("Focused", pid=999, address="0xdef")
        old = client("Focused", pid=123, address="0x123")
        with mock.patch.object(workspace_exec, "hypr_clients", side_effect=[
            [unrelated, old, client("Focused")], [client()],
        ]), mock.patch.object(workspace_exec, "process_has_launch_id", side_effect=lambda pid, _: pid == 123), \
                mock.patch.object(workspace_exec.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "ok\n", "")) as run, \
                mock.patch.object(workspace_exec.time, "sleep"):
            workspace_exec.verify_window("Command Center · Agents", "marker", {"0x123"})
        run.assert_called_once()
        self.assertEqual(run.call_args.args[0], [workspace_exec.HYPRCTL, "dispatch", "movetoworkspacesilent", "name:Command Center · Agents,address:0xabc"])

    def test_silent_move_failure_is_not_reported_as_success(self):
        with mock.patch.object(workspace_exec, "hypr_clients", return_value=[client("Wrong")]), \
                mock.patch.object(workspace_exec, "process_has_launch_id", return_value=True), \
                mock.patch.object(workspace_exec.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "Invalid window", "")), \
                self.assertRaisesRegex(RuntimeError, "silently place"):
            workspace_exec.verify_window("Target", "marker", set())

    def test_no_window_unmarked_old_unmapped_and_invalid_addresses_time_out(self):
        cases = [[], [client()], [client(address="unsafe,address:0x1")], [client(mapped=False)], [client(address="0x123")]]
        for clients in cases:
            with self.subTest(clients=clients), \
                    mock.patch.object(workspace_exec, "hypr_clients", return_value=clients), \
                    mock.patch.object(workspace_exec, "process_has_launch_id", return_value=False), \
                    mock.patch.object(workspace_exec.time, "monotonic", side_effect=[0, 0, 16]), \
                    mock.patch.object(workspace_exec.time, "sleep"), \
                    mock.patch.object(workspace_exec.subprocess, "run") as run, \
                    self.assertRaisesRegex(RuntimeError, "application may still be running"):
                workspace_exec.verify_window("Target", "marker", {"0x123"})
            run.assert_not_called()

    def test_successful_move_without_actual_placement_times_out(self):
        with mock.patch.object(workspace_exec, "hypr_clients", return_value=[client("Wrong")]), \
                mock.patch.object(workspace_exec, "process_has_launch_id", return_value=True), \
                mock.patch.object(workspace_exec.time, "monotonic", side_effect=[0, 0, 16]), \
                mock.patch.object(workspace_exec.time, "sleep"), \
                mock.patch.object(workspace_exec.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "ok\n", "")), \
                self.assertRaisesRegex(RuntimeError, "no new window"):
            workspace_exec.verify_window("Target", "marker", set())

    def test_environment_marker_is_exact_and_missing_process_is_not_a_match(self):
        with mock.patch.object(Path, "read_bytes", return_value=b"OTHER=1\0PROJECT_OBJECT_LAUNCH_ID=exact\0"):
            self.assertTrue(workspace_exec.process_has_launch_id(123, "exact"))
            self.assertFalse(workspace_exec.process_has_launch_id(123, "exac"))
        for pid in [None, "123", True, -1, 0]:
            self.assertFalse(workspace_exec.process_has_launch_id(pid, "exact"))
        with mock.patch.object(Path, "read_bytes", side_effect=PermissionError):
            self.assertFalse(workspace_exec.process_has_launch_id(123, "exact"))

    def test_second_window_cannot_hide_ineffective_move_or_replace_first_window(self):
        for second_poll in [[client("Wrong"), client(address="0xdef")], [client(address="0xdef")]]:
            with self.subTest(second_poll=second_poll), \
                    mock.patch.object(workspace_exec, "hypr_clients", side_effect=[
                        [client("Wrong"), client(address="0xdef")], second_poll,
                    ]), mock.patch.object(workspace_exec, "process_has_launch_id", return_value=True), \
                    mock.patch.object(workspace_exec.time, "monotonic", side_effect=[0, 0, 1, 16]), \
                    mock.patch.object(workspace_exec.time, "sleep"), \
                    mock.patch.object(workspace_exec.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "ok\n", "")) as run, \
                    self.assertRaisesRegex(RuntimeError, "no new window"):
                workspace_exec.verify_window("Command Center · Agents", "marker", set())
            for call in run.call_args_list:
                self.assertIn("address:0xabc", call.args[0][-1])

    def test_sandboxed_window_matches_marked_waiting_parent(self):
        def environ(path):
            if str(path) == "/proc/123/environ":
                raise PermissionError
            return b"PROJECT_OBJECT_LAUNCH_ID=exact\0"
        with mock.patch.object(Path, "read_bytes", autospec=True, side_effect=environ), \
                mock.patch.object(workspace_exec, "parent_pid", return_value=456):
            self.assertTrue(workspace_exec.process_has_launch_id(123, "exact"))

    def test_cyclic_or_gone_ancestry_does_not_hang(self):
        for parent in [123, None]:
            with mock.patch.object(Path, "read_bytes", side_effect=PermissionError), \
                    mock.patch.object(workspace_exec, "parent_pid", return_value=parent):
                self.assertFalse(workspace_exec.process_has_launch_id(123, "exact"))

    def test_hypr_clients_failure_and_invalid_json(self):
        for status, stdout, stderr in [(1, "", "unavailable"), (0, "not-json", ""), (0, "{}", "")]:
            with self.subTest(stdout=stdout), \
                    mock.patch.object(workspace_exec.subprocess, "run", return_value=subprocess.CompletedProcess([], status, stdout, stderr)), \
                    self.assertRaises(RuntimeError):
                workspace_exec.hypr_clients()


if __name__ == "__main__":
    unittest.main()
