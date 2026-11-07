# Native tablet apps: Vivaldi first

The roster is Pi, Vivaldi, Spotify, Pegasus and Krita. Only Pi and Vivaldi are
integrated; the other three remain explicitly labelled preview scenes. No app
management UI, AI plugin, model or new system service is included.

## Reusable boundary

- `apps.json` is the shared declarative registry for the controller, frontend and
  persistent Home/cover stage. It supplies IDs, labels, icons, provider kind and
  provider-specific launch/capability metadata. Non-native `tablet-iterate`
  downgrades window providers to previews rather than offering a broken route.
- `tablet_apps.py` owns exact native windows and their launch/park/resume/close
  lifecycle. The supervisor owns policy, voice/question guards and presentation
  barriers; neither the frontend nor the registry can submit arbitrary commands.
- `ExternalAppView.qml` adapts a verified native toplevel to existing
  `AppNavigator`, `AppHistory` and `BottomGesture` components. Pi retains its
  native QML adapter. Other real apps should add provider metadata/necessary
  capability handling, not duplicate the Home/switcher or Pi's RPC machinery.

The implementation adopts Quickshell's maintained
[`ScreencopyView`](https://quickshell.org/docs/v0.3.0/types/Quickshell.Wayland/ScreencopyView/)
and [Hyprland toplevel metadata](https://quickshell.org/docs/v0.3.0/types/Quickshell.Hyprland/HyprlandToplevel/),
plus native window dispatchers. It does not embed Vivaldi in Qt WebEngine, add a
nested compositor to production, implement a capture protocol, or install a
browser debugger/extension. Nested compositors and a tiny libwayland pointer
client are test-only dependencies.

## Ownership and ordinary browser state

With a compatible normal Vivaldi window already running, this first adapter opens
a **new normal window in the normal profile**, not a separate profile or app-style
web wrapper. Existing bookmarks/logins remain available.
A private local startup page has a random title. A launch can claim only one
new mapped Vivaldi window with that nonce, excluding every pre-existing address.
Ambiguity/timeout leaves unknown windows alone and reports failure; a successful
process invocation alone is not a successful app launch. Claim also requires the
candidate to descend from the pre-verified warm process family with unchanged
start identities; a concurrent browser exit cannot silently turn this into a cold
session-restoring launch.

Once identified, the exact window gets a random dynamic tag. Future operations
require its address, PID/start time, tag, class and one of its explicitly owned
workspace locations. The capture adapter verifies address/PID/tag too and refreshes
metadata on record changes. A same-process/address replacement without the tag,
a user move to another workspace, pinning or grouping releases ownership.
Pinning/grouping the presented app returns to ordinary desktop management rather
than occluding that now-unowned input focus or moving an entire group. Never
close/move a guessed window, kill a browser PID, or inspect/store tab URLs to
route normal use. Runtime ownership records live privately under XDG runtime,
are scoped to the compositor, and are distinct from supervised process children.

Home/Pi first obtain the opaque launch cover, then park the owned browser in its
recorded random special workspace. This actually releases its keyboard/text-input
focus; simply painting Home above a still-focused browser would send keys to a
hidden app and could resurrect its OSK. Resume moves only that parked window back.
Explicit tablet exit silently returns parked windows to ordinary `tablet-trial`;
browser processes and unrelated windows remain alive. Before re-entering that
workspace, the next compatible controller validates and parks prior owned windows
under cover. Entry refuses unowned windows/dialogs rather than painting Home over
their native keyboard focus. Crash recovery keeps the
runtime identity available for the next compatible trial; it never signals a
shared browser process as a disposable UI child.

Card dismissal requests `closewindow` for that specific presented window. For an
inactive card it presents the window before requesting close, so confirmation is
visible. A refused/cancelled close leaves its card and window intact. Removal is
based on observed window disappearance, not a optimistic request acknowledgement.
App-operation races and refused dispatches return to covered Home with an error
after parking any surviving focused browser. A vanished window needs no parking.
Persistent parking failure refuses the Home handoff (or requires safety cleanup)
rather than hiding a still-focused native app; ordinary close/placement races do
not tear down Pi or the keyboard. Deferred closes are cleared on navigation
and operation failure, never delivered to a later unrelated reopen.

## Native presentation and input

The ordinary window is floated/fitted with address-specific operations between
32px top and 56px bottom opaque Home strips. No focused-window fullscreen
command, global browser rule, kiosk restriction or normal desktop layout change
is used. Initial reveal requires current native geometry, captured content,
rendered overlay frames and the existing stage/no-animation barriers. Unexpected
geometry drift is corrected under cover. Expected keyboard/rotation layout
changes resize over the persistent Home floor without a launch-cover flash.

The overlay's input region covers the top/footer strips only during ordinary
use, including the area that visually shields Waybar; body input passes directly
to Vivaldi. During a gesture/switcher it expands to the card scene. Capture targets
only the owned toplevel, never the whole desktop. Proportional snapshots are kept
in the existing in-memory cache; no user-page screenshots are written to disk.

Vivaldi's tested minimum height is 400 logical pixels. If keyboard reservation
leaves less room, the keyboard overlays the lower app area instead of endlessly
requesting an impossible resize. The bottom gesture strip stays above the OSK.
Small viewports, rotation and physical pen/touch still need device acceptance.

Vivaldi's real text-input protocol controls Squeekboard while the app is active;
Pi's focus bridge must not continuously force it hidden. Home/switcher entry
invalidates stale visibility acknowledgements and hides the owned keyboard.
Background Pi questions do not trap the user in Vivaldi: Home/Pi remain reachable
to answer; other app opens still refuse until input is resolved.

## Running-browser compatibility

This first adapter is **warm-only**: it requires an existing normal Vivaldi window
with explicit verified native Wayland/IME/text-input-v3 switches. Chromium forwards
`--new-window` to its existing process; new flags **cannot reconfigure that process**.
The guard checks same-user process ancestry (Chromium can expose a child PID) and
Vivaldi's flattened process-title argv. Executables are checked and parsing stops
before URLs. The same-user process probe also detects background-only browsers;
no compositor windows is not proof that a process is cold.

Cold/first-normal-window startup is intentionally refused before launching or
changing views. Actual tests showed Vivaldi restoring an extra normal session
window even with a two-phase `--no-startup-window` experiment. Those windows have
no proven tablet ownership and must not inherit keyboard focus invisibly behind
Home. No workaround that changes session restoration, guesses/moves those windows,
or uses another profile was adopted. Unexpected unmanaged windows/dialogs prevent
parking; failed app presentation with unowned native focus returns to ordinary
desktop management rather than painting Home above it.

XWayland and unverifiable IME processes are also refused before any launch/view
change. Implicit/default support without explicit switches is not claimed verified.

The approved ordinary-startup policy is defined in
`hosts/kirax1/modules/desktop/vivaldi.nix`: the upstream Nixpkgs
`commandLineArgs` override supplies `--ozone-platform=wayland`,
`--enable-wayland-ime` and `--wayland-text-input-version=3`. The overlay applies
to desktop launchers and Home Manager consumers through the shared package,
preserving any pre-existing wrapper arguments. No profile, startup-page,
session-restoration or search-policy setting is changed. Cold/first-window tablet
launch remains desktop-first: open a normal window, then use its tablet tile.

These flags take effect only when a new browser process starts. A running old
process is not reconfigured by deployment or by forwarding a new window request;
it remains guarded until a safe, explicitly agreed normal restart. No automatic
restart is performed. Do not claim seamless support for arbitrary already-running
or background-only processes.

## Verification

Unit tests cover nonce ambiguity, old/unrelated windows, window/PID/address/tag
reuse, user moves/groups, private ownership persistence, parking/resume/release,
capability flags including flattened argv/URL confusion, graceful closing,
rotation/keyboard geometry, dispatch failure and frontend/voice/question guards.
Pure Qt tests retain aspect, snapshot, Home-backdrop and gesture coverage.
The existing sandboxed Labwc test keeps external apps mocked and verifies Pi,
Squeekboard, dialog/draft protection and frontend handoff. UI replacement is
queued until Home/Pi rather than replacing a live native-window gesture surface.

For **actual** Vivaldi, build and execute the isolated native test:

```sh
nix build --impure --no-link --print-out-paths --expr '
  let f = builtins.getFlake (toString ./.);
  in import ./tests/tablet-window-apps.nix {
    pkgs = f.nixosConfigurations.kirax1.pkgs;
    hyprland = f.nixosConfigurations.kirax1.config.programs.hyprland.package;
  }'
# Run the returned path's bin/tablet-window-apps-test.
```

It uses a private GPU-backed Labwc parent and nested pinned Hyprland, one headless
output, private D-Bus/keyfile settings and a disposable established browser profile.
No host sockets, accounts, physical input, audio or models are used. Local pages
prove real click-through and native Squeekboard visibility. A persistent private
virtual pointer exercises the actual bottom handle and upward card dismissal.
The journey checks same-profile/process handoff, retained native previews,
Home-from-focused-input parking, resume, close confirmation, unrelated browser
preservation, reopening and cold-start refusal. Lossless video checks every pixel for glaring test
desktop/chrome; a negative recording must fail the detector.

`TABLET_TEST_UNCONFIGURED=1` runs the separate ordinarily-launched browser case
without verified IME switches, hiding compositor discovery from the guard to
exercise the process-only/windowless-warm path: it must remain untouched, with no
new window, restart, view switch or false keyboard claim. The native harness
limits process enumeration to its own known test browser; a separate unit test
checks the production same-user executable scanner against a private proc fixture. Logs/images/videos remain only in
the printed temporary test directory. These are not recordings of the user's
live desktop or proof of physical-device acceptance.

Backend/registry changes invalidate frontend-only compatibility. Never inject
this UI into an old controller or restart an active chat. Build the new preview;
start it only after the previous trial has been explicitly closed. Production
promotion, deployment, and the other real-app adapters remain separate work.
