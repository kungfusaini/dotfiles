# Pi model discovery

A Home Manager systemd **user** timer (`pi-model-discovery.timer`) checks the
Codex subscription catalog daily, with up to five minutes of jitter and persistent
catch-up after a missed run. It does not wake a sleeping laptop. Execution depends
on the user manager, which may remain running after logout if lingering is enabled.
No persistent checker process is needed.

`pi-model-discovery check` performs one bounded authenticated GET. The endpoint
and client headers follow the upstream [Codex models client](https://github.com/openai/codex/blob/main/codex-rs/codex-api/src/endpoint/models.rs).
The client version comes from the Nix-packaged Codex version. This is an internal
subscription endpoint, not a promise of a stable public API. Discovery is currently
implemented only for `openai-codex`; other mode providers are explicitly reported
as unsupported. Pi's bundled Codex provider is a static catalog, so listing Pi's
models alone cannot discover provider additions. No new dependency beyond Python
stdlib is used.

## Privacy and failure handling

- Reads Pi's existing `auth.json` (honors `PI_CODING_AGENT_DIR` and XDG paths).
- Never logs, copies, refreshes, rotates, or writes credentials.
- No inference requests, paid trials, mode changes, policy edits, or deployments.
- Redirects are rejected; network timeout is 20 seconds and response limit is 4 MiB.
- Only allowlisted catalog metadata is written atomically to
  `$XDG_STATE_HOME/pi-model-discovery/catalog.json` (default
  `~/.local/state/pi-model-discovery/catalog.json`), private directory/file modes.
- Failed checks retain the last successful catalog and record a sanitized status.
  An expired token requires normal Pi authentication/refresh before a later check;
  the checker must not race Pi by rotating shared credentials.
- A catalog omission is **not proof that a model is unusable**. Internal routing,
  client versions, hidden aliases, and catalog rollout may differ from inference.

## Pi integration and review

The existing mode extension reads only this local state at startup and every minute
in the TUI. It shows a compact review/failure/staleness indicator. `/mode-review`
shows the evidence. Sessions clean up their timer on replacement/reload/shutdown.
A successful catalog older than 48 hours is stale. Failed checks remain visible
rather than appearing up to date. The four-mode picker and its key handling are
unchanged; discovering a model does not register it in Pi or alter a mapping.

Listed API-supported entries absent from the current mappings and the optional
`reviewedModels[provider]` list are **unreviewed**, not necessarily new or better.
Pinned models absent from the visible catalog and reasoning-level discrepancies
also request review. The first run can therefore flag older models or aliases.
After deliberate review, edit `home/config/pi/model-modes.json` in canonical Nix
sources. Change mappings only after validation; record retained/rejected IDs in,
for example, `"reviewedModels": {"openai-codex": ["intentionally-not-selected"]}`
and update `reviewedAt`. That allowlist suppresses candidate notices only, not
missing pinned models, reasoning discrepancies, stale data, or check failures.

## Operations

- `pi-model-discovery status`: local sanitized JSON, no network.
- `systemctl --user start pi-model-discovery.service`: immediate check.
- `systemctl --user status pi-model-discovery.timer pi-model-discovery.service`
- `journalctl --user -u pi-model-discovery.service`: sanitized result/error status.

The service is sandboxed with read-only home/system access except its private state
directory. Home Manager creates that directory via user tmpfiles.

Tests: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v` from
this package directory; extension tests: `node --experimental-strip-types --test
tests/pi-model-modes.test.mjs` from the Nix repository. Neither suite uses real auth
or makes real network calls.
