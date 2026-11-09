# Pi browser automation

`pi-browser` runs Microsoft's official `@playwright/cli` 0.1.23 with its exact
locked Playwright 1.65.0-alpha-2026-10-30 dependency and Nix-managed Vivaldi.
Upstream: https://github.com/microsoft/playwright-cli (Apache-2.0).
The published CLI pins an alpha Playwright build; upgrades require deliberate
lockfile updates and real-browser acceptance, not floating runtime installs.

## Responsibilities

- **Skill:** command syntax and capabilities across workflows.
- **AGENTS.md:** mode selection, authorization, workspace/focus, login handoff,
  authenticated-session scope, secret handling and cleanup behavior.
- **Wrapper:** Nix runtime defaults, Pi session ownership, private state, command
  serialization and artifact paths. Not a workflow policy or security sandbox.

The original headless-only design conflated these layers. Visible sessions,
persistent profiles and upstream attachment are now available without another
plugin. No browser extension or everyday-browser debugging is enabled by default.

## Modes

```
pi-browser open http://localhost:3000
project-workspace-exec pi-browser open --headed https://example.com
project-workspace-exec pi-browser open --headed --persistent https://example.com
project-workspace-exec pi-browser open --headed --profile=/absolute/profile https://example.com
pi-browser attach --cdp=http://localhost:9222
pi-browser detach
```

The managed default is temporary headless Vivaldi with its Chromium sandbox enabled.
Playwright's engine name remains `chromium`; `executablePath` selects Vivaldi.
Headless Vivaldi requires `--disable-vivaldi` to bypass its UI bootstrap. Headed
defaults now use that same internal switch plus `--force-dark-mode`, selecting the
bundled Chromium interface rather than Vivaldi's custom chrome. The executable,
profile, packaged extensions, sandbox, official CLI and native consent are retained.
The Chromium interface has no Vivaldi left panel or bottom status bar; tabs and
address bar remain. No everyday profile is reused or everyday debugging changed.
The existing shared profile is reused in place, without cookies/vault state being
copied or inspected. Its legacy Dark/hidden-bar Vivaldi preferences are still
maintained offline under the profile lock; malformed/redirected preferences fail
closed. Explicit `--config` keeps its own interface arguments unchanged. No live
Preferences file is edited and no unsupported protocol patch is introduced.

For native UI compatibility the wrapper launches an owned Vivaldi process with an
OS-selected loopback CDP port, then starts the pinned official Playwright daemon
without its implicit first-page snapshot/navigation. It selects the exact created
web target through official CLI commands, rather than capturing or navigating an
unrelated restored tab. This uses version-pinned internal daemon entry points;
upgrades require both native/headless acceptance, not just a package build.
An inert local bootstrap target is created first; the requested URL is navigated
through the official backend only after its file/network policy is configured.
Native startup waits for a rendered web target; completely hidden workspaces can
delay first-frame initialization. Hidden tests keep the target on a separate
virtual output while focus remains elsewhere. Exact per-launch class rules ensure
initial workspace placement, no initial focus and suppressed activation requests;
they are disabled on close/detach. No global focus repair is used.

Process ownership records include PID/start time and endpoint identity. `close`
sends `Browser.close` to the verified owned endpoint before a PID-checked fallback;
`detach` relinquishes ownership without terminating the native browser. Temporary
owned profiles are removed after verified shutdown; persistent and explicit
profiles are retained. Native headed defaults, with or without `--persistent`,
reuse `$XDG_STATE_HOME/pi-browser/shared-profile` across Pi chats. `--no-persistent`
opts into temporary native browsing. Headless remains temporary by default;
headless `--persistent` uses `session/profile`, never the human sign-in profile.
Explicit `--profile` and `--config` preserve their own selection semantics.
`delete-data` refuses the shared sign-in profile and removes only session-local
persistent data, not explicitly supplied profiles. Active profile locks fail
closed, with a separate cross-session startup lock covering the check-to-launch
race. No implicit attachment, profile copying or silent fresh-profile fallback.
`--headed` overrides headless mode. `open` now refuses to close/restart a live
owned headed browser (including when the new request is headless). Use `connect`
after handback for an existing manual browser, or authorized `goto`/`tab-new` on an
already connected browser. Deliberate replacement requires an approved `close`
first, not an automatic reset. Help remains available; untracked headless/external
session behavior is unchanged. A human can use the same headed browser to log in,
then hand control back; the agent continues without exporting credentials or cookies.
Workflow and permission rules for doing so live in the canonical Pi `AGENTS.md`.

