#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).parents[1] / "scripts/steamctl.py"
SPEC = importlib.util.spec_from_file_location("steamctl", SCRIPT)
assert SPEC and SPEC.loader
steamctl = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(steamctl)


class GameLogTests(unittest.TestCase):
    def test_common_tracked_process_lifecycle(self) -> None:
        log = """
[2026-11-01 20:00:00] AppID 1426210 adding PID 1000 as a tracked process
[2026-11-01 20:01:00] AppID 1426210 no longer tracking PID 1000, exit code 0
"""
        self.assertEqual(steamctl.parse_game_running_state(log, 1426210), (False, 2))

    def test_running_state(self) -> None:
        log = "[2026-11-01] AppID 400 state changed : Fully Installed,App Running\n"
        self.assertEqual(steamctl.parse_game_running_state(log, 400), (True, 1))

    def test_log_rotation_or_truncation_is_reparsed_from_current_content(self) -> None:
        old_log = """
[2026-11-01] AppID 400 adding PID 1000 as a tracked process
[2026-11-01] AppID 400 no longer tracking PID 1000
"""
        rotated_log = "[2026-11-02] AppID 400 adding PID 2000 as a tracked process\n"
        self.assertEqual(steamctl.parse_game_running_state(old_log, 400)[0], False)
        self.assertEqual(steamctl.parse_game_running_state(rotated_log, 400)[0], True)

    def test_start_and_stop_arriving_between_polls_are_both_counted(self) -> None:
        log = """
[2026-11-01] AppID 400 adding PID 1000 as a tracked process
[2026-11-01] AppID 400 no longer tracking PID 1000
"""
        state, starts, stops, matches = steamctl.parse_game_lifecycle(log, 400)
        self.assertEqual((state, starts, stops, matches), (False, 1, 1, 2))

    def test_one_of_multiple_tracked_processes_remains_running(self) -> None:
        log = """
[2026-11-01] AppID 400 adding PID 1000 as a tracked process
[2026-11-01] AppID 400 adding PID 1001 as a tracked process
[2026-11-01] AppID 400 no longer tracking PID 1000
"""
        self.assertEqual(steamctl.parse_game_running_state(log, 400)[0], True)


