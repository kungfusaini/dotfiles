import importlib.util
import json
from pathlib import Path
import tempfile
import subprocess
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("policy", Path(__file__).resolve().parents[1] / "policy.py")
p = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(p)


def graph(current="a2dp-sink", capture=False, serial=10):
    names = ["off", "a2dp-sink", "a2dp-sink-aac", "headset-head-unit-msbc", "headset-head-unit"]
    profiles = [{"index": i, "name": name, "available": "yes"} for i, name in enumerate(names)]
    result = [{"id": 99, "info": {"props": {"device.name": p.SONY_CARD, "object.serial": serial}, "params": {
        "Profile": [next(x for x in profiles if x["name"] == current)], "EnumProfile": profiles,
    }}}]
    if capture:
        result.append({"id": 11, "info": {"state": "running", "props": {"media.class": "Stream/Input/Audio"}}})
    return result


class DecisionTests(unittest.TestCase):
    def test_gaming_selects_aac(self):
        self.assertEqual(p.decide(p.snapshot(graph()), True)["target"], 2)

    def test_normal_restores_ldac(self):
        self.assertEqual(p.decide(p.snapshot(graph("a2dp-sink-aac")), False)["target"], 1)

    def test_no_repeated_request_if_already_selected(self):
        for mode, name in [(True, "a2dp-sink-aac"), (False, "a2dp-sink")]:
            self.assertNotIn("target", p.decide(p.snapshot(graph(name)), mode))

    def test_active_capture_wins_including_priming_restore(self):
        for current in ["a2dp-sink", "headset-head-unit"]:
            for gaming in [True, False]:
                for restore in [True, False]:
                    result = p.decide(p.snapshot(graph(current, True)), gaming, restore)
                    self.assertNotIn("target", result)
                    self.assertEqual(result.get("pending_restore", False),
                                     restore and not (current == "a2dp-sink" and not gaming))

    def test_call_profile_owned_by_wireplumber(self):
        for current in ["headset-head-unit", "headset-head-unit-msbc"]:
            self.assertNotIn("target", p.decide(p.snapshot(graph(current)), True))

    def test_explicit_priming_completion_restores_playback(self):
        for gaming, target in [(True, 2), (False, 1)]:
            self.assertEqual(p.decide(p.snapshot(graph("headset-head-unit")), gaming, True)["target"], target)

    def test_deferred_restore_after_recording_ends(self):
        result = p.decide(p.snapshot(graph("headset-head-unit", True)), True, True)
        self.assertTrue(result["pending_restore"])
        self.assertEqual(p.decide(p.snapshot(graph("headset-head-unit")), True,
                                  pending_restore=True)["target"], 2)

    def test_off_stays_off(self):
        self.assertNotIn("target", p.decide(p.snapshot(graph("off")), True, True))

    def test_missing_or_unavailable_aac_never_falls_back(self):
        for missing in [True, False]:
            data = graph()
            profiles = data[0]["info"]["params"]["EnumProfile"]
            if missing:
                profiles.remove(profiles[2])
            else:
                profiles[2]["available"] = "no"
            self.assertNotIn("target", p.decide(p.snapshot(data), True))

    def test_no_card_or_ambiguous_card_is_safe(self):
        self.assertIsNone(p.snapshot([]))
        self.assertIsNone(p.snapshot(graph() * 2))
        self.assertNotIn("target", p.decide(None, True))

    def test_pipewire_restart_changes_connection_scope(self):
        one, two = graph(), graph()
        one.append({"type": "PipeWire:Interface:Core", "info": {"cookie": 1}})
        two.append({"type": "PipeWire:Interface:Core", "info": {"cookie": 2}})
        self.assertNotEqual(p.snapshot(one)["serial"], p.snapshot(two)["serial"])

    def test_capture_without_state_is_conservatively_active(self):
        data = graph(capture=True)
        del data[1]["info"]["state"]
        self.assertTrue(p.snapshot(data)["capturing"])

    def test_idle_capture_and_audio_playback_do_not_block(self):
        data = graph(capture=True)
        data[1]["info"]["state"] = "idle"
        data.append({"info": {"state": "running", "props": {"media.class": "Stream/Output/Audio"}}})
        self.assertFalse(p.snapshot(data)["capturing"])


