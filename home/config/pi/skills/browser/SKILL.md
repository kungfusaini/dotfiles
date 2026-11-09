---
name: browser
description: Use the Microsoft Playwright CLI through pi-browser for browser navigation, DOM/accessibility inspection, clicks, forms, screenshots, tabs, persistent profiles, visible sessions, manual-login handoff, or attaching to an existing browser. Covers tool mechanics across workflows; AGENTS.md defines behavior and permissions.
---

# Browser tools

`pi-browser` is the packaged Microsoft Playwright CLI with a Pi-session-specific
workspace, cache and command lock. It supports headless and headed browsing,
persistent profiles, and attachment. Behavioral rules live in `AGENTS.md`.

## Commands and observation

```bash
pi-browser --help
pi-browser open --help
pi-browser open http://localhost:3000
pi-browser snapshot
pi-browser fill e3 'Example text'
pi-browser click e4
pi-browser screenshot
```

Snapshots are inline YAML or a reported file containing element refs such as `e3`.
Refs represent the DOM at snapshot time; a new snapshot obtains current refs.
`find 'text'` and `snapshot --depth=4` produce smaller views. Pi's `read` tool reads
snapshot files and displays screenshot images.

```bash
pi-browser paths
```

`paths` returns absolute `session`, `artifacts` and `temporary` directories.
Reported relative artifact paths resolve against `session`, not the shell cwd.
Config/profile inputs resolve against the shell cwd; absolute paths work for all
file arguments. Other relative file arguments resolve against `session`.
Use `--` before dash-prefixed positional text: `pi-browser fill e3 -- '--help'`.

## Browser modes

```bash
# Default: temporary, headless Nix Vivaldi.
pi-browser open https://example.com

# Visible browser through the workspace launcher.
project-workspace-exec pi-browser open --headed https://example.com

# Native headed defaults reuse the same agent profile across chats.
project-workspace-exec pi-browser open --headed --persistent https://example.com

# Explicitly isolated temporary browser (no saved human logins).
project-workspace-exec pi-browser open --headed --no-persistent https://example.com

# Explicit profile path; the same path can be reused by a later Pi session.
project-workspace-exec pi-browser open --headed --profile=/absolute/profile https://example.com

# Explicit configuration, including alternate browser/launch/context settings.
pi-browser open --config=/absolute/config.json https://example.com
```

Native headed defaults (with or without `--persistent`) reuse
`$XDG_STATE_HOME/pi-browser/shared-profile` across chats. This profile starts Dark,
using the bundled Chromium interface: no Vivaldi left panel or bottom status bar;
tabs/address bar and the packaged extensions remain.
`--no-persistent` explicitly uses a temporary profile. Headless defaults remain
temporary and isolated; headless `--persistent` stays session-local. Explicit
`--config` retains its own profile semantics and does not select the shared default.
`--profile` selects an explicit profile path. A profile can only be open in one
browser process at a time; an occupied shared profile fails, never silently
replaces another agent's browser or falls back to a fresh signed-out profile.
Use the owning chat, or explicitly authorize a separate isolated browser. Reusing
a profile does not grant access to its other authenticated tabs or vault.
No cookies are imported and everyday Vivaldi is untouched.
The default config selects Nix Vivaldi with its Chromium sandbox enabled; explicit
configs select their own browser/launch settings. Native headed Vivaldi is launched
with its own temporary loopback debugging endpoint, then connected to the pinned
official Playwright daemon/CLI. Headless mode uses the same Vivaldi executable with
`--disable-vivaldi` to bypass the custom UI bootstrap. Headed defaults also use
`--disable-vivaldi`, plus `--force-dark-mode`, for the tested Chromium interface.
The Vivaldi executable, shared profile, sandbox and extensions are unchanged;
there is no cookie/profile migration or new automation backend. Existing windows
keep their launch mode until explicitly reopened; never restart another chat's
browser merely to apply the default. The adapter selects the exact task tab, not a restored unrelated tab.
Vivaldi needs an initial rendered frame before native UI automation is ready; a
completely hidden workspace can delay startup. This does not require focusing its
window. Session diagnostics are private `vivaldi.log`/`daemon.log` files.
Native launch fields are `executablePath`, `headless`, `chromiumSandbox` and `args`;
other launch fields fail explicitly. Native custom configs use JSON; INI configs
are forwarded unchanged to upstream without this native-launch adapter. Malformed
JSON fails before launch. Native context/device emulation and init
callbacks are not applied to existing CDP contexts, so those settings are rejected
rather than silently ignored; headless mode retains upstream support. External
endpoints retain upstream behavior.
`--idle-timeout=<milliseconds>` controls CLI-session inactivity (`0` disables it).
For native headed sessions it disconnects automation; `close` stops the owned
Vivaldi process.
Upstream defaults headless sessions to one hour; headed sessions do not idle-close.
The workspace launcher verifies window mapping; daemon registration can follow a
moment later. `pi-browser list` reports session readiness before page commands.

