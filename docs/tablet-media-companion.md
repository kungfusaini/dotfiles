# Tablet-window-only playback pause

Packaging this proof does **not** load an extension into the normal browser.
Real-profile installation, site grants, pairing and replacement of the live
watcher require their own approval/acceptance gate. The accepted persistent
workspace implementation remains live until that gate is satisfied.

## Contract

- Remove the native Home's Return-to-desktop button and the Control Centre exit
  tile. Unfolding and emergency keyboard exit remain available. Legacy preview
  defaults are unchanged.
- Pause HTML audio/video in the **registered tablet browser window only** when
  tablet mode exits. Other Vivaldi windows, Spotify and other laptop players must
  remain untouched. No MPRIS, global media keys, mute, tab discard or browser
  process termination is used.
- Retain the real tablet window/tabs and page state. Returning releases the
  suspended-window gate but **never calls `play()`**. A later explicit user/site
  play action can run while tablet mode is active; this is not a browser-wide
  autoplay-policy change.
- Initially supported sites are HTTPS YouTube and YouTube-nocookie origins.
  Unpermitted audible tabs produce an explicit failure, not a fake claim that
  all media paused. Other sites, Web Audio-only players and new native app
  adapters are not claimed supported by this proof.

## Why a companion

Chromium's standard media controller follows its active browser media session;
shared-process identity is not individual-window identity. The installed Vivaldi
Break Mode implementation queries all tabs, so it is also unsuitable here.
[Chrome scripting](https://developer.chrome.com/docs/extensions/reference/api/scripting)
can operate on specific tab IDs, while
[native messaging](https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging)
provides a browser-owned connection without enabling debugging on a personal
profile. This reuses browser/stdlib APIs rather than adding another media-control
framework or borrowing a third-party extension's broad permissions.

## Permissions and data

The production manifest grants `nativeMessaging`, `scripting`, `storage` and
explicit YouTube plus `http://tablet.localhost/*` host access. There is **no**
`tabs`, history, cookies, debugger, webRequest, all-URLs or ordinary loopback-host
permission. Page-access grants still mean the browser permits read/modify access
on those sites; the implemented scripts only find/pause media and maintain a
pause gate. They do not collect text, HTML, titles, history, cookies, credentials
or video URLs. This is an audited operation scope, not a security sandbox against
other programs running as the same Unix user.

The dedicated local origin serves one-time registration pages from an ephemeral
127.0.0.1 HTTP listener. There are no HTTP pause/control endpoints, CORS grants or
remote scripts. Exact registered URL/port/nonce checks reject other local pages.
Access logging is disabled; registration capabilities never enter ordinary logs,
Git or browser-independent state files. The extension's session storage contains
only suspended window IDs. Site/window IDs, not page contents, cross native
messaging. The fixed public manifest key stabilizes extension ID
`cfepbdnljmjhpbaoephifiehkdahpgll`; no signing private key is stored.

## Exact window registration

The native host runs only for the whitelisted extension origin. Its private
0700 runtime and 0600 Unix socket validate UID and SO_PEERCRED PID/start-time
against the current tablet backend or journaled recovery owner. Requests must
match the current compositor/native address/PID/start-time/class/stableId and
remain in `tablet-trial`.

Neither shared browser PID nor focus alone binds a browser window:

1. A fresh local registration nonce produces a unique page title and URL.
2. Chrome supplies the registration sender's tab/window IDs. The extension
   verifies the tab remains in that exact normal, non-incognito window, with
   the expected URL and exactly one matching registration tab.
3. The host confirms that the exact native tablet window has that nonce title,
   checks the current tablet lease, and revalidates before committing.
4. State application is acknowledged before publishing the binding. Pairing and
   native pause/resume operations are serialized, and pairing rechecks current
   exit state so a late registration resume cannot undo an acknowledged pause.

Existing tablet windows pair through the companion action or its Options page.
This opens and then removes only its own temporary registration tab. New Home
launches obtain the registration URL before creating their own tablet-local
browser window; normal-profile/warm-process and new-window nonce guards remain.
No laptop window is moved or adopted. Closing/recycling a source cannot redirect
media actions to a replacement window. Lost host connections require pairing
again; no guessed fallback player is selected.

The native host clears inherited Chromium library-path/preload overrides for
its own process. A private test reproduced Vivaldi's libstdc++ path preventing
packaged `hyprctl` from starting. Browser environment, sandbox and process are
not modified by this host-only sanitization.

## Pause gate and failure handling

The extension enumerates only the bound window. Before acknowledging a pause it
explicitly installs and verifies the fixed idempotent media helper in permitted
frames, including documents loaded **before** companion installation/reload.
Missing receivers are not treated as proof of a working gate. Reinstallation
removes prior listeners rather than accumulating them.

The helper pauses existing media and rechecks Chrome's current sender-window
state on subsequent play events. Tab detach clears old gate state; attachment
refreshes/installs the gate in the new window. A moved tab does not retain its
old tablet blocking state in a laptop window, and a tab moved into a suspended
tablet window receives the gate. Tab/window state is checked again after
injection; movement during an operation is an explicit error. Browser event
handling is asynchronous, not an atomic cross-process window transaction.

Native exit records suspended/pending state and requests verified pause before
window/IME teardown and workspace return. Failure cannot trigger another
player's pause. It emits one generic notification and retains recovery evidence,
while independent covered presentation/input/rotation cleanup still returns a
usable laptop. It does not trap the display because an extension is unavailable.
The pending journal prevents pretending the exit was completely successful.
Recovery retries only the exact registered source; a closed or no-longer-tablet
source is not reclaimed. No automatic playback resume is sent on later entry.

## Verification

- Python tests cover source/peer/lifetime fencing, nonce/tab/lease confirmation,
  pairing acknowledgement/exit-state ordering and native cleanup pause ordering,
  failure notification/recovery and exit-button removal.
- Node VM tests use the real background/helper scripts for two-window isolation,
  preloaded documents, repeated helper installation, no auto-play, moves in both
  directions, play before move notifications arrive, unsupported audible failure
  and production permission bounds.
- The real private Labwc → Hyprland → Vivaldi suite loads the actual native host
  and companion in a disposable profile, opens its real Options UI, clicks Pair,
  and confirms registration-tab removal. Two real local WebM players run in
  distinct windows. Tablet exit pauses only the tablet; the second keeps playing.
  A later background play attempt is re-paused; reentry does not restart playback.
  Existing native fullscreen/global controls/IME, workspace resume, rotation and
  stage/backend/focus-loss recovery checks run alongside it.
- The test derivation adds only its private fixture origin. **It deliberately
  adds no declarative script for fixture pages**, proving the explicit helper
  path works on preloaded documents. Production has no fixture origin or runtime
  permission-bypass switch. No real website/profile, credentials, CDP, global
  input, physical sensor, audio or backlight is used by this suite. The players
  are real media elements but muted; assertions measure actual playing/paused
  state rather than claiming a physical sound test.

## Managed installation and activation gate

Home Manager installs the read-only extension directory at
`~/.local/share/tablet-media-companion`, the whitelisted manifest at
`~/.config/vivaldi/NativeMessagingHosts/org.machine.tablet_media.json`, and the
packaged `tablet-native` CLI. The normal Vivaldi wrapper, Project Object bridge,
other extensions and other profiles remain unchanged. No browser restart is
required for a human to load the unpacked companion into the existing normal
profile. Vivaldi's extension UI requires its Developer mode / Load unpacked
consent; choose the managed directory above. The agent must not enable personal
profile debugging or edit profile preferences to bypass that permission UI.

`programs.tablet-native.automatic` defaults to `false`: installing the host and
assets does not prematurely replace fold/entry/shortcut routes. After the
companion is loaded, pair the existing tablet window through its companion
button or Options page and verify actual YouTube pause on the temporary native
watcher. Only then enable the accepted native default. Existing sign-ins, tabs,
profiles, legacy Pi data and extension state are preserved.

Managed files are deployed only from a reviewed, committed canonical snapshot
through `deploy-kirax1`, with exact-snapshot non-privileged validation and live
generation checks. Promote only the owned tablet paths, never the entire old
stream branch. The install contract checks immutable paths, whitelisted ID/site
permissions, unchanged browser derivation and disabled automatic routes. Source
verification does not substitute for the real browser permission/pairing step.
Do not activate the companion-dependent native watcher without the companion.
