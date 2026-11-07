# Continuous tablet presentation

**Hard contract:** once tablet Home is onscreen, app launches, Home/app navigation
and live UI replacement must not expose Hyprland wallpaper or desktop chrome.
The intended feel is an app opening within iOS/iPadOS, not a trip through another
desktop. This applies to every app route, not a special case for Pi.

This remains an undeployed preview. Pi and Vivaldi have real app adapters;
Spotify, Pegasus and Krita are explicitly simulated preview screens. See
[native-window integration](tablet-window-apps.md) for ownership, browser-profile
compatibility, input/capture policy and real-window test evidence.
Explicit **Exit tablet**, workspace escape and fatal safety cleanup still restore
the normal desktop; this is not a kiosk or a new global shortcut lock.

## One session from the first Home

`tablet-home-preview` invokes `tablet-chat start`, not a standalone Quickshell
launcher. The controller binds/enters once and presents the production session's
Home. Its windowless agent host is connected but Pi RPC remains stopped until
`Pi` invokes `launchPi` within that same supervised session. No second frontend,
workspace entry, keyboard startup or app-history reset occurs at that click.
Opening the entry again attaches to the current session without changing its view.
The obsolete standalone `shell.qml` has been removed to eliminate the split path.

## Ownership and ordering

- `shell.qml` presents Home fullscreen rather than in a resizable desktop tile.
- The supervisor starts and journals a separate `stage.qml` **before** entering
  `tablet-trial`. Its opaque Bottom-layer Home survives every replaceable app/UI
  process. It is targeted only at the configured laptop screen.
- A temporary Overlay-layer Home cover protects workspace entry and Home/Pi
  switches, including the desktop's Top-layer bar. Bottom wallpaper alone cannot
  hide that bar. Each cover is a fresh layer surface: remapping an old layer can
  leave it underneath a newer app, preventing a valid cover handshake.
