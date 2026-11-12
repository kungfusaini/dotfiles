# Codex usage tracker

A Python-standard-library-only collector and terminal report. No daemon, web
server, Pi extension, model requests, or new authentication setup.

## Use

```sh
codex-usage                         # quota + model/project/stream usage
codex-usage --all-streams           # include every stream, not just the largest twelve
codex-usage refresh                 # fetch latest quota + new logs, then show report
codex-usage week                    # same report
codex-usage week --start 2026-10-26  # seven days from this date, UTC
codex-usage history                 # observed quota windows and peak percentages
codex-usage collect                 # one live snapshot and incremental local import
codex-usage collect --local-only    # import/backfill without calling OpenAI
systemctl --user status codex-usage.timer
journalctl --user -u codex-usage.service
```

Normal reports are offline and read-only: they read the database and join tracked
request identities against registered retained logs for project/stream attribution.
They never call OpenAI. The attribution reader is bounded to 4 GiB and 30 seconds;
source gaps and read limits are reported explicitly. No report cache or extra
collector is installed.
`refresh` runs one collection on demand and then displays the updated report; it
leaves the hourly schedule unchanged. It uses the same bounded incremental import
and shared lock as the timer. If another collector is running, it skips and exits
nonzero; retry after that collection finishes. On a network/auth/import error, it
exits nonzero and explicitly labels the report as saved, potentially stale data.
It refreshes measurements, not OAuth credentials.

The hourly systemd user timer makes one GET to `https://chatgpt.com/backend-api/wham/usage`
(timeout 15 seconds, no retries) and imports newly appended local records. Missed
timer events coalesce into one collection after login/resume; the laptop is not
woken from suspend. Fresh successful collections also deliver reset reminders within 24 hours and
again within 4 hours, when at least 10% of the weekly allowance remains. Delivery
is deduplicated per account/window/stage, including one-second reset jitter.
The existing hourly schedule means a reminder can arrive up to about an hour
after its threshold, or after resume; it does not wake the laptop. A first sample
inside 4 hours sends only the 4-hour reminder. Failed delivery is retried on the
next fresh collection. Stale/offline reports and local-only imports never notify.
These are normal desktop notifications and respect Do Not Disturb. Notification
bodies contain allowance/reset metadata only, not prompts or account identities.

## Project and stream usage

Default, `status`, `week` and `refresh` reports include project totals and the largest
twelve stream/project-session buckets. Add `--all-streams` to any of these commands
for every recorded stream, e.g. `codex-usage week --start 2026-11-02 --all-streams`.
Project totals include their streams: the two tables are separate views, not
additive. Rows show calls, output including reasoning, and **Pi output share** of
all tracked output in the interval, including unmatched usage. These shares are
not subscription-quota percentages, cost estimates or judgments about waste.

Reports freeze model totals, tracked identities and source offsets in one short
SQLite read snapshot, releasing it before scanning so collectors can still commit.
Parent-context lookups are short read-only queries; resulting identities must match
the frozen set. They show
the quota window (or explicit UTC calendar interval), newest tracked usage, import
freshness, matched-call coverage and output-weighted coverage. Missing output is
flagged; zero-output shares are N/A. The reader uses the collector's exact shared
request identity, including fallback metadata and parent context for compaction and
standalone usage. Copies count once; conflicting scope ownership is Ambiguous.
Deleted/unreadable sources remain Unmatched, never subtracted from the denominator.

Scope IDs come from canonical source paths below
`$XDG_STATE_HOME/project-object/projects`; project/stream names, including archived
scopes, come from `$XDG_DATA_HOME/project-object/{projects.json,projects/*/streams.json}`.
Unknown registry names retain IDs. Ordinary sessions are Other / unattached, not
inferred from conversation text. Only registered source bytes through imported
offsets are read, line by line; symlink, replaced-inode and truncated files are
refused, malformed/oversized lines
are counted, and conversation content is neither printed nor persisted. The hourly
`collect` service does not run this on-demand attribution scan.

