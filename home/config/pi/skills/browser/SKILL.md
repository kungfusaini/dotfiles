---
name: browser
description: Use the Microsoft Playwright CLI through pi-browser for browser navigation, DOM/accessibility inspection, clicks, forms, screenshots, tabs, persistent profiles, visible sessions, manual-login handoff, or attaching to an existing browser. Covers tool mechanics across workflows; AGENTS.md defines behavior and permissions.
---

# Browser tools

`pi-browser` packages Microsoft's Playwright CLI with Pi-session-specific state,
cache, artifacts and command lock. It supports headless/headed Chromium,
persistent profiles and attachment. Behavioral permissions live in `AGENTS.md`.

## Commands and paths

```bash
pi-browser --help
pi-browser open --help
pi-browser open http://localhost:3000
pi-browser snapshot
pi-browser fill e3 'Example text'
pi-browser click e4
pi-browser screenshot
pi-browser paths
```

Snapshots are inline YAML or a reported file containing element refs such as `e3`.
Refs belong to that snapshot; refresh when the page changes. `find 'text'` and
`snapshot --depth=4` reduce output. Pi's `read` tool reads files/images.
`paths` returns absolute `session`, `artifacts` and `temporary` directories.
Relative artifact/file arguments resolve against `session`, not shell cwd;
config/profile inputs resolve against shell cwd. Use absolute paths when useful.
Use `--` before dash-prefixed literal text: `pi-browser fill e3 -- '--help'`.

## Browser modes and profiles

```bash
# Default: temporary isolated headless Nix Chromium.
pi-browser open https://example.com

# Immediately connected headed browser. For new human sign-in, use manual below.
project-workspace-exec pi-browser open --headed https://example.com
project-workspace-exec pi-browser open --headed --persistent https://example.com

# Separate temporary or explicit profile: authenticated work needs approval.
project-workspace-exec pi-browser open --headed --no-persistent https://example.com
project-workspace-exec pi-browser open --headed --profile=/absolute/profile https://example.com
pi-browser open --config=/absolute/config.json https://example.com
```

Native headed defaults reuse
`$XDG_STATE_HOME/pi-browser/shared-chromium-profile` across chats. They use Chromium's
native tabs/address bar, dark mode, Chromium sandbox and packaged Bitwarden/Project
Object extensions. No Vivaldi custom interface is involved. `--no-persistent`
explicitly uses a temporary profile. Headless defaults are temporary; headless
`--persistent` uses session-local `profile-chromium`, never the human sign-in profile.
Explicit `--config` retains its own profile semantics and browser settings.

**Backend migration:** Sumeet approved Chromium with a new dedicated shared profile
and fresh website/Bitwarden sign-ins. The former Vivaldi `shared-profile` and
headless `session/profile` are retained, not migrated/copied. The old shared profile
is refused as an explicit launch or deletion target. Do not copy cookies/vault
state, open the old profile with Chromium, or close another chat's existing Vivaldi
browser to apply the fix. Existing browsers keep their backend until an authorized,
coordinated replacement; deployment does not restart them. Legacy runtime names
`vivaldi-process.json`, `vivaldi.log` and `pi-vivaldi-*` classes intentionally remain.

A profile can be open in only one process. An occupied profile fails closed, never
silently replaces another chat or falls back to a fresh signed-out profile. Use
its owning chat or obtain explicit approval for a separate profile. Reuse does not
authorize unrelated signed-in tabs or vault access. Everyday Vivaldi is untouched.

Headed launch starts an owned Chromium process with a temporary loopback endpoint,
then the pinned official Playwright daemon. The exact task tab is selected, not a
restored unrelated tab. Immediately connected startup navigates only after upstream
file/network policy is applied. Workspace helpers verify mapping without host
focus/input. Native launch fields are `executablePath`, `headless`, `chromiumSandbox`
and `args`; unsupported settings fail. JSON native configs reject context/device
emulation and init callbacks on existing CDP contexts; headless mode supports them.
INI configs require an explicit checked `--profile` to override any opaque
profile selection; use JSON for profile-free configs. External endpoints retain
upstream behavior. Personal global CLI config is isolated per session so it cannot
silently select the old profile. Malformed JSON fails before launch. `--idle-timeout=<milliseconds>` ends native automation, not the owned
browser; `close` stops that browser. Upstream headless idle timeout is one hour;
headed sessions have no default idle-close. `list` reports readiness metadata.

