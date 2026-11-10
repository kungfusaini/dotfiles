# Command Center daily roundups

Nix-managed, Codex-only, headless daily achievement records. The Home Manager module installs the package, immutable configuration, user service, persistent timer and private directory rules. Runtime never imports code from the checkout.

## Operation

- At 00:15 **Europe/London**, generate the previous calendar day. DST uses local calendar dates, not fixed 24-hour UTC subtraction.
- Startup and hourly cheap pending checks catch missed days without waking a sleeping laptop. Persistent systemd activation is one catch-up invocation, so the application enumerates all missing dates itself.
- Start at 3 November 2026. Existing dated `roundup.md` + `sources.json` accounts are preserved, including the manually reviewed first day. No automatic revision or silent replacement.
- At most three missing dates are processed per invocation. Each failed date gets at most three attempts per local day. Draft, review, citation and source-change problems retry after **two minutes from failure completion**; network/service and other failures keep a one-hour backoff. Existing days cause no model calls.
- A separate Nix-managed one-shot timer is armed by the service's stop hook only while a fast failure has budget remaining. It stops after success or exhaustion, is not enabled at login, and never wakes the laptop. Daily/startup/hourly checks remain the fallback. There is no permanent two-minute poll. A durable per-attempt dispatch marker prevents rearming the same stale failure if a subsequent run cannot record progress (for example, disk full or an inaccessible archive). Timer-control failures fall back to the normal hourly checks rather than looping. A retry still needs its own generation/review time; two minutes is the wait, not a completion promise.
- Empty dates receive a deterministic no-recorded-activity account without model calls or success notifications. This does not claim the user did no work.

Inputs are the registered project/stream worklogs, **including archived scopes**. Raw AI transcripts, arbitrary repository files and project notes are not read. UUID-based paths, no-follow file access, single-link/ownership checks, byte bounds and strict parsing protect managed state. Daily source packets have no fixed aggregate size cutoff and are never silently truncated; the complete day's events go to drafting and review. Individual file byte bounds remain in place. Incomplete lines and malformed sources fail closed. Provider context limits and the existing process deadlines still apply; context/deadline failures leave the date pending rather than publishing a partial account. A conservative obvious-secret detector blocks suspicious input; it is **not a complete secret/privacy scanner**. Ordinary worklog prose is processed by the configured Codex subscription provider, as in normal Pi work.

## Generation and checks

The existing managed Pi package runs `openai-codex/gpt-6.1-sol` with medium reasoning. Sessions, agent tools, extensions, skills, templates and project context discovery are disabled; the normal existing login resolves authentication. There is no NanoGPT call or provider fallback. Pi may perform normal bounded provider transport retries within a 180-second process deadline.

1. Draft structured JSON with explicit source IDs and plain-language project sections.
2. Validate schema, reference existence and representation of every active source scope.
3. A **separate fresh Codex invocation** compares the draft against the source packet. Explicitly guard the observed finance error: absence of a reconciliation event is not evidence of unfinished reconciliation.
4. If revisions are needed, allow one correction plus a second review: at most four Pi invocations per date attempt, each bounded to 180 seconds.
5. Re-read the selected source events before publication. Changed sources defer the day rather than publishing against stale input.
6. Publish Markdown and source metadata together with Linux atomic no-replace directory rename. A concurrent or pre-existing account is never overwritten.

An automated same-model reviewer can miss errors. A passed check is **not** independent factual verification or a guarantee of all claims. The renderer labels that limitation. There is no claim of live deployment verification. Source IDs, paths, line numbers, timestamps and hashes preserve traceability without copying complete source logs.

Unresolved reviews remain private under state `pending/DATE/` and do not become completed archive days. State also keeps the **latest 90 attempts**, with start/finish times, outcome/reason code and bounded reviewer feedback (at most two reviews, ten 500-character issues each). Each completed review is checkpointed immediately, so history survives later retries/success or interruption during a correction. Interrupted attempts retain an explicit unknown-outcome observation rather than a fabricated finish time. No per-attempt raw draft/transcript copy is made. Obvious secret patterns in review feedback are withheld, though this is not a complete secret scanner. Only safe reason codes go to the journal, never reviewer text, raw exceptions or worklog payloads. Successful model reasoning/event streams are temporary, private and discarded. Existing Codex auth can be refreshed normally; no key is copied into the store or another credential directory.

## Storage and notifications

- Archive: `$XDG_DATA_HOME/command-center/roundups/YYYY/MM/YYYY-MM-DD/{roundup.md,sources.json}`.
- Private retry/review/notification state: `$XDG_STATE_HOME/command-center/roundups/`.
- Directories 0700; files 0600. This is local storage, not an independently configured backup.
- A normal Mako desktop notification says which dates are ready, never includes achievement text or personal details. Catch-up successes are combined. No window opens or focus changes, and do-not-disturb remains respected.
- No notification server: leave success notifications queued for a later invocation. A server-accepted notification is recorded as sent; that is not proof the user saw it. A crash after server acceptance but before state persistence can cause a duplicate; no exactly-once delivery claim.
- Persistent failures produce a generic attention notification at most once per local day. No repeated hourly popup barrage.

Late-written historical events are not silently folded into an existing roundup. A deliberate correction should preserve prior artifacts under a revision before replacing them; that manual process is outside this initial generator.

## Commands and checks

```console
command-center-roundup run
command-center-roundup status
command-center-roundup schedule-retry  # service stop hook; normally automatic
command-center-roundup test-notification
```

`--config PATH` supports isolated fixture runs. Normal configuration is Home Manager's `~/.config/command-center/roundup.json`. Test notification is visible only when explicitly invoked; unit/package tests mock notifications and models.

Package checks cover time boundaries/DST, multi-day catch-up, empty days, correction/rejection, failed/offline calls, differentiated retry deadlines from completion, daily budgets, on-demand timer arming/stopping, bounded private attempt history, concurrent execution/publication, source changes, malformed files, symlink/hardlink/FIFO containment, permissions, deferred notifications and actual-model/no-tool enforcement.

The service sandbox makes the source root read-only and allows writes only to the archive, private state and existing Pi auth directory (atomic OAuth refresh needs the containing directory). Nix-managed Pi files resolve into the read-only store. This is not an OS sandbox against all same-user processes; model tools are disabled rather than entrusted with system access.
