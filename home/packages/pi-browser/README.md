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
sessions keep the real Vivaldi UI, including its extension-backed browser chrome.
No everyday profile is reused and everyday debugging settings remain untouched.
The shared headed profile's offline startup preferences select built-in Dark
(`Vivaldi2`), disable OS/timeline theme switching, and hide the left panel bar and
bottom status bar. Tabs and address bar remain. Only those appearance keys are
updated, under the profile launch lock and before Vivaldi runs; malformed or
redirected preferences fail closed. Explicit/custom and temporary profiles keep
Vivaldi's normal appearance. No live Preferences file is edited.

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
`--headed` overrides headless mode. A human can use the same headed browser to log in, then
hand control back; the agent continues without exporting credentials or cookies.
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

## Human-first sign-in with native runtime consent

```sh
project-workspace-exec pi-browser open --headed --manual --persistent https://mail.google.com/
# After explicit human handback, request the next permission stage:
pi-browser connect
```

Manual mode launches ordinary Vivaldi without debugger/automation flags or an
agent connection. It never toggles the browser's native debugging preference.
Owned-window metadata determines UI readiness; ordinary singleton URL handoff
opens the task. A readable waiting parent preserves sandboxed-process ancestry
for verified workspace placement. Existing modes remain available.

The native runtime feature is available in the pinned Vivaldi, despite third-party
channel lists naming Chrome/Edge only. `connect` verifies the exact live owned
PID/start identity and profile-lock owner. Without a marker, it opens
`vivaldi://inspect/#remote-debugging` and returns `enable-debugging`; Sumeet enables
**Allow remote debugging for this browser instance**. A later `connect` requests
Vivaldi's native **Allow remote debugging?** consent and returns
`approve-connection`. This private daemon waits without timing out or capturing
pages. After explicit handback, `connect` finalizes attachment, selecting the single
existing HTTP(S) task-origin tab. Missing/ambiguous tabs fail closed.

There is **no restart, new task page, navigation, cookie copying, state export or
profile import**. The browser, page and login remain live. The native UI writes a
strictly validated direct WebSocket endpoint in the owned profile's
`DevToolsActivePort`; HTTP `/json/version` is not served by this on-demand endpoint.
Raw CLI stdout/stderr, code, page/title and tab metadata are captured and filtered,
not forwarded. Only status and validated origin are emitted. A version-pinned,
fail-closed CLI patch disables its hardcoded automatic snapshots only in the
private consent daemon. Explicit snapshots still work. Normal modes are unchanged.

Native permission grants full browser debugging capability; origin selection is
not a security sandbox. AGENTS.md authorization, manual-entry pause, explicit
handback, task scope and password-manager restrictions remain authoritative.
Declining a request leaves the same manual browser/profile intact, with no automatic
retry. `close` or `detach` also terminates the exact owned pending daemon by
PID/start identity; detach releases browser/profile ownership. Existing temporary
cleanup and explicit/persistent-profile retention are unchanged.

Tests use only a private compositor/DBus and synthetic local login. They prove
startup has no debugger flags, normal `navigator.webdriver` behavior is unmodified,
native permission approval/denial, same PID/profile/login, real interaction after
attachment and metadata-only output. A synthetic Local State seed models the
checkbox; test-human permission input is bounded to the private compositor and
excluded only during explicit consent markers. Browser placement and all agent
focus events outside that interval remain checked. Address reuse no longer causes
false focus failures; all browser classes/lifetimes are checked.

A restart prototype and Playwright-extension experiment were not shipped. The
built-in route follows [Chrome's runtime-consent mechanism](https://developer.chrome.com/blog/chrome-devtools-mcp-debug-your-browser-session).
See also [Google's browser guidance](https://support.google.com/accounts/answer/7675428?hl=en)
and [MDN's webdriver documentation](https://developer.mozilla.org/en-US/docs/Web/API/Navigator/webdriver).
**Real Google sign-in acceptance still requires Sumeet's manual check**; synthetic
login cannot prove it. There is no stealth override, account-security downgrade or
provider-login retry loop. The everyday Vivaldi/profile is unchanged.

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
the no-config/default profile across two different Pi sessions: native Dark chrome,
hidden bars, preserved local fixture login and synthetic MV3 extension storage,
concurrent profile rejection, and shared delete-data refusal. It never opens real
accounts or reads vault storage. Compositor events check transient focus.