- Before switching workspace or hiding the outgoing app, require rendered cover
  content **and** actual Hyprland `layers -j` evidence: exactly one matching
  PID/layer/namespace, full logical monitor geometry and alpha >= .999.
  **Hyprland's field is `alpha().goal()`, not current animated opacity**
  ([pinned implementation](https://github.com/hyprwm/Hyprland/blob/efb50993780079460b0cbed1363e2166a2de1d9f/src/debug/HyprCtl.cpp)).
  All guarded surfaces therefore reuse the already-deployed `tablet-rotation-fade`
  namespace with `no_anim on`; PID and layer level disambiguate their roles.
  Entry and transitions refuse to proceed without that installed policy. No new
  global runtime rule, config reload or system deployment is performed.
  Qt animates the app content inside opaque surfaces instead of relying on
  compositor fades. `QWindow.visible` alone is not sufficient. Failure leaves the
  old screen in place rather than switching into an uncovered workspace.
- `FrameWitness.qml` observes native Qt `frameSwapped` signals, including resets
  on window/geometry changes. Visible scenes queue two frames; the already-opaque
  persistent background needs its first buffer (occluded backgrounds may not
  receive further frame callbacks). These signals mean queued frames, not a
  hardware presentation timestamp; the compositor-alpha barrier is separate.
- An unconnected backend or failed draft restore cannot map an empty chat over
  the loading cover/Cancel action. A native scene becomes paintable only with a
  connected bridge, restored draft, and history ready (or a startup question/error
  that the user must interact with). The valid app then expands **above** opaque
  Home intentionally: the cover is a continuity floor, not a freeze-frame that
  hides the iOS-like app animation. Admission is latched for that frontend:
  answering a startup question while history is still loading must not unmap an
  already-presented app and uncover desktop chrome. It stays as a loading scene.
- Reveal only when the frontend reports the **requested view**, restored draft,
  connected backend and rendered content, and its matching compositor surface is
  opaque under the guarded no-animation policy. A stale previous-view
  acknowledgement must not open a gap.
- Live UI replacement keeps the old scene until the new one meets the same
  barriers. The stable stage remains mapped throughout; its visual Home assets
  follow the validated immutable UI bundle without unmapping its opaque base.
- Home first resolves private voice input, then covers, then releases the old
  app. Failed voice cancellation never hides unresolved recording controls.
- Cleanup stops the stage **last**, after child teardown and workspace return.
  PID/start-time ownership is journaled. Its parent watchdog prevents an orphaned
  cover from trapping the display, and Cancel launch signals only that owner.

The implementation reuses maintained Quickshell layer-shell/IPC and Qt rendering
signals instead of adding a compositor plugin. See
[Qt's frameSwapped semantics](https://doc.qt.io/qt-6/qml-qtquick-window.html#frameSwapped-signal)
and [Quickshell LazyLoader](https://quickshell.org/docs/v0.3.0/types/Quickshell/LazyLoader/).
`AppSurface.qml` supplies the same restrained 200 ms scale/fade for Pi and
simulated app screens, with opaque tablet Home underneath at every intermediate
opacity. Native Vivaldi has a separate capture/presentation adapter; only its
isolated native-window test launches a real browser.

## Bottom navigation and open apps

A shared Qt bottom-edge handle is available in native Pi, Home and preview app
screens. A short upward flick of at least 60 logical pixels returns Home; a slow
release (300 ms or longer), or an upward drag of at least 72 pixels followed by a
160 ms pause, opens the app switcher. Short/cancelled gestures do neither. A tap
on the handle remains an accessible Home fallback. The strip is above the on-screen
keyboard when it is present; it does not intercept the keyboard's own bottom edge.

The current app shrinks interactively into an aspect-fitted, same-window Qt
texture. Home stays behind the shrinking app and switcher cards, not a dimmed
full-size copy of Pi or a mock app. Qt's built-in
[`ShaderEffectSource.hideSource`](https://doc.qt.io/qt-6/qml-qtquick-shadereffectsource.html#hideSource-prop)
remains active throughout navigation, even after the live texture gives way to
retained cards; source rendering for image capture and normal app resume stay
intact. Home's backdrop content is visible but non-interactive.
The switcher retains a proportional last-view image for each opened app,
not just the active one. Capture finishes before leaving its source view; opening
another app does not replace previous cards. Swipe horizontally and tap to resume.
Swipe a card upward by at least 80 logical pixels or 20% of its height (whichever
is larger) to dismiss it; short, downward, cancelled or blocked drags do not close
anything. Dismissing the active card returns Home; dismissing an inactive card
leaves the foreground app alone. Pi dismissal removes its card, not its saved
conversation: backend, draft and any reply stay alive, and Pi can be reopened.
Unintegrated entries remain explicitly labelled previews. Vivaldi's real window
adapter uses the same cards/gestures and sends a graceful, exact-window close
request; a browser confirmation keeps the card until the window actually closes.

Images use Qt's built-in in-memory `ItemGrabResult` URLs, with the retained result
owning their lifetime, and `Image.PreserveAspectFit` (no screenshot utility or new
dependency). Each image is capped at 900 pixels on its longest edge and released
on dismissal. Images are not written to disk or exported through handoff IPC;
a frontend replacement recaptures the current app, while inactive cards use their
text summaries until opened again. This cache lifetime is distinct from app IDs,
which do survive handoff.

Opened IDs, active preview and switcher visibility travel through the existing
frontend handoff in `TABLET_UI_NAVIGATION` before the candidate is admitted; no
chat text or screenshots are put in that environment variable. A UI update freezes
the switcher instead of closing it, including rollback. Voice/dialog arrival
instead returns to the app's controls. Navigation refuses unresolved dictation:
finish or explicitly cancel it first; even native `home` IPC cannot silently
cancel it. No compositor gesture plugin or global input injection is involved.

## Transition evidence

`tests/tablet-iteration-shell.nix` runs a private software Labwc compositor inside
the Nix sandbox, with no host Wayland socket, physical input devices or microphone. A
fixture supplies glaring magenta work wallpaper **and desktop chrome**. A lossless
60 fps video covers the initial guarded entry and actual session Home with Pi
still stopped, every simulated app, lazy Pi startup with delayed history, Home/Pi
switches, live UI replacement across
different immutable asset paths, invalid-QML rollback and storage/input deferrals. Delayed backend history and a
failed draft restore must keep chat unmapped and the launch cover visible; only
the still-unmapped frontend is restarted after repairing the private fixture.
An admitted startup-question scene must stay mapped after its answer while
history remains deliberately delayed. Initial Home→Pi asserts identical frontend,
stage and backend-host PIDs and preserved app history; an additional idle-host
probe closes cleanly without starting Pi. The journey no longer substitutes a
standalone Home fixture for the production entry.
`check_tablet_frames.py` checks every pixel of every recorded frame, verifies the
decoded frame count, and emits a bounded JSON summary/contact sheet. A separate
negative-control recording after explicit exit must expose and detect the work
desktop. The large recordings are temporary build artifacts, not stored outputs.

Python checks separately reject transparent, undersized, wrong-owner and duplicate
Hyprland surfaces; they verify cover-before-workspace ordering, guarded release
and stage-last cleanup. Setup also scans a real-shaped `/proc` fixture containing
another Quickshell process, so panel discovery cannot overwrite the selected app
entrypoint. Retired/disconnected polling clients must not tear down the supervisor
or expose the desktop, including a non-reading client whose large reply times
out. Pure Qt checks cover the reusable animations, layout, ordinary-window
activation, explicit composer/Tab focus and dialog editing without a helper
pre-blurring every new chat.

The private Wayland fixture additionally registers a virtual keyboard seat that
sleeps without sending keys, and uses a virtual pointer only after asserting the
headless fixture environment. This activates the actual OnDemand Pi layer by
clicking non-text header padding, selects its editor, exercises controller Home/Pi
remapping, and checks that stale editor focus does not return. It preserves
legitimate editor focus/cursor/draft across UI handoff and clears input on a
transcript tap. That remap regression failed before the focus correction.

The fixture now also starts **real Squeekboard on a private D-Bus session** with
private keyfile settings. It reads the keyboard's own `Visible` property rather
than inferring it from Qt focus. Editor selection must show the keyboard; header,
margin and transcript taps must actually hide it, and reselecting the editor must
reopen it. Home/remapping and genuine-focus handoff are checked too. The real-panel
check failed even after Qt focus cleared, exposing the missing visibility bridge.
The supervisor addresses only a PID-verified unique bus peer; tests reject foreign
keyboards, stale frontends, background requests and delayed shows over Home.

These are actual keyboard visibility checks in the hermetic compositor, **not**
a physical laptop/Squeekboard acceptance recording.

**Limit:** Labwc video is not a recording of real Hyprland workspace animations.
An attempted nested pinned-Hyprland test could not initialize Aquamarine's backend
inside the hermetic software-only sandbox; no GPU/device access or sandbox
exception was granted to force it. Real-device Hyprland transition/rotation,
keyboard, dictation and actual external application checks remain acceptance
work, not claimed proven by settled screenshots or this private recording.