Explicit `--config` files replace the generated launch defaults and can select
other browser/launch/context options. For the native Vivaldi bridge, supported
launch fields are `executablePath`, `headless`, `chromiumSandbox` and `args`;
unsupported launch fields fail rather than being silently ignored. Native custom
configs are JSON; INI configs are forwarded untouched through upstream, not
silently replaced by managed defaults. Malformed JSON fails before launch. Native
`contextOptions`, `--device`, `--mobile`, `initPage` and `initScript` are rejected:
CDP attaches an existing context, and daemon-wide init callbacks could affect
unrelated restored tabs. These features remain available in headless mode.
Other browsers
and explicit external endpoints retain upstream behavior. Configs must supply a usable executable/channel
when not using the packaged Vivaldi configuration. Config/profile paths resolve
against the invoking shell cwd. Other relative file paths resolve against the
private session directory; absolute paths work for all file arguments.

Upstream `attach`/`detach`, CDP, Playwright server endpoints and extension mode are
exposed. Extension use requires its own installed extension and supported browser;
Vivaldi launch and CDP attachment are tested; extension compatibility is not
established. Attachment retains the external
browser's own scope and ownership and may expose authenticated pages. Detach leaves
the external browser alive. No profile/cookie copying or implicit connection target.

## Preauthorized localhost debugging and manual handback

```sh
project-workspace-exec pi-browser open --headed --manual --persistent https://mail.google.com/
# After explicit human handback; no native Allow prompt in this default mode:
pi-browser connect
# Opt into per-connection native permission instead:
project-workspace-exec pi-browser open --headed --manual --native-consent https://example.com/
```

Sumeet approved always-authorized remote debugging for this dedicated agent
browser. Manual mode now launches a standard debugging server bound only to
`127.0.0.1`, but **does not attach an agent or observe pages before handback**.
New debugger connections need no native Allow click, including after browser
restart. **Reachable local programs can control this signed-in browser without
further approval**; this intentionally trades per-connection protection for the
requested convenience. It is not a hard security/tab sandbox. Everyday Vivaldi
and provider/vault security settings are unchanged. Do not expose/share the
endpoint, copy authentication data or assume this authorizes unrelated tabs.

