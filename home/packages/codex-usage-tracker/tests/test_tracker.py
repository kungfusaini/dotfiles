import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import sys
import unittest
from unittest import mock
import urllib.error

# Match the installed script's sibling-module resolution even outside package cwd.
sys.path.insert(0, str(Path(__file__).parents[1]))
spec = importlib.util.spec_from_file_location("tracker", Path(__file__).parents[1] / "codex_usage.py")
t = importlib.util.module_from_spec(spec)
spec.loader.exec_module(t)


def header(session="session-1"):
    return {"type": "session", "version": 3, "id": session}


def change(entry="model", parent=None, **kw):
    return {"type": "model_change", "id": entry, "parentId": parent,
            "provider": "openai-codex", "modelId": "gpt-test", **kw}


def effort(entry="effort", parent="model", value="medium"):
    return {"type": "thinking_level_change", "id": entry, "parentId": parent, "thinkingLevel": value}


def response(entry="response", parent="effort", **kw):
    return {"type": "message", "id": entry, "parentId": parent,
            "message": {"role": "assistant", "provider": "openai-codex", "model": "gpt-test",
                        "timestamp": 1793640000000, "content": "PRIVATE PROMPT RESPONSE",
                        "usage": {"input": 10, "cacheRead": 100, "cacheWrite": 0,
                                  "output": 20, "reasoning": 5, "totalTokens": 130},
                        "stopReason": "toolUse", **kw}}


def quota(**kw):
    return {"plan_type": "pro", "email": "PRIVATE EMAIL", "user_id": "PRIVATE USER",
            "rate_limit": {"allowed": True, "limit_reached": False,
                           "primary_window": {"limit_window_seconds": 604800, "used_percent": 17,
                                              "reset_at": 1794225111}, "secondary_window": None}, **kw}


class TrackerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.env = mock.patch.dict(os.environ, {
            "XDG_CONFIG_HOME": str(self.root / "config"),
            "XDG_DATA_HOME": str(self.root / "data"),
            "XDG_STATE_HOME": str(self.root / "state"),
            "PI_CODING_AGENT_DIR": str(self.root / "config/pi/agent"),
        })
        self.env.start()
        self.directory = self.root / "tracker"
        self.log = self.root / "session.jsonl"

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def write(self, entries, path=None, mode="w"):
        path = path or self.log
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open(mode) as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")

    def test_quota_allowlist_and_secondary_window(self):
        parsed = t.parse_quota(quota(), "PRIVATE ACCOUNT")
        self.assertEqual(parsed[1:], ("pro", 1794225111, 604800, 17, 1, 0))
        self.assertNotIn("PRIVATE", repr(parsed))
        q = quota()
        q["rate_limit"]["secondary_window"] = q["rate_limit"]["primary_window"]
        q["rate_limit"]["primary_window"] = {"limit_window_seconds": 18000, "used_percent": 1}
        self.assertEqual(t.parse_quota(q, "account")[4], 17)

    def test_quota_schema_changes_do_not_become_zero(self):
        for value in (-1, 101, float("nan"), "10", True):
            q = quota()
            q["rate_limit"]["primary_window"]["used_percent"] = value
            with self.assertRaises(ValueError):
                t.parse_quota(q, "account")
        with self.assertRaises(ValueError):
            t.parse_quota(quota(rate_limit={}), "account")

    def test_incremental_skip_and_append(self):
        self.write([header(), change(), effort(), response()])
        with t.database(self.directory) as db:
            one = t.ingest(db, [self.log])
            self.assertEqual(one["imported"], 1)
            self.assertEqual(t.ingest(db, [self.log])["bytes"], 0)
            self.write([response("r2", "response", stopReason="aborted")], mode="a")
            two = t.ingest(db, [self.log])
            self.assertEqual(two["imported"], 1)
            self.assertLess(two["bytes"], one["bytes"])
            row = db.execute("SELECT * FROM requests WHERE status='aborted'").fetchone()
            self.assertEqual(row["effort"], "medium")
            self.assertEqual((row["input"], row["cached"], row["output"], row["reasoning"], row["total"]), (10, 100, 20, 5, 130))

    def test_branch_effort_uses_parent_not_latest_setting(self):
        self.write([header(), change(), effort(), response(), effort("high", "response", "high"),
                    response("high-r", "high"), response("old-branch-r", "effort")])
        with t.database(self.directory) as db:
            t.ingest(db, [self.log])
            rows = db.execute("SELECT effort,COUNT(*) FROM requests GROUP BY effort ORDER BY effort").fetchall()
            self.assertEqual([tuple(r) for r in rows], [("high", 1), ("medium", 2)])

    def test_partial_line_is_retried(self):
        self.write([header(), change(), effort()])
        text = json.dumps(response())
        with self.log.open("a") as f:
            f.write(text[:40])
        with t.database(self.directory) as db:
            self.assertEqual(t.ingest(db, [self.log])["imported"], 0)
            with self.log.open("a") as f:
                f.write(text[40:] + "\n")
            self.assertEqual(t.ingest(db, [self.log])["imported"], 1)

    def test_backfill_budget_resumes_unchanged_file(self):
        self.write([header(), change(), effort(), response(), response("r2", "response")])
        with t.database(self.directory) as db:
            count = t.ingest(db, [self.log], budget=5)
            self.assertEqual(count["backlog"], 1)
            self.assertEqual(t.ingest(db, [self.log])["imported"], 2)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM requests").fetchone()[0], 2)

    def test_truncation_replacement_and_copy_deduplication(self):
        entries = [header(), change(), effort(), response()]
        self.write(entries)
        with t.database(self.directory) as db:
            t.ingest(db, [self.log])
            self.write(entries + [response("r2", "response")])
            self.assertEqual(t.ingest(db, [self.log])["imported"], 1)
            self.log.unlink()
            self.write(entries)
            self.assertEqual(t.ingest(db, [self.log])["imported"], 0)
            copy = self.root / "fork.jsonl"
            self.write([header("fork-1"), *entries[1:]], copy)
            self.assertEqual(t.ingest(db, [copy])["imported"], 0)

    def test_response_id_deduplication(self):
        self.write([header(), change(), effort(), response(responseId="resp-stable"),
                    response("new-id", responseId="resp-stable")])
        with t.database(self.directory) as db:
            self.assertEqual(t.ingest(db, [self.log])["imported"], 1)

    def test_recorded_compaction_and_usage(self):
        r = response()["message"]
        self.write([header(), change(), effort(),
                    {"type": "compaction", "id": "c", "parentId": "effort",
                     "timestamp": "2026-11-02T16:00:00Z", "usage": r["usage"]},
                    {"type": "usage", "id": "u", "parentId": "c", "provider": "openai-codex",
                     "model": "gpt-test", "timestamp": "2026-11-02T16:01:00Z", "usage": r["usage"]}])
        with t.database(self.directory) as db:
            self.assertEqual(t.ingest(db, [self.log])["imported"], 2)

    def test_other_provider_and_user_text_are_not_usage(self):
        self.write([header(), change(), effort(), response(provider="other"),
                    {"type": "message", "id": "u", "parentId": "effort", "message": {"role": "user", "content": "PRIVATE"}}])
        with t.database(self.directory) as db:
            self.assertEqual(t.ingest(db, [self.log])["imported"], 0)

    def test_malformed_and_oversized_lines_are_visible_gaps(self):
        self.write([header(), change(), effort()])
        with self.log.open("ab") as f:
            f.write(b"not json\n" + b"x" * 1000 + b"\n")
        self.write([response()], mode="a")
        with t.database(self.directory) as db, mock.patch.object(t, "MAX_LINE", 600):
            counts = t.ingest(db, [self.log])
            self.assertEqual(counts["issues"], 2)
            self.assertEqual(counts["imported"], 1)

    def test_oversized_line_larger_than_budget_is_skipped_incrementally(self):
        self.write([header(), change(), effort()])
        with self.log.open("ab") as f:
            f.write(b"x" * 5000 + b"\n")
        self.write([response()], mode="a")
        with t.database(self.directory) as db, mock.patch.object(t, "MAX_LINE", 600):
            total_imported = 0
            for _ in range(20):
                result = t.ingest(db, [self.log], budget=1000)
                self.assertLessEqual(result["bytes"], 1601)
                total_imported += result["imported"]
                if not result["backlog"]:
                    break
            self.assertEqual(total_imported, 1)
            self.assertEqual(db.execute("SELECT discarding FROM sources").fetchone()[0], 0)

    def test_interrupted_import_is_not_reported_as_healthy(self):
        with t.database(self.directory) as db:
            db.execute("INSERT INTO snapshots(sampled_at,account,plan,reset_at,duration,used,allowed,reached) VALUES (?,?,?,?,?,?,?,?)",
                       (1793640000, *t.parse_quota(quota(), "account")))
            db.execute("INSERT INTO runs(started_at,quota_status) VALUES (?,?)", (1793640000, "ok"))
            output = io.StringIO()
            with contextlib.redirect_stdout(output), mock.patch.object(t.time, "time", return_value=1793640001):
                t.report(db)
            self.assertIn("unfinished", output.getvalue())
            self.assertIn("has not completed", output.getvalue())
            self.assertNotIn("Collector: ok", output.getvalue())

    def test_sources_are_narrow_and_include_managed_sessions(self):
        agent = self.root / "config/pi/agent"
        project = self.root / "state/project-object/projects/p"
        included = [agent / "sessions/cwd/session.jsonl", project / "pi-sessions/a.jsonl",
                    project / "streams/s/pi-sessions/b.jsonl"]
        excluded = [agent / "sessions.backup/cwd/session.jsonl", project / "worktree/sessions/c.jsonl"]
        for path in included + excluded:
            self.write([header()], path)
        self.assertEqual(set(t.roots()), set(included))

    def test_private_state_and_no_message_or_identity_content(self):
        self.write([header(), change(), effort(), response()])
        with t.database(self.directory) as db:
            t.ingest(db, [self.log])
            db.execute("INSERT INTO snapshots(sampled_at,account,plan,reset_at,duration,used,allowed,reached) VALUES (?,?,?,?,?,?,?,?)",
                       (1793640000, *t.parse_quota(quota(), "PRIVATE ACCOUNT")))
            db.commit()
        self.assertEqual(self.directory.stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.directory / "usage.sqlite").stat().st_mode & 0o777, 0o600)
        self.assertNotIn(b"PRIVATE", (self.directory / "usage.sqlite").read_bytes())

    def test_reject_symlink_state_and_database(self):
        target = self.root / "target"
        target.mkdir()
        self.directory.symlink_to(target)
        with self.assertRaises(ValueError):
            with t.database(self.directory):
                pass
        self.directory.unlink()
        self.directory.mkdir()
        (self.directory / "usage.sqlite").symlink_to(target / "database")
        with self.assertRaises(ValueError):
            with t.database(self.directory):
                pass

    def test_report_boundaries_and_staleness(self):
        with t.database(self.directory) as db:
            db.execute("INSERT INTO snapshots(sampled_at,account,plan,reset_at,duration,used,allowed,reached) VALUES (?,?,?,?,?,?,?,?)",
                       (1793640000, *t.parse_quota(quota(), "account")))
            output = io.StringIO()
            with contextlib.redirect_stdout(output), mock.patch.object(t.time, "time", return_value=1793640000+8000):
                t.report(db, "2026-10-26")
                t.history(db)
            text = output.getvalue()
            self.assertIn("stale", text)
            self.assertIn("at least 17%", text)
            self.assertIn("2026-11-02 00:00 UTC (end exclusive)", text)
            self.assertNotIn("unused", text)

    def test_refresh_collects_once_and_reports_new_data(self):
        self.write([header(), change(), effort(), response()])
        output = io.StringIO()
        with mock.patch.object(t.sys, "argv", ["codex-usage", "refresh"]), \
                mock.patch.object(t, "fetch_quota", return_value=(t.parse_quota(quota(), "account"), "ok")) as fetch, \
                mock.patch.object(t, "roots", return_value=[self.log]), \
                contextlib.redirect_stdout(output):
            self.assertEqual(t.main(), 0)
        fetch.assert_called_once_with()
        self.assertIn("17% used", output.getvalue())
        self.assertIn("gpt-test / medium", output.getvalue())
        with t.database(t.state_dir(), readonly=True) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM requests").fetchone()[0], 1)

    def test_refresh_failure_returns_failure_and_labels_saved_report(self):
        output = io.StringIO()
        with mock.patch.object(t.sys, "argv", ["codex-usage", "refresh"]), \
                mock.patch.object(t, "fetch_quota", return_value=(None, "network_error")), \
                mock.patch.object(t, "roots", return_value=[]), contextlib.redirect_stdout(output):
            self.assertEqual(t.main(), 1)
        self.assertIn("refresh incomplete", output.getvalue())
        self.assertIn("No successful quota snapshots", output.getvalue())

    def test_refresh_does_not_claim_success_when_collection_is_locked(self):
        with mock.patch.object(t.sys, "argv", ["codex-usage", "refresh"]), \
                mock.patch.object(t, "collect", return_value=None) as collect, \
                mock.patch.object(t, "report") as report:
            self.assertEqual(t.main(), 1)
        collect.assert_called_once_with(t.state_dir())
        report.assert_not_called()

    def test_plain_report_remains_offline(self):
        with t.database(t.state_dir()):
            pass
        with mock.patch.object(t.sys, "argv", ["codex-usage"]), \
                mock.patch.object(t, "collect") as collect, \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(t.main(), 0)
        collect.assert_not_called()

    def test_expired_auth_never_refreshes_or_writes(self):
        path = self.root / "auth.json"
        content = json.dumps({"openai-codex": {"access": "PRIVATE TOKEN", "accountId": "account", "expires": 1}})
        path.write_text(content)
        with mock.patch.object(t.urllib.request, "build_opener") as opener:
            self.assertEqual(t.fetch_quota(path), (None, "auth_expired"))
            opener.assert_not_called()
        self.assertEqual(path.read_text(), content)

    def test_http_failure_is_sanitized_and_local_import_continues(self):
        path = self.root / "auth.json"
        path.write_text(json.dumps({"openai-codex": {"access": "PRIVATE TOKEN", "accountId": "account", "expires": 9999999999999}}))
        error = urllib.error.HTTPError("url", 401, "PRIVATE BODY", {}, None)
        with mock.patch.object(t.urllib.request, "build_opener") as opener:
            opener.return_value.open.side_effect = error
            self.assertEqual(t.fetch_quota(path), (None, "auth_expired"))
        self.write([header(), change(), effort(), response()])
        with mock.patch.object(t, "fetch_quota", return_value=(None, "network_error")), mock.patch.object(t, "roots", return_value=[self.log]), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(t.collect(self.directory), 1)
        with t.database(self.directory, readonly=True) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM requests").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT quota_status FROM runs").fetchone()[0], "network_error")


if __name__ == "__main__":
    unittest.main()
