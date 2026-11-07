import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("tablet_apps", ROOT / "home/scripts/desktop/tablet_apps.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
REGISTRY = json.loads((ROOT / "home/config/quickshell/tablet-home-preview/apps.json").read_text())


class WindowAppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.clients = []
        self.dispatch = Mock(side_effect=self.dispatched)
        self.apps = module.WindowApps(self.temp.name, REGISTRY, lambda *args: self.clients, self.dispatch, lambda pid: "start")
        self.apps.check_compatible = Mock()  # Lifecycle tests isolate the capability probe below.
        self.apps.require_compatible = Mock(return_value={"processes":{os.getpid():"start"},"windows":[]})
        self.apps.verify_launch = Mock()
        self.apps.browser_pids = Mock(return_value={os.getpid()})  # Never enumerate host browsers in tests.

    def tearDown(self):
        self.temp.cleanup()

    def dispatched(self, command, argument):
        if command == "tagwindow":
            tag, address = argument.split(" address:")
            for c in self.clients:
                if c["address"] == address: c["tags"] = [tag.removeprefix("+")]
        elif command == "movetoworkspacesilent":
            workspace, address = argument.split(",address:")
            for c in self.clients:
                if c["address"] == address: c["workspace"]["name"] = workspace.removeprefix("name:")

    def client(self, address="0xab", **kw):
        return {"address": address, "pid": os.getpid(), "class": "vivaldi-stable", "title": "Ordinary browser",
                "mapped": True, "workspace": {"name": "tablet-trial"}, "tags": [], **kw}

    def launch(self):
        with patch.object(module.subprocess, "Popen") as spawn:
            spawn.return_value.poll.return_value = 0
            self.apps.open("browser")
        self.assertNotIn("--user-data-dir", " ".join(spawn.call_args.args[0]))
        self.assertIn("--new-window", spawn.call_args.args[0])
        return self.apps.pending["marker"]

    def own(self):
        marker = self.launch()
        client = self.client(title=marker)
        self.clients.append(client)
        self.apps.tick()
        return client

    def test_cold_and_first_window_launch_are_refused_before_any_spawn(self):
        self.apps.require_compatible=lambda app:module.WindowApps.require_compatible(self.apps,app)
        with patch.object(module.subprocess,"Popen") as spawn:
            self.apps.check_compatible.return_value=False
            with self.assertRaisesRegex(RuntimeError,"cold startup"):self.apps.open("browser")
            self.apps.check_compatible.return_value=True  # Even a compatible background-only process may restore sessions.
            with self.assertRaisesRegex(RuntimeError,"cold startup"):self.apps.open("browser")
        spawn.assert_not_called()
        self.assertIsNone(self.apps.pending)

    def test_process_probe_finds_same_user_browser_without_windows(self):
        proc=Path(self.temp.name)/"proc";proc.mkdir()
        for pid,name in ((22,"vivaldi-bin"),(23,"other-app")):
            (proc/str(pid)).mkdir();(proc/str(pid)/"exe").symlink_to("/store/"+name)
        (proc/"not-a-pid").mkdir()
        real_path=Path
        with patch.object(module,"Path",side_effect=lambda p:proc if p=="/proc" else real_path(p)):
            self.assertEqual(module.WindowApps.browser_pids(self.apps,self.apps.registry["browser"]),{22})

    def test_windowless_warm_browser_cannot_bypass_capability_guard(self):
        self.apps.browser_pids.return_value={os.getpid()}
        self.assertEqual(self.clients,[])
        with patch.object(Path,"read_bytes",return_value=b"vivaldi\0--no-startup-window\0"):
            with self.assertRaisesRegex(RuntimeError,"Cannot verify native keyboard"):
                module.WindowApps.check_compatible(self.apps,"browser")
        self.dispatch.assert_not_called()

    def test_existing_unverified_browser_is_rejected_without_launch_or_mutation(self):
        self.clients.append(self.client())
        with patch.object(Path,"read_bytes",return_value=b"vivaldi\0--new-window\0private-url\0"):
            with self.assertRaisesRegex(RuntimeError,"Cannot verify native keyboard"):
                module.WindowApps.check_compatible(self.apps,"browser")
        self.dispatch.assert_not_called()
        self.assertFalse(self.apps.windows)

    def test_existing_verified_ime_browser_is_accepted(self):
        self.clients.append(self.client())
        with patch.object(Path,"read_bytes",return_value=b"vivaldi\0--enable-wayland-ime\0--wayland-text-input-version=3\0"), \
                patch.object(Path,"readlink",return_value=Path("/store/vivaldi-bin")):
            verified=module.WindowApps.check_compatible(self.apps,"browser")
        self.assertEqual(verified,{os.getpid():"start"})
        self.dispatch.assert_not_called()

    def test_vivaldi_flattened_process_title_flags_are_recognized(self):
        self.clients.append(self.client())
        with patch.object(Path,"read_bytes",return_value=b"/store/vivaldi-bin --enable-wayland-ime --wayland-text-input-version=3 about:blank\0"), \
                patch.object(Path,"readlink",return_value=Path("/store/vivaldi-bin")):
            module.WindowApps.check_compatible(self.apps,"browser")

    def test_url_text_cannot_supply_capability_switches(self):
        self.clients.append(self.client())
        with patch.object(Path,"read_bytes",return_value=b"/store/vivaldi-bin https://example.test/ --enable-wayland-ime --wayland-text-input-version=3\0"), \
                patch.object(Path,"readlink",return_value=Path("/store/vivaldi-bin")):
            with self.assertRaisesRegex(RuntimeError,"Cannot verify"):
                module.WindowApps.check_compatible(self.apps,"browser")

    def test_xwayland_browser_is_rejected_even_with_flags(self):
        self.clients.append(self.client(xwayland=True))
        with self.assertRaisesRegex(RuntimeError,"XWayland"):
            module.WindowApps.check_compatible(self.apps,"browser")

    def test_native_minimum_height_does_not_trap_keyboard_resize(self):
        self.apps.active = "browser"
        self.assertEqual(self.apps.geometry({"width":960,"height":640},320),(0,32,960,400))

    def test_pinning_or_grouping_an_owned_window_releases_it(self):
        client = self.own()
        client["grouped"] = ["0xab", "0xac"]
        self.dispatch.reset_mock()
        self.apps.tick()
        self.assertFalse(self.apps.windows)
        self.dispatch.assert_not_called()

    def test_only_selected_roster_is_declared(self):
        self.assertEqual([a["label"] for a in REGISTRY], ["Pi", "Vivaldi", "Spotify", "Pegasus", "Krita"])
        self.assertEqual([a["id"] for a in REGISTRY if a["kind"] == "window"], ["browser"])

    def test_launch_does_not_reuse_preexisting_same_pid_browser(self):
        old = self.client()
        self.clients.append(old)
        marker = self.launch()
        old["title"] = marker
        self.apps.tick()
        self.assertIsNotNone(self.apps.pending)
        self.assertFalse(self.apps.windows)
        self.dispatch.assert_not_called()

    def test_unrelated_new_window_not_claimed_even_same_pid(self):
        self.launch()
        self.clients.append(self.client())
        self.apps.tick()
        self.assertFalse(self.apps.windows)
        self.dispatch.assert_not_called()

    def test_nonce_claim_tags_only_exact_new_window_and_resume_does_not_spawn(self):
        old = self.client(address="0xaa")
        self.clients.append(old)
        client = self.own()
        self.assertIs(self.apps.owned("browser"), client)
        with patch.object(module.subprocess, "Popen") as spawn:
            self.apps.open("browser")
        spawn.assert_not_called()
        self.assertEqual(old["tags"], [])
        self.assertEqual(Path(self.temp.name, "app-windows.json").stat().st_mode & 0o777, 0o600)

    def test_verified_new_window_can_be_placed_in_explicit_tablet_workspace(self):
        marker = self.launch()
        client = self.client(title=marker, workspace={"name":"elsewhere"})
        self.clients.append(client)
        self.apps.tick()
        self.assertEqual(client["workspace"]["name"], "tablet-trial")
        self.dispatch.assert_any_call("movetoworkspacesilent", "name:tablet-trial,address:0xab")

    def test_process_replaced_after_verification_cannot_become_a_new_authority(self):
        self.clients.append(self.client())
        proof={"processes":{os.getpid():"start"},"windows":[{"address":"0xab","pid":os.getpid(),"start":"start"}]}
        def verified(app):
            self.apps.start_time=lambda pid:"replacement-start"
            return proof
        self.apps.require_compatible.side_effect=verified
        self.apps.verify_launch=lambda app,verification:module.WindowApps.verify_launch(self.apps,app,verification)
        with patch.object(module.subprocess,"Popen") as spawn:
            with self.assertRaisesRegex(RuntimeError,"changed before launch"):self.apps.open("browser")
        spawn.assert_not_called()
        self.apps.browser_pids.assert_not_called()  # No post-verification authority enumeration.
        self.assertEqual(proof["processes"][os.getpid()],"start")
        self.assertIsNone(self.apps.pending)

    def test_last_normal_window_disappearing_prevents_first_window_restore_launch(self):
        proof={"processes":{os.getpid():"start"},"windows":[{"address":"0xab","pid":os.getpid(),"start":"start"}]}
        with self.assertRaisesRegex(RuntimeError,"window changed"):
            module.WindowApps.verify_launch(self.apps,"browser",proof)

    def test_nonce_from_replacement_cold_process_is_not_claimed(self):
        marker = self.launch()
        self.apps.pending["authorities"] = {}  # Verified warm process exited/replaced before handoff.
        self.clients.append(self.client(title=marker))
        self.apps.tick()
        self.assertFalse(self.apps.windows)
        self.assertIn("process changed",self.apps.error)
        self.dispatch.assert_not_called()

    def test_ambiguous_nonce_claim_fails_closed(self):
        marker = self.launch()
        self.clients.extend([self.client(title=marker), self.client(address="0xac",title=marker)])
        self.apps.tick()
        self.assertFalse(self.apps.windows)
        self.assertIn("Ambiguous", self.apps.error)
        self.dispatch.assert_not_called()

    def test_timeout_never_closes_unknown_window_or_process(self):
        self.launch()
        self.apps.pending["deadline"] = 0
        self.apps.tick()
        self.assertFalse(self.apps.windows)
        self.assertIsNone(self.apps.pending)
        self.assertIn("could not be verified", self.apps.error)
        self.dispatch.assert_not_called()

    def test_close_is_per_window_graceful_not_per_process(self):
        client = self.own()
        self.dispatch.reset_mock()
        self.apps.close("browser")
        self.dispatch.assert_called_once_with("closewindow", "address:" + client["address"])
        self.assertIn("browser", self.apps.windows)  # May show a confirmation or refuse close.
        self.clients.clear()
        self.apps.tick()
        self.assertNotIn("browser", self.apps.windows)

    def test_address_reuse_same_pid_without_tag_is_not_owned(self):
        client = self.own()
        client["tags"] = []
        with self.assertRaises(RuntimeError): self.apps.close("browser")
        self.apps.tick()
        self.assertNotIn("browser", self.apps.windows)

    def test_pid_reuse_never_owned(self):
        self.own()
        self.apps.start_time = lambda pid: "new-start"
        with self.assertRaises(RuntimeError): self.apps.focus("browser")
        self.apps.tick()
        self.assertFalse(self.apps.windows)

    def test_home_parks_exact_window_and_resume_recovers_only_its_recorded_slot(self):
        client = self.own()
        self.apps.park("browser")
        self.assertTrue(client["workspace"]["name"].startswith("special:tablet-app-"))
        self.assertIs(self.apps.owned("browser"),client)
        with self.assertRaises(RuntimeError):self.apps.close("browser")
        with self.assertRaises(RuntimeError):self.apps.focus("browser")
        self.apps.open("browser")
        self.assertEqual(client["workspace"]["name"],"tablet-trial")
        self.apps.park("browser")
        self.apps.release()
        self.assertEqual(client["workspace"]["name"],"tablet-trial")

    def test_corrupted_parking_destination_cannot_authorize_another_workspace(self):
        client = self.own()
        self.apps.windows["browser"]["parking"] = "user-destination"
        client["workspace"]["name"] = "user-destination"
        self.assertIsNone(self.apps.owned("browser"))
        self.dispatch.reset_mock()
        self.apps.release()
        self.dispatch.assert_not_called()

    def test_window_moved_by_user_is_not_stolen_back_or_closed(self):
        client = self.own()
        client["workspace"] = {"name":"user-destination"}
        self.dispatch.reset_mock()
        self.apps.tick()
        self.assertFalse(self.apps.windows)
        with self.assertRaises(RuntimeError): self.apps.close("browser")
        self.dispatch.assert_not_called()

    def test_ownership_survives_controller_restart_but_not_compositor_restart(self):
        self.own()
        again = module.WindowApps(self.temp.name, REGISTRY, lambda *args:self.clients, self.dispatch,lambda pid:"start")
        self.assertIsNotNone(again.owned("browser"))
        with patch.dict(os.environ,{"HYPRLAND_INSTANCE_SIGNATURE":"other-instance"}):
            other = module.WindowApps(self.temp.name, REGISTRY, lambda *args:self.clients,self.dispatch,lambda pid:"start")
        self.assertFalse(other.windows)

    def test_layout_requires_actual_geometry_and_repairs_external_resize(self):
        client = self.own()
        monitor = {"width":1000,"height":800,"scale":1,"x":0,"y":0}
        self.dispatch.reset_mock()
        self.assertFalse(self.apps.fit(client,monitor))
        self.dispatch.assert_any_call("setprop", "address:0xab no_anim on")
        client.update(floating=True,at=[0,32],size=[1000,712])
        self.dispatch.reset_mock()
        self.assertTrue(self.apps.fit(client,monitor))
        self.dispatch.assert_not_called()
        client["size"] = [900,600]
        self.assertFalse(self.apps.fit(client,monitor))
        self.dispatch.assert_any_call("resizewindowpixel", "exact 1000 712,address:0xab")

    def test_geometry_handles_rotation_scale_and_keyboard(self):
        monitor = {"width":1600,"height":1000,"scale":2,"transform":1,"x":100,"y":50}
        self.assertEqual(self.apps.geometry(monitor,200), (100,82,500,512))

    def test_no_preview_app_can_be_launched_by_command_injection(self):
        with patch.object(module.subprocess,"Popen") as spawn:
            for app in ("music", "browser;evil", "unknown", None):
                with self.assertRaises(RuntimeError): self.apps.open(app)
        spawn.assert_not_called()


if __name__ == "__main__": unittest.main()