class GamingTests(unittest.TestCase):
    def test_known_pegasus_and_emulators(self):
        for exe in p.GAMING_EXECUTABLES:
            self.assertTrue(p.is_gaming_process(exe, {}))

    def test_packaged_symphony_dotnet_is_not_any_dotnet_app(self):
        self.assertTrue(p.is_gaming_process("dotnet", {}, ["dotnet", "/nix/store/example/lib/symphony-recomp/sotn.dll"]))
        self.assertFalse(p.is_gaming_process("dotnet", {}, ["dotnet", "/tmp/sotn.dll"]))

    def test_steam_game_identity(self):
        self.assertTrue(p.is_gaming_process("P5R.exe", {"SteamAppId": "1687950"}))
        self.assertTrue(p.is_gaming_process("game", {"SteamGameId": "123456789012345"}))

    def test_steam_client_is_not_a_game(self):
        for identity in [{}, {"SteamAppId": "0"}, {"SteamAppId": "bad"}, {"SteamGameId": "-1"}]:
            self.assertFalse(p.is_gaming_process("steam", identity))
        self.assertFalse(p.is_gaming_process("vivaldi", {}))

    def test_proc_detection_uses_executable_not_truncated_comm(self):
        with tempfile.TemporaryDirectory() as directory:
            proc = Path(directory)
            entry = proc / "123"
            entry.mkdir()
            (entry / "exe").symlink_to("/nix/store/example/bin/.pegasus-fe-wrapped")
            (entry / "environ").write_bytes(b"UNRELATED=not-logged\0")
            self.assertTrue(p.gaming_active(proc))

    def test_disappearing_proc_is_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "123").mkdir()
            self.assertFalse(p.gaming_active(Path(directory)))


class ReconcileTests(unittest.TestCase):
    def execute(self, graphs, connected=True, gaming=True, state=None, restore=False, now=100):
        calls = []
        values = iter(graphs)
        def run(command):
            calls.append(command)
            if command[0] == "pw-dump":
                return json.dumps(next(values))
            if command[0] == "bluetoothctl":
                return "Connected: yes" if connected else "Connected: no"
            return ""
        with patch.object(p, "run", side_effect=run), patch.object(p, "gaming_active", return_value=gaming):
            if state is None:
                state = {"serial": "10", "pending_restore": False} if restore else {}
            updated = p.reconcile(state, restore=restore, now=now)
        return updated, [c for c in calls if c[0] == "wpctl"]

    def test_requires_both_controller_and_gaming(self):
        for connected, gaming in [(False, True), (True, False), (False, False)]:
            _, calls = self.execute([graph("a2dp-sink-aac")] * 2, connected, gaming)
            self.assertEqual(calls, [["wpctl", "set-profile", "99", "1"]])

    def test_runtime_profile_indices_not_hardcoded(self):
        data = graph()
        data[0]["info"]["params"]["EnumProfile"][2]["index"] = 4567
        _, calls = self.execute([data, data])
        self.assertEqual(calls, [["wpctl", "set-profile", "99", "4567"]])

    def test_capture_started_during_detection_blocks_change(self):
        _, calls = self.execute([graph(), graph(capture=True)])
        self.assertFalse(calls)

    def test_card_replaced_during_detection_blocks_change(self):
        _, calls = self.execute([graph(), graph(serial=20)])
        self.assertFalse(calls)

    def test_missing_card(self):
        updated, calls = self.execute([[]])
        self.assertEqual(updated, {})
        self.assertFalse(calls)

    def test_bounded_cooldown_and_retries(self):
        state, calls = self.execute([graph(), graph()])
        self.assertEqual(len(calls), 1)
        for now, expected in [(101, 0), (110, 1), (120, 1), (140, 0)]:
            state, calls = self.execute([graph(), graph()], state=state, now=now)
            self.assertEqual(len(calls), expected)

    def test_new_connection_resets_old_retry_state(self):
        state = {"serial": "old", "request_key": ["10", 1, 2], "attempts": 99, "requested_at": 99}
        _, calls = self.execute([graph(), graph()], state=state)
        self.assertEqual(len(calls), 1)

    def test_pending_priming_restore_survives_active_recording(self):
        state, calls = self.execute([graph("headset-head-unit", capture=True)], restore=True)
        self.assertTrue(state["pending_restore"])
        self.assertFalse(calls)
        _, calls = self.execute([graph("headset-head-unit")] * 2, state=state)
        self.assertEqual(calls, [["wpctl", "set-profile", "99", "2"]])

    def test_post_priming_request_survives_intervening_cooldown_polls(self):
        state, _ = self.execute([graph("headset-head-unit")] * 2, restore=True)
        for now in [101, 102, 109]:
            state, calls = self.execute([graph("headset-head-unit")] * 2, state=state, now=now)
            self.assertTrue(state["pending_restore"])
            self.assertFalse(calls)
        state, calls = self.execute([graph("headset-head-unit")] * 2, state=state, now=111)
        self.assertTrue(state["pending_restore"])
        self.assertEqual(len(calls), 1)

    def test_capture_deferral_preserves_cooldown_and_attempt_cap(self):
        state, _ = self.execute([graph(), graph()])
        for capture_at, poll_at in [(101, 102), (111, 112), (121, 122)]:
            state, calls = self.execute([graph(capture=True)], state=state, now=capture_at)
            self.assertFalse(calls)
            state, calls = self.execute([graph(), graph()], state=state, now=poll_at)
            self.assertEqual(len(calls), 0 if poll_at == 102 else 1)
        state, _ = self.execute([graph(capture=True)], state=state, now=140)
        _, calls = self.execute([graph(), graph()], state=state, now=141)
        self.assertFalse(calls)

    def test_temporarily_missing_aac_preserves_priming_restore(self):
        state, _ = self.execute([graph("headset-head-unit")] * 2, restore=True)
        missing = graph("headset-head-unit")
        del missing[0]["info"]["params"]["EnumProfile"][2]
        state, calls = self.execute([missing], state=state, now=101)
        self.assertTrue(state["pending_restore"])
        self.assertEqual(state["attempts"], 1)
        self.assertFalse(calls)
        _, calls = self.execute([graph("headset-head-unit")] * 2, state=state, now=111)
        self.assertEqual(len(calls), 1)

    def test_first_restore_with_missing_graph_keeps_registered_connection_scope(self):
        state = {"serial": "10", "pending_restore": False}
        state, calls = self.execute([[]], state=state, restore=True)
        self.assertTrue(state["pending_restore"])
        self.assertFalse(calls)
        _, calls = self.execute([graph("headset-head-unit")] * 2, state=state, now=101)
        self.assertEqual(len(calls), 1)
        # A different PipeWire connection must not inherit the old request.
        _, calls = self.execute([graph("headset-head-unit", serial=20)], state=state, now=102)
        self.assertFalse(calls)

    def test_initial_restore_cannot_escape_registered_connection(self):
        for state in [{}, {"serial": "old", "pending_restore": True}]:
            _, calls = self.execute([graph("headset-head-unit", serial=20)], state=state, restore=True)
            self.assertFalse(calls)

    def test_off_cancels_pending_restore_even_during_transient_deferral(self):
        for capturing, missing in [(True, False), (False, True), (True, True)]:
            state = {"serial": "10", "pending_restore": True}
            data = graph("off", capture=capturing)
            if missing:
                del data[0]["info"]["params"]["EnumProfile"][2]
            state, calls = self.execute([data], state=state)
            self.assertFalse(state["pending_restore"])
            self.assertFalse(calls)
            _, calls = self.execute([graph("headset-head-unit")], state=state, now=101)
            self.assertFalse(calls)

    def test_missing_graph_preserves_pending_intent(self):
        state, _ = self.execute([graph("headset-head-unit")] * 2, restore=True)
        after, calls = self.execute([[]], state=state, now=101)
        self.assertEqual(after, state)
        self.assertFalse(calls)

    def test_acknowledgement_during_capture_clears_pending_intent(self):
        state, _ = self.execute([graph("headset-head-unit")] * 2, restore=True)
        after, calls = self.execute([graph("a2dp-sink-aac", capture=True)], state=state, now=101)
        self.assertFalse(after["pending_restore"])
        self.assertNotIn("attempts", after)
        self.assertFalse(calls)

    def test_successful_selection_clears_retry_state(self):
        state, _ = self.execute([graph(), graph()])
        state, calls = self.execute([graph("a2dp-sink-aac")], state=state)
        self.assertNotIn("request_key", state)
        self.assertFalse(calls)