`open` refuses to replace a live owned headed browser, even with headless open.
For a manual browser use `connect` after handback. For an already connected browser,
use task-authorized `goto` or `tab-new`, not reopen. Deliberate replacement needs an
authorized `close` first. Help and untracked headless/external behavior are unchanged.
An old Vivaldi manual browser awaiting connection may need its original packaged
launcher; do not restart it merely to evade an executable-identity refusal.

## Human-first manual handback

For a new human-assisted sign-in, `AGENTS.md` requires manual launch, explicit human
handback, then connection to the **same browser**, without closing/reopening it:

```bash
project-workspace-exec pi-browser open --headed --manual --persistent https://mail.google.com/
# After explicit handback:
pi-browser connect
# Optional per-connection native permission rather than preauthorized debugging:
project-workspace-exec pi-browser open --headed --manual --native-consent https://example.com/
```

A plain headed open attaches immediately; pausing commands is not manual mode.
Keep an already connected browser for authorized work rather than restart it.
Sumeet approved preauthorized debugging for this dedicated agent browser: it uses
`127.0.0.1` and a nonzero OS-selected port. **Any local program reaching it can
control the signed-in browser without another Allow prompt**, even after detach.
This is not a sandbox. Do not expose the endpoint or enable it on everyday browsers.

`--manual` means no agent attachment/page observation until handback, not debugging
disabled. Pause browser actions, snapshots, screenshots, DOM/traffic/console reads
while Sumeet enters credentials, handles MFA or uses Bitwarden. Wait for explicit
handback; inspect only the task website's non-sensitive login outcome, not filled
credential fields, extension storage or vault data. Manual page commands refuse
before connection. Initial automatic handoff snapshots are disabled; explicit
snapshots remain available for task-authorized work afterward.

Startup verifies PID/start, socket ownership, IPv4 loopback binding and endpoint
identity, rejecting foreign/wildcard listeners and changed endpoints without a
fallback. No webdriver/UA spoofing or stealth overrides. `connect` returns only
status and validated origin, not raw tab/page/credential metadata:

- `connecting`: daemon starting; use a bounded retry after handback. No native
  permission action is needed in the default preauthorized mode.
- Only with `--native-consent`, `enable-debugging`: `chrome://inspect/#remote-debugging`
  is open. The human enables **Allow remote debugging for this browser instance**.
- Only with `--native-consent`, `approve-connection`/`awaiting-approval`: the native
  **Allow remote debugging?** dialog needs human confirmation. Never automate it.
  It has no automatic expiry; do not poll while the human uses it.
- `connected:true`: the single HTTP(S) task-origin tab was selected without restart,
  navigation or a new tab. Missing/ambiguous tabs fail closed.
- `connected:true,reused:true`: this chat's existing approved connection is still
  owned/live. No new debugger connection, tab command, page read or prompt. This
  is connection metadata, **not** page-health/account/permission verification.

Keep the live browser/approved daemon open between authorized operations. Reuse is
scoped to its owning Pi chat, not cross-chat attachment. New preauthorized connections
need no Allow prompt; new opt-in native-consent connections still do. Ownership
checks remain mandatory. Declined/dead/changed connections fail without silent
replacement. `close` stops only the owned browser/daemon; `detach` relinquishes
ownership and leaves the debugging server running until that browser exits.

