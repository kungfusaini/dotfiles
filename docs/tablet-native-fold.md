# Native tablet workspace resume

## Required lifecycle

**Fold switches into the dedicated `tablet-trial` workspace and resumes the
state there. Unfold returns to the laptop workspace and focus that were left.**
Laptop apps are never adopted, borrowed or transported into tablet mode. The
same Hyprland session and normal browser profile are retained, but they do not
imply using the laptop's current workspace or browser window.

The companion-dependent proof now removes visible desktop-exit buttons and
pauses only the registered tablet browser's supported media on exit; see
[tablet media companion](tablet-media-companion.md). Its real-profile installation
is a separate gate. Do not install the new native package without its companion.

The earlier in-place native trial (`1d13607`) used the wrong workspace model.
Its successful fullscreen/design proof is reusable; its foreground-app entry
semantics are superseded. The installed default is not changed by building this
corrected package. Host/assets installation can precede physical acceptance with
automatic routes disabled; physical acceptance precedes enabling the native
automatic default.

## Persistent state and application ownership

- Tablet apps remain in `tablet-trial` on unfold. They are not closed/restarted
  or moved back to the laptop. Native presentation, IME and rotation ownership
  are released, then the exact originating laptop workspace/focus is restored.
- Home/app view, settings/switcher state and the selected tablet browser's
  address/PID/start-time/class/stableId are saved privately in
  `$XDG_STATE_HOME/tablet-native/session.json`. Browser tabs/logins/page state
  remain in the real application; they are not inspected, copied or serialized.
- Next entry resumes the exact still-valid tablet-local source and view. A
  disappeared, moved or recycled source is not replaced by a laptop browser.
  With no saved source, a single eligible native browser already in the tablet
  workspace can be registered. Ambiguity is not permission to guess.
- An empty tablet workspace opens Home with a real **Vivaldi** launcher. Clicking
  it creates a new tablet-local window using the normal browser profile.
  Existing laptop browser windows remain untouched. A unique local-page nonce,
  a pre-launch client snapshot and verified normal-process ancestry identify
  only that new window; placement is specified at creation, not by moving a
  guessed existing client. A launch arriving elsewhere is not reclaimed.
- The existing warm-browser/IME capability verifier is reused, without probing
  other compositors' background processes. Native launch is warm-only: an
  already-running compatible **normal-profile** browser is required, but it
  need not be focused or on the tablet workspace. A custom-profile process is
  not authority to cold-start the normal profile and restore unrelated windows.
  If normal Vivaldi is not running, Home reports that limitation; it does not
  restart another profile or silently restore desktop windows.
- Vivaldi remains the first real-window adapter. Other app integrations and a
  general multi-app switcher are not claimed. Legacy Pi/chat data and app
  ownership records are preserved, not migrated or erased by this change.

## Original presentation, native windows

`native.qml` reuses the actual `TabletHome`, `TabletWallpaper`, `ControlCenter`,
`GlassTile`, `PillSlider`, `AppNavigator`, `BottomGesture` and `AppHistory`
components. Icon geometry, typography, glass materials, Home fade/scale, drawer
animation and swipe/pause navigation remain in those components. Their legacy
preview defaults remain unchanged. Native mode suppresses the mock app surface.

A transparent overlay exposes the real native browser, not a screenshot or
floating rectangle. Its fullscreen lease is scoped to the tablet-local
address/PID/start-time/stableId/tag. Internal/client `2/1` provides native app
maximization, while real client media fullscreen can request `2/2`. There are
no permanent reserved bands or repeated geometry enforcement. Legacy IPC acts
on the active window: transitions remain focus-checked, **not compositor-atomic
conditional transactions**.

Idle input regions are the top-right 144×24 corner and bottom-centre 160×14
edge. Initial bottom contact expands the mask for the original navigator;
quick swipe goes Home and swipe/pause opens its card. Gesture and input-region
geometry both move above the native IME. A real browser card has an honest text
summary, not a fake live preview. Card dismissal does not close desktop windows.

Volume/mute and brightness use real backends; missing controls are disabled.
Unconnected battery/network/media readouts say unknown/not connected rather
than showing preview values.

