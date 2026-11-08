# Weekly agent techniques

A short-lived, declaratively managed Sunday 09:00 Europe/London discovery job. `Persistent=true` catches a missed timer after login/resume, without waking the laptop. This replaces automatic historical retries; historical curation remains paused.

## Operation

- Fetch one public r/PiCodingAgent Atom listing (up to 100 posts), select at most 50 unseen posts since the last covered successful cutoff, and read at most two thread feeds with three-second spacing. At most eight bounded comment excerpts per thread. First run starts with seven days, not all history.
- One pending failed thread may be revisited on a later weekly run. Unrequested comments remain explicit coverage gaps, not an unbounded crawl queue.
- 403/429 stops further Reddit fetching immediately. Honor an advertised Retry-After even if it extends beyond the next run. No same-week retry, alternative identities, logged-in browser, JSON fallback or tight loop. HTML error bodies do not count as feeds. RSS availability is not guaranteed; unsupported access is a visible failure, not success.
- A weekly attempt marker is written under a process lock **before** work. A crash consumes that scheduled week's attempt. Sunday-to-Sunday keys let Monday catch-up and the next Sunday both run once; duplicate manual starts do not create more model calls.
- One fresh, named, persisted Pi SDK session uses the managed `openai-codex/gpt-6-luna` subscription at low effort. No tools, extensions, skills, context-file discovery, custom models, automatic retries or compaction. One inference invocation, provider retries disabled, SSE-only transport (no WebSocket fallback), cache warming disabled, 150 KB UTF-8 serialized-input cap, 240-second model subprocess timeout, eight-minute service cgroup timeout. Request `maxTokens=4096`, but the current Codex adapter does not enforce this field: it is **not a hard provider token cap**. Cancel best-effort after 24,000 streamed text/thinking characters; unreported reasoning and in-flight output can exceed that observation. Call/runtime/input bounds limit work but do not guarantee an allowance percentage. Provider-side/in-flight accounting is not controlled by local timeouts.
- An explicit resource loader supplies a fixed instruction and quoted public sources. The model cannot fetch arbitrary links, execute source commands, edit files or assign user intent. The deterministic host validates source IDs, related IDs, field lengths and schema and escapes model Markdown.

## Outputs and limits

Candidate ideas and a readable digest live at:

`~/matrix/projects/agent-techniques/weekly/<scheduled-Sunday>/`

These are **machine-selected, source-reported candidates**, not promoted/verified technique entries. Related IDs group duplicate/enriching ideas with existing curated entries or earlier candidates; existing `techniques/` notes and personal intent are never rewritten. No automatic Git commits or external publications. No durable linked-code verification or social popularity claim is inferred from RSS excerpts.

The deterministic ledger at `~/.local/state/agent-techniques-weekly/` records weekly attempts, cutoff, seen IDs, pending failed comments, gaps and per-run manifests. Listing/input limits leave the cutoff unadvanced; a busy feed can outrun bounded discovery and is flagged for review rather than called complete. A model failure does not mark sources seen or advance the cutoff. Publications are no-overwrite files; an interrupted publication may be partial and remains visible for review. Invalid local state fails closed. No model calls for no eligible posts or a blocked listing.

Session transcripts live under the ordinary usage-tracker import pattern:

`~/.config/pi/agent/sessions/--agent-techniques-weekly/*.jsonl`

They preserve prompts/source excerpts, replies, usage and errors for later **on-demand** agent-quality analysis; no analyser is scheduled. Usage tracker imports ordinary Pi logs on its existing hourly schedule. Other clients affect account-wide quota, so a quota delta is not exclusively this job. The transcript is private; do not publish it. Runtime state is not a Git artifact or a credential backup. No credentials are copied; normal Pi OAuth resolution/refresh uses its existing auth registry. Subscription unavailability fails without an API-key fallback. The runtime is not a sandbox against arbitrary host-code compromise; the model itself has no execution tools.

## Commands

```sh
agent-techniques-weekly status
systemctl --user list-timers agent-techniques-weekly.timer
journalctl --user -u agent-techniques-weekly.service -n 20 --no-pager
```

`agent-techniques-weekly run` is an intentional manual attempt under the same weekly gate, **not** a force/retry option. Never delete state just to force a retry; investigate or obtain separate authorization. The timer has no retry hook or startup polling interval. Read `weekly/<date>/digest.md` for results; no desktop windows are opened.

A service stop hook sends one normal desktop notification per recorded weekly outcome: candidate count and digest location on success, an explicit no-new-ideas message for an empty result, or blocked/failed/interrupted status without claiming a digest exists. It respects Do Not Disturb, contains no prompts, account details or source snippets, and never runs the model. Blocked, failed and interrupted runs have distinct safe messages. The hook checks that a notification daemon already owns the bus name; it does not launch one or mark unavailable/failed delivery as sent. Delivery errors are journalled but do not turn a successfully completed scan service into a failure. Deduplication is saved only after `notify-send` succeeds; this acknowledges delivery to the daemon, not that the human read the notification. `agent-techniques-weekly notify` retries only this delivery, not collection or inference.

## Validation

Python standard-library tests use temporary files and synthetic feeds; JavaScript tests use a fake SDK, no provider/network. `default.nix` runs both. A live deployment check must separately verify the installed unit/calendar and actual source/provider access; unit tests do not establish Reddit reliability or allowance accounting.