A nonzero OS-selected developer port preserves normal manual behavior rather
than using Chromium's special `port=0` automation indicator. There are no JS,
user-agent, webdriver or stealth overrides; see [MDN's documented flags](https://developer.mozilla.org/en-US/docs/Web/API/Navigator/webdriver).
The reservation is released before Chromium binds, so startup verifies exact
PID/start, its `/proc` listening socket inode, IPv4 loopback binding and a bounded
HTTP version/WebSocket identity response. It rejects wildcard listeners, port
collisions, reused processes and changed endpoints before attaching. Cleanup
skips unowned endpoint access and stops only the owned process. No insecure
fallback or native prompt is attempted if the authorized endpoint is unavailable.
The custom agent profile follows [Chrome's non-default-profile debugging guidance](https://developer.chrome.com/blog/remote-debugging-port).

`--manual` still means no agent attachment: page commands refuse until `connect`
after explicit human handback. Stop actions, screenshots, DOM and traffic
observation while Sumeet enters credentials or unlocks a vault. Automatic snapshots
remain disabled in the handoff daemon. A new connection returns `connecting`
until ready, then only `connected` and the validated task origin. The single task
tab is selected/activated using the owned endpoint API, without navigation, a new
tab or desktop focus/input. This also handles first-install extension onboarding
tabs that can otherwise stay in front in an unfocused browser window.

Owned-window metadata and a readable waiting parent preserve verified workspace
placement. Explicit shared/profile paths, the sandbox, installed extensions and
all file/network policy remain unchanged. No native consent preference is toggled.

### Optional native-consent mode

`--headed --manual --native-consent` retains the previous no-startup-debugger mode.
Its native runtime feature is available in the pinned Vivaldi, despite third-party
channel lists naming Chrome/Edge only. `connect` verifies the exact live owned
PID/start identity and profile-lock owner. Without a marker, it opens
`vivaldi://inspect/#remote-debugging` and returns `enable-debugging`; Sumeet enables
**Allow remote debugging for this browser instance**. A later `connect` requests
Vivaldi's native **Allow remote debugging?** consent and returns
`approve-connection`. This private daemon waits without timing out or capturing
pages. After explicit handback, `connect` finalizes attachment, selecting the single
existing HTTP(S) task-origin tab. Missing/ambiguous tabs fail closed. Only this
opt-in mode asks for renewed native approval for genuinely new connections.
Its direct WebSocket comes from the owned `DevToolsActivePort`; HTTP version
requests are unavailable on that native on-demand endpoint.

### Shared handoff and reuse semantics

Further `connect` calls in that same Pi session reuse the existing authorized runtime
connection. The wrapper checks owned browser PID/start, the profile-lock owner,
recorded runtime daemon PID/start and the owned endpoint identity, then returns only
`{"connected":true,"reused":true}`. No new daemon/WebSocket, permission prompt,
CLI page command, tab selection, navigation, snapshot or origin read is performed.
It does not depend on subsequently regenerated CLI config or report the original
origin as if it were the current page. This is connection metadata, not proof of
responsive pages or task success. Missing/dead/reused daemon identity, detached
ownership or an endpoint change fails without starting a replacement connection.

Keep a live headed browser and approved daemon between authorized operations;
headed sessions already have no default idle shutdown. This reduces unnecessary
same-chat reconnects. There is no cross-chat broker or shared automation ownership.
Preauthorized mode permits fresh local debugger connections without prompts;
opt-in native-consent mode retains [Chrome's per-connection consent design](https://developer.chrome.com/blog/chrome-devtools-mcp-debug-your-browser-session).
Neither mode clicks or automates the native permission UI.

There is **no restart, new task page, navigation, cookie copying, state export or
profile import**. The browser, page and login remain live. Preauthorized endpoints
are validated through the owned loopback HTTP version API; the native-consent
mode uses its strictly validated owned marker instead.
Raw CLI stdout/stderr, code, page/title and tab metadata are captured and filtered,
not forwarded. Only status and validated origin are emitted. A version-pinned,
fail-closed CLI patch disables its hardcoded automatic snapshots only in the
private handoff daemon. Explicit snapshots still work. Non-manual modes are unchanged.

Both modes permit full browser debugging; origin selection is not a security
sandbox. In preauthorized mode, `detach` leaves the local server enabled until
browser exit; releasing Pi ownership does not revoke that local capability. AGENTS.md authorization, manual-entry pause, explicit
handback, task scope and password-manager restrictions remain authoritative.
Declining a request leaves the same manual browser/profile intact, with no automatic
retry. `close` or `detach` also terminates the exact owned pending daemon by
PID/start identity; detach releases browser/profile ownership. Existing temporary
cleanup and explicit/persistent-profile retention are unchanged.

Tests use only a private compositor/DBus and synthetic local login. They prove
default startup has no agent attachment but does have owned loopback debugging;
normal `navigator.webdriver` behavior is unmodified. Default initial/reconnections
and browser restarts pass without permission input; opt-in native mode still tests
approval/denial. Both retain PID/profile/login, interaction and metadata-only output. A synthetic Local State seed models the
checkbox; test-human permission input is bounded to the private compositor and
excluded only during explicit consent markers. Browser placement and all agent
focus events outside that interval remain checked. Address reuse no longer causes
false focus failures; all browser classes/lifetimes are checked. The same private
suite verifies that manual/connected repeated opens fail without altering browser
state and repeated connects reuse the exact approved daemon without new consent,
while subsequent interaction and the popup/reconnect regressions remain usable.

A restart-on-handoff prototype and Playwright-extension experiment were not
shipped. The optional native route follows [Chrome's runtime-consent mechanism](https://developer.chrome.com/blog/chrome-devtools-mcp-debug-your-browser-session).
See also [Google's browser guidance](https://support.google.com/accounts/answer/7675428?hl=en)
and [MDN's webdriver documentation](https://developer.mozilla.org/en-US/docs/Web/API/Navigator/webdriver).
**Real Google sign-in acceptance still requires Sumeet's manual check**; synthetic
login cannot prove it. There is no stealth override, provider account-security
change or login retry loop. The local debugging exposure is intentionally changed
only for the dedicated agent browser, as authorized above. The everyday Vivaldi/profile is unchanged.

## Legacy custom-interface popup stall (avoided by the default)

The pinned custom Vivaldi interface + Playwright combination is **not accepted
for popup-dependent automation**. The managed default now uses the same binary's
Chromium interface, which passes the regression; the legacy engine/UI path itself
has not been repaired. A synthetic local button using `window.open('')`
and `document.write()` works in the same native browser without an agent
connection, but its Playwright click hangs after either native-consent attachment
or the ordinary debugging-port connection. The popup remains blank and receives
no fixture image request. No request-routing policy is needed to reproduce it.

Private protocol traces show an initially `other` popup target and a pending
`Runtime.runIfWaitingForDebugger` alongside the opener's pending mouse-release
command. This narrows the failure to native popup/debugger interaction, not
Gmail sign-in, internet access or consent alone; it does **not** establish the
precise engine defect. It resembles the separately reported
[CEF popup initialization stall](https://github.com/chromiumembedded/cef/issues/4308),
not necessarily the [routed-popup subresource bug](https://github.com/microsoft/playwright/issues/43496).

Target filtering, changing pause-on-start behavior, non-awaiting unsupported-target
detach, treating `other` as pages and Vivaldi's popup-in-tab preference did not
resolve the local fixture. Those experimental protocol patches were removed. The subsequently authorized
startup-debugging mode is a separate, documented local-access trade-off; routing,
file-access policy, sandbox and provider account security remain unchanged. A single
recovery probe found that detach returned successfully and a new manual fixture
tab loaded, but the pending popup stayed blank. That is not proof of safe retry,
complete recovery or a successful Gmail submission.

Do not repeatedly submit a real form, equate process/listener liveness with page
health, or claim reconnect/restart fixed a task without equivalent page-level
verification. The shipped mitigation is interface selection, not an engine patch,
policy bypass or proof that Gmail's underlying forwarding error is resolved.

To reproduce on the **private** compositor, use the normal `manual_integration.py`
command (same harness/executable arguments as `headed_integration.py`) with these
flags. Default acceptance needs no keyboard/pointer input or permission automation:

- No extra flags: default Chromium-interface preauthorized handoff acceptance.
- `PI_BROWSER_TEST_NATIVE_CONSENT=1` plus `--wtype /absolute/wtype`: opt-in native
  approval/renewed-approval controls. `PI_BROWSER_TEST_DENY_FIRST=1` adds denial.
- `PI_BROWSER_TEST_SHARED_RUNTIME=1` reuses a fresh synthetic profile and local
  fixture origin across two chats/browser lifetimes, verifying no-prompt startup,
  unmodified webdriver behavior and retained fixture login.
- `PI_BROWSER_TEST_POPUP=1`: strict popup/image/navigation acceptance; passes in
  the default interface.
- Also `PI_BROWSER_TEST_DIRECT=1`: default debugging-port control.
- `PI_BROWSER_TEST_NATIVE_UI=1`: explicitly restore the legacy custom interface
  in a fresh fixture profile. Adding `PI_BROWSER_TEST_POPUP=1` reproduces the
  bounded failure; it remains a strict failing regression, not an accepted mode.
- Also `PI_BROWSER_TEST_MANUAL_POPUP=1`: synthetic human input without an agent
  connection; passes. This enters only fixed local-fixture JavaScript through
  the private compositor's address bar and closes the exact fixture popup.
- `PI_BROWSER_TEST_TRACE=1`: optional protocol evidence in private logs; fresh
  synthetic profiles only, never real accounts or vault data.

The legacy failing regression remains opt-in, outside package unit checks. The
same fixture/browser build is used for both interfaces; no real profile is used. Manual native-dialog test input remains focus-sensitive, so distinguish a
consent rejection from reaching the popup regression.

## Backend comparison and adopted Chromium-interface default

The broader private comparison found a narrower change than replacing the
backend: keep the pinned Vivaldi binary and Playwright, but pass
`--disable-vivaldi --force-dark-mode` for the task browser. Headless mode already
uses the first switch; headed mode then uses the bundled Chromium interface
instead of Vivaldi's custom interface. This is an internal, version-pinned switch,
not a promise of a stable public Vivaldi API. New versions require this acceptance
suite again. This mode is now the managed headed default after explicit approval;
custom configuration files remain unchanged.

Local results with fresh synthetic profiles:

| Combination | Result |
| --- | --- |
| Existing official CLI + native Vivaldi interface | Popup stalls (above) |
| Puppeteer Core 25.16.0 + native Vivaldi interface | Popup mouse-release protocol timeout |
| Packaged Chromium 153 + Playwright | Popup, navigation and same-process reconnect pass |
| Same Vivaldi 8.2/Chromium 152 binary, Chromium interface + Playwright | Popup, navigation and reconnect pass |
| Same-binary Chromium-interface browser + official CLI native consent | Popup, navigation, renewed native consent and same-process reconnect pass |
| Chromium-interface profile reused across two chat identities/browser restarts | Website fixture marker and synthetic Bitwarden extension storage marker retained |

The last three Vivaldi candidate suites pass both verified placement cases without
stealing host focus. The same-binary control avoids confusing the Chromium 152/153
version difference with the interface change. A raw-Playwright/native-interface
probe also failed task binding before reaching the popup; that is **not** counted
as a second popup reproduction. Native-dialog synthetic keyboard input remains
focus-sensitive; a consent rejection is not a popup failure.

These are synthetic outcomes, not proof of real Google acceptance, real Bitwarden
account/session persistence or resolution of Gmail's underlying forwarding error.
No real profile was opened, copied or inspected. Moving an existing signed-in
profile to this interface still requires confirmation on Sumeet's real session.
Native consent and existing file/network policy must remain unchanged. Known
upstream routed-popup limitations are not declared solved by this comparison.

`backend_comparison.py` reuses the private compositor harness and takes its usual
arguments (`--browser-class vivaldi --keep-target-visible`), but `--chromium`
carries the actual browser executable, plus
`--backend playwright|puppeteer --module /absolute/module-entry.js`. The harness's
Vivaldi label is the exact placement class, not browser identification; the probe
reports the actual version/user agent. Modules are
explicit test dependencies; the probe never installs packages at runtime.
The Puppeteer comparison used `puppeteer-core@25.16.0` with install scripts and
browser downloading disabled in a temporary test directory. It is not a system
or production dependency. Add these optional environment flags:

- `PI_PROBE_BROWSER_ARGS='["--disable-vivaldi","--force-dark-mode"]'` for the
  same-binary candidate.
- `PI_PROBE_SHARED_PROFILE=1 PI_PROBE_EXTENSION=1` to verify cross-chat/browser
  restart persistence in a **new private fixture profile**, including only an
  explicitly synthetic `chrome.storage.local` marker in the packaged extension.
- For actual-default official CLI preauthorized acceptance, use
  `manual_integration.py` with `PI_BROWSER_TEST_POPUP=1 PI_BROWSER_TEST_RECONNECT=1`
  and optionally `PI_BROWSER_TEST_SHARED_RUNTIME=1`. This uses **no interface
  override/config or permission input** and verifies a fresh debugger attachment.
  Set `PI_BROWSER_TEST_NATIVE_CONSENT=1` and pass `--wtype /absolute/wtype` for the
  separate opt-in native-approval regression.

Build versus adopt: [Puppeteer's maintained CDP API](https://pptr.dev/api/puppeteer.connectoptions)
was tested directly and did not fix the native-interface stall, so introducing it
would add migration/maintenance cost without solving the observed problem.
[Chrome DevTools MCP](https://github.com/ChromeDevTools/chrome-devtools-mcp) is also
Puppeteer-based, officially targets Chrome, and enables usage statistics by
default; no MCP daemon or new agent integration was installed. The same-binary
default requires neither dependency nor custom protocol patch. Live-profile
verification follows deployment and an explicit human handback; never inspect
credential fields or vault data to infer successful sign-in.

## Bitwarden availability

Managed Vivaldi packages the official Bitwarden `dist-chrome-2026.10.2.zip` release
from [Bitwarden's releases](https://github.com/bitwarden/clients/releases/tag/browser-v2026.10.2),
with a fixed SHA-256 hash. The public Chrome Web Store key in
`bitwarden-public-key.txt` preserves the normal extension ID
`nngceckbapebfimnlniiiahkandclblb`; its SHA-256-derived ID, release version and MV3
manifest are checked during the build. This is public identity metadata, not a
private key or any copied user/vault data. See Chrome's
[consistent extension ID documentation](https://developer.chrome.com/docs/extensions/reference/manifest/key).
The compiled official client is unchanged except for this manifest identity.

The managed browser's load list includes both Bitwarden and the pre-existing
Project Object bridge. The ordinary Vivaldi package and everyday profile are not
changed. No vault/account state is copied, unlocked or exported. Persistent
profiles retain their own extension state; fresh profiles require their own login.
The extension cannot obtain Desktop credentials simply because Desktop is running.
The shared headed profile retains its own extension sign-in across chat/browser
restarts. This is not an always-unlocked vault: normal lock/logout timeouts,
organization policy and session revocation remain authoritative. No vault timeout,
credentials, account data or extension storage is inspected or changed by the
wrapper. See [Bitwarden's lock versus logout documentation](https://bitwarden.com/help/vault-timeout/).

Before native startup, `NativeMessagingHosts/com.8bit.bitwarden.json` receives an
immutable link to a Nix-generated manifest pointing at Bitwarden Desktop's packaged
`libexec/desktop_proxy`. Only Bitwarden's exact extension origin is allowed. Old
links owned by this package are updated; existing user/app-owned files or links
are not overwritten. Redirected host directories fail closed. No generated Desktop
manifest or proxy in the normal browser is edited. Optional nativeMessaging and
integration/unlock consent remain under Bitwarden's normal UI; no permission or
real vault connection is exercised by acceptance tests.

Tests inspect only extension ID/version and permission metadata in fresh synthetic
profiles, prove both extensions remain in the load list, and check host wiring
without launching the Desktop proxy. Runtime login/unlock still requires Sumeet.
For manual use, follow [Bitwarden's browser extension guide](https://bitwarden.com/help/getting-started-browserext/).

## Session mechanics

`PI_SESSION_ID` (or `PI_SESSION_FILE` fallback) selects a private folder beneath
`$XDG_STATE_HOME/pi-browser/` (default `~/.local/state/pi-browser/`). Different Pi
sessions have different caches/artifacts and headless profiles, even in the same repo;
the native headed default is the deliberately shared persistent agent profile.
shell cwd changes do not change browser ownership. Explicit profile paths and
attachments deliberately allow reuse beyond these defaults. Concurrent commands
within a Pi session are serialized. Global close/kill commands and runtime install
commands are rejected; per-session `close`, `detach` and `delete-data` are supported.

```
pi-browser snapshot
pi-browser fill e3 'Some text'
pi-browser fill e3 -- '--help'
pi-browser click e4
pi-browser screenshot
pi-browser paths
pi-browser close
```

Snapshots may be inline or files. `paths` reports absolute session, artifact and
temporary directories; reported relative artifact paths resolve against `session`.
Temporary files use short `/run/user/$UID/pib/` paths for Vivaldi/Chromium's Unix socket
length limit. Profiles/artifacts can contain sensitive data. Close does not delete
persistent data. Upstream defaults headless sessions to one hour of inactivity;
headed sessions do not idle-close. An explicit `--idle-timeout` ends the automation
connection in native mode; `close` terminates the owned native Vivaldi process.

The wrapper preserves graphical and project-launch environment for headed routing,
but removes inherited Playwright/MCP connection settings so modes are explicit.
Update checks, browser downloads and Vivaldi's automatic codec download are disabled;
all runtime dependencies are
Nix-store packaged, with no dependency on the checkout. CLI options are forwarded
rather than maintained in a restrictive feature allowlist. Session aliases are
rejected to keep Pi session ownership unambiguous.

## Verification

`python3 -m unittest discover -s tests -v` runs package-level unit checks.
`python3 tests/integration.py /nix/store/.../bin/pi-browser` tests local fixtures,
headless interaction, isolation, persistence and external CDP detach behavior.
`headed_integration.py` reuses the Project Object isolated compositor harness to
exercise native Vivaldi/persistent browsers on a hidden desktop, never the real
desktop. Pass `--browser-class vivaldi --keep-target-visible` plus the documented
executable paths. Set `PI_BROWSER_TEST_TEMPORARY=1` for fresh native-profile and
close-cleanup coverage; the default covers explicit-profile cross-session/mode
reuse and synthetic login continuation. `PI_BROWSER_TEST_SHARED=1` instead tests
the no-config/default profile across two different Pi sessions: Chromium-interface
and Dark flags, absence of Vivaldi's custom UI app, preserved local fixture login
and synthetic MV3 extension storage, concurrent profile rejection, and shared
delete-data refusal. `PI_BROWSER_TEST_CHROME_CAPTURE=1` optionally saves a private
`grim` capture for visual Dark/tab/address-bar acceptance. No real accounts or
vault storage are read. Compositor events check transient focus.
