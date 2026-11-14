# Codex usage tracker

A Python-standard-library-only collector and terminal report. No daemon, web
server, Pi extension, model requests, or new authentication setup.

## Use

```sh
codex-usage                         # quota + usage + compact environmental/flight summary
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

## Environmental summary and optional details

Normal, `status`, `week` and `refresh` reports include a compact environmental
scenario: covered operational energy in readable Wh/kWh, carbon in g/kg CO2e,
and equivalent **long-haul economy flight time for one passenger**, not an entire
aircraft. The default period is the **quota week so far**, with the declared
window and last recorded usage timestamp displayed. An expired snapshot is
labelled **Saved quota week**, not current usage; `--start` retains the selected
seven-day UTC interval and does not imply complete records. No quota snapshot
means an explicitly labelled calendar-week fallback. Existing freshness/backlog
warnings still apply; missing logs are not zero usage. No annualization or
extrapolation is included in this summary.

Use `--environment` to expand the assumptions and add project/stream energy and
carbon columns. `--grid-carbon` can adjust the summary's explicit electricity
scenario with or without `--environment`.

```sh
codex-usage
codex-usage --grid-carbon 100
codex-usage --environment
codex-usage status --environment --all-streams
codex-usage week --start 2026-11-09 --environment
codex-usage --environment --grid-carbon 100  # assumed g CO2e/kWh, not measured
```

Reports remain offline/read-only. No tracing SDK, network calls, additional
collector, schema changes or transcript uploads. Detailed table columns use
**Wh** and **g CO2e**. All estimates cover the **covered subset only**.
Project/stream rows sum per-request model estimates, never allocate the account
quota or multiply output shares by a universal coefficient. Parent projects and
streams are separate, non-additive views. Unmatched and ambiguous scope buckets
retain their estimates; attribution coverage is separate from model coverage.

`codex_environment.py` adapts only the operational energy equations of
[EcoLogits](https://ecologits.ai/latest/methodology/llm_inference/), pinned to
[3a8e85ca7970c439d00ee44cfb1c5b29fd1afeff](https://github.com/genai-impact/ecologits/tree/3a8e85ca7970c439d00ee44cfb1c5b29fd1afeff).
The OpenAI subset of its model catalog is bundled in `environment_models.json`,
with upstream warnings and sources. Module/data are MPL-2.0; the license is
included as `LICENSE-EcoLogits`. No full lifecycle-estimator dependency is needed
for this small offline metadata-only report; the equations and pinned golden
fixtures are tested locally. Catalog updates require a reviewed code change,
not runtime fetching. It is not the full EcoLogits impact calculation.

### Flight equivalence

This is a climate-impact scale comparison, not a measured route or a claim that
AI and aviation have identical climate effects. It uses rounded long-haul economy
factors from the [UK DESNZ 2026 methodology](https://www.gov.uk/government/publications/greenhouse-gas-reporting-conversion-factors-2026):

- 0.0632 kg CO2/passenger-km, plus 0.0005 kg CO2e/passenger-km other GHGs;
- the UK **1.7x non-CO2 warming allowance applied only to the CO2 component**;
- **assumed 800 km/h** effective airborne speed, not a measured itinerary.

Thus `(0.0632 * 1.7 + 0.0005) * 800 = 86.352 kg CO2e/passenger-hour`,
and equivalent hours = scenario kg CO2e / 86.352. No additional 8% great-circle
distance uplift is applied: the illustrative speed already represents assumed
kilometres flown, not a geographic route distance. Warming effects such as
contrails vary greatly and are uncertain; this is an accounting convention, not
an exact physical equivalence. Cabin, route, aircraft and occupancy change the
result. Comparisons shorter than an hour display minutes. Zero modeled carbon
in an explicit zero-grid scenario is not a zero total footprint; unestimated
usage remains unknown, including its flight equivalent.

The flight factors and source are pinned in code; no live calculator/API or new
library is needed for this small unit conversion. Changes require reviewed code.

### Assumptions and exclusions — read before interpreting numbers

- Architecture parameter counts for proprietary models are **inferred**, not
  provider measurements. Source warnings are displayed, including multimodality.
- Uses H100 80GB, FP16, batch size 64, 1.2 kW host per 8 GPUs and **assumed PUE
  1.2**. Required GPU count rounds FP16 model memory up to a power of two.
- GPU energy uses the upstream regression against active parameters and output
  tokens. Host energy uses the model catalog's estimated TTFT/TPS, falling back
  to the upstream latency regression. No request duration is measured or used as
  a server-energy proxy; upstream's optional request-latency cap is absent.
- Output includes reasoning **once**. Input, cached input and cache writes are
  **not separately modeled**. In particular, long-context prefill/cache effects
  can make these estimates materially wrong for coding agents. Partial recorded
  output from errors/aborts is included, not assumed free.
- Ranges vary the catalog's inferred parameter-count endpoints only. They are
  **not confidence intervals, actual-impact bounds, or proof of model rankings**.
  They do not capture unknown hardware, batching, cache or serving optimizations.
- Carbon is conditional on **illustrative 400 g CO2e/kWh**, or an explicit
  `--grid-carbon` scenario. The provider's actual serving region/electricity mix
  is unknown; the laptop's location is not substituted. A zero-intensity scenario
  means zero modeled operational electricity emissions, not zero total footprint.
- Excludes training, embodied hardware emissions, reserved idle capacity, water,
  laptop/builds/tools, other clients and unrecorded work. This is **not a complete
  environmental footprint** or an audited carbon inventory.
- Unknown models (including a concrete unsupported response model), missing
  output and zero-output calls remain **unknown, not zero**. No fuzzy model-name
  matching. Exact catalog aliases are supported. Missing output is reported as a
  separate count and cannot appear in output-weighted coverage's denominator.
  Call coverage and recorded-output coverage are both displayed. Even 100%
  coverage means model applicability, not measurement accuracy.

For reproducibility, preserve report interval/import freshness, catalog revision,
PUE and grid scenario. Comparing reports under different assumptions is not an
improvement measurement. No laptop power instrumentation is installed.

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
