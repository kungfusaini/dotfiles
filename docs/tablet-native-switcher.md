# Native switcher previews and window dismissal

This extends the Vivaldi/Pegasus/[Stremio](tablet-stremio.md) native tablet workspace, not the set of supported
apps or the permanent fold policy. Automatic native folding remains a separate
physical-acceptance gate.

## Window pixels, not desktop screenshots

`NativeAppPreview.qml` reuses Quickshell's
[ScreencopyView per-toplevel capture](https://quickshell.org/docs/v0.3.0/types/Quickshell.Wayland/ScreencopyView/),
already used by the older `ExternalAppView`. No new capture service, browser
extension, monitor screenshot, disk-thumbnail library or compositor patch is
introduced. The ordinary app stays a real interactive window.

The backend publishes two separate maps:

- `cardLifetimes`: registered address/PID/start/class/stableId and compositor
  lifetime still exist. This retains the card and its cached image.
- `cardSources`: that exact window is also mapped/eligible in `tablet-trial`,
  with matching ownership tag when leased. Only these windows may be captured,
  resumed or closed.

Quickshell additionally matches its toplevel metadata against the descriptor;
permission changes trigger an explicit refresh. A temporarily unmapped, moved,
pinned or grouped window loses capture/actions, not its registered identity or
last cached frame. Cards show “unavailable” and cannot open a substitute. An
ineligible live game is not silently replaced by its still-running library.

`AppHistory` keeps ItemGrabResult images in memory. Their ownership key prevents
an old asynchronous grab from populating a replacement card. Identity change or
verified disappearance releases pixels. Folding destroys the frontend/cache;
only identity/navigation metadata are persisted. Never export real user previews
into test screenshots, recordings, logs or Git without separate capture consent.

## One interaction selects one lifetime

At pointer/touch press, the card freezes an immutable descriptor. The descriptor
must remain current at release and again after asynchronous frame retention.
Both resume and dismiss carry that descriptor to the backend, rather than looking
up whichever window currently occupies an app slot. If a game exits mid-swipe,
the gesture is cancelled, not retargeted to the library. A new press can select
the new library card.

The backend revalidates registration, process lifetime, eligibility and current
internal tablet workspace. Native Lua resolves the window object and checks
stableId/PID/class/workspace/tag/floating/group/pin in the same callback as its
addressed focus/normal-close request. This does not kill a PID, force-close an
application, act on a shared browser process or operate on an unrelated window.
Card resume never falls back to launching another window. Launcher icons remain
a distinct action, and also refuse a live ineligible registered source.

The card scene stays until authoritative acknowledgement. A dismissed card
animates offscreen during capture/request instead of snapping back on release;
failure restores it. A per-gesture completion token prevents an old failed
request from resetting a newer gesture after the switcher is reopened. On close, the selected
original is revealed so beforeunload/application confirmation can be answered.
The card is removed only after disappearance is verified; refusal/cancellation
keeps it. Quickshell/Wayland
[normal close is a request](https://quickshell.org/docs/v0.3.0/types/Quickshell.Wayland/Toplevel/),
not a guarantee that every third-party app honors it.

Stremio uses the same per-window capture, frozen interaction and guarded normal
close. Its client normally hides to tray; only the explicit Home launcher can
reactivate the exact owned singleton, not a stale card or desktop instance.

The games card represents the running game, otherwise its library. Normal close
of the game preserves the library. A subsequent library-card dismissal requests
closure of that library, not its browser or game process tree. Unfold alone still
does not close applications. A lost process with a lingering compositor client
snapshot is reconciled as disappearance; permission/read failures are not.

## Interaction and lifecycle invariants

- View/control observation survives temporary attached-browser ineligibility;
  strict fullscreen/lease mutation guards are not relaxed.
- Status/IME updates do not rebuild an unchanged card model or destroy an active
  DragHandler. A deliberate mid-drag metadata-update regression covers this.
- Cards fit above keyboard plus Home handle in landscape/portrait. Upward card
  swipes cannot accidentally begin on the Home indicator.
- A real-frame capture can be asynchronous. The current Home visual is retained
  until it hands off to the already-guarded native Home presentation.
- No failure is permission to adopt a replacement, recreate an app, force a
  close, bypass a confirmation, or steal focus from another workspace/output.

## Verification

`tests/tablet-home-preview.nix` covers layout, pointer/touch gestures, retained
frames, stale press/drag/async-capture identity, unavailable cached cards and
acknowledgement behavior. `test_tablet_native_fold.py` covers lifetime scope,
stale close/resume rejection, process-exit races, attached-browser ineligibility,
no replacement launch/library substitution and addressed callback guards. Existing
mocked Python contracts use explicit `HYPRLAND_CONTROL_TEST_BACKEND=legacy`.

`tests/tablet-touch.nix` renders actual native browser/video/game/library content
in a hidden private Lua compositor, asserts preview pixels and sends real
`wl_touch` card gestures. Its beforeunload fixture verifies refusal/cancel/retry;
shared-process laptop windows survive. A game exits while its card is grabbed;
the library survives the obsolete gesture. A moved live card retains its cache
but rejects stale close/resume with an unchanged window set; restoring the same
window permits capture again. Recordings/timelines retain those transitions.

These are isolated synthetic-profile tests, not proof of physical pen/touch,
all games' confirmation behavior, real account/site contents or iPadOS parity.
Use the recorded evidence and a separate supervised device trial before enabling
the new native fold route permanently.
