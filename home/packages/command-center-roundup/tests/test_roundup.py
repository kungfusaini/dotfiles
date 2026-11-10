import datetime as dt
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid

spec = importlib.util.spec_from_file_location("roundup", Path(__file__).parents[1] / "roundup.py")
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


class RoundupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.pid, self.sid = str(uuid.uuid4()), str(uuid.uuid4())
        self.home = self.source / "projects" / self.pid
        self.stream = self.home / "streams" / self.sid
        self.stream.mkdir(parents=True)
        self.write(self.source / "projects.json", {"version": 1, "projects": [{"id": self.pid, "name": "Project", "archivedAt": "yesterday"}]})
        self.write(self.home / "streams.json", {"version": 1, "streams": [{"id": self.sid, "name": "Factory", "archivedAt": "yesterday"}]})
        self.log = self.home / "worklogs/events.jsonl"
        self.slog = self.stream / "worklogs/events.jsonl"
        self.events(self.log, [self.event("2026-11-03T10:00:00Z", "Classified a personal bill; this is not evidence of unfinished reconciliation.")])
        self.events(self.slog, [self.event("2026-11-03T11:00:00Z", "Factory safeguards committed, not deployed.", stream=True)])
        self.config = {"sourceRoot": str(self.source), "archiveRoot": str(self.root / "archive"), "stateRoot": str(self.root / "state"), "firstDate": "2026-11-03", "timezone": "Europe/London", "model": "test-model", "piBin": "unused", "agentDir": str(self.root / "agent"), "notifyBin": "notify", "busBin": "bus"}
        self.now = dt.datetime(2026, 11, 4, 12, tzinfo=r.UTC)
        self.calls, self.notices = [], []

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value) + "\n")
        path.chmod(0o600)

    def events(self, path, values):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(v) + "\n" for v in values))
        path.chmod(0o600)

    def event(self, time, summary, stream=False):
        e = {"time": time, "project": self.pid, "scope": "stream" if stream else "project", "summary": summary, "type": "finish"}
        if stream:
            e["stream"] = {"id": self.sid, "name": "Factory"}
        return e

    def draft(self, events):
        return {"overview": "Recorded achievements, not a fresh audit.", "sections": [{"title": "Project", "items": [{"text": e["summary"], "sources": [e["id"]]} for e in events]}], "unfinished": []}

    def model(self, stage, payload):
        self.calls.append((stage, payload))
        return self.draft(payload["events"]) if stage == "draft" else {"verdict": "pass", "issues": []}

    def notify(self, config, title, body):
        self.notices.append((title, body))
        return True

    def run_job(self, **kwargs):
        return r.run(self.config, now=kwargs.pop("now", self.now), model=kwargs.pop("model", self.model), notifier=kwargs.pop("notifier", self.notify), **kwargs)

    def test_archived_scopes_and_precise_provenance(self):
        events, sources = r.collect(self.source, self.now.date() - dt.timedelta(days=1), "Europe/London")
        self.assertEqual(len(events), 2)
        self.assertEqual(len(sources), 2)
        self.assertEqual(sources[0]["events"][0]["line"], 1)
        self.assertEqual(len(sources[0]["events"][0]["sha256"]), 64)

    def test_normal_publish_and_idempotent_no_extra_calls(self):
        self.assertEqual(self.run_job()["published"], ["2026-11-03"])
        self.assertEqual([x[0] for x in self.calls], ["draft", "review"])
        path = r.day_path(Path(self.config["archiveRoot"]), dt.date(2026, 11, 3))
        self.assertTrue((path / "roundup.md").is_file())
        self.assertEqual(r.read_json(path / "sources.json")["automated_review"]["passes"], 1)
        self.assertEqual(self.run_job()["published"], [])
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(len(self.notices), 1)

    def test_manual_roundup_preserved_and_not_notified(self):
        day = dt.date(2026, 11, 3)
        r.publish(Path(self.config["archiveRoot"]), day, "Original user-reviewed account", {"date": str(day)})
        self.run_job()
        self.assertFalse(self.calls)
        self.assertFalse(self.notices)
        self.assertEqual((r.day_path(Path(self.config["archiveRoot"]), day) / "roundup.md").read_text(), "Original user-reviewed account")

    def test_review_corrects_known_finance_regression(self):
        def model(stage, payload):
            self.calls.append(stage)
            if stage == "review":
                return {"verdict": "revise", "issues": ["No evidence reconciliation is unfinished"]} if len(self.calls) == 2 else {"verdict": "pass", "issues": []}
            draft = self.draft(payload["events"])
            if "previous_draft" not in payload:
                draft["sections"][0]["items"][0]["text"] = "Reconciliation remains unfinished."
            return draft
        self.assertEqual(self.run_job(model=model)["status"], "ok")
        self.assertEqual(self.calls, ["draft", "review", "draft", "review"])
        text = (r.day_path(Path(self.config["archiveRoot"]), dt.date(2026, 11, 3)) / "roundup.md").read_text()
        self.assertNotIn("Reconciliation remains unfinished", text)

    def test_unresolved_review_never_published(self):
        def model(stage, payload):
            return self.draft(payload["events"]) if stage == "draft" else {"verdict": "revise", "issues": ["Unsupported claim E00001"]}
        result = self.run_job(model=model)
        self.assertEqual(result["status"], "pending")
        self.assertFalse(r.day_path(Path(self.config["archiveRoot"]), dt.date(2026, 11, 3)).exists())
        self.assertTrue((Path(self.config["stateRoot"]) / "pending/2026-11-03/review.json").is_file())
        self.assertEqual(self.notices[0][0], "Daily roundup needs attention")

    def test_retry_throttle_and_recovery(self):
        def failed(stage, payload):
            raise r.Problem("codex_unavailable")
        self.run_job(model=failed)
        self.assertEqual(self.run_job()["published"], [])
        self.assertFalse(self.calls)
        result = self.run_job(now=self.now + dt.timedelta(hours=2))
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["published"], ["2026-11-03"])

    def test_quality_retry_two_minutes_and_stops_at_daily_budget(self):
        def rejected(stage, payload):
            self.calls.append(stage)
            return self.draft(payload["events"]) if stage == "draft" else {"verdict": "revise", "issues": ["Explain the internal test name E00002"]}
        first = self.run_job(model=rejected)
        self.assertEqual(first["failure_reasons"], {"2026-11-03": "draft_needs_review"})
        state = r.read_json(Path(self.config["stateRoot"]) / "state.json")
        self.assertEqual(state["failures"]["2026-11-03"]["retry_after"], self.now.timestamp() + 120)
        self.assertTrue(r.fast_retry_pending(state, self.now, "Europe/London"))
        self.run_job(model=rejected, now=self.now + dt.timedelta(seconds=119))
        self.assertEqual(len(self.calls), 4)
        self.run_job(model=rejected, now=self.now + dt.timedelta(seconds=120))
        self.assertEqual(len(self.calls), 8)
        self.run_job(model=rejected, now=self.now + dt.timedelta(seconds=240))
        self.run_job(model=rejected, now=self.now + dt.timedelta(seconds=360))
        self.assertEqual(len(self.calls), 12)
        state = r.read_json(Path(self.config["stateRoot"]) / "state.json")
        self.assertFalse(r.fast_retry_pending(state, self.now, "Europe/London"))
        self.assertEqual(len(self.notices), 1)

    def test_backoff_starts_at_failure_completion_not_job_start(self):
        end = self.now + dt.timedelta(minutes=5)
        for code, delay in [("invalid_model_json", 120), ("codex_unavailable", 3600)]:
            with self.subTest(code=code):
                state_path = Path(self.config["stateRoot"]) / "state.json"
                state_path.unlink(missing_ok=True)
                def failed(stage, payload):
                    raise r.Problem(code)
                self.run_job(model=failed, clock=lambda: end)
                state = r.read_json(state_path)
                self.assertEqual(state["failures"]["2026-11-03"]["retry_after"], end.timestamp() + delay)
                self.assertEqual(state["history"][-1]["finished_at"], r.iso_now(end))

    def test_network_deadline_survives_local_midnight(self):
        def failed(stage, payload):
            raise r.Problem("codex_unavailable")
        late = dt.datetime(2026, 11, 4, 23, 50, tzinfo=r.UTC)
        self.run_job(model=failed, now=late)
        self.run_job(now=late + dt.timedelta(minutes=20))
        self.assertFalse(self.calls)
        self.assertEqual(self.run_job(now=late + dt.timedelta(hours=1))["published"][0], "2026-11-03")

    def test_attempt_history_survives_later_success(self):
        def rejected(stage, payload):
            return self.draft(payload["events"]) if stage == "draft" else {"verdict": "revise", "issues": ["Unsupported claim E00001"]}
        self.run_job(model=rejected)
        self.run_job(now=self.now + dt.timedelta(minutes=2))
        state = r.read_json(Path(self.config["stateRoot"]) / "state.json")
        self.assertFalse(state["failures"])
        self.assertEqual([h["status"] for h in state["history"]], ["failed", "published"])
        self.assertEqual(state["history"][0]["code"], "draft_needs_review")
        self.assertEqual(state["history"][0]["reviews"][1]["issues"], ["Unsupported claim E00001"])
        self.assertEqual(state["history"][1]["reviews"][0]["verdict"], "pass")

    def test_attempt_history_is_bounded_and_private(self):
        state_path = Path(self.config["stateRoot"]) / "state.json"
        old = {"version": 1, "failures": {}, "notified": [], "history": [{"id": str(i), "status": "published"} for i in range(100)]}
        r.save_json(state_path, old)
        self.run_job()
        state = r.read_json(state_path)
        self.assertEqual(len(state["history"]), 90)
        self.assertEqual(stat.S_IMODE(state_path.stat().st_mode), 0o600)
        self.assertEqual(state["history"][0]["id"], "11")

    def test_private_review_history_masks_obvious_secrets(self):
        value = "sk-" + "A" * 40
        def rejected(stage, payload):
            return self.draft(payload["events"]) if stage == "draft" else {"verdict": "revise", "issues": [value]}
        self.run_job(model=rejected)
        state = r.read_json(Path(self.config["stateRoot"]) / "state.json")
        self.assertNotIn(value, json.dumps(state["history"]))
        self.assertEqual(state["history"][0]["reviews"][0]["issues"], ["Private review detail withheld"])
        self.assertNotIn(value, json.dumps(self.notices))

    def test_schedule_retry_arms_then_stops_without_permanent_polling(self):
        def rejected(stage, payload):
            raise r.Problem("invalid_model_json")
        self.run_job(model=rejected)
        self.config["systemctlBin"] = "systemctl"
        class Reply:
            returncode = 0
        with patch.object(r.subprocess, "run", return_value=Reply()) as call:
            self.assertEqual(r.schedule_retry(self.config), {"fast_retry_timer": "armed"})
            self.assertIn("restart", call.call_args.args[0])
            self.assertIn("--no-block", call.call_args.args[0])
        self.run_job(now=self.now + dt.timedelta(minutes=2))
        with patch.object(r.subprocess, "run", return_value=Reply()) as call:
            self.assertEqual(r.schedule_retry(self.config), {"fast_retry_timer": "stopped"})
            self.assertIn("stop", call.call_args.args[0])

    def test_fast_timer_not_rearmed_if_attempt_cannot_advance(self):
        def failed(stage, payload):
            raise r.Problem("invalid_model_json")
        self.run_job(model=failed)
        self.config["systemctlBin"] = "systemctl"
        class Reply:
            returncode = 0
        with patch.object(r.subprocess, "run", return_value=Reply()) as call:
            self.assertEqual(r.schedule_retry(self.config)["fast_retry_timer"], "armed")
            self.assertIn("restart", call.call_args.args[0])
        original = r.directory
        def inaccessible(path, create=False):
            if Path(path) == Path(self.config["archiveRoot"]):
                raise PermissionError("archive unavailable")
            return original(path, create)
        with patch.object(r, "directory", side_effect=inaccessible):
            with self.assertRaises(PermissionError):
                self.run_job(now=self.now + dt.timedelta(minutes=3))
        for _ in range(3):
            with patch.object(r.subprocess, "run", return_value=Reply()) as call:
                self.assertEqual(r.schedule_retry(self.config)["fast_retry_timer"], "stopped")
                self.assertIn("stop", call.call_args.args[0])
        state = r.read_json(Path(self.config["stateRoot"]) / "state.json")
        self.assertEqual(state["failures"]["2026-11-03"]["attempts"], 1)
        self.assertEqual(len(state["fast_retry_scheduled"]), 1)

    def test_schedule_reservation_failure_does_not_arm_timer(self):
        def failed(stage, payload):
            raise r.Problem("invalid_model_json")
        self.run_job(model=failed)
        self.config["systemctlBin"] = "systemctl"
        class Reply:
            returncode = 0
        with patch.object(r, "save_json", side_effect=OSError("disk full")), patch.object(r.subprocess, "run", return_value=Reply()) as call:
            with self.assertRaises(OSError):
                r.schedule_retry(self.config)
            self.assertEqual(call.call_count, 1)
            self.assertIn("stop", call.call_args.args[0])

    def test_repeated_stop_hook_does_not_cancel_not_yet_due_retry(self):
        def failed(stage, payload):
            raise r.Problem("invalid_model_json")
        self.run_job(model=failed)
        self.config["systemctlBin"] = "systemctl"
        state_path = Path(self.config["stateRoot"]) / "state.json"
        state = r.read_json(state_path)
        state["failures"]["2026-11-03"]["retry_after"] = dt.datetime.now(r.UTC).timestamp() + 120
        r.save_json(state_path, state)
        class Reply:
            returncode = 0
        with patch.object(r.subprocess, "run", return_value=Reply()):
            self.assertEqual(r.schedule_retry(self.config)["fast_retry_timer"], "armed")
        Reply.stdout = b"waiting\n"
        with patch.object(r.subprocess, "run", return_value=Reply()) as call:
            self.assertEqual(r.schedule_retry(self.config), {"fast_retry_timer": "unchanged", "reason": "timer_still_waiting"})
            self.assertEqual(call.call_count, 1)
            self.assertIn("show", call.call_args.args[0])

    def test_delayed_dispatch_uses_actual_timer_state_not_old_failure_deadline(self):
        def failed(stage, payload):
            raise r.Problem("invalid_model_json")
        self.run_job(model=failed)
        self.config["systemctlBin"] = "systemctl"
        class Reply:
            returncode = 0
            stdout = b"waiting\n"
        # The fixture failure is in the past; a long backfill delayed dispatch.
        with patch.object(r.subprocess, "run", return_value=Reply()):
            self.assertEqual(r.schedule_retry(self.config)["fast_retry_timer"], "armed")
        with patch.object(r.subprocess, "run", return_value=Reply()) as call:
            self.assertEqual(r.schedule_retry(self.config)["fast_retry_timer"], "unchanged")
            self.assertEqual(call.call_count, 1)
            self.assertIn("show", call.call_args.args[0])

    def test_completed_review_survives_interrupted_correction(self):
        calls = []
        def model(stage, payload):
            calls.append(stage)
            if stage == "review":
                return {"verdict": "revise", "issues": ["First completed critique E00001"]}
            if len(calls) > 1:
                raise KeyboardInterrupt()
            return self.draft(payload["events"])
        with self.assertRaises(KeyboardInterrupt):
            self.run_job(model=model)
        state = r.read_json(Path(self.config["stateRoot"]) / "state.json")
        entry = state["history"][0]
        self.assertEqual(entry["status"], "started")
        self.assertNotIn("finished_at", entry)
        self.assertEqual(entry["reviews"], [{"verdict": "revise", "issues": ["First completed critique E00001"]}])
        self.run_job()
        state = r.read_json(Path(self.config["stateRoot"]) / "state.json")
        self.assertEqual(state["history"][0]["status"], "interrupted")
        self.assertEqual(state["history"][0]["reviews"], entry["reviews"])

    def test_service_failure_does_not_arm_fast_timer(self):
        def failed(stage, payload):
            raise r.Problem("codex_unavailable")
        self.run_job(model=failed)
        state = r.read_json(Path(self.config["stateRoot"]) / "state.json")
        self.assertFalse(r.fast_retry_pending(state, self.now, "Europe/London"))
        self.assertEqual(state["history"][0]["retry_delay_seconds"], 3600)

    def test_three_failed_attempts_per_local_day(self):
        def failed(stage, payload):
            self.calls.append(stage)
            raise r.Problem("codex_failed")
        for hours in (0, 2, 4, 6):
            self.run_job(model=failed, now=self.now + dt.timedelta(hours=hours))
        self.assertEqual(len(self.calls), 3)
        self.assertEqual(len(self.notices), 1)
        self.run_job(model=failed, now=self.now + dt.timedelta(days=1))
        # The older date is eligible for retry on a new local day.
        self.assertGreater(len(self.calls), 3)

    def test_multiday_backfill_bounded_and_combined_notification(self):
        self.config["firstDate"] = "2026-11-01"
        base = self.event("2026-11-01T10:00:00Z", "One")
        self.events(self.log, [base, {**base, "time": "2026-11-02T10:00:00Z"}, {**base, "time": "2026-11-03T10:00:00Z"}])
        result = self.run_job(now=self.now + dt.timedelta(days=2))
        self.assertEqual(result["published"], ["2026-11-01", "2026-11-02", "2026-11-03"])
        self.assertEqual(len(self.notices), 1)
        self.assertIn("3 days", self.notices[0][1])

    def test_empty_day_no_model_no_notification(self):
        self.config["firstDate"] = "2026-11-02"
        result = self.run_job(now=dt.datetime(2026, 11, 3, 12, tzinfo=r.UTC))
        self.assertEqual(result["published"], ["2026-11-02"])
        self.assertFalse(self.calls)
        self.assertFalse(self.notices)
        text = (r.day_path(Path(self.config["archiveRoot"]), dt.date(2026, 11, 2)) / "roundup.md").read_text()
        self.assertIn("does not mean no work happened", text)

    def test_before_0015_never_publishes_just_closed_day(self):
        self.assertEqual(self.run_job(now=dt.datetime(2026, 11, 4, 0, 10, tzinfo=r.UTC))["published"], [])
        self.assertEqual(self.run_job(now=dt.datetime(2026, 11, 4, 0, 15, tzinfo=r.UTC))["published"], ["2026-11-03"])

    def test_summer_timezone_and_dst_boundaries(self):
        self.events(self.log, [self.event("2026-07-01T23:30:00Z", "Belongs to July 2 London")])
        self.assertEqual(len(r.collect(self.source, dt.date(2026, 7, 2), "Europe/London")[0]), 1)
        self.assertEqual(len(r.collect(self.source, dt.date(2026, 7, 1), "Europe/London")[0]), 0)
        self.events(self.log, [self.event("2026-10-25T00:30:00Z", "First 01:30"), self.event("2026-10-25T01:30:00Z", "Second 01:30")])
        self.assertEqual(len(r.collect(self.source, dt.date(2026, 10, 25), "Europe/London")[0]), 2)

    def test_notification_deferred_then_recovered_after_restart(self):
        self.run_job(notifier=lambda *_: False)
        state = r.read_json(Path(self.config["stateRoot"]) / "state.json")
        self.assertEqual(state["notified"], [])
        self.run_job()
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(len(self.notices), 1)
        self.run_job()
        self.assertEqual(len(self.notices), 1)

    def test_crash_gap_notification_derived_from_published_manifest(self):
        self.run_job(notifier=lambda *_: False)
        (Path(self.config["stateRoot"]) / "state.json").unlink()
        self.run_job()
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(len(self.notices), 1)

    def test_changed_sources_not_published(self):
        def model(stage, payload):
            if stage == "review":
                self.events(self.log, [self.event("2026-11-03T10:00:00Z", "Changed")])
                return {"verdict": "pass", "issues": []}
            return self.draft(payload["events"])
        self.assertEqual(self.run_job(model=model)["status"], "pending")
        self.assertEqual(r.read_json(Path(self.config["stateRoot"]) / "state.json")["failures"]["2026-11-03"]["code"], "sources_changed_retry")

    def test_bad_citations_or_missing_scope_rejected(self):
        events, _ = r.collect(self.source, dt.date(2026, 11, 3), "Europe/London")
        draft = self.draft(events)
        draft["sections"][0]["items"][0]["sources"] = ["E99999"]
        with self.assertRaisesRegex(r.Problem, "invalid_citation"):
            r.validate_draft(draft, events)
        draft = self.draft(events[:1])
        with self.assertRaisesRegex(r.Problem, "missing_workstream"):
            r.validate_draft(draft, events)

    def test_invalid_draft_and_review_schemas(self):
        for draft in ([], {}, {"overview": "x", "sections": [], "unfinished": []}):
            with self.assertRaises(r.Problem):
                r.validate_draft(draft, [])
        for review in ({"verdict": "pass", "issues": ["x"]}, {"verdict": "revise", "issues": []}, {"verdict": "unknown", "issues": []}, []):
            with self.assertRaises(r.Problem):
                r.validate_review(review)

    def test_malformed_and_partial_worklogs_fail_closed(self):
        for content in ('{"time":', '[]\n', '{"time":"no"}\n', '{"time":"2026-11-03T12:00:00"}\n'):
            self.log.write_text(content)
            with self.assertRaises(r.Problem):
                r.collect(self.source, dt.date(2026, 11, 3), "Europe/London")

    def test_wrong_source_scope_rejected(self):
        event = self.event("2026-11-03T10:00:00Z", "Wrong")
        event["project"] = str(uuid.uuid4())
        self.events(self.log, [event])
        with self.assertRaisesRegex(r.Problem, "scope_mismatch"):
            r.collect(self.source, dt.date(2026, 11, 3), "Europe/London")

    def test_possible_secrets_stop_before_model_call(self):
        self.events(self.log, [self.event("2026-11-03T10:00:00Z", "sk-" + "A" * 40)])
        self.assertEqual(self.run_job()["status"], "pending")
        self.assertFalse(self.calls)
        self.assertNotIn("sk-", json.dumps(self.notices))

    def test_large_day_reaches_draft_and_review_without_truncation(self):
        summaries = [f"Recorded achievement {i}: " + "Completed work. " * 700 for i in range(40)]
        self.events(self.log, [self.event("2026-11-03T10:00:00Z", text) for text in summaries])
        events, sources = r.collect(self.source, dt.date(2026, 11, 3), "Europe/London")
        self.assertGreater(len(json.dumps(events, ensure_ascii=False).encode("utf-8")), 400_000)
        self.assertEqual([e["summary"] for e in events[:-1]], summaries)
        self.assertEqual(sum(len(s["events"]) for s in sources), 41)
        def model(stage, payload):
            self.calls.append((stage, payload))
            if stage == "review":
                return {"verdict": "pass", "issues": []}
            return {"overview": "Recorded achievements.", "sections": [{"title": "Project", "items": [
                {"text": "Completed the recorded work.", "sources": [e["id"] for e in payload["events"]]}
            ]}], "unfinished": []}
        self.assertEqual(self.run_job(model=model)["published"], ["2026-11-03"])
        self.assertEqual([stage for stage, _ in self.calls], ["draft", "review"])
        for _, payload in self.calls:
            self.assertEqual(payload["events"], events)
        path = r.day_path(Path(self.config["archiveRoot"]), dt.date(2026, 11, 3))
        self.assertEqual(r.read_json(path / "sources.json")["event_count"], 41)

    def test_symlinked_source_file_and_parent_rejected(self):
        target = self.root / "outside"
        target.write_text("{}\n")
        self.log.unlink()
        self.log.symlink_to(target)
        with self.assertRaises(OSError):
            r.collect(self.source, dt.date(2026, 11, 3), "Europe/London")
        self.log.unlink()
        self.log.parent.rmdir()
        self.log.parent.symlink_to(self.stream)
        with self.assertRaises(OSError):
            r.collect(self.source, dt.date(2026, 11, 3), "Europe/London")

    def test_hardlinks_and_fifos_rejected(self):
        os.link(self.log, self.root / "hardlink")
        with self.assertRaisesRegex(r.Problem, "unsafe_file"):
            r.read_file(self.log)
        fifo = self.root / "fifo"
        os.mkfifo(fifo)
        with self.assertRaisesRegex(r.Problem, "unsafe_file"):
            r.read_file(fifo)

    def test_symlink_state_and_destination_do_not_modify_target(self):
        state = Path(self.config["stateRoot"])
        state.mkdir()
        outside = self.root / "outside"
        outside.write_text("untouched")
        (state / "state.json").symlink_to(outside)
        with self.assertRaises(OSError):
            self.run_job()
        with self.assertRaises(r.Problem):
            r.atomic_file(state / "state.json", b"modified")
        self.assertEqual(outside.read_text(), "untouched")

    def test_unsafe_uuid_and_registry_rejected(self):
        for value in ("../outside", str(uuid.uuid4()).upper(), None):
            with self.assertRaises(r.Problem):
                r.canonical_id(value)
        self.write(self.source / "projects.json", {"version": 1, "projects": [None]})
        with self.assertRaises(r.Problem):
            list(r.scope_records(self.source))

    def test_existing_partial_day_never_overwritten(self):
        day = dt.date(2026, 11, 3)
        path = r.day_path(Path(self.config["archiveRoot"]), day)
        path.mkdir(parents=True)
        result = self.run_job()
        self.assertEqual(result["status"], "pending")
        self.assertFalse(self.calls)
        self.assertFalse((path / "roundup.md").exists())
        self.assertEqual(self.notices[0][0], "Daily roundup needs attention")

    def test_partial_day_does_not_block_later_catchup(self):
        self.config["firstDate"] = "2026-11-02"
        partial = r.day_path(Path(self.config["archiveRoot"]), dt.date(2026, 11, 2))
        partial.mkdir(parents=True)
        result = self.run_job()
        self.assertEqual(result["published"], ["2026-11-03"])
        self.assertEqual(result["pending_days"], ["2026-11-02"])
        self.assertEqual(list(partial.iterdir()), [])
        self.assertEqual(len(self.notices), 1)
        self.assertIn("pending review", self.notices[0][1])

    def test_malformed_existing_manifest_preserved_and_later_day_published(self):
        self.config["firstDate"] = "2026-11-02"
        partial = r.day_path(Path(self.config["archiveRoot"]), dt.date(2026, 11, 2))
        partial.mkdir(parents=True)
        (partial / "sources.json").write_text("not json")
        result = self.run_job()
        self.assertEqual(result["published"], ["2026-11-03"])
        self.assertEqual((partial / "sources.json").read_text(), "not json")

    def test_interrupted_attempt_reservation_survives_restart(self):
        def interrupted(stage, payload):
            raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.run_job(model=interrupted)
        state = r.read_json(Path(self.config["stateRoot"]) / "state.json")
        self.assertEqual(state["failures"]["2026-11-03"]["attempts"], 1)
        self.assertEqual(state["history"][0]["status"], "started")
        self.assertEqual(self.run_job()["published"], [])
        state = r.read_json(Path(self.config["stateRoot"]) / "state.json")
        self.assertEqual(state["history"][0]["status"], "interrupted")
        self.assertEqual(state["history"][0]["code"], "outcome_not_recorded")
        self.assertFalse(self.calls)
        self.assertEqual(self.run_job(now=self.now + dt.timedelta(hours=2))["published"], ["2026-11-03"])

    def test_atomic_no_replace_even_racing_empty_directory(self):
        day = dt.date(2026, 11, 3)
        path = r.day_path(Path(self.config["archiveRoot"]), day)
        original = r.rename_new
        def race(parent, source, destination):
            os.mkdir(destination, dir_fd=parent)
            original(parent, source, destination)
        with patch.object(r, "rename_new", side_effect=race):
            with self.assertRaisesRegex(r.Problem, "already_exists"):
                r.publish(Path(self.config["archiveRoot"]), day, "must not win", {"date": str(day)})
        self.assertEqual(list(path.iterdir()), [])

    def test_concurrent_job_does_not_generate(self):
        state = Path(self.config["stateRoot"])
        state.mkdir()
        with (state / "run.lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertEqual(self.run_job()["status"], "already_running")
        self.assertFalse(self.calls)

    def test_private_permissions_and_no_raw_worklog_copy(self):
        self.run_job()
        for root in (Path(self.config["stateRoot"]), Path(self.config["archiveRoot"])):
            for path in [root, *root.rglob("*")]:
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700 if path.is_dir() else 0o600)
        manifest = r.read_json(r.day_path(Path(self.config["archiveRoot"]), dt.date(2026, 11, 3)) / "sources.json")
        self.assertNotIn("summary", json.dumps(manifest))
        self.assertEqual(manifest["event_count"], 2)

    def test_renderer_does_not_activate_model_html_or_image_links(self):
        draft = {"overview": "<img src=x>", "sections": [{"title": "[outside](https://example.com)", "items": [{"text": "![bad](https://example.com)", "sources": ["E00001"]}]}], "unfinished": []}
        text = r.render(dt.date(2026, 11, 3), draft, "Europe/London")
        self.assertIn(r"\<img src=x\>", text)
        self.assertNotIn("\n<img", text)
        self.assertIn(r"\!\[bad\]", text)
        self.assertNotIn("![bad]", text)

    def test_notification_checks_existing_server_without_activation(self):
        class Reply:
            returncode = 0
            stdout = b"b false\n"
        with patch.object(r.subprocess, "run", return_value=Reply()) as call:
            self.assertFalse(r.notify(self.config, "Title", "Body"))
            self.assertEqual(call.call_count, 1)
        Reply.stdout = b"b true\n"
        with patch.object(r.subprocess, "run", return_value=Reply()) as call:
            self.assertTrue(r.notify(self.config, "Title", "Body"))
            self.assertEqual(call.call_count, 2)

    def fake_pi(self, reply, extra=None, before=None):
        script = self.root / "fake-pi"
        data = (before or []) + [{"type": "message_end", "message": reply}, {"type": "agent_settled"}]
        if extra:
            data += extra
        code = f"#!{sys.executable}\nimport sys,json\nassert '--no-tools' in sys.argv and '--no-extensions' in sys.argv and '--no-context-files' in sys.argv\nassert 'SOURCE DATA' in sys.stdin.read()\n"
        code += "\n".join("print(" + repr(json.dumps(record)) + ")" for record in data)
        script.write_text(code)
        script.chmod(0o700)
        self.config["piBin"] = str(script)
        state = Path(self.config["stateRoot"])
        state.mkdir(exist_ok=True)
        return r.Codex(self.config, state)

    def test_backend_enforces_actual_model_and_no_tools(self):
        reply = {"role": "assistant", "model": "test-model", "provider": "openai-codex", "stopReason": "stop", "content": [{"type": "text", "text": '{"verdict":"pass","issues":[]}'}]}
        self.assertEqual(self.fake_pi(reply)("review", {}), {"verdict": "pass", "issues": []})
        reply["model"] = "wrong"
        with self.assertRaisesRegex(r.Problem, "wrong_model"):
            self.fake_pi(reply)("review", {})
        reply["model"] = "test-model"
        with self.assertRaisesRegex(r.Problem, "unsafe_or_unfinished"):
            self.fake_pi(reply, [{"type": "tool_execution_start"}])("review", {})

    def test_backend_accepts_documented_recovered_retry(self):
        success = {"role": "assistant", "model": "test-model", "provider": "openai-codex", "stopReason": "stop", "content": [{"type": "text", "text": '{"verdict":"pass","issues":[]}'}]}
        failure = {**success, "stopReason": "error", "content": []}
        before = [{"type": "message_end", "message": failure}, {"type": "auto_retry_start", "attempt": 1}, {"type": "auto_retry_end", "success": True}]
        self.assertEqual(self.fake_pi(success, before=before)("review", {})["verdict"], "pass")
        with self.assertRaisesRegex(r.Problem, "unexpected_codex_turns"):
            self.fake_pi(success, before=[{"type": "message_end", "message": success}])("review", {})
        with self.assertRaisesRegex(r.Problem, "unexpected_codex_turns"):
            self.fake_pi(success, before=[{"type": "message_end", "message": failure}])("review", {})

    def test_backend_rejects_aborted_and_invalid_json(self):
        reply = {"role": "assistant", "model": "test-model", "provider": "openai-codex", "stopReason": "aborted", "content": [{"type": "text", "text": '{}'}]}
        with self.assertRaises(r.Problem):
            self.fake_pi(reply)("review", {})
        reply["stopReason"] = "stop"
        reply["content"][0]["text"] = "not json"
        with self.assertRaisesRegex(r.Problem, "invalid_model_json"):
            self.fake_pi(reply)("review", {})


if __name__ == "__main__":
    unittest.main()