The established `stage.qml` owns an opaque Home floor and fresh overlay cover.
Its rendered-frame acknowledgement and matching PID/layer/geometry/alpha check
must pass **before workspace entry**. The already-installed
`tablet-rotation-fade` no-animation rule is required; compositor alpha is a goal,
not evidence that a fade completed. The native frontend acknowledges its own
rendered view before the cover is revealed. Home covers browser launch until
the new tablet window is verified and natively maximized. Exit covers window/IME
teardown and workspace return; the stage stops last. Independent parent-lifetime
watchdogs prevent orphan covers. See [continuous presentation](tablet-presentation.md).

## Posture, rotation and recovery

`watch-fold` shares the old watcher's singleton lock and refuses coexistence.
A fold starts/resumes the tablet session without resetting its saved view.
Folding an already-open manual tablet session adopts fold ownership without
resetting it; unfolding then exits it. An unfolded manual session is not closed
without a fold. Explicit exit while still folded consumes that edge and does
not repeatedly reopen Home. Headless folds are consumed without takeover on
wake; unknown posture is not an unfold. External-display focus, special
workspaces, sleeping eDP-1 or a tablet workspace on another output block entry.

The established orientation controller and declared touch/pen policy are reused.
Native eligibility requires an exact live same-compositor backend lifetime,
explicit rotation ownership and the foreground tablet workspace/source.
Separate native daemon/journal names prevent an idle legacy controller from
restoring new rotation state; the operation lock still serializes transactions.
Sensor claims, fade, input transforms, config-token handling and suspend timing
remain in the existing controller.

Recovery records workspace return context **before** entry and before client
mutations. Cleanup independently attempts journaling, rotation restoration,
IME/settings restoration, client release and eligible workspace return, then
stops the stage. Coverage is revalidated after rotation/child shutdown and
immediately before client/workspace changes. A dead stage is replaced with a
new verified cover; native crash recovery establishes its own cover before
retiring old presentation children. If coverage cannot be obtained, input and
sensor ownership can be released but client modes/workspace return are deferred
with recovery evidence retained. A completed lease is recorded so
later rotation-only recovery does not need a removed tag or a focus change.
Child exit during lifetime lookup does not abort journaling. An intentionally
empty origin can be recreated on return; a vanished origin that contained apps
is not silently recreated. User workspace escape is never followed by a focus
steal. A failed focus-checked client release cannot return to another workspace.
Automatic recovery never activates a background browser; explicit coordinated
`recover --activate` targets only the recorded lifetime. Apps are never recreated
as crash recovery. Legacy trial/workspace entry is blocked while native recovery
state is owned; active or pending legacy sessions block native entry.

## Verification and physical gate

Build/run only the packaged store program, not checkout Python/QML:

```sh
.../bin/tablet-native start
.../bin/tablet-native status
.../bin/tablet-native close
.../bin/tablet-native recover --activate
.../bin/tablet-native watch-fold
```

Private tests must start from an unrelated laptop app, not a prepared laptop
Vivaldi window. They cover tablet Home/app resume across repeated folds, exact
laptop focus/layout return, no laptop-window moves, tablet-only new browser
launch and reuse, native app/media fullscreen, global settings/navigation over
video and above IME, real native typing, shared rotation with a private fake
sensor, and SIGKILL/focus-loss recovery. Normal exit must not silently depend on
supervisor recovery. Cover timeout/loss, dead-stage replacement and covered
backend-crash recovery are checked too. Qt checks retain original layout/animation/touch coverage;
Python checks reject laptop adoption and stale/recycled/wrong-workspace sources.
No host system bus, physical sensor, real browser profile, audio or backlight is
used by the private compositor suite.

For physical acceptance, temporarily replace only the verified old watcher with
the committed new store watcher, preserving the old command for reversal.
**Do not prepare/focus Vivaldi: fold from normal laptop use.** Open/use the tablet
browser, unfold, continue laptop work, then fold again and verify the same tablet
window/view resumes. Check Home resume too, fullscreen video, touch typing,
portrait touch/pen alignment, manual exit while folded, and suspend/resume.
Only after acceptance coordinate required stream changes onto canonical main,
validate its exact committed snapshot and use the authorized deployment workflow.
An exec-once source change does not replace an existing watcher: verify the
running generation explicitly. Preserve unrelated canonical work and never
promote the whole historical stream branch wholesale.
