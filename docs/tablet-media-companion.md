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
- Supported sites are HTTP and HTTPS pages, across all tabs in the registered
  window. HTML audio/video in cross-origin frames, inherited-origin frames and
  existing open shadow roots is included. Closed shadow roots, Web Audio-only
  players, protected browser pages, local files and native app adapters are not
  guaranteed. Unpermitted audible tabs produce an explicit failure, not a fake
  claim that every possible player paused.

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
`http://*/*` / `https://*/*` host access, including local HTTP services and the
registration origin. This broadened page-access scope requires explicit user
approval and browser consent. Chrome grants site access profile-wide, not per
window: the browser permits reading/modifying any matching site, although our
fixed implementation only pauses media in the exactly paired tablet window.
There is **no** `tabs`, history, cookies, debugger or webRequest API permission,
no `<all_urls>` pattern, and no top-level file/internal-browser-page grant.
The helper is installed at document start across matching pages, but unpaired
windows have no blocked state; it does not scan their DOM or pause their media.
Only while blocked does it traverse audio/video elements and open shadow roots,
attach their play guards and pause them. It does not collect text, HTML, titles,
history, cookies, credentials or video URLs. This is an audited operation scope, not a security sandbox against
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
removes prior listeners, including shadow-root listeners, rather than accumulating
them. Static [Chrome content scripts](https://developer.chrome.com/docs/extensions/develop/concepts/content-scripts)
use `all_frames` and `match_origin_as_fallback` for frames created by granted
HTTP(S) origins; top-level browser/file pages remain outside the grant.

The helper pauses existing media and rechecks Chrome's current sender-window
state on subsequent play events. Tab detach clears old gate state; attachment
refreshes/installs the gate in the new window. A moved tab does not retain its
old tablet blocking state in a laptop window, and a tab moved into a suspended
tablet window receives the gate. Tab/window state is checked again after
injection; movement during an operation is an explicit error. An injection failure
is collected per tab so remaining tablet tabs are still attempted; the overall
acknowledgement fails afterward. An audible tab with no reachable HTML media
also fails conservatively. Mixed/custom audio graphs are not proven stopped by
an HTML-element count. Browser event
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
  and confirms registration-tab removal. Real local WebM players run across two
  tablet site origins/tabs, a cross-origin iframe, an inherited-origin blank
  frame and an open shadow root. A separate browser window also plays. Exit
  pauses every tablet player while the other window continues. Background play
  attempts in all tablet documents are re-paused; reentry restarts none.
  Existing native fullscreen/global controls/IME, workspace resume, rotation and
  stage/backend/focus-loss recovery checks run alongside it.
- The test derivation uses the production HTTP(S) permissions unchanged. It
  **excludes declarative scripts on fixture HTTP pages**, proving the explicit
  helper path works on preloaded documents. There is no test-origin permission
  exception or runtime permission-bypass switch. A private mount namespace masks
  the host headless-posture file and isolates X11 sockets, so host display posture neither
  invalidates tests nor has to be changed. Production panel guards stay intact. No real website/profile, credentials, CDP, global
  input, physical sensor, audio or backlight is used by this suite. The players
  are real media elements but muted; assertions measure actual playing/paused
  state rather than claiming a physical sound test.

## Managed installation and activation gate

Home Manager installs the immutable extension directory at
`~/.local/share/tablet-media-companion`, the whitelisted manifest at
`~/.config/vivaldi/NativeMessagingHosts/org.machine.tablet_media.json`, and the
packaged `tablet-native` CLI. The normal Vivaldi wrapper, Project Object bridge,
other extensions and other profiles remain unchanged. No browser restart is
required for a human to load the unpacked companion into the existing normal
profile. Vivaldi's extension UI requires its Developer mode / Load unpacked
consent; choose the managed directory above. The agent must not enable personal
profile debugging or edit profile preferences to bypass that permission UI.
Vivaldi's directory picker resolves this directory symlink to its Nix-store
target. For an existing installation pointing directly into the old store,
select the managed folder again with Load unpacked after deployment and accept
the broader access. Reload on the old entry alone reloads the **old** generation.
Verify the entry's own version/path before activation. A private comparison
found that a real folder of per-file symlinks did not run the registration
content script in this Vivaldi build, whereas identical regular files worked;
do not switch to recursive per-file links or assume that layout is equivalent.
No mutable extension copy or preference edit is introduced to bypass consent.

`programs.tablet-native.automatic` defaults to `false`: installing the host and
assets does not prematurely replace fold/entry/shortcut routes. After the
companion is loaded, pair the existing tablet window through its companion
button or Options page and verify actual site-media pause on the temporary native
watcher. Only then enable the accepted native default. Existing sign-ins, tabs,
profiles, legacy Pi data and extension state are preserved.

Managed files are deployed only from a reviewed, committed canonical snapshot
through `deploy-kirax1`, with exact-snapshot non-privileged validation and live
generation checks. Promote only the owned tablet paths, never the entire old
stream branch. The install contract checks immutable paths, whitelisted ID/site
permissions, unchanged browser derivation and disabled automatic routes. Source
verification does not substitute for the real browser permission/pairing step.
Do not activate the companion-dependent native watcher without the companion.