`open` refuses to replace a live owned headed browser, even when requesting a
headless open. For an existing manual browser, use `connect` only after human
handback. For an already connected browser, use task-authorized `goto` or `tab-new`
instead of reopening it. Navigating changes its page. Deliberate replacement needs
an authorized `close` first; do not close/reopen merely to get around this guard.
Untracked headless/external session behavior is unchanged. A running headed
session can be used directly by a human: login or other manual actions take effect
in the same page/context. No cookie export is needed.
After manual interaction, `pi-browser snapshot` observes the resulting page and
the usual click/fill commands operate in that same browser.

## Manual handback with preauthorized localhost debugging

```bash
# Dedicated browser: localhost debugging enabled, no agent attached before handback.
project-workspace-exec pi-browser open --headed --manual --persistent https://mail.google.com/

# After explicit handback; no native Allow click is needed in the default mode.
pi-browser connect

# Optional per-connection native approval instead of preauthorized debugging.
project-workspace-exec pi-browser open --headed --manual --native-consent https://example.com
```

Sumeet explicitly approved always-authorized debugging for the dedicated agent
browser. It starts a standard server bound to `127.0.0.1` on a nonzero OS-selected
port. **Any local program able to reach it can control the signed-in browser
without another Allow prompt**, even after Pi detaches. This is not a security
sandbox. Everyday Vivaldi/profile is unchanged; do not enable this mode on other
browsers/profiles without authorization or share its endpoint.

`--manual` means **no agent attachment/page observation until handback**, not
"debugging disabled". Pause all browser actions/observations during human login,
vault unlock or credential entry, despite the server already being enabled.
`list` reports manual/not connected with `debugging: preauthorized`; page commands
refuse until handback. Startup verifies PID/start, listening-socket ownership,
loopback address and endpoint identity. Port conflicts fail closed. No native
checkbox/dialog is automated, and native preferences are not overwritten.

`connect` returns JSON status, without restarting or navigating the task page:

- `connecting`: the default preauthorized-mode daemon is starting. Retry with a
  bounded wait after handback; no native permission action is required.
- Only with `--native-consent`, `enable-debugging`: the native `vivaldi://inspect/#remote-debugging` page is open.
  Its **Allow remote debugging for this browser instance** checkbox belongs to the
  human, not the agent.
- Only with `--native-consent`, `approve-connection`: a background request is pending. Vivaldi's native
  **Allow remote debugging?** dialog requires human confirmation.
- Only with `--native-consent`, `awaiting-approval`: that request is still pending. It has no automatic expiry;
  there is no need to poll while the human uses the browser.
- `connected: true`: a later `connect`, after explicit handback, selects the single
  HTTP(S) tab matching the original task origin. Missing/ambiguous task tabs fail
  closed. Output contains only the origin, never page content or raw CLI metadata.
- `connected: true, reused: true`: an additional `connect` on this chat's existing
  approved runtime connection reuses it after browser/profile ownership, daemon
  PID/start and endpoint checks. It creates no debugger WebSocket, permission
  request, tab, navigation or page observation, and does not change the task.
  Owned endpoint version metadata may be checked.
  This is connection metadata, **not** a page-health or task-success check. A dead,
  changed or detached connection fails closed; it is never silently reconnected.

Keep the owned browser/connection open between authorized operations to avoid
unnecessary new prompts. This reuse is scoped to the owning Pi chat, not automatic
cross-chat access. Default preauthorized connections need no Allow prompt, including
new connections after a browser restart. New connections in `--native-consent`
mode still need approval; never automate its checkbox/dialog.

The browser PID, profile, page and login stay unchanged. No cookies are copied,
exported or imported. Automatic snapshots are disabled in this manual handoff connection;
explicit `snapshot` remains available for authorized tasks. Native permission grants
browser-wide debugging capability, not a hard tab-only sandbox; task scope and
password-manager rules still apply. `close` stops only the owned browser/daemon;
`detach` releases them without deleting profiles or closing the browser. The
preauthorized debugging server remains enabled until that browser exits.