## One dedicated Pi session, stopped at reset

In an interactive project/stream terminal:

```sh
pi-oneshot                    # or: pi-oneshot start
pi-oneshot status             # inspect owned sessions and deadline timers
pi-oneshot stop SESSION_ID    # optional early stop; exact ID printed at launch
```

The launcher fetches fresh Codex quota without refreshing shared credentials,
then opens **one ordinary named, persisted Pi session** in the invoking terminal.
Enter one large task in Pi; there is no queue/batch system and no automatic task
selection or authorization bypass. Project/stream attachment and session storage
are inherited from that terminal. Outside a project, normal Pi session storage
applies. Startup explicitly selects the Codex model/thinking level from the
managed default model mode, regardless of other saved provider/model defaults.

Before Pi can start, a separate systemd user calendar timer is armed for the
**reported reset timestamp itself**, with no early-stop margin. At that deadline
it sends SIGKILL to every process in this session's systemd service cgroup,
including ordinary subprocesses, detached shells, and nested Pi processes.
This is an abrupt stop: do not rely on a final model summary or shutdown hooks;
write/checkpoint useful progress during the task. Existing session entries and
files survive, but an interrupted write/tool action may be incomplete. Other Pi
sessions are not targeted. This is a scheduling deadline, not a hard-real-time
promise: system load and manager scheduling can add a small delay.

The deadline is pinned to the original allowance window and is never extended
into the next one. Pi is never automatically resumed or restarted. The timer
survives a launcher crash and catches up after suspend (without waking the
machine); a monotonic service runtime limit is a second bound. The worker checks
that its timer is active and fetches quota again immediately before launching Pi,
rejecting account/window changes, unavailable quota, restrictions, and expired
windows. Starts with five seconds or less remaining are rejected, not run early.
No credentials or prompts are put in systemd arguments/configuration. Only a
hashed account discriminator and window/session IDs are passed internally.

Do not start separate systemd services, Project Object workers, cloud agents, or
other work outside the owned cgroup from this session: those are **unsupported**
and cannot be stopped by its deadline. The appended session instructions prohibit
these and provider/account changes, paid-credit fallbacks, and automatic
continuation, but this wrapper is not a security sandbox against arbitrary code.
A local kill also cannot establish how the provider accounts for an already
in-flight request. An explicit manual resume later is a new user decision, not
an automated continuation of this run.

The managed Pi path and Codex model/thinking selection are deployed in
`~/.config/command-center/oneshot.json`.
`pi-oneshot` opens no windows and takes no global input; invoke it from the desired
terminal. It does not change Pi defaults or launch any model work on deployment.

## Measurements and limits

- Each quota snapshot stores sample time, a hashed account discriminator, plan,
  percentage used, reset time, window duration, allowed/reached flags. Fields are
  allowlisted; the original response is never saved.
- Only the seven-day window is accepted, whether returned as primary or secondary.
  Unexpected schemas produce a visible `schema_error`, never a made-up zero.
- Each local response stores its timestamp, requested/concrete model if available,
  reasoning effort, uncached input, cached input, cache-write, output, reasoning,
  total tokens, and completion status. Reasoning is a subset of output, not added
  twice. `toolUse` is a successful model response, not a failure or user message.
- Branch-aware context follows `parentId` for model and effort. All generated
  branches count as consumed work. Copied/forked responses are deduplicated using
  provider response IDs where present, otherwise stable entry/usage metadata.
- Recorded compaction, branch-summary, and standalone usage are included when the
  Codex model/provider can be identified. Unattributed tool work is not guessed.
  This is not a complete audit of nested tools, image generation, or other clients.
- Default local sources are `${PI_CODING_AGENT_DIR:-$XDG_CONFIG_HOME/pi/agent}/sessions/*/*.jsonl`
  and project/stream `pi-sessions/*.jsonl` under
  `$XDG_STATE_HOME/project-object/projects/`. No recursive scan of the home
  directory, repositories, archives, or dependencies is performed. Existing logs
  in these locations are backfilled, not just newly created sessions.
