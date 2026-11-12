"""Offline project/stream reporting regression tests; synthetic private records only."""
import contextlib
import io
import json
import os
import unittest
from unittest import mock
import test_tracker as fixtures
from test_tracker import t, header, change, effort, response


class AttributionTests(unittest.TestCase):
    setUp = fixtures.TrackerTests.setUp
    tearDown = fixtures.TrackerTests.tearDown
    write = fixtures.TrackerTests.write
    pid = "11111111-1111-4111-8111-111111111111"
    sid = "22222222-2222-4222-8222-222222222222"

    def project_log(self, pid=None, sid=None, filename="session.jsonl"):
        root = self.root / "state/project-object/projects" / (pid or self.pid)
        return (root / "streams" / sid if sid else root) / "pi-sessions" / filename

    def registry(self):
        root = self.root / "data/project-object"
        (root / "projects" / self.pid).mkdir(parents=True)
        (root / "projects.json").write_text(json.dumps({"projects": [
            {"id": self.pid, "name": "Example\u001b project", "archivedAt": "2026-11-01"}]}))
        (root / "projects" / self.pid / "streams.json").write_text(json.dumps({"streams": [
            {"id": self.sid, "name": "Example stream", "archivedAt": "2026-11-01"}]}))

    def test_rollups_fallback_compaction_and_readonly(self):
        self.registry()
        main = self.project_log()
        stream = self.project_log(sid=self.sid)
        self.write([header(), change(), effort(), response(responseId="main")], main)
        usage = response()["message"]["usage"]
        self.write([header("stream-session"), change(), effort(),
                    response(responseId="stream"),
                    {"type": "compaction", "id": "c", "parentId": "effort",
                     "timestamp": 1793640000000, "usage": usage},
                    {"type": "usage", "id": "u", "parentId": "effort",
                     "timestamp": 1793640000000, "usage": usage}], stream)
        with t.database(self.directory) as db:
            t.ingest(db, [main, stream])
        before = (self.directory / "usage.sqlite").read_bytes()
        with t.database(self.directory, readonly=True) as db:
            result = t.attribution(db, 1793640000, 1793640001)
            self.assertEqual(result["groups"], {(self.pid, None): [1, 20, 0],
                                                (self.pid, self.sid): [3, 60, 0]})
            self.assertEqual((result["calls"], result["matched_calls"], result["output"]), (4, 4, 80))
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                t.report_attribution(db, 1793640000, 1793640001, True)
            text = output.getvalue()
            self.assertIn("Example project | 4 | 80 | 100.00%", text)
            self.assertIn("Example project / Example stream | 3 | 60 | 75.00%", text)
            self.assertIn("4/4 calls matched", text)
            self.assertNotIn("PRIVATE", text)
            self.assertNotIn("\u001b", text)
        self.assertEqual((self.directory / "usage.sqlite").read_bytes(), before)

    def test_duplicates_conflicts_and_unattached(self):
        a, b = self.project_log(), self.project_log(filename="copy.jsonl")
        c = self.project_log(sid=self.sid)
        self.write([header(), change(), response(responseId="stable")], a)
        self.write([header("fork"), change(), response("copy", responseId="stable")], b)
        self.write([header(), change(), response(responseId="other")], self.log)
        with t.database(self.directory) as db:
            t.ingest(db, [a, b, self.log])
            result = t.attribution(db, 1793640000, 1793640001)
            self.assertEqual(result["groups"][(self.pid, None)][0], 1)
            self.assertEqual(result["groups"][(None, None)][0], 1)
            self.write([header("another"), change(), response("duplicate", responseId="stable")], c)
            t.ingest(db, [c])
            result = t.attribution(db, 1793640000, 1793640001)
            self.assertEqual(result["groups"][("ambiguous", None)], [1, 20, 0])
            self.assertEqual(result["matched_calls"], 1)
            self.assertEqual(result["calls"], 2)

    def test_collector_rejected_copies_cannot_supply_ownership(self):
        original = self.project_log()
        self.write([header(), change(), response(responseId="stable")], original)
        no_id = response(responseId="stable")
        del no_id["id"]
        copies = [
            [response(responseId="stable")],  # no session
            [header("copy1"), change(), no_id],
            [header("copy2"), change(), response(parent="model", responseId="stable", provider=None)],
            [header("copy3"), change(), response(parent="model", responseId="stable", model=None)],
        ]
        with t.database(self.directory) as db:
            t.ingest(db, [original])
            for i, entries in enumerate(copies):
                path = self.project_log(sid=self.sid, filename=f"rejected-{i}.jsonl")
                self.write(entries, path)
                self.assertEqual(t.ingest(db, [path])["imported"], 0)
            result = t.attribution(db, 1793640000, 1793640001)
            self.assertEqual(result["groups"], {(self.pid, None): [1, 20, 0]})
            original.unlink()
            result = t.attribution(db, 1793640000, 1793640001)
            self.assertEqual(result["groups"], {("unmatched", None): [1, 20, 0]})

    def test_deleted_symlink_and_unmatched_denominator(self):
        a = self.project_log()
        self.write([header(), change(), response(responseId="missing")], a)
        self.write([header(), change(), response(responseId="present")], self.log)
        with t.database(self.directory) as db:
            t.ingest(db, [a, self.log])
            a.unlink()
            result = t.attribution(db, 1793640000, 1793640001)
            self.assertEqual(result["groups"][("unmatched", None)], [1, 20, 0])
            self.assertEqual((result["matched_output"], result["output"]), (20, 40))
            self.assertEqual(result["issues"], 1)
            a.symlink_to(self.log)
            self.assertEqual(t.attribution(db, 1793640000, 1793640001)["issues"], 1)

    def test_bounds_empty_zero_output_and_missing_values(self):
        self.write([header(), change(), response(usage={"output": 0}, responseId="zero"),
                    response("missing", usage={}, responseId="missing")])
        with t.database(self.directory) as db:
            t.ingest(db, [self.log])
            for kwargs in ({"budget": 1}, {"seconds": 0}):
                result = t.attribution(db, 1793640000, 1793640001, **kwargs)
                self.assertTrue(result["limited"])
                self.assertLessEqual(result["bytes"], kwargs.get("budget", 0))
                self.assertEqual(result["matched_calls"], 0)
            self.assertEqual(t.attribution(db, 1793640001, 1793640002)["calls"], 0)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                t.report_attribution(db, 1793640000, 1793640001)
            self.assertIn("N/A", output.getvalue())
            self.assertIn("output values are unknown", output.getvalue())

    def test_malformed_oversized_and_appended_records(self):
        self.write([header(), change(), response(responseId="known")])
        with t.database(self.directory) as db:
            t.ingest(db, [self.log])
            # Bytes appended after the import snapshot must not be read.
            self.write([response(responseId="unimported")], mode="a")
            self.assertEqual(t.attribution(db, 1793640000, 1793640001)["calls"], 1)
            with self.log.open("ab") as f:
                f.write(b"invalid\n" + b"x" * 1500 + b"\n")
            t.ingest(db, [self.log])
            with mock.patch.object(t, "MAX_LINE", 1000):
                result = t.attribution(db, 1793640000, 1793640001)
            self.assertEqual(result["matched_calls"], 2)
            self.assertEqual(result["issues"], 2)

    def test_replaced_and_truncated_source_bytes_are_not_attributed(self):
        a = self.project_log()
        entries = [header(), change(), response(responseId="stable")]
        self.write(entries, a)
        with t.database(self.directory) as db:
            t.ingest(db, [a])
            a.rename(a.with_suffix(".old"))
            self.write(entries, a)  # same identities, different file: not imported
            result = t.attribution(db, 1793640000, 1793640001)
            self.assertEqual(result["matched_calls"], 0)
            self.assertEqual(result["issues"], 1)
            t.ingest(db, [a])
            a.write_text("")  # same inode but imported bytes are gone
            result = t.attribution(db, 1793640000, 1793640001)
            self.assertEqual(result["matched_calls"], 0)
            self.assertEqual(result["issues"], 1)

    def test_report_releases_snapshot_before_scan_and_keeps_frozen_totals(self):
        self.write([header(), change(), response(responseId="stable")])
        with t.database(self.directory) as db:
            t.ingest(db, [self.log])
        with t.database(self.directory, readonly=True) as db:
            original = t.report_attribution
            def scan(db, since, until, all_streams=False, snapshot=None):
                self.assertFalse(db.in_transaction)
                # Collector commits must work during scanning, not wait for its end.
                with t.database(self.directory) as writer:
                    writer.execute("INSERT INTO runs(started_at,quota_status) VALUES (1,'local_only')")
                    writer.commit()
                self.assertEqual(len(snapshot[0]), 1)
                return original(db, since, until, all_streams, snapshot=snapshot)
            with mock.patch.object(t, "report_attribution", side_effect=scan), \
                    contextlib.redirect_stdout(io.StringIO()):
                t.report(db, "2026-11-02")

    def test_registry_unknown_and_path_containment(self):
        self.registry()
        self.assertEqual(t.source_scope(self.project_log(sid=self.sid)), (self.pid, self.sid))
        self.assertEqual(t.source_scope(self.root / self.pid / "pi-sessions/session.jsonl"), (None, None))
        root = self.root / "data/project-object"
        (root / "projects.json").write_text('{"projects":[{"id":"../outside"}]}')
        projects, streams, issues = t.scope_names()
        self.assertEqual(projects, {})
        self.assertEqual(issues, 1)
        self.assertEqual(streams, {})

    def test_all_streams_cli_and_remainder(self):
        groups = {(self.pid, f"stream-{i}"): [1, i, 0] for i in range(15)}
        result = {"groups": groups, "calls": 15, "output": 105, "matched_calls": 15,
                  "matched_output": 105, "issues": 0, "limited": False}
        with t.database(t.state_dir()) as db, mock.patch.object(t, "attribution", return_value=result), \
                mock.patch.object(t, "scope_names", return_value=({self.pid: "Project"}, {}, 0)):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                t.report_attribution(db, 0, 1)
            self.assertIn("Remaining 3 streams/buckets", output.getvalue())
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                t.report_attribution(db, 0, 1, True)
            self.assertNotIn("Remaining", output.getvalue())
            self.assertIn("stream-0", output.getvalue())
        for argv in (["codex-usage", "--all-streams"], ["codex-usage", "status", "--all-streams"],
                     ["codex-usage", "week", "--start", "2026-11-02", "--all-streams"],
                     ["codex-usage", "refresh", "--all-streams"]):
            with mock.patch.object(t.sys, "argv", argv), mock.patch.object(t, "report") as report, \
                    mock.patch.object(t, "collect", return_value=0):
                self.assertEqual(t.main(), 0)
                self.assertTrue(report.call_args.kwargs.get("all_streams", report.call_args.args[-1]))


if __name__ == "__main__":
    unittest.main()