class CloudLogTests(unittest.TestCase):
    def setUp(self):
        running = mock.patch.object(steamctl, "steam_running", return_value=True)
        started = mock.patch.object(steamctl, "steam_session_start_time", return_value=None)
        running.start()
        started.start()
        self.addCleanup(running.stop)
        self.addCleanup(started.stop)

    def check_log(self, text, expected):
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(steamctl, "LOGS", Path(directory)):
            path = steamctl.LOGS / "cloud_log.txt"
            path.write_text(text)
            self.assertEqual(steamctl.active_cloud_appids(), expected)
            self.assertEqual(path.read_text(), text)  # Never erase evidence to clear status.

    def test_init_cache_completion_clears_actual_civ6_false_blocker(self):
        self.check_log("[AppID 289070] Starting sync (init,)\n"
                       "[AppID 289070] Init cache request complete\n"
                       "[AppID 289070] YldWriteCacheDirectoryToFile - empty vector, deleting cache\n", [])

    def test_completed_download_clears_actual_controller_cloud_sequence(self):
        self.check_log("[AppID 241100] HTTP download for file 'controller' beginning\n"
                       "[AppID 241100] Download complete, result OK\n"
                       "[AppID 241100] Successfully synced to ChangeNumber 13\n"
                       "[AppID 241100] YldWriteCacheDirectoryToFile - saved\n", [])

    def test_completed_download_does_not_clear_unfinished_upload(self):
        self.check_log("[AppID 400] HTTP download for file 'save' beginning\n"
                       "[AppID 400] Upload batch initiated\n"
                       "[AppID 400] Download complete, result OK\n"
                       "[AppID 400] Successfully synced\n"
                       "[AppID 400] YldWriteCacheDirectoryToFile\n", [400])

    def test_completed_upload_does_not_clear_unfinished_download(self):
        self.check_log("[AppID 400] HTTP download for file 'save' beginning\n"
                       "[AppID 400] Upload batch initiated\n"
                       "[AppID 400] Upload complete, result OK\n", [400])

    def test_quota_callback_does_not_clear_unfinished_transfer(self):
        self.check_log("[AppID 400] Upload batch initiated\n"
                       "[AppID 400] GetAppQuotaUsage - success\n", [400])

    def test_init_completion_does_not_hide_started_transfer(self):
        self.check_log("[AppID 400] Starting sync (init,)\n"
                       "[AppID 400] HTTP download for file beginning\n"
                       "[AppID 400] Init cache request complete\n", [400])

    def test_cache_write_does_not_hide_transfer_after_success_marker(self):
        self.check_log("[AppID 400] Starting sync (up,)\n"
                       "[AppID 400] Successfully synced\n"
                       "[AppID 400] Upload batch initiated\n"
                       "[AppID 400] YldWriteCacheDirectoryToFile\n", [400])

    def test_offline_client_has_no_active_cloud_work(self):
        with mock.patch.object(steamctl, "steam_running", return_value=False):
            self.check_log("[AppID 400] Starting sync (up,)\n", [])

    def test_old_unfinished_current_session_upload_stays_protected(self):
        self.check_log("[2000-01-01 12:00:00] [AppID 400] Starting sync (up,)\n", [400])

    def test_previous_process_lifetime_ignored_even_without_version_marker(self):
        import time
        started = time.mktime(time.strptime("2026-11-07 12:00:00", "%Y-%m-%d %H:%M:%S"))
        with mock.patch.object(steamctl, "steam_session_start_time", return_value=started):
            self.check_log("[2026-11-06 12:00:00] [AppID 400] Starting sync (up,)\n"
                           "[2026-11-07 12:00:10] [AppID 401] Starting sync (up,)\n", [401])

    def test_completed_sync_is_not_active(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            old_logs = steamctl.LOGS
            steamctl.LOGS = Path(directory)
            try:
                (steamctl.LOGS / "cloud_log.txt").write_text(
                    "[AppID 400] Starting sync (up,)\n"
                    "[AppID 400] Upload complete, result OK\n"
                )
                self.assertEqual(steamctl.active_cloud_appids(), [])
            finally:
                steamctl.LOGS = old_logs

    def test_unfinished_sync_is_active(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            old_logs = steamctl.LOGS
            steamctl.LOGS = Path(directory)
            try:
                (steamctl.LOGS / "cloud_log.txt").write_text(
                    "[AppID 400] Starting sync (up,)\n"
                )
                self.assertEqual(steamctl.active_cloud_appids(), [400])
            finally:
                steamctl.LOGS = old_logs

    def test_upload_batch_after_sync_success_remains_active_until_upload_complete(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            old_logs = steamctl.LOGS
            steamctl.LOGS = Path(directory)
            try:
                log = steamctl.LOGS / "cloud_log.txt"
                log.write_text(
                    "[AppID 400] Starting sync (up,)\n"
                    "[AppID 400] Successfully synced to ChangeNumber 10\n"
                    "[AppID 400] Upload batch initiated, ID: 1\n"
                    "[AppID 400] HTTP upload for file 'save' beginning . . .\n"
                )
                self.assertEqual(steamctl.active_cloud_appids(), [400])
                with log.open("a") as handle:
                    handle.write("[AppID 400] Upload complete, result OK\n")
                self.assertEqual(steamctl.active_cloud_appids(), [])
            finally:
                steamctl.LOGS = old_logs

    def test_new_client_session_discards_stale_activity(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            old_logs = steamctl.LOGS
            steamctl.LOGS = Path(directory)
            try:
                (steamctl.LOGS / "cloud_log.txt").write_text(
                    "[AppID 400] Starting sync (up,)\n"
                    "[2026-11-02] Client version: 123\n"
                )
                self.assertEqual(steamctl.active_cloud_appids(), [])
            finally:
                steamctl.LOGS = old_logs


class DownloadActivityTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.logs = Path(self.directory.name)
        self.games = []
        for attribute, value in (("LOGS", self.logs),):
            patcher = mock.patch.object(steamctl, attribute, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        for attribute, value in (("steam_running", True), ("steam_session_start_time", None)):
            patcher = mock.patch.object(steamctl, attribute, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.object(steamctl, "manifests", side_effect=lambda: self.games)
        patcher.start()
        self.addCleanup(patcher.stop)

    def manifest(self, flags):
        self.games = [{"appid": 242550, "state_flags": flags, "fully_installed": False}]

    def test_installed_pending_rayman_update_is_not_active(self):
        self.manifest(6)
        self.assertEqual(steamctl.active_download_appids(), [])

    def test_paused_partial_download_is_not_active(self):
        self.manifest(2 | 512 | 1024)
        self.assertEqual(steamctl.active_download_appids(), [])

    def test_running_and_download_install_phases_are_protected(self):
        for bit in [256, 2048, *[1 << n for n in range(16, 24)]]:
            with self.subTest(bit=bit):
                self.manifest(4 | bit)
                self.assertEqual(steamctl.active_download_appids(), [242550])

    def test_ambiguous_started_install_remains_protected(self):
        self.manifest(1026)
        self.assertEqual(steamctl.active_download_appids(), [242550])

    def test_confirmed_suspended_update_not_kept_active_by_started_flag(self):
        self.manifest(1026)
        (self.logs / "content_log.txt").write_text("AppID 242550 App update changed : None\n")
        self.assertEqual(steamctl.active_download_appids(), [])

    def test_shader_work_is_protected_even_without_manifest(self):
        log = self.logs / "content_log.txt"
        log.write_text("AppID 400 Shader update changed : Running Update,Downloading,\n"
                       "AppID 400 App update changed : None\n")
        self.assertEqual(steamctl.active_download_appids(), [400])
        with log.open("a") as f:
            f.write("AppID 400 Shader update changed : None\n")
        self.assertEqual(steamctl.active_download_appids(), [])

    def test_workshop_transfer_protected_until_completed(self):
        log = self.logs / "content_log.txt"
        log.write_text("AppID 241100 Workshop update changed : Running Update,Downloading,\n")
        self.assertEqual(steamctl.active_download_appids(), [241100])
        with log.open("a") as f:
            f.write("AppID 241100 Workshop update changed : None\n")
        self.assertEqual(steamctl.active_download_appids(), [])

    def test_offline_client_has_no_active_downloads(self):
        self.manifest(1026)
        with mock.patch.object(steamctl, "steam_running", return_value=False):
            self.assertEqual(steamctl.active_download_appids(), [])

    def test_leftover_staging_directory_is_not_proof_of_activity(self):
        staging = self.logs / "steamapps/downloading/242550"
        staging.mkdir(parents=True)
        self.manifest(6)
        with mock.patch.object(steamctl, "library_paths", return_value=[self.logs]):
            self.assertEqual(steamctl.active_download_appids(), [])


class WatcherSafetyTests(unittest.TestCase):
    def test_stale_pid_record_is_not_signalled(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            old_pidfile = steamctl.HIDE_WATCH_PID
            steamctl.HIDE_WATCH_PID = Path(directory) / "hide-watch.pid"
            try:
                steamctl.HIDE_WATCH_PID.write_text(
                    '{"pid": %d, "start_ticks": -1}\n' % __import__("os").getpid()
                )
                with mock.patch.object(steamctl.os, "kill") as kill:
                    steamctl.stop_hide_watch()
                    kill.assert_not_called()
            finally:
                steamctl.HIDE_WATCH_PID = old_pidfile


class AccountSelectionTests(unittest.TestCase):
    def test_most_recent_login_account_is_selected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            old_root, old_userdata = steamctl.STEAM_ROOT, steamctl.USERDATA
            steamctl.STEAM_ROOT = Path(directory)
            steamctl.USERDATA = Path(directory) / "userdata"
            (steamctl.STEAM_ROOT / "config").mkdir(parents=True)
            (steamctl.STEAM_ROOT / "config/loginusers.vdf").write_text(
                '"users" { "76561198000000001" { "MostRecent" "0" } '
                '"76561198000000002" { "MostRecent" "1" } }'
            )
            try:
                self.assertEqual(steamctl.account_id64(), 76561198000000002)
            finally:
                steamctl.STEAM_ROOT, steamctl.USERDATA = old_root, old_userdata


    def test_ambiguous_login_metadata_does_not_fall_back_to_userdata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            old_root, old_userdata = steamctl.STEAM_ROOT, steamctl.USERDATA
            steamctl.STEAM_ROOT = Path(directory)
            steamctl.USERDATA = Path(directory) / "userdata"
            (steamctl.STEAM_ROOT / "config").mkdir(parents=True)
            (steamctl.USERDATA / "123").mkdir(parents=True)
            (steamctl.STEAM_ROOT / "config/loginusers.vdf").write_text(
                '"users" { "76561198000000001" { "MostRecent" "0" } '
                '"76561198000000002" { "MostRecent" "0" } }'
            )
            try:
                with self.assertRaisesRegex(steamctl.SteamError, "Multiple Steam login accounts"):
                    steamctl.account_id64()
            finally:
                steamctl.STEAM_ROOT, steamctl.USERDATA = old_root, old_userdata


class ConsoleInstallTests(unittest.TestCase):
    def test_login_ready_uses_latest_client_session(self) -> None:
        text = (
            "Client version: old\nSetLoginState: Success - OK\n"
            "Client version: new\nSetLoginState: WaitingForNetwork - OK\n"
        )
        self.assertFalse(steamctl.steam_login_ready_text(text))
        self.assertTrue(steamctl.steam_login_ready_text(text + "SetLoginState: Success - OK\n"))

    def test_console_acknowledgement_matches_exact_install_command(self) -> None:
        log = "ExecCommandLine: \"'~/.steam/root/steam' '-console' '+app_install' '242550'\"\n"
        self.assertTrue(steamctl.console_command_acknowledged(log, "app_install", 242550))
        self.assertFalse(steamctl.console_command_acknowledged(log, "app_install", 620))

    def test_console_install_uses_no_steam_install_uri(self) -> None:
        log = "ExecCommandLine: \"'/steam' '-console' '+app_install' '242550'\"\n"
        with mock.patch.object(steamctl, "steam_running", return_value=True), mock.patch.object(
            steamctl, "wait_steam_ready"
        ), mock.patch.object(steamctl.shutil, "which", return_value="/steam"), mock.patch.object(
            steamctl, "file_marker", return_value={"inode": 1, "offset": 0}
        ), mock.patch.object(steamctl, "file_text_since", return_value=log), mock.patch.object(
            steamctl, "hide_windows", return_value=0
        ), mock.patch.object(steamctl, "steam_windows", return_value=[]), mock.patch.object(
            steamctl.subprocess, "Popen"
        ) as popen:
            result = steamctl.request_console_install(242550, approved=True)
        self.assertTrue(result["acknowledged"])
        command = popen.call_args.args[0]
        self.assertEqual(command, ["/steam", "-console", "+app_install", "242550"])
        self.assertFalse(any("steam://install" in part for part in command))

    def test_console_install_refuses_unexpected_gui_dialog(self) -> None:
        log = "ExecCommandLine: \"'/steam' '-console' '+app_install' '242550'\"\n"
        with mock.patch.object(steamctl, "steam_running", return_value=True), mock.patch.object(
            steamctl, "wait_steam_ready"
        ), mock.patch.object(steamctl.shutil, "which", return_value="/steam"), mock.patch.object(
            steamctl, "file_marker", return_value={"inode": 1, "offset": 0}
        ), mock.patch.object(steamctl, "file_text_since", return_value=log), mock.patch.object(
            steamctl, "hide_windows", return_value=1
        ), mock.patch.object(
            steamctl, "steam_windows", return_value=[{"title": "Install"}]
        ), mock.patch.object(steamctl.subprocess, "Popen"):
            with self.assertRaisesRegex(steamctl.SteamError, "unexpected install dialog"):
                steamctl.request_console_install(242550, approved=True)


class CredentialTests(unittest.TestCase):
    def test_environment_key_takes_precedence(self) -> None:
        with mock.patch.dict(steamctl.os.environ, {"STEAM_WEB_API_KEY": "test-key"}, clear=True), mock.patch.object(
            steamctl, "secret_tool_path"
        ) as secret_tool:
            self.assertEqual(steamctl.steam_api_key(), ("test-key", "STEAM_WEB_API_KEY"))
            secret_tool.assert_not_called()

    def test_secret_service_key_is_loaded_without_being_emitted(self) -> None:
        result = mock.Mock(returncode=0, stdout="secret-value\n")
        with mock.patch.dict(steamctl.os.environ, {}, clear=True), mock.patch.object(
            steamctl, "secret_tool_path", return_value="/bin/secret-tool"
        ), mock.patch.object(steamctl.subprocess, "run", return_value=result) as run:
            self.assertEqual(
                steamctl.steam_api_key(), ("secret-value", "desktop Secret Service")
            )
            self.assertNotIn("secret-value", repr(run.call_args))

    def test_missing_key_fails_safely(self) -> None:
        with mock.patch.dict(steamctl.os.environ, {}, clear=True), mock.patch.object(
            steamctl, "secret_tool_path", return_value=None
        ):
            with self.assertRaisesRegex(steamctl.SteamError, "Steam Web API key"):
                steamctl.steam_api_key()


class OwnershipTests(unittest.TestCase):
    def test_official_owned_response_wins_over_cache(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            old_root = steamctl.STEAM_ROOT
            steamctl.STEAM_ROOT = Path(directory)
            try:
                with mock.patch.object(
                    steamctl,
                    "owned_response",
                    return_value=({"games": [{"appid": 620, "name": "Portal 2"}]}, "test"),
                ), mock.patch.object(steamctl, "manifests", return_value=[]):
                    result = steamctl.ownership(620)
                self.assertEqual(result["classification"], "self_owned")
            finally:
                steamctl.STEAM_ROOT = old_root

    def test_cache_only_is_not_claimed_as_family_owned(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            old_root = steamctl.STEAM_ROOT
            steamctl.STEAM_ROOT = Path(directory)
            (steamctl.STEAM_ROOT / "appcache/librarycache/1086940").mkdir(parents=True)
            try:
                with mock.patch.object(
                    steamctl, "owned_response", return_value=({"games": []}, "test")
                ), mock.patch.object(steamctl, "manifests", return_value=[]):
                    result = steamctl.ownership(1086940)
                self.assertEqual(result["classification"], "not_self_owned_cache_present")
                self.assertIn("cannot prove", result["note"])
            finally:
                steamctl.STEAM_ROOT = old_root


class CatalogTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        state = mock.patch.object(steamctl, "STATE_DIR", Path(temporary.name))
        state.start()
        self.addCleanup(state.stop)

    def test_storage_parser_handles_gb_and_mb(self) -> None:
        self.assertEqual(steamctl.storage_gb("Storage: 8 GB available space"), 8.0)
        self.assertEqual(steamctl.storage_gb("Hard Drive: 512 MB HD space"), 0.5)
        self.assertEqual(
            steamctl.storage_gb("Storage: 8 GB", "Storage: 12 GB available space"), 12.0
        )

    def test_two_player_recommendation_filters_owned_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            old_cache, old_root, old_apps = (
                steamctl.CATALOG_CACHE,
                steamctl.STEAM_ROOT,
                steamctl.STEAM_APPS,
            )
            root = Path(directory)
            steamctl.CATALOG_CACHE = root / "catalog.json"
            steamctl.STEAM_ROOT = root / "Steam"
            steamctl.STEAM_APPS = steamctl.STEAM_ROOT / "steamapps"
            steamctl.STEAM_APPS.mkdir(parents=True)
            cache = {
                "version": steamctl.CATALOG_CACHE_VERSION,
                "apps": {
                    "620": {
                        "fetched_at": int(__import__("time").time()),
                        "data": {
                            "type": "game",
                            "name": "Portal 2",
                            "short_description": "Cooperative puzzles",
                            "categories": [{"id": 39, "description": "Shared/Split Screen Co-op"}],
                            "genres": [{"id": "23", "description": "Adventure"}],
                            "platforms": {"linux": True, "windows": True},
                            "controller_support": "full",
                            "publisher_declared_storage_gb": 8.0,
                            "metacritic_score": 95,
                            "recommendation_count": 1000,
                        },
                    },
                    "400": {
                        "fetched_at": int(__import__("time").time()),
                        "data": {
                            "type": "game",
                            "name": "Single Game",
                            "short_description": "Solo",
                            "categories": [{"id": 2, "description": "Single-player"}],
                            "genres": [{"id": "1", "description": "Action"}],
                            "platforms": {"linux": True},
                            "controller_support": None,
                            "publisher_declared_storage_gb": 2.0,
                            "metacritic_score": 80,
                            "recommendation_count": 100,
                        },
                    },
                    "220": {
                        "fetched_at": int(__import__("time").time()),
                        "data": {
                            "type": "game",
                            "name": "Remote-only Single Game",
                            "short_description": "Solo with Remote Play Together metadata",
                            "categories": [
                                {"id": 2, "description": "Single-player"},
                                {"id": 44, "description": "Remote Play Together"},
                            ],
                            "genres": [{"id": "1", "description": "Action"}],
                            "platforms": {"linux": True},
                            "controller_support": "full",
                            "publisher_declared_storage_gb": 3.0,
                            "metacritic_score": 90,
                            "recommendation_count": 1000,
                        },
                    },
                },
                "proton": {},
            }
            steamctl.save_catalog_cache(cache)
            try:
                with mock.patch.object(
                    steamctl,
                    "owned_response",
                    return_value=(
                        {
                            "games": [
                                {"appid": 620, "name": "Portal 2", "playtime_forever": 0},
                                {"appid": 400, "name": "Single Game", "playtime_forever": 0},
                                {"appid": 220, "name": "Remote-only Single Game", "playtime_forever": 0},
                            ]
                        },
                        "test",
                    ),
                ):
                    result = steamctl.recommend_games(
                        "couch", None, 2, 10, True, "full", "native", None, 10
                    )
                    style_result = steamctl.recommend_games(
                        "couch", "Puzzle", 2, None, False, "any", "any", None, 10
                    )
                self.assertEqual([game["appid"] for game in result["games"]], [620])
                self.assertEqual(result["games"][0]["compatibility"]["tier"], "native")
                self.assertEqual(result["games"][0]["ownership"], "self_owned")
                self.assertEqual([game["appid"] for game in style_result["games"]], [620])
            finally:
                steamctl.CATALOG_CACHE, steamctl.STEAM_ROOT, steamctl.STEAM_APPS = (
                    old_cache,
                    old_root,
                    old_apps,
                )

    def test_cache_only_titles_are_not_recommended_as_owned(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            old_cache, old_root, old_apps = (
                steamctl.CATALOG_CACHE,
                steamctl.STEAM_ROOT,
                steamctl.STEAM_APPS,
            )
            root = Path(directory)
            steamctl.CATALOG_CACHE = root / "catalog.json"
            steamctl.STEAM_ROOT = root / "Steam"
            steamctl.STEAM_APPS = steamctl.STEAM_ROOT / "steamapps"
            steamctl.STEAM_APPS.mkdir(parents=True)
            steamctl.save_catalog_cache(
                {"version": steamctl.CATALOG_CACHE_VERSION, "apps": {}, "proton": {}}
            )
            try:
                with mock.patch.object(
                    steamctl, "owned_response", return_value=({"games": []}, "test")
                ):
                    result = steamctl.recommend_games(
                        "any", None, None, None, False, "any", "any", None, 10
                    )
                self.assertEqual(result["games"], [])
            finally:
                steamctl.CATALOG_CACHE, steamctl.STEAM_ROOT, steamctl.STEAM_APPS = (
                    old_cache,
                    old_root,
                    old_apps,
                )


class ShutdownSafetyTests(unittest.TestCase):
    def test_stop_refuses_active_work_without_override(self) -> None:
        with mock.patch.object(steamctl, "steam_running", return_value=True), mock.patch.object(
            steamctl,
            "shutdown_blockers",
            return_value={
                "running_games": [400],
                "active_downloads": [],
                "active_cloud_syncs": [],
            },
        ):
            with self.assertRaisesRegex(steamctl.SteamError, "Refusing to stop"):
                steamctl.stop_steam(10, False, False, False)


if __name__ == "__main__":
    unittest.main()
