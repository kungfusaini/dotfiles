#!/usr/bin/env python3
"""Private, incremental Codex quota and Pi usage accounting. Python stdlib only."""
import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.request

UTC = dt.timezone.utc
MAX_LINE = 8 * 1024 * 1024
BYTE_BUDGET = 64 * 1024 * 1024
SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
 id INTEGER PRIMARY KEY, sampled_at INTEGER NOT NULL, account TEXT NOT NULL,
 plan TEXT NOT NULL, reset_at INTEGER NOT NULL, duration INTEGER NOT NULL,
 used REAL NOT NULL, allowed INTEGER NOT NULL, reached INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS snapshot_window ON snapshots(account, plan, reset_at, sampled_at);
CREATE TABLE IF NOT EXISTS reminders (
 account TEXT NOT NULL, reset_at INTEGER NOT NULL, stage INTEGER NOT NULL,
 sent_at INTEGER NOT NULL, PRIMARY KEY(account, reset_at, stage)
);
CREATE TABLE IF NOT EXISTS runs (
 id INTEGER PRIMARY KEY, started_at INTEGER NOT NULL, finished_at INTEGER, quota_status TEXT,
 files INTEGER NOT NULL DEFAULT 0, bytes INTEGER NOT NULL DEFAULT 0,
 imported INTEGER NOT NULL DEFAULT 0, issues INTEGER NOT NULL DEFAULT 0,
 backlog INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS sources (
 path TEXT PRIMARY KEY, device INTEGER, inode INTEGER, size INTEGER, mtime INTEGER,
 offset INTEGER NOT NULL DEFAULT 0, session TEXT, discarding INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS contexts (
 session TEXT NOT NULL, entry TEXT NOT NULL, provider TEXT, model TEXT, effort TEXT,
 PRIMARY KEY(session, entry)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS requests (
 key TEXT PRIMARY KEY, timestamp INTEGER NOT NULL, model TEXT NOT NULL,
 response_model TEXT, effort TEXT, kind TEXT NOT NULL, status TEXT NOT NULL,
 input INTEGER, cached INTEGER, cache_write INTEGER, output INTEGER,
 reasoning INTEGER, total INTEGER
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS request_time ON requests(timestamp);
"""


def stamp(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        return int(value / 1000)
    if isinstance(value, str):
        return int(dt.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())
    raise ValueError("missing timestamp")


def number(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0:
        return int(value)
    return None


def label(value):
    # Never render control characters from upstream or local logs in the terminal.
    return "".join(c for c in str(value) if c.isprintable())[:100] if value is not None else None


def roots(home=None):
    home = Path(home or Path.home())
    config = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config"))
    state = Path(os.environ.get("XDG_STATE_HOME", home / ".local/state"))
    agent = Path(os.environ.get("PI_CODING_AGENT_DIR", config / "pi/agent"))
    found = list((agent / "sessions").glob("*/*.jsonl"))
    projects = state / "project-object/projects"
    found += list(projects.glob("*/pi-sessions/*.jsonl"))
    found += list(projects.glob("*/streams/*/pi-sessions/*.jsonl"))
    # Explicit patterns avoid crawling worktrees, dependencies, backups, or private documents.
    return sorted(set(found))


def state_dir():
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "codex-usage-tracker"


@contextlib.contextmanager
def database(directory, readonly=False):
    path = directory / "usage.sqlite"
    if readonly:
        if not path.is_file():
            raise ValueError("No measurements yet; run codex-usage collect.")
        db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    else:
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        if directory.is_symlink() or directory.stat().st_uid != os.getuid():
            raise ValueError("Unsafe tracker state directory")
        directory.chmod(0o700)
        if path.is_symlink():
            raise ValueError("Unsafe tracker database")
        db = sqlite3.connect(path, timeout=5)
        path.chmod(0o600)
        db.executescript(SCHEMA)
    db.row_factory = sqlite3.Row
    try:
        yield db
    finally:
        db.close()


def fetch_quota(auth_path=None):
    """Read Pi's current token without refreshing/rotating its shared credentials."""
    config = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    agent = Path(os.environ.get("PI_CODING_AGENT_DIR", config / "pi/agent"))
    try:
        auth = json.loads(Path(auth_path or agent / "auth.json").read_text())["openai-codex"]
        token, account = auth["access"], auth["accountId"]
        if not isinstance(token, str) or not token or not isinstance(account, str) or not account:
            return None, "auth_missing"
        if auth.get("expires", 0) <= time.time() * 1000 + 1000:
            return None, "auth_expired"
    except (OSError, ValueError, KeyError, TypeError):
        return None, "auth_missing"
    request = urllib.request.Request(
        "https://chatgpt.com/backend-api/wham/usage",
        headers={"Authorization": "Bearer " + token, "ChatGPT-Account-Id": account,
                 "Accept": "application/json", "User-Agent": "codex-usage-tracker/1.0"},
    )
    # Do not allow an unexpected redirect to forward credentials to another host.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=15) as response:
            raw = response.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            return None, "schema_error"
        data = json.loads(raw)
        return parse_quota(data, account), "ok"
    except urllib.error.HTTPError as exc:
        return None, "auth_expired" if exc.code == 401 else f"http_{exc.code}"
    except (urllib.error.URLError, TimeoutError, OSError):
        return None, "network_error"
    except (ValueError, KeyError, TypeError, AttributeError):
        return None, "schema_error"


def parse_quota(data, account):
    limit = data["rate_limit"]
    windows = [w for w in (limit.get("primary_window"), limit.get("secondary_window"))
               if isinstance(w, dict) and w.get("limit_window_seconds") == 604800]
    if len(windows) != 1:
        raise ValueError("Unknown weekly quota schema")
    w = windows[0]
    used = w["used_percent"]
    reset = w["reset_at"]
    if isinstance(used, bool) or not isinstance(used, (int, float)) or not math.isfinite(used) or not 0 <= used <= 100:
        raise ValueError("Invalid quota percentage")
    if isinstance(reset, bool) or not isinstance(reset, int) or reset <= 0:
        raise ValueError("Invalid reset time")
    if not isinstance(data["plan_type"], str) or not isinstance(limit["allowed"], bool) or not isinstance(limit["limit_reached"], bool):
        raise ValueError("Invalid quota metadata")
    # Explicit allowlist: never persist the upstream payload or identity/credentials.
    return (hashlib.sha256(account.encode()).hexdigest()[:24], label(data["plan_type"]),
            reset, 604800, used, int(limit["allowed"]), int(limit["limit_reached"]))


def context_for(db, session, parent):
    row = db.execute("SELECT provider, model, effort FROM contexts WHERE session=? AND entry=?",
                     (session, parent)).fetchone()
    return tuple(row) if row else (None, None, None)


def request_key(entry, source, provider, model, kind):
    """Shared immutable identity for collection and read-only attribution."""
    identity = source.get("responseId") or [entry.get("id"), source.get("timestamp", entry.get("timestamp")),
                                           provider, model, kind, source["usage"]]
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()


def usage_record(entry, session, provider, model):
    """Collector eligibility and inheritance; explicit null never means inherit."""
    if not session or not entry.get("id"):
        return None
    kind = entry.get("type")
    message = entry.get("message") or {}
    if kind == "message" and message.get("role") == "assistant":
        source, request_kind = message, "response"
        status = label(message.get("stopReason", "unknown"))
    elif kind == "usage":
        source, request_kind, status = entry, "usage", "recorded"
    elif kind in ("compaction", "branch_summary") and entry.get("usage"):
        source, request_kind, status = entry, kind, "recorded"
    else:
        return None
    provider, model = source.get("provider", provider), source.get("model", model)
    if provider != "openai-codex" or not model:
        return None
    if not isinstance(source.get("usage"), dict):
        raise ValueError("Missing usage")
    return source, request_kind, status, provider, model


def ingest_entry(db, entry, session):
    """Count all branches as real usage; deduplicate copied/forked responses."""
    kind, entry_id = entry.get("type"), entry.get("id")
    if kind == "session":
        return label(entry_id), 0
    if not session or not entry_id:
        return session, 0
    provider, model, effort = context_for(db, session, entry.get("parentId"))
    if kind == "model_change":
        provider, model = label(entry.get("provider")), label(entry.get("modelId"))
    if kind == "thinking_level_change":
        effort = label(entry.get("thinkingLevel"))
    db.execute("INSERT OR REPLACE INTO contexts VALUES (?,?,?,?,?)",
               (session, entry_id, provider, model, effort))
    record = usage_record(entry, session, provider, model)
    if record is None:
        return session, 0
    source, request_kind, status, provider, model = record
    usage = source["usage"]
    ts = stamp(source.get("timestamp", entry.get("timestamp")))
    # responseId is stable across forks; older logs lack it, so use immutable metadata.
    key = request_key(entry, source, provider, model, request_kind)
    tokens = [number(usage.get(k)) for k in ("input", "cacheRead", "cacheWrite", "output", "reasoning", "totalTokens")]
    cursor = db.execute("INSERT OR IGNORE INTO requests VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (key, ts, label(model), label(source.get("responseModel")),
                        label(source.get("providerThinkingLevel")) or effort,
                        request_kind, status, *tokens))
    return session, cursor.rowcount


def ingest(db, paths, budget=BYTE_BUDGET):
    counts = dict(files=0, bytes=0, imported=0, issues=0, backlog=0)
    for path in paths:
        try:
            st = path.stat()
            if not stat.S_ISREG(st.st_mode) or path.is_symlink():
                continue
            old = db.execute("SELECT * FROM sources WHERE path=?", (str(path),)).fetchone()
            if old and (old["device"], old["inode"], old["size"], old["mtime"]) == (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns):
                continue
            if counts["bytes"] >= budget:
                counts["backlog"] += 1
                continue
            same = old and (old["device"], old["inode"]) == (st.st_dev, st.st_ino) and st.st_size > old["size"]
            offset = old["offset"] if same else 0
            session = old["session"] if same else None
            discarding = bool(old["discarding"]) if same else False
            counts["files"] += 1
            with path.open("rb") as stream, db:
                stream.seek(offset)
                while counts["bytes"] < budget:
                    start = stream.tell()
                    # Only the first chunk of a normal line can exceed the run budget
                    # (by at most MAX_LINE). Oversized-line draining is resumable.
                    limit = min(65536, budget-counts["bytes"]) if discarding else MAX_LINE + 1
                    raw = stream.readline(limit)
                    if not raw:
                        break
                    counts["bytes"] += len(raw)
                    if discarding:
                        discarding = not raw.endswith(b"\n")
                    elif len(raw) > MAX_LINE:
                        counts["issues"] += 1
                        discarding = not raw.endswith(b"\n")
                    elif not raw.endswith(b"\n"):
                        stream.seek(start)  # Writer has not finished the entry: retry on append.
                        break
                    else:
                        try:
                            entry = json.loads(raw)
                            session, added = ingest_entry(db, entry, session)
                            counts["imported"] += added
                        except (ValueError, TypeError, AttributeError, OverflowError):
                            counts["issues"] += 1
                    offset = stream.tell()
                offset = stream.tell()
                behind = offset < st.st_size and counts["bytes"] >= budget
                if behind:
                    counts["backlog"] += 1
                # A budget-limited file must be revisited even when it hasn't grown.
                saved_size = offset if behind else st.st_size
                saved_mtime = -1 if behind else st.st_mtime_ns
                db.execute("INSERT OR REPLACE INTO sources VALUES (?,?,?,?,?,?,?,?)",
                           (str(path), st.st_dev, st.st_ino, saved_size, saved_mtime, offset, session, int(discarding)))
        except OSError:
            counts["issues"] += 1
    return counts


def remind(db, quota, now=None):
    """At most one reminder per stage/window; only called with a fresh quota."""
    now = int(time.time()) if now is None else now
    account, _plan, reset, _duration, used, _allowed, _reached = quota
    left = reset - now
    if not 0 < left <= 86400 or 100 - used < 10:
        return False
    stage = 4 if left <= 14400 else 24
    # Upstream reset timestamps can jitter by one second. A 4h reminder also
    # suppresses the earlier 24h stage if the clock subsequently moves backward.
    if db.execute("SELECT 1 FROM reminders WHERE account=? AND ABS(reset_at-?)<=2 AND stage<=?",
                  (account, reset, stage)).fetchone():
        return False
    body = (f"{100-used:g}% of weekly Codex allowance remains. Reset: {iso(reset)}. "
            "Run pi-oneshot in a project terminal to start one Pi session that stops at reset.")
    try:
        subprocess.run(["notify-send", "--app-name=Codex One-shot", "--urgency=normal",
                        "--expire-time=0", "--", f"Codex reset within {stage} hours", body],
                       check=True, timeout=10, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        print("WARNING: reset reminder delivery failed; will retry at the next collection.", file=sys.stderr)
        return False
    with db:
        db.execute("INSERT OR REPLACE INTO reminders VALUES (?,?,?,?)", (account, reset, stage, now))
    return True


def collect(directory, local_only=False):
    started = int(time.time())
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if directory.is_symlink():
        raise ValueError("Unsafe tracker state directory")
    directory.chmod(0o700)
    lock_path = directory / "collect.lock"
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Collection already running; skipped.")
            return
        with database(directory) as db:
            quota, status = (None, "local_only") if local_only else fetch_quota()
            with db:
                run_id = db.execute("INSERT INTO runs(started_at,quota_status) VALUES (?,?)", (started, status)).lastrowid
                if quota:
                    db.execute("INSERT INTO snapshots(sampled_at,account,plan,reset_at,duration,used,allowed,reached) VALUES (?,?,?,?,?,?,?,?)",
                               (int(time.time()), *quota))
            counts = ingest(db, roots())
            with db:
                db.execute("UPDATE runs SET finished_at=?,files=?,bytes=?,imported=?,issues=?,backlog=? WHERE id=?",
                           (int(time.time()), *counts.values(), run_id))
            print(f"Quota: {status}; imported {counts['imported']} records; "
                  f"read {counts['bytes']} bytes in {counts['files']} files; "
                  f"issues {counts['issues']}; backlog {counts['backlog']} files.")
            if quota:
                remind(db, quota)
            if status not in ("ok", "local_only") or counts["issues"]:
                return 1
    return 0


def iso(value):
    return dt.datetime.fromtimestamp(value, UTC).strftime("%Y-%m-%d %H:%M UTC")


def scope_names():
    root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "project-object"
    projects, streams = {}, {}
    issues = 0
    def records(path, key):
        nonlocal issues
        try:
            if path.is_symlink() or path.stat().st_size > MAX_LINE:
                raise ValueError("unsafe registry")
            data = json.loads(path.read_text())[key]
            if not isinstance(data, list):
                raise ValueError("invalid registry")
            return data
        except (OSError, ValueError, KeyError, TypeError):
            issues += 1
            return []
    for project in records(root / "projects.json", "projects"):
        if not isinstance(project, dict):
            issues += 1
            continue
        pid = project.get("id")
        # IDs become path components; never accept arbitrary registry paths.
        if not valid_scope_id(pid):
            issues += 1
            continue
        projects[pid] = label(project.get("name")) or pid
        path = root / "projects" / pid / "streams.json"
        if path.exists():
            for stream in records(path, "streams"):
                if isinstance(stream, dict) and valid_scope_id(stream.get("id")):
                    streams[pid, stream["id"]] = label(stream.get("name")) or stream["id"]
                else:
                    issues += 1
    return projects, streams, issues


def valid_scope_id(value):
    import uuid
    try:
        return isinstance(value, str) and str(uuid.UUID(value)) == value
    except ValueError:
        return False


def source_scope(path):
    root = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "project-object/projects"
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        return (None, None)
    if len(parts) == 3 and valid_scope_id(parts[0]) and parts[1] == "pi-sessions":
        return (parts[0], None)
    if (len(parts) == 5 and valid_scope_id(parts[0]) and parts[1] == "streams"
            and valid_scope_id(parts[2]) and parts[3] == "pi-sessions"):
        return (parts[0], parts[2])
    return (None, None)


def attribution_snapshot(db, since, until):
    owned = not db.in_transaction
    if owned:
        db.execute("BEGIN")
    try:
        requests = {r["key"]: r["output"] for r in db.execute(
            "SELECT key,output FROM requests WHERE timestamp>=? AND timestamp<?", (since, until))}
        sources = db.execute("SELECT path,offset,device,inode FROM sources ORDER BY mtime DESC,path").fetchall()
        return requests, sources
    finally:
        if owned:
            db.rollback()


def attribution(db, since, until, budget=4 * 1024**3, seconds=30, snapshot=None):
    """Join frozen tracked identities to registered logs without persisting content.

    Bounded, local and on demand. Missing/conflicting identities remain explicit.
    Parent context comes from the collector, including compaction/usage fallbacks.
    """
    requests, sources = snapshot if snapshot is not None else attribution_snapshot(db, since, until)
    owners, ambiguous = {}, set()
    issues = read = 0
    deadline = time.monotonic() + seconds
    limited = False
    for row in sources if requests else []:
        if read >= budget or time.monotonic() >= deadline:
            limited = True
            break
        path = Path(row["path"])
        scope = source_scope(path)
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, "rb") as log:
                st = os.fstat(log.fileno())
                if (not stat.S_ISREG(st.st_mode) or (st.st_dev, st.st_ino) != (row["device"], row["inode"])
                        or st.st_size < row["offset"]):
                    issues += 1
                    continue
                session = None
                while log.tell() < row["offset"]:
                    if read >= budget or time.monotonic() >= deadline:
                        limited = True
                        break
                    raw = log.readline(min(MAX_LINE + 1, row["offset"] - log.tell(), budget - read))
                    if not raw:
                        issues += 1  # registered bytes are no longer available
                        break
                    read += len(raw)
                    if len(raw) > MAX_LINE or not raw.endswith(b"\n"):
                        issues += 1
                        # Do not interpret a fragment of an oversized record as JSON.
                        while raw and not raw.endswith(b"\n") and log.tell() < row["offset"]:
                            if read >= budget or time.monotonic() >= deadline:
                                limited = True
                                break
                            raw = log.readline(min(65536, budget-read, row["offset"]-log.tell()))
                            read += len(raw)
                        continue
                    try:
                        entry = json.loads(raw)
                        kind = entry.get("type")
                        if kind == "session":
                            session = label(entry.get("id"))
                            continue
                        if kind not in ("message", "usage", "compaction", "branch_summary"):
                            continue
                        source = (entry.get("message") or {}) if kind == "message" else entry
                        inherited = (None, None, None)
                        if "provider" not in source or "model" not in source:
                            inherited = context_for(db, session, entry.get("parentId"))
                        record = usage_record(entry, session, *inherited[:2])
                        if record is None:
                            continue
                        source, request_kind, _status, provider, model = record
                        if not since <= stamp(source.get("timestamp", entry.get("timestamp"))) < until:
                            continue
                        key = request_key(entry, source, provider, model, request_kind)
                        if key in requests:
                            if key in owners and owners[key] != scope:
                                ambiguous.add(key)
                            else:
                                owners[key] = scope
                    except (ValueError, TypeError, AttributeError, OverflowError):
                        issues += 1
        except OSError:
            issues += 1
    groups = {}
    matched_calls = matched_output = 0
    for key, output in requests.items():
        scope = owners.get(key, ("unmatched", None))
        if key in ambiguous:
            scope = ("ambiguous", None)
        elif key in owners:
            matched_calls += 1
            matched_output += output or 0
        totals = groups.setdefault(scope, [0, 0, 0])
        totals[0] += 1
        totals[1] += output or 0
        totals[2] += output is None
    return {"groups": groups, "calls": len(requests), "output": sum(v or 0 for v in requests.values()),
            "matched_calls": matched_calls, "matched_output": matched_output,
            "issues": issues, "limited": limited, "bytes": read}


def report_attribution(db, since, until, all_streams=False, snapshot=None):
    result = attribution(db, since, until, snapshot=snapshot)
    projects, streams, registry_issues = scope_names()
    def project_name(pid):
        return {None: "Other / unattached", "unmatched": "Unmatched", "ambiguous": "Ambiguous"}.get(
            pid, projects.get(pid, f"Unknown project {pid}"))
    def stream_name(pid, sid):
        return streams.get((pid, sid), f"Unknown stream {sid}") if sid else "Main / project sessions"
    def share(output):
        return f"{output / result['output'] * 100:.2f}%" if result["output"] else "N/A"
    def show(name, totals):
        print(f"{name} | {totals[0]:,} | {totals[1]:,} | {share(totals[1])}")
    print("\nProjects | Calls | Output (includes reasoning) | Pi output share")
    rollups = {}
    for (pid, _sid), totals in result["groups"].items():
        summed = rollups.setdefault(pid, [0, 0, 0])
        for i in range(3):
            summed[i] += totals[i]
    for pid, totals in sorted(rollups.items(), key=lambda item: (-item[1][1], str(item[0]))):
        show(project_name(pid), totals)
    print("\nStreams (parent projects include these rows) | Calls | Output | Pi output share")
    ranked = sorted(result["groups"].items(), key=lambda item: (-item[1][1], str(item[0])))
    selected = ranked if all_streams else ranked[:12]
    for (pid, sid), totals in sorted(selected, key=lambda item: (project_name(item[0][0]), -item[1][1], str(item[0]))):
        show(f"{project_name(pid)} / {stream_name(pid, sid)}", totals)
    if len(selected) < len(ranked):
        show(f"Remaining {len(ranked)-len(selected)} streams/buckets (use --all-streams)",
             [sum(t[i] for _, t in ranked[len(selected):]) for i in range(3)])
    print(f"Attribution: {result['matched_calls']:,}/{result['calls']:,} calls matched; "
          f"{share(result['matched_output'])} output-weighted coverage.")
    print("Pi output shares are not subscription quota shares or measures of waste/productivity.")
    if result["issues"] or result["limited"] or registry_issues:
        print(f"WARNING: attribution incomplete: {result['issues']} source issues, "
              f"{registry_issues} registry issues; read limit reached: {result['limited']}.")
    if any(t[2] for t in result["groups"].values()):
        print("WARNING: some output values are unknown; shares cover recorded output only.")


def report(db, start=None, all_streams=False):
    # One SQLite read snapshot keeps model totals, identities and coverage consistent.
    owned_snapshot = not db.in_transaction
    if owned_snapshot:
        db.execute("BEGIN")
    latest = db.execute("SELECT * FROM snapshots ORDER BY sampled_at DESC,id DESC LIMIT 1").fetchone()
    now = int(time.time())
    if latest:
        print(f"{latest['plan']} | {latest['used']:g}% used | resets {iso(latest['reset_at'])}")
        print(f"Last snapshot: {iso(latest['sampled_at'])} ({max(0, now-latest['sampled_at'])//60} minutes ago)")
        if now >= latest["reset_at"] or now - latest["sampled_at"] > 7200:
            print("WARNING: quota is stale; current usage is unknown.")
        elif latest["allowed"] == 0 or latest["reached"]:
            print("WARNING: account currently reports a usage restriction.")
    else:
        print("No successful quota snapshots; historical percentages are unknown.")
    run = db.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone()
    completed = db.execute("SELECT * FROM runs WHERE finished_at IS NOT NULL ORDER BY id DESC LIMIT 1").fetchone()
    if run:
        if run["finished_at"] is None:
            print("WARNING: latest collection is unfinished; local token accounting may be incomplete.")
        else:
            print(f"Collector: {run['quota_status']} | backlog {run['backlog']} files | issues {run['issues']}")
    if completed:
        print(f"Last completed import: {iso(completed['finished_at'])}")
    if not completed or now-completed["finished_at"] > 7200:
        print("WARNING: local token accounting is stale or has not completed yet.")
    if completed and completed["backlog"]:
        print("WARNING: local backfill is still in progress; token totals are incomplete.")
    if db.execute("SELECT 1 FROM runs WHERE issues>0 LIMIT 1").fetchone():
        print("WARNING: some log entries could not be imported; token totals are incomplete.")
    if start:
        since = int(dt.datetime.combine(dt.date.fromisoformat(start), dt.time(), UTC).timestamp())
        until = since + 604800
    elif latest:
        since, until = latest["reset_at"] - latest["duration"], latest["reset_at"]
    else:
        today = dt.datetime.now(UTC).date()
        since = int(dt.datetime.combine(today-dt.timedelta(days=today.weekday()), dt.time(), UTC).timestamp())
        until = since + 604800
    print(f"\nPi usage: {iso(since)} to {iso(until)} (end exclusive)")
    print(f"{'Model / effort':36} {'Calls':>7} {'Input':>12} {'Cached':>12} {'Output':>10} {'Err/abort':>10}")
    rows = db.execute("""SELECT model,COALESCE(effort,'unknown') AS effort,COUNT(*) AS n,
        SUM(input) AS i,SUM(cached) AS c,SUM(output) AS o,
        SUM(status='error') AS e,SUM(status='aborted') AS a
        FROM requests WHERE timestamp>=? AND timestamp<? GROUP BY model,effort ORDER BY SUM(total) DESC""", (since, until)).fetchall()
    for row in rows:
        name = f"{row['model']} / {row['effort']}"
        print(f"{name:36} {row['n']:7,} {row['i'] or 0:12,} {row['c'] or 0:12,} {row['o'] or 0:10,} {row['e']}/{row['a']}")
    if not rows:
        print("No locally recorded usage in this interval.")
    print("Calls include tool-use responses and recorded compaction/other usage, not user messages.")
    print("Input excludes cached tokens; reasoning tokens are already included in output.")
    print("Pi-only token attribution; other Codex clients and missing/deleted logs are not included.")
    cutoff = db.execute("SELECT MAX(timestamp) FROM requests WHERE timestamp>=? AND timestamp<?",
                        (since, until)).fetchone()[0]
    print(f"Recorded usage through: {iso(cutoff) if cutoff is not None else 'no records'}")
    if latest and not start and now < latest["reset_at"]:
        window = db.execute("""SELECT sampled_at,used FROM snapshots
            WHERE account=? AND plan=? AND reset_at=? ORDER BY sampled_at,id""",
                            (latest["account"], latest["plan"], latest["reset_at"])).fetchall()
        span = window[-1]["sampled_at"] - window[0]["sampled_at"]
        continuous = all(b["used"] >= a["used"] and b["sampled_at"]-a["sampled_at"] <= 7200
                         for a, b in zip(window, window[1:]))
        if continuous and span >= 21600 and now-latest["sampled_at"] <= 7200:
            projection = latest["used"] + (window[-1]["used"]-window[0]["used"]) / span * (latest["reset_at"]-now)
            print(f"Rough projection at reset: {projection:.0f}% (linear observed pace; not a guarantee).")
    frozen = attribution_snapshot(db, since, until)
    if owned_snapshot:
        # Release the rollback-journal shared lock before the potentially long log scan.
        db.rollback()
    report_attribution(db, since, until, all_streams, snapshot=frozen)


def history(db):
    print("Observed weekly quota windows (not calendar weeks):")
    for row in db.execute("""SELECT account,plan,reset_at,MIN(sampled_at) AS first,
        MAX(sampled_at) AS last,MAX(used) AS peak,COUNT(*) AS n FROM snapshots
        GROUP BY account,plan,reset_at ORDER BY reset_at DESC,first DESC LIMIT 26"""):
        print(f"Reset {iso(row['reset_at'])} | {row['plan']} | at least {row['peak']:g}% used | "
              f"{row['n']} snapshots; last {iso(row['last'])}")
    print("Peaks are lower bounds: usage after the last sample is unknown, including while asleep/offline.")
    print("Plan/account changes and allowance resets can prevent exact week-to-week comparisons.")


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command")
    p = sub.add_parser("collect", help="Take one quota snapshot and incrementally import local logs")
    p.add_argument("--local-only", action="store_true", help="Backfill logs without an API call")
    p = sub.add_parser("refresh", help="Fetch quota, import logs and report model/project/stream usage")
    p.add_argument("--all-streams", action="store_true", help="Show every stream instead of the largest twelve")
    parser.add_argument("--all-streams", action="store_true", help="Show every stream in the default report")
    for name in ("status", "week"):
        p = sub.add_parser(name, help="Show quota and model/project/stream token usage")
        p.add_argument("--start", help="Start a seven-day report on YYYY-MM-DD (UTC)")
        p.add_argument("--all-streams", action="store_true", help="Show every stream instead of the largest twelve")
    sub.add_parser("history", help="List observed quota windows and their peak percentages")
    args = parser.parse_args()
    directory = state_dir()
    try:
        if args.command == "collect":
            return collect(directory, args.local_only)
        if args.command == "refresh":
            result = collect(directory)
            if result is None:  # Another collector holds the lock; no new measurement was made.
                return 1
            if result:
                print("WARNING: refresh incomplete; showing the latest saved data, which may not be fresh.")
            with database(directory, readonly=True) as db:
                report(db, all_streams=args.all_streams)
            return result
        with database(directory, readonly=True) as db:
            if args.command == "history":
                history(db)
            else:
                report(db, getattr(args, "start", None), args.all_streams)
    except (OSError, sqlite3.Error, ValueError):
        # Exceptions from HTTP/auth or session parsing can contain private data.
        print("codex-usage: unavailable state or invalid input; see README for troubleshooting.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