Preauthorized mode validates the owned HTTP `/json/version` endpoint and selects/
activates the exact existing task tab, without global desktop input or focus.
It never probes foreign listeners or falls back to native approval on failure.
The opt-in native-consent mode instead reads its owned `DevToolsActivePort` direct
WebSocket; that endpoint has no HTTP version route. Existing windows retain their
launch mode until explicitly reopened. Real provider acceptance still needs human
confirmation; synthetic tests do not establish it. Everyday Vivaldi is untouched.

## Popup compatibility and legacy custom interface

The managed Chromium-interface default passes the local popup/image, navigation,
native-consent/reconnect and synthetic profile/extension persistence tests. This
avoids the reproduced `window.open('')` + `document.write()` freeze in Vivaldi's
custom interface; it is not an engine patch or proof of every website workflow.
An explicit `--config` that restores the custom Vivaldi UI retains that known
popup stall, including possible blank pages and reconnect failure. Do not select
that legacy interface for popup-dependent automation. The internal UI switch is
version-pinned; upgrades require the private acceptance suite again.

Saved sign-ins are separate from debugging mode. Default preauthorized connections
need no native approval; opt-in native-consent connections still require it. Real Google/Bitwarden login outcomes still need human
confirmation. Never repeat a submission whose dispatch/outcome is unknown, equate
process/listener liveness with page health, remove request/file policy, or restart
an existing browser without authorization. Known upstream routed-popup limitations
are not declared solved. Tests and comparison evidence are in the packaged
`share/doc/pi-browser/README.md`.

## Bitwarden in native Vivaldi

The managed native browser includes the official Bitwarden extension, pinned by
Nix, under its normal Chrome extension ID `nngceckbapebfimnlniiiahkandclblb`.
It is available from the browser's Extensions menu; the popup entry is
`chrome-extension://nngceckbapebfimnlniiiahkandclblb/popup/index.html`.

The extension starts with that profile's own account state. A persistent profile
retains its Bitwarden sign-in/settings; a fresh temporary profile does not inherit
the everyday browser's vault or login. Bitwarden Desktop being logged in does not
automatically sign in the browser extension. The shared headed profile retains
its own Bitwarden sign-in across chats and restarts, subject to Bitwarden's normal
session rules. Signed in is not unlocked: normal locking, organization policies,
explicit logout and session revocation still apply. Never change vault timeout or
read extension account/vault storage to implement persistence; Sumeet handles
login and unlock manually. See [Bitwarden's lock versus logout guide](https://bitwarden.com/help/vault-timeout/).

A per-profile native-messaging manifest points to the packaged Bitwarden Desktop
proxy. Desktop integration/unlock features still require Bitwarden's own settings
and permission prompts; nativeMessaging is not granted automatically. Existing
user/app-owned native-host manifests are preserved. Extension updates are Nix
package updates, not profile copying or runtime installation.

## Existing-browser attachment

```bash
pi-browser attach --cdp=http://localhost:9222
pi-browser attach --endpoint=ws://localhost:3000/playwright
pi-browser attach --extension=chrome
pi-browser detach
```

CDP requires an existing debugging endpoint. Extension mode requires the official
Playwright browser extension and a supported browser; its connection UI may need
manual confirmation. These commands do not install an extension, enable debugging
or copy profiles. Chrome/Edge extension support is documented upstream; Vivaldi
extension compatibility is not established here. Vivaldi launch and CDP attachment
are tested independently of extension mode. CDP/extension connections can access the
attached browser's authenticated pages, not just a fresh isolated profile.
`detach` releases an attachment without closing its browser. For a managed headed
Vivaldi this explicitly hands process ownership back; later `close` does not kill
that detached browser. Use a concrete
endpoint rather than an upstream named-session attachment across private caches.

## Tabs, state and lifecycle

```bash
pi-browser tab-list
pi-browser tab-new https://example.com
pi-browser tab-select 0
pi-browser console
pi-browser requests --static
pi-browser eval 'document.title'
pi-browser close
```

`state-save /absolute/state.json` and `state-load /absolute/state.json` export/import
authentication state; these files may contain credentials. `run-code` executes a
Playwright snippet. Upload, evaluation and network inspection use the process's
normal file/network permissions; this wrapper is not a sandbox.

Pi supplies `PI_SESSION_ID` (or `PI_SESSION_FILE`) for browser ownership across shell
calls and cwd changes. Artifacts, caches and automation ownership stay session-local;
only the native headed default profile is shared across chats. `close` stops this
session's owned browser and removes its temporary profile; persistent profiles
and artifacts remain. `delete-data` refuses the shared sign-in profile; it can
remove the session-local headless persistent profile, not explicit profiles. Global close/kill
commands and runtime installation are unavailable: package installation is Nix-managed.

Upstream reference: https://github.com/microsoft/playwright-cli