The earlier real Cloudflare manual-login/connection success used the old Vivaldi
backend. It is not proof of Chromium acceptance or a universal challenge fix.
Synthetic tests preserve unmodified `navigator.webdriver=false` in manual mode,
but do not prove provider acceptance. [Cloudflare does not support automation
frameworks for solving production challenges](https://developers.cloudflare.com/cloudflare-challenges/reference/supported-browsers/).
If verification loops recur, stop retries and diagnose rather than reset profiles
or promise a bypass. Never repeat an uncertain submission or infer task success
from process/listener liveness.

## Downloads, popup compatibility and Bitwarden

The former `--disable-vivaldi` workaround avoided Vivaldi's custom-interface popup
stall but failed dummy HTTP/blob/sandbox downloads, even with CDP allow. Restoring
full Vivaldi UI is not an accepted fix because it revives known regressions. The
Chromium default passes local popup/image/navigation/reconnect and byte-checked
download tests. This does not prove that any particular website export succeeds,
or fix a server's HTTP404. Known upstream routed-popup limitations remain unproven.

Before agent attachment, manual Chromium uses its ordinary native Downloads
behavior. Once attached, the owned daemon enables Playwright's normal download
events/storage; automatic CLI copies are session artifacts, not a promised
`~/Downloads` destination. Use `saveAs()` for the authorized durable/private copy.
External attachment retains upstream's browser-default download handling.
A fresh Bitwarden install may open its welcome tab asynchronously; after human
handback, select the authorized task tab rather than infer a login failure or
restart the browser. Never inspect vault state to resolve this tab behavior.

Use the normal [Playwright download flow](https://playwright.dev/docs/downloads)
when authorized to save a file. `run-code` accepts a snippet such as:

```javascript
async page => {
  const pending = page.waitForEvent('download');
  await page.getByRole('link', {name: 'Download', exact: true}).click();
  const download = await pending;
  await download.saveAs('/approved/absolute/destination/file.csv');
  return {saved: (await download.failure()) === null};
}
```

Wait before clicking, save to the approved destination, and verify the file before
claiming completion. Temporary downloads may be removed on context close; `saveAs`
preserves the requested copy. A missing save dialog alone is not failure. Do not
change account/site/download security policy as a workaround without authorization.

Bitwarden is packaged under official ID `nngceckbapebfimnlniiiahkandclblb`, available
from Extensions. Popup: `chrome-extension://nngceckbapebfimnlniiiahkandclblb/popup/index.html`.
The new persistent Chromium profile starts with its own account state; Desktop
being signed in does not sign in the extension. Normal locking, organization policy,
logout/revocation remain authoritative. Sumeet signs in/unlocks/autofills manually.
Never change vault timeout or inspect extension account/vault storage to keep
sign-ins alive. [Bitwarden lock versus logout](https://bitwarden.com/help/vault-timeout/).
The native-host manifest points to the packaged Desktop proxy, but optional
nativeMessaging/Desktop integration permissions still need normal human prompts.
Existing user/app-owned manifests are preserved. No real vault/proxy access in tests.

## Attachment and lifecycle

```bash
pi-browser attach --cdp=http://localhost:9222
pi-browser attach --endpoint=ws://localhost:3000/playwright
pi-browser attach --extension=chrome
pi-browser detach
pi-browser tab-list
pi-browser tab-new https://example.com
pi-browser tab-select 0
pi-browser console
pi-browser requests --static
pi-browser eval 'document.title'
pi-browser close
```

External attachment needs authorization for that concrete browser/profile and task.
CDP needs an existing verified endpoint. Extension mode needs the official Playwright
extension, supported browser and coordinated human approval; these commands do not
install it or grant access to unrelated signed-in tabs. Do not attach by another
chat's cached session name. Detach from externally owned browsers, do not close them.

`state-save`/`state-load` export/import authentication and can contain credentials;
separate explicit authorization is needed. `run-code`, upload and evaluation retain
the user's normal file/network permissions; neither wrapper nor skill is a sandbox.
Pi's `PI_SESSION_ID` (or `PI_SESSION_FILE`) supplies ownership across cwd changes.
Only headed defaults share the profile; caches/artifacts remain session-local.
`delete-data` refuses the new and legacy shared profiles and removes only the
current headless persistent profile, never explicit profiles. No global kill/close
or runtime installation; dependencies are Nix-managed. Packaged test/comparison
evidence is in `share/doc/pi-browser/README.md`.

Upstream reference: https://github.com/microsoft/playwright-cli