- Account quota includes other clients, whereas tokens are Pi-only. Historical
  quota is **unknown** before the first snapshot. Calendar-week token reports do
  not imply that quota windows start on Mondays.
- `history` reports **at least X% used**, not an exact final amount or guaranteed
  unused percentage. The last sample can miss usage before reset, while asleep,
  offline, or logged out. Each row shows its last sample time. Mid-window plan
  changes split rows; allowance resets and quota decreases complicate comparisons.
- The optional projection appears after at least six hours of non-decreasing
  observations with no gaps longer than two hours, and is explicitly a rough
  linear estimate. It is not a per-model quota conversion.

## Lightweight operation

- No process remains resident between hourly runs; reports are on demand.
- Only metadata and byte offsets are stored in SQLite. Unchanged files are skipped
  using stat metadata. Appends resume from a saved newline boundary; partial lines
  are retried on the next append. Truncated/replaced logs are re-read idempotently.
- Each run imports approximately 64 MiB at most (plus the current line). Initial
  backfill may take several runs; `backlog` shows remaining files. Repeated
  `collect --local-only` runs can finish a one-time backfill without extra API calls.
- Parsing is line-by-line, not whole-file. Individual lines over 8 MiB are skipped
  with an issue count so embedded images cannot cause unbounded memory allocation.
  Discarding an oversized line resumes across runs within the I/O budget.
- One advisory collection lock prevents duplicate collectors. Per-file database
  transactions make interrupted imports safe to replay.
- The service runs nice 19 / idle I/O, at most 10% of one CPU and 128 MiB RAM,
  with a two-minute execution timeout. It is sandboxed read-only except for its
  own state directory. Normal incremental runs should use far less than these caps.
- The tracker neither refreshes nor writes Pi's shared OAuth credentials, avoiding
  token-rotation races. Active Pi sessions handle refresh as usual. If Pi's token
  expires, local imports continue and the quota status becomes `auth_expired`;
  it recovers automatically on the next hourly run after Pi refreshes/login occurs.
- No raw error responses, OAuth secrets, prompts, responses, thinking text, tool
  arguments, or API-price estimates are persisted. This measures subscription
  allowance, not pay-as-you-go API spend.

State: `$XDG_DATA_HOME/codex-usage-tracker/usage.sqlite` (normally
`~/.local/share/codex-usage-tracker/usage.sqlite`). Directory mode 0700, database
and lock 0600, umask 0077. SQLite metadata includes local source paths and a hashed
account discriminator; treat the database as private. Nothing is uploaded.

## Health

`codex-usage` shows last snapshot age, collection status, backlog, import issues,
and last completed import time. Interrupted runs are explicitly flagged; a fresh
quota snapshot does not imply local token accounting completed successfully.
Stale data is labelled unknown rather than zero. A failed quota request does not
prevent local token collection. Network/auth/schema errors are recorded as bounded
status codes, not upstream bodies. Service failures are visible in systemd/journal.
Snapshots cannot reconstruct usage during an outage; the collector never invents
measurements for missed hours. Oversized/malformed records cause a persistent
incomplete-token-data warning. Deleted logs already imported remain accounted for.

## Tests

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

Unit tests use temporary directories and mocked HTTP/notifications/systemd; no
real credentials, quota, or live session files are required.

An opt-in integration test exercises the real user manager with a real Pi RPC
process and a detached child, isolated temporary Pi configuration, no prompts or
model requests, and an unrelated control service:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 tests/deadline_integration.py --pi /absolute/path/to/managed/pi
```

It verifies continued execution up to the reset, group termination near the
absolute deadline, and survival of the unrelated service. It creates only its own
uniquely named transient user units and cleans those up; no windows/global input,
live quota, credentials, or system suspend is used.
