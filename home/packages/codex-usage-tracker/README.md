# Codex usage tracker

A Python-standard-library-only collector and terminal report. No daemon, web
server, Pi extension, model requests, or new authentication setup.

## Use

```sh
codex-usage                         # current quota window + per-model/effort tokens
codex-usage week                    # same report
codex-usage week --start 2026-10-26  # seven days from this date, UTC
codex-usage history                 # observed quota windows and peak percentages
codex-usage collect                 # one live snapshot and incremental local import
codex-usage collect --local-only    # import/backfill without calling OpenAI
systemctl --user status codex-usage.timer
journalctl --user -u codex-usage.service
```

Reports read the database only; they don't call OpenAI or rescan logs. The hourly
systemd user timer makes one GET to `https://chatgpt.com/backend-api/wham/usage`
(timeout 15 seconds, no retries) and imports newly appended local records. Missed
timer events coalesce into one collection after login/resume; the laptop is not
woken from suspend. There is no automatic weekly notification: run `codex-usage`
or `history` whenever useful.

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

Tests use temporary directories and mocked HTTP; no real credentials, quota, or
live session files are required.
