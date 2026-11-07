# Native tablet Pi chat

`tablet-home-preview` now starts one supervised tablet session on Home.
The **Pi** icon opens a small native Qt chat in that **same frontend**, not another
Home/interface/workspace or a borrowed terminal. Its backend starts lazily on the
first tap; the shared stage, settings, app history and keyboard lifecycle already
belong to the session and are not restarted.
It has a message list, composer, Send/Stop reply, New chat, Home and Exit tablet. It is a separate
persistent tablet conversation; the existing terminal session is untouched.
No file explorer, IDE, terminal controls or model-picker UI is added.

## App navigation

Flick upward from the bottom handle to return Home without stopping Pi. Swipe
up slowly or pause mid-gesture to open the horizontal app-card switcher; tap Pi
to resume the same conversation, draft and streaming reply. Home also has the
same switcher, with proportionally fitted last-view previews retained when opening
another app. Swipe a card upward to dismiss it; dismissing Pi returns Home without
deleting its conversation or draft, and does not terminate its backend.
Finish or explicitly cancel pending dictation before navigating;
it is never discarded by a Home gesture. See [presentation](tablet-presentation.md#bottom-navigation-and-open-apps)
for gesture thresholds and frontend-handoff behavior.

Vivaldi now uses the shared switcher with a real native window, not a simulated
browser screen. Its exact-window ownership, normal-profile/IME compatibility,
parking, keyboard and graceful-close policy are documented in
[native tablet apps](tablet-window-apps.md). Spotify, Pegasus and Krita remain
previews; their icons are not evidence of real app integration.

## Input behavior

- Opening/resuming Pi uses an explicit non-text focus target. The composer’s
  nested focus flag is cleared on navigation/visibility changes, so a later
  window activation cannot silently restore it and summon the keyboard.
- Tap the composer (or deliberately Tab into it): Qt's Wayland text-input focus shows the existing Squeekboard
  backend and reveals the Mic action.
- Tap the header, margins, message area, unused action-row space or scroll/go
  Home: input focus is cleared, the keyboard hides and the idle Mic hides.
  Tapping inside the editor frame reactivates input. Send/voice editing buttons
  retain their deliberate cursor/focus behavior; active voice controls persist.
- Qt focus alone is insufficient to dismiss Squeekboard on this stack. The
  supervisor synchronizes visibility via [Squeekboard's supported D-Bus API](https://developer.puri.sm/Librem5/APIs.html#on-screen-keyboard).
  It verifies the current frontend PID and owned keyboard process, resolves the
  service's unique bus peer and refuses foreign/stale/background requests. A
  delayed show request cannot reopen the keyboard over Home. No global toggle,
  simulated Escape or unowned keyboard operation is used.
- Mic is always explicit. Focus never starts recording. Stop/Cancel/pending
  dictation controls remain visible even after focus is lost, so an active
  recording cannot be hidden accidentally.
- **Mic → Stop recording → Use dictation** inserts text directly at the native
  composer cursor. It never sends, simulates keystrokes or touches the clipboard.
- Send is a separate action. During a reply it becomes Stop reply; drafts remain
  editable. Home hides the chat but preserves its draft and running Pi process.
- An approved live frontend update restores a genuinely focused composer and
  exact cursor/draft, not implicit entry focus. Dictation insertion deliberately
  focuses the editor; it still never sends. Pending voice controls remain visible.
Draft text is also autosaved atomically in the private workspace state directory,
with a synchronous save on Home/Close; rejected sends are returned to the draft.

**Home** is the in-tablet return path. **Exit tablet** explicitly ends the trial
and requests orderly RPC shutdown; it is not an app-to-Home transition. Closing an active reply stops it; changes
already made by tools are not rolled back. The persistent conversation is loaded
again next time. The chat's Exit tablet button asks for confirmation when a reply or
voice operation is pending, or the current session selection is not safely saved. The Home control-centre exit is an explicit trial
exit and also stops the backend.

## New chat

**New chat** starts a separate Pi session in the same registered workspace. It asks
before stopping a reply or discarding a non-empty draft. Finish or cancel pending
voice input first; New chat never implicitly discards dictation. The frontend
pauses draft writes while Pi acknowledges `clear_queue → abort → new_session →
get_state → get_messages`. Only a successful, uncancelled reset clears the transcript/draft.
An extension veto or error retains both; previous session files are not deleted.
There is no automatic prompt in the new session. Pi lazily creates session files
only after an assistant entry, so private `selection.json` remembers the chosen
session path: reopening an unused New chat stays fresh instead of resurrecting
the old conversation, and resumes that exact file once Pi has persisted it.
Each fresh startup refreshes this bookmark to its new actual session path.
Selection writes are independently retried and verified against disk; while a
save is pending, a persistent warning remains visible and live UI handoff waits.
Close warns about the unsaved selection rather than silently treating it as saved.

## Live UI updates

After an **approved frontend edit**, the tablet agent runs:

```sh
"$TABLET_ITERATE_BIN" update-ui
"$TABLET_ITERATE_BIN" status
```

Native-window views defer a frontend replacement until Home or Pi, preserving
the active app's input/capture surface. Backend/registry changes require a newly
started compatible trial, never a frontend-only injection or silent chat restart.

The helper builds the pure Qt/headless-compositor checks and `tablet-ui-bundle`
from the **registered Nix worktree**, then queues the immutable store bundle. It
does not stage files, commit, invoke a model, run a privileged rebuild or deploy
NixOS. As with other flake builds, new source files must already be tracked.
`uiUpdate.phase` is `queued`, `loading`, `applied` or `failed`; “staged” is not a
claim that the screen has changed. Waiting for dictation or in-flight input actions
is shown in the chat. An open extension dialog defers handoff, preserving its
unfinished answer/selection; a quarantined scene cannot answer a late-arriving dialog. A queued update applies after those actions finish.

The existing Pi RPC client runs in a separately supervised, windowless
`agent.qml`; frontend-only `PiClient.qml` reconnects over built-in
[Quickshell IPC](https://quickshell.org/docs/v0.3.0/types/Quickshell.Io/IpcHandler/).
A managed [Process](https://quickshell.org/docs/v0.2.0/types/Quickshell.Io/Process/)
would be killed on a shell reload, so simply using `PersistentProperties` is not
sufficient. There is no new HTTP service or detached/untracked agent. Prompt
bodies travel through stdin and 0600 temporary files, not command-line arguments.
Editor/rejected-prompt events are acknowledged only after a synchronous draft
save and backend verification against the actual file. Failed writes leave the
event recoverable, retry persistence without reinserting text, and defer handoff.

The [persistent tablet stage](tablet-presentation.md) is rendered and confirmed
compositor-opaque before entering the tablet workspace. It survives UI processes;
Home/Pi switches also use a fresh cover so desktop chrome never fills their gap.
The supervisor waits for completed dictation and pending input/reset operations,
quiesces the old composer, flushes its exact draft/cursor, and starts the new
screen **while keeping the old opaque tablet backdrop mapped**. Only a rendered,
reconnected, draft-restored scene can acknowledge readiness; compositor opacity
and geometry must also pass before retiring the old surface. It then retires the
old screen; the same Pi process continues its reply. A failed/timed-out candidate
is stopped and the original screen re-enabled. No keyboard/voice process is
restarted for a UI refresh. Composer focus is restored locally when appropriate;
compositor policy may still require a tap to reacquire input on the new surface.

Workspace-private `ui-roots/<id>` links keep built bundles alive across garbage
collection; `current-ui.json` selects the last successfully applied UI on reopen.
The bundle protocol/backend signature must match the running controller, Pi
client, input/runtime/model configuration and tablet prompt context. Backend
changes are **not** silently applied: coordinate a trial restart separately.
Full-system promotion/deployment remains outside this preview feature's approval.

The initial upgrade from the older native-UI-owned backend needs
one normal close/reopen when idle. Only trials started with this decoupled backend
support live UI handoff; do not kill an older active conversation to upgrade it.

## Workspace and context

`tablet-chat bind` registers the current worktree and non-secret Project Object
scope fields, not a terminal PID or this conversation's session ID. The agent
runs this registration before opening the preview. Opening refuses a missing
worktree instead of silently using a different directory.

The RPC subprocess uses the registered working directory, normal Pi resources
and configured credentials, the default non-NanoGPT model policy, and an appended
`tablet-context.md` describing touch/voice/tablet use without weakening any
approval or project guidance. Its history is under
`$XDG_STATE_HOME/tablet-chat/<workspace-hash>/`, with a separate private runtime
under `$XDG_RUNTIME_DIR/tablet-chat/`. CLI `--session-dir` initially continues only this tablet history, never a live
terminal conversation. After New chat, selection is explicit (or stays fresh
while the chosen session is still empty).

No initial model prompt is sent automatically. Startup reads history only.
`--offline` disables automatic Pi network discovery, not explicit user prompts.
The frontend uses Pi's supported [RPC protocol](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/rpc.md):
strict LF-delimited JSON, continuous output consumption, correlated prompt
responses, streamed text blocks and `agent_settled` rather than `agent_end` for
completion. Extension-handled prompts that start no agent run are reconciled
with authoritative RPC state instead of waiting forever for a settled event.
Tool activity is one compact status line, not an IDE panel.

Extension confirm/select/input/editor requests are rendered as native dialogs;
Cancel never grants approval. Notifications are shown, editor-text requests
populate the draft without submitting, and unsupported TUI-only features are
not emulated. Message rendering is plain text, so replies cannot fetch remote
images or execute HTML. Initial scope is text chat; image upload and rich
Markdown are not implemented.

## Reused trial infrastructure

This is still an explicitly started, reversible trial, not the default deployed
fold shell. It reuses the managed Squeekboard/private Voxtype/settings/cleanup
lifecycle described in [tablet-iteration-trial.md](tablet-iteration-trial.md).
The old terminal-based trial binary remains only as a reference/fallback;
**the Pi icon now uses native chat and never moves or resizes a terminal.**

The chat panel uses on-demand keyboard focus, stays over the tablet backdrop,
and accounts for the keyboard's reported reserved monitor space. All microphone
operations still use the isolated on-demand Voxtype instance, never desktop
recording controls. Conversation replies, keyboard showing/hiding and local
voice capture require final real-device/user acceptance; source/headless tests
do not claim that physical flow has been exercised.

## Validation

- Python tests cover context registration without a terminal, native navigation,
  direct dictation insertion without clipboard/Enter, and the existing lifecycle.
- Pure Qt tests cover composer focus/Mic visibility, blur, explicit voice/send,
  retained recording controls, drafts, New chat/voice guards, update locking,
  portrait header layout, and visible cancellation of confirmations.
- The isolated headless Labwc test loads the real native scene and exercises the
  actual QML subprocess client against a fake JSONL Pi: history, multi-block and
  Unicode-separator streaming, settled lifecycle, confirmation correlation,
  draft injection without auto-send, and EOF shutdown. No model, real keyboard,
  microphone, host display, host focus or global input is used. New-session
  tests cover an extension-cancelled reset followed by successful empty history.
- A second private-compositor integration uses the real controller/IPC/frontend
  with fake Pi: an ongoing stream survives UI process replacement with exactly
  one backend PID; draft survives; fake pending dictation defers application;
  invalid QML rolls back; pending extension input defers replacement without
  automatic answers; unwritable draft storage fails safely, rejects premature acks and
  retries after recovery before replacing the screen; failed selection-marker
  writes retain a visible warning and recover before queued handoff;
  cancelled/successful New chat preserve
  or clear the draft/history respectively.
- `tests/tablet_pi_selection.py CONTROLLER.py UI_BUNDLE PI_BINARY` is an optional
  installed-Pi probe. It runs the real windowless backend offscreen with resources
  disabled and synthetic saved-message fixtures: failed selection writes retry,
  empty New chat stays fresh after close/reopen, and the exact selected saved
  file resumes. It sends no model prompt and tests neither authentication/model
  replies nor configured third-party extensions.

```sh
python -B -m unittest discover -s tests -p 'test_tablet_*.py'
nix build --impure --no-link --expr '
  let f = builtins.getFlake (toString ./.);
  in import ./tests/tablet-home-preview.nix { pkgs = f.nixosConfigurations.kirax1.pkgs; }'
nix build --impure --no-link --expr '
  let f = builtins.getFlake (toString ./.);
  in import ./tests/tablet-iteration-shell.nix { pkgs = f.nixosConfigurations.kirax1.pkgs; }'
```