class BeginPrimingTests(unittest.TestCase):
    def test_registers_identity_without_any_profile_change(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict("os.environ", {"XDG_RUNTIME_DIR": directory}), \
                 patch("sys.argv", ["sony-headset-playback", "--begin-priming"]), \
                 patch.object(p, "run", return_value=json.dumps(graph())) as run:
                self.assertIsNone(p.main())
                run.assert_called_once_with(["pw-dump"])
            state = json.loads((Path(directory) / "sony-headset-prime/playback.json").read_text())
            self.assertEqual(state, {"serial": "10", "pending_restore": False})

    def test_initial_restore_intent_survives_transient_command_failures(self):
        for error in [subprocess.TimeoutExpired("pw-dump", 5), OSError("unavailable")]:
            with tempfile.TemporaryDirectory() as directory:
                state_path = Path(directory) / "sony-headset-prime/playback.json"
                state_path.parent.mkdir()
                state_path.write_text(json.dumps({"serial": "10", "pending_restore": False}))
                with patch.dict("os.environ", {"XDG_RUNTIME_DIR": directory}), \
                     patch("sys.argv", ["sony-headset-playback", "--restore-playback"]), \
                     patch.object(p, "run", side_effect=error):
                    p.main()
                state = json.loads(state_path.read_text())
                self.assertEqual(state["serial"], "10")
                self.assertTrue(state["pending_restore"])

    def test_missing_graph_or_capture_defers_without_profile_changes(self):
        for data in [[], graph(capture=True)]:
            with tempfile.TemporaryDirectory() as directory:
                with patch.dict("os.environ", {"XDG_RUNTIME_DIR": directory}), \
                     patch("sys.argv", ["sony-headset-playback", "--begin-priming"]), \
                     patch.object(p, "run", return_value=json.dumps(data)) as run:
                    self.assertEqual(p.main(), 2)
                    run.assert_called_once_with(["pw-dump"])
                self.assertFalse((Path(directory) / "sony-headset-prime/playback.json").exists())


if __name__ == "__main__":
    unittest.main()
