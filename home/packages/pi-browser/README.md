# Pi browser automation

`pi-browser` runs Microsoft's official `@playwright/cli` 0.1.23 with its locked
Playwright 1.65.0-alpha-2026-10-30 dependency and **Nix-managed Chromium**.
[Upstream CLI](https://github.com/microsoft/playwright-cli) is Apache-2.0.
The alpha dependency is pinned; upgrades require real-browser acceptance.

## Responsibilities

- **Skill:** command syntax and capabilities.
- **AGENTS.md:** authorization, manual login/handback, workspace placement,
  authenticated scope, privacy and cleanup behavior.
- **Wrapper:** packaging, private state, ownership, serialization and launch
  defaults. It is not a security sandbox or an alternative workflow policy.

## Downloads and the Chromium migration

The former Vivaldi backend with `--disable-vivaldi` passes popup tests but fails
local HTTP attachment, blob and sandboxed-frame downloads: no download events or
files, even with explicit CDP `allowAndName`. Restoring Vivaldi's full UI plus
automatic-download preferences permits those files, but reintroduces the known
popup/debugger stall and did not pass private no-focus acceptance. A download
permission toggle alone is therefore not an accepted fix.

Installed Chromium passed the same dummy HTTP attachment test headlessly, and
HTTP/blob/sandbox downloads before and after headed attachment. The adopted fix
uses Chromium directly, not a custom downloader, stealth patch, weakened sandbox
or second automation library. The exact internal Vivaldi defect is not established.
Google Takeout's observed HTTP404 is separate; these tests do not prove that its
export link or any real authenticated export now works.

[Playwright supports Chromium](https://playwright.dev/docs/browsers); the Nix
browser executable remains separately version-pinned by the flake rather than
runtime-installed by Playwright. This still needs local compatibility acceptance.
[Downloads](https://playwright.dev/docs/downloads) should use the page's download
event and `saveAs()` for a durable destination, awaiting completion before close.
Before agent attachment, manual Chromium uses its ordinary native Downloads
behavior. After attachment, owned daemons use Playwright's normal accepted-download
storage/events so `saveAs()` works. A version-pinned, fail-closed patch changes only
`acceptDownloads` for owned CDP daemons, retaining `noDefaults` (no emulation/init
changes). The wrapper strips inherited `PI_BROWSER_OWNED_DOWNLOADS`; it sets it only
on its own native daemon launches. External attachments keep upstream defaults.
Automatic CLI copies live under the session artifacts; use `saveAs()` for the
approved durable/private destination. No account/site security policy is changed.

**Profile boundary:** new native headed defaults share
`$XDG_STATE_HOME/pi-browser/shared-chromium-profile`. The old Vivaldi
`shared-profile` remains intact, is not copied/imported, and is refused as an
explicit launch profile or `delete-data` target. New website/Bitwarden sign-ins
are required. This backend/profile change was explicitly approved. Do not silently
reuse a different profile for future authenticated tasks. Headless persistent
profiles now use `session/profile-chromium`, leaving old `session/profile` intact.
The legacy `vivaldi-process.json`, `vivaldi.log` and `pi-vivaldi-*` placement class
are intentionally retained so existing browser ownership is not stranded.
Deployment never restarts or attaches to an existing browser. Already-running
Vivaldi windows do not acquire the fix; coordinate their replacement separately.
An old manual browser awaiting its first connection may need its original packaged
launcher because its executable differs; do not restart it as a workaround.
Fresh Bitwarden installation can asynchronously open its welcome tab; this is not
an account/login failure. Synthetic tests wait for that first-install tab and
return to the fixture after handback without reading extension/vault storage.

## Modes and ownership

```sh
pi-browser open http://localhost:3000
project-workspace-exec pi-browser open --headed https://example.com
project-workspace-exec pi-browser open --headed --persistent https://example.com
project-workspace-exec pi-browser open --headed --no-persistent https://example.com
project-workspace-exec pi-browser open --headed --profile=/absolute/profile https://example.com
pi-browser attach --cdp=http://localhost:9222
pi-browser detach
```

Defaults are temporary headless Chromium with its sandbox enabled, or native
headed Chromium with the new cross-chat profile and `--force-dark-mode`. Packaged
extensions include Bitwarden and the Project Object bridge. Everyday Vivaldi and
its profile/debugging settings are unchanged. Neither cookies nor vault state are
copied. `--no-persistent` selects a temporary headed profile; headless persistence
is session-local. Explicit `--config` retains its own settings and profile semantics.

The native adapter launches an owned process with loopback CDP, then the pinned
Playwright daemon. It selects the exact task target, not an unrelated restored
tab. The immediately connected path first creates an inert bootstrap target and
navigates only after upstream file/network policy is configured. Exact-class
workspace rules suppress initial focus and activation, and are released on
close/detach. No global focus repair or desktop input is used. Internal daemon
entry points are pinned; package unit tests alone do not validate an upgrade.

Ownership checks use PID/start, profile lock and endpoint identity. A live
profile fails closed; the startup lock also covers the check-to-launch gap.
`open` refuses to replace a live owned headed browser, including with headless
open. Use `connect` after handback, or task-authorized `goto`/`tab-new` if connected.
Deliberate replacement requires explicit authorization and `close` first.
`close` stops only the owned browser/daemon; temporary profile cleanup requires
verified shutdown. Explicit/shared profiles remain. `detach` releases ownership
without closing the browser. Later `close` does not kill that handed-back process.
`delete-data` removes only the current session's `profile-chromium`, not explicit,
shared or legacy profiles. Global close/kill and runtime install are refused.

Custom native JSON configurations support `executablePath`, `headless`,
`chromiumSandbox` and `args`. Unsupported launch fields, sandbox disabling,
`contextOptions`, device/mobile emulation and init callbacks fail rather than
being silently ignored on an existing CDP context. Headless/external endpoints
retain upstream support. INI configs require an explicit checked `--profile` (which upstream prioritizes
over config `userDataDir`) before forwarding unchanged, so opaque INI settings
cannot open the retained Vivaldi profile. Use JSON for profile-free configurations.
Malformed JSON fails before launch. Config/profile paths resolve from the caller cwd; other
relative paths resolve from the private session directory.

## Human-first login and connection

For new assisted sign-ins, launch without agent attachment:

```sh
project-workspace-exec pi-browser open --headed --manual --persistent https://mail.google.com/
# After explicit human handback, without reopening the browser:
pi-browser connect
# Optional per-connection native consent instead of preauthorized debugging:
project-workspace-exec pi-browser open --headed --manual --native-consent https://example.com/
```

Sumeet approved the dedicated agent browser's preauthorized debugging server.
It binds `127.0.0.1` on a nonzero OS-selected port. **Any local program reaching
that server can control the signed-in browser without another Allow prompt.**
This is not a security sandbox. It stays enabled after detach until browser exit.
Everyday browsers must not be exposed this way without separate authorization.

`--manual` means no agent attachment/page observation before handback, not no
debugging server. Stop all actions/capture/traffic inspection during credentials,
MFA or vault interaction. Do not inspect filled fields or extension storage.
Manual page commands refuse until `connect`; automatic handoff snapshots are
disabled by a fail-closed, version-pinned patch. Explicit snapshots are supported
for authorized tasks after handback. A plain headed open is immediately connected
and is not a substitute for manual launch.

Preauthorized startup verifies PID/start, listening-socket ownership, IPv4
loopback binding, bounded version metadata and WebSocket identity. Foreign/wildcard
listeners, changed identities and port races fail without fallback. Nonzero CDP
ports retain unmodified `navigator.webdriver=false` in the synthetic manual
suite; there are no webdriver/UA overrides. See [MDN's documented flags](https://developer.mozilla.org/en-US/docs/Web/API/Navigator/webdriver)
and [Chrome's separate-profile debugging guidance](https://developer.chrome.com/blog/remote-debugging-port).

`connect` returns `connecting` until the daemon is ready, then `connected:true`
and the validated task origin. It selects the single matching HTTP(S) task tab
without navigation/restart or unrelated page capture. Ambiguity fails closed.
Repeated connects reuse only an already-approved live owned daemon, returning
`connected:true,reused:true` without a new connection, tab command or page read.
That is connection metadata, not page-health/account/task verification.

Opt-in `--native-consent` instead starts without startup debugging. If needed,
`connect` opens `chrome://inspect/#remote-debugging` and returns `enable-debugging`.
The human enables the checkbox; a later connect requests the native Allow dialog
and returns `approve-connection`/`awaiting-approval`. Never automate native
permission UI in production. The owned direct WebSocket comes from the validated
`DevToolsActivePort` marker. Denial leaves the same browser/profile intact, with
no automatic retry. See [Chrome's runtime consent design](https://developer.chrome.com/blog/chrome-devtools-mcp-debug-your-browser-session).

The earlier real Cloudflare success was observed on Vivaldi using human-first
manual launch, handback and same-browser connect. It does not establish provider
acceptance on Chromium. Do not promise a challenge bypass, repeatedly submit a
form of uncertain outcome, or infer account success from listener/process liveness.

## Bitwarden and Project Object

The Nix Chromium wrapper loads the official pinned Bitwarden
`dist-chrome-2026.10.2.zip` and the Project Object extension in one load list.
Bitwarden's public manifest key preserves ID
`nngceckbapebfimnlniiiahkandclblb`. The release hash, ID, version and MV3 manifest
are build-checked. [Official release](https://github.com/bitwarden/clients/releases/tag/browser-v2026.10.2)
and [Chrome extension identity](https://developer.chrome.com/docs/extensions/reference/manifest/key).
No runtime extension installation, copied vault storage or personal profile.

Before native launch, the profile's `NativeMessagingHosts/com.8bit.bitwarden.json`
gets an immutable link to the packaged Desktop proxy manifest. Only Bitwarden's
exact origin is allowed; existing user/app-owned manifests are preserved and
redirected directories refused. [Linux native host registration](https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging).
Optional nativeMessaging permission and Desktop integration/unlock require the
normal human prompts. Tests never invoke the real proxy or inspect a vault.
Persistent profiles retain their own extension state, subject to normal
[lock/logout rules](https://bitwarden.com/help/vault-timeout/); signed in is not
unlocked. Never alter vault timeouts or security settings to keep a session alive.

## Session mechanics and verification

`PI_SESSION_ID` (or `PI_SESSION_FILE`) selects private session state beneath
`$XDG_STATE_HOME/pi-browser` (default `~/.local/state/pi-browser`). CLI caches,
artifacts, command locks and automation ownership are session-local; only headed
defaults deliberately share the Chromium profile. `pi-browser paths` reports
session/artifacts/temporary paths. Short `/run/user/$UID/pib/` runtime directories
avoid Chromium's Unix-socket length limit. Artifacts/profiles may be sensitive.
Inherited Playwright/MCP endpoint settings are removed so attachment is explicit.
Personal global CLI configuration is replaced by a session-private global-config
directory, preventing inherited profile settings from selecting old authentication.
Update checks, Playwright browser installation and automatic Vivaldi codec updates
are disabled; website file downloads are **not** disabled. All dependencies are
Nix-store packaged, never runtime dependencies on this checkout.

- `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v`: unit checks including legacy profile
  protection, shared/headless separation, launch ownership and endpoint validation.
- `python3 tests/integration.py /nix/store/.../bin/pi-browser`: real headless
  interaction, isolation, persistence, HTTP/blob/sandbox byte-checked downloads,
  explicit configs and external CDP detach.
- `headed_integration.py`: native immediately connected launch, packaged extension
  metadata, sandbox flags, login continuation and byte-checked downloads.
  `PI_BROWSER_TEST_SHARED=1` tests the actual new shared default across chats,
  synthetic extension storage persistence, collisions and delete-data refusal.
- `manual_integration.py`: human-first launch/handback, same-process connection,
  repeated connect/open guards, unmodified webdriver and byte-checked downloads
  under the untouched configured policy. `PI_BROWSER_TEST_POPUP=1` adds popup/image
  and navigation regression; `PI_BROWSER_TEST_RECONNECT=1` adds same-process
  detach/reattach; `PI_BROWSER_TEST_SHARED_RUNTIME=1` reuses a synthetic profile
  across chats/restarts. `PI_BROWSER_TEST_DIRECT=1` tests immediate connection.
  `PI_BROWSER_TEST_NATIVE_CONSENT=1` plus `--wtype /absolute/wtype` tests optional
  native consent; `PI_BROWSER_TEST_DENY_FIRST=1` adds denial/renewed approval.

Headed suites reuse `project-object/tests/workspace_exec_integration.py` with
`--harness`, `--hyprland`, `--hyprctl`, `--labwc`, `--kitty`, `--chromium` (carrying
pi-browser), `--helper`, `--browser-class vivaldi` (legacy placement class) and
`--keep-target-visible`. They use a private headless compositor/DBus, fresh HOME
and synthetic profiles, never host input or real accounts. Focus and placement
assertions remain active outside explicitly bounded private synthetic consent.
Real sign-ins and authenticated downloads still need human handback and task scope.
