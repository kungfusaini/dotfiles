# Resume recovery — isolated prototype

**Not deployed, enabled, or imported by `default.nix`.** This directory proves a
provider-boundary approach, not a finished Pi extension or production patch.
Nothing here runs in existing Pi sessions. No extra npm dependency is needed.

## Approach

`recovery.mjs` wraps a provider stream function, retaining the ordinary provider
implementation and its request options. A sleep/wake pair invalidates only
provider requests still active at wake. A separate AbortController cancels their
transport without cancelling the parent agent or its tools. The resulting
transport cancellation becomes a retryable network error. Pi's existing
agent-level retry handles continuation, accounting and session lifecycle.

The next provider request waits for network readiness. Ordinary requests keep
their existing timeout; manual cancellation wins over automatic recovery. A
newer sleep cycle invalidates an older connectivity check. No user prompt is
injected and no tool is automatically rerun by this wrapper.

`linux.mjs` uses native Linux interfaces:

- `dbus-monitor --system` subscribes only to logind's `PrepareForSleep` signal.
  `busctl monitor` is denied on this host; dbus-monitor's ordinary AddMatch
  subscription fallback works without elevated privileges.
- `busctl get-property` reads NetworkManager state, polling only when recovery
  is waiting. SITE/GLOBAL connectivity opens the gate; local-only connectivity
  does not. This is a routing hint, **not proof that the model endpoint works**.
  Transient D-Bus/NetworkManager restart and timeout errors keep waiting without
  consuming model retries; missing executables or permission failures surface.
  Provider retry policy still handles DNS, VPN and endpoint failures.

References:
- [logind signals](https://www.freedesktop.org/software/systemd/man/latest/org.freedesktop.login1.html#Signals)
- [NetworkManager states](https://networkmanager.dev/docs/api/latest/nm-dbus-types.html#NMState)

## Run tests

Use the installed package directory, not its executable:

```sh
PI_OFFLINE=1 PI_TEST_ROOT=/nix/store/…-pi-coding-agent-0.87.1/lib/node_modules/pi-monorepo \
  node --test home/packages/pi-coding-agent/resume-recovery-prototype/{test,linux.test}.mjs
```

Tests import the installed SDK and Codex transport implementation. SDK fixtures
use temporary agent directories, in-memory sessions, no discovered resources,
no real credentials, disabled model discovery/cache warming, and synthetic
providers. Auth preflight is deliberately replaced only in the synthetic SDK
fixture. The real Codex transport tests use a fake JWT with a synthetic account,
a fake fetch, and a fake WebSocket; they never contact a provider.

Coverage includes:
- existing Pi auto-retry and final `agent_settled` after a wake interruption;
- retry held until network readiness;
- a running tool surviving wake, executing exactly once;
- incomplete streamed tool calls never executing;
- manual cancellation during streaming and during network wait;
- unchanged timeout for an ordinary slow response;
- actual Codex SSE-header and WebSocket waits cancelled promptly;
- actual Codex SSE cancellation connected end to end to Pi SDK auto-retry;
- socket disposal, duplicate notifications, parallel request isolation;
- repeated sleep cycles, parser filtering and watcher cleanup;
- network-state gating, transient service restart, permanent failures and cancellation.

All 16 tests pass on the installed 0.87.1 SDK. Independent read-only review found
that a transient NetworkManager query failure could prematurely stop recovery;
that issue was corrected and covered by a regression test.

The measured ~30–40ms synthetic wake-to-completion includes an intentional 30ms
fake offline delay and a 1ms test retry backoff. It is **not** a prediction of
real provider latency; production's normal retry backoff is 2 seconds.

## What remains before deployment

- Select a supported production integration point. Public extension
  `ctx.abort()` cancels the whole operation; payload/header hooks cannot replace
  a provider signal. The prototype wraps `ModelRuntime.streamSimple` only on
  isolated SDK instances. A narrowly scoped core integration is likely needed;
  do not monkey-patch live sessions or replace built-in provider registrations.
- Wire one lifecycle-owned listener and readiness gate into that boundary, with
  visible waiting/recovering status, guaranteed watcher cleanup, startup/reload
  race handling, initial sleep-state reconciliation and watcher failure policy.
  The prototype reports watcher failure but does not reconnect it automatically.
- Decide coverage for nested/compaction requests and idle cached sockets. The
  prototype proves active wrapped requests only. A tool's own network calls are
  intentionally untouched.
- Test real notification delivery under an isolated D-Bus service/compositor or
  separately approved real suspend. The native smoke check only established
  that the unprivileged listener stays alive and reads current network state.
- Validate the actual bundled package, not just its installed SDK modules,
  before any NixOS deployment. Then verify affected new Pi processes load it.

No machine suspend, Wi-Fi disruption, live Pi abort, deployment, or real model
request is part of these tests. Existing unrelated repository changes must remain
untouched.
