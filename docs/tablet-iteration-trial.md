# Legacy borrowed-terminal iteration trial

The Home **Pi** icon now uses [native tablet chat](tablet-native-chat.md), not
this borrowed-terminal route. The shared keyboard, isolated voice and cleanup
infrastructure below is still used; terminal borrowing remains only a fallback.
User preference now explicitly allows a separate tablet conversation.

This is an explicit, reversible **live integration trial**, not a deployment.
The home-screen preview now includes **Improve tablet mode**. Unlike the other
simulated app icons, this icon opens the bound, already-running Pi stream.
No new Pi chat/process/session is created.

## Entry and navigation

The owning agent binds the intended terminal with the built package's
`tablet-iterate bind` from that Project Object terminal. Binding records the
compositor instance, stream UUID, terminal PID/start time, client address and
original workspace in a private runtime directory. Opening refuses stale or
ambiguous identities instead of launching a replacement chat.

Tap **Improve tablet mode** in the preview:

1. Enter the existing `tablet-trial` workspace using the packaged workspace
   controller, retaining its orientation/input/headless safety policy.
2. Temporarily bring only the exact bound terminal into that workspace as a
   floating window over the persistent tablet wallpaper and Home icons.
3. Start the previously successful Squeekboard input-method backend and the
   keyboard-only dark UK assets, scoped to the trial's keyboard process.
4. Show non-focus-stealing input controls above the terminal.

**Home** returns the terminal to its original workspace and raises the tablet
home grid; it does not leave tablet mode. Tap Improve tablet mode to bring the
same terminal back. Pi's original tiled/floating state and floating geometry are
journaled before borrowing and restored on return/recovery. If you move Pi to a
third workspace, its new workspace/position are respected while the trial's
floating/size changes are undone; a restoration failure retains the journal.
The trial refuses
fullscreen, pinned or grouped terminals instead of dismantling those sessions.

A separate opaque tablet Home base stays mapped below normal windows throughout
both views. Interactive Home is an overlay above apps only while Home is selected;
opening Pi no longer hides the tablet backdrop or exposes the work wallpaper.
Pi resizes/recentres only when display/keyboard reservations change, leaving room
for touch input and rotation without stealing focus. Closing/moving the actual
Pi terminal returns the UI to Home rather than terminating tablet mode; a closed
terminal is not secretly replaced with a new chat. Unresolved voice controls
remain visible on Home rather than hiding a possible recording.
**Close trial** restores the original surface/settings and returns from tablet
mode if this trial introduced that entry. Leaving the tablet workspace also
ends the trial; it never drags you back. There is a one-hour safety timeout.
Waybar stays unchanged. Other app/settings tiles still simulate their actions.

The dedicated workspace-entry command starts orientation but does not spawn the
ordinary button panel, avoiding an asynchronous startup/retirement race. Any
already-running ordinary panel is temporarily retired only when its QML source
exactly matches the known panel; it is restarted during cleanup.
No unrelated Quickshell instance, keyboard, application or terminal is killed.
An already-running Squeekboard/wvkbd causes preflight refusal, not a takeover.

## Automatic keyboard

This reuses the successful earlier Squeekboard trial, rather than substituting a
fold-only keyboard watcher. Automatic showing/hiding follows the compositor's
text-input/input-method protocol. The earlier native/Vivaldi trial was successful;
this newly packaged terminal integration still needs live user confirmation.
A terminal exposes a text-input surface, not semantic knowledge of Pi's editor
versus every other element in the TUI. Do not claim universal application support.

The wrapper packages the keyboard assets, schema paths and dconf integration.
It does not depend on `/run/user/1000/tablet-auto-keyboard-trial.py`, store paths
from that experiment, or files in a mutable repository checkout. Trial-owned
GSettings values are journaled before modification and restored on exit only if
they still match the trial's applied values; later user changes are preserved.

## Voice input

- **Mic** explicitly starts Voxtype recording. Selecting an input never records.
- **Stop** ends recording and waits asynchronously for transcription.
- **Insert draft** explicitly focuses and verifies the bound Pi terminal, then
  pastes the completed text without pressing Enter. Review/edit it in Pi before
  sending.
- **Cancel** discards the trial's dictation. Home/exit cancels an owned recording.

On the first explicit Mic action, a temporary Voxtype daemon starts in a private
runtime namespace using the existing local model with on-demand loading. It
writes to a private transcript instead of injecting into the currently focused
app. Per-recording `--no-auto-submit --no-smart-auto-submit`, plus a trial-only
config with automatic submission and OSD disabled, leave desktop Voxtype settings
and daemon untouched. No automatic output is used. Draft insertion temporarily uses the plain-text
clipboard and restores it if it remains unchanged. Rich/non-text clipboard data
causes insertion refusal; the transcript remains pending instead of destroying
that clipboard content. Plain-text clipboard access is internal, never logged.

The installed Voxtype interface has no recording-ID API, so a state-file check
alone cannot make shared-daemon Stop/Cancel race-free. Instead, **every tablet
voice operation uses the private XDG runtime**; normal desktop shortcuts still
address the original daemon. The private daemon's PID/start-time identity is
verified, and only its own state files are inspected. The original PipeWire and
PulseAudio runtime endpoints are passed explicitly so local audio remains usable.
No desktop keybindings, services, model files or configuration are replaced.

A pending voice operation is journaled **before** signalling Voxtype. A durable
guard remains until idle is positively confirmed, independent of UI recording
flags and the transcription waiter. CLI/inspection errors expose uncertainty
and retain recovery state; cleanup does not falsely declare the microphone idle.
A private daemon with unresolved voice state remains tracked for recovery rather
than being silently abandoned. PID identity must be confirmed before recovery
cancels it. A second local model instance can briefly consume additional memory
while tablet dictation runs; on-demand loading avoids another permanently
resident model. Audio capture/typing still require live user testing.

## Cleanup and recovery

`$XDG_RUNTIME_DIR/tablet-iterate/` is mode 0700; binding, recovery journal,
transcript and logs are runtime-only, never source-controlled. Cleanup terminates
only trial-owned keyboard/UI children, returns the borrowed terminal only if it
is still on the trial workspace, restores trial settings and restarts the known
normal tablet panel. A user-moved terminal is not stolen back.

A retained `recovery.json` prevents another trial from starting. The owning agent
can run the same packaged `tablet-iterate recover`; it requires the original
compositor and no active trial owner. It verifies child process start times,
waits for confirmed child termination (including transcription waiters), restores
journaled state and only cancels a positively identified private voice instance.
Unconfirmed ownership retains the journal. Failure retains
the journal instead of claiming recovery succeeded. Rebind after replacing the
Pi terminal or compositor. The application icon never guesses a new session.

## Validation

```sh
python -B -m unittest discover -s tests -p 'test_tablet_*.py'
nix build --impure --no-link --expr '
  let f = builtins.getFlake (toString ./.);
  in import ./tests/tablet-iteration-shell.nix {
    pkgs = f.nixosConfigurations.kirax1.pkgs;
  }'
nix build .#nixosConfigurations.kirax1.config.system.build.toplevel --no-link
```

Python tests use fake compositor/process/Voxtype/clipboard calls: they never
record, type into a real terminal or change real settings. The layer-shell smoke
check uses Labwc only as a **test dependency** with software rendering, a private
runtime/socket and headless backend, no host display/input devices. It loads
both Home and Pi surfaces using a status stub, without starting the supervisor,
keyboard, sensor or microphone. A mock floating application and bright magenta
work wallpaper reproduce the original layering defect. Pixel assertions verify
that tablet Home covers the application in Home view, the app renders above it
in Pi view, and neither view leaks the work wallpaper. The test derivation
retains its isolated Home/Pi screenshots for review. Plain offscreen Qt cannot load a PanelWindow
backend, so it is not an adequate integration smoke test.

Live acceptance remains: open the exact stream, check automatic keyboard
appearance and touch typing, Home/re-entry, deliberate voice recording and
no-submit insertion, and cleanup/rotation restoration. Agents must not silently
record audio or induce physical rotation to perform these checks.

## Reuse rather than a new dictation stack

The system already provides Voxtype; its
[record/file-output controls](https://github.com/peteonrails/voxtype/blob/dev/docs/USER_MANUAL.md)
are reused with per-recording overrides, not a new cloud API or transcription
service. The existing desktop Parakeet daemon and model files remain unchanged;
the temporary tablet instance reuses the installed binary and cached model. Kitty's
[text-input support](https://github.com/kovidgoyal/kitty/issues/3410) supplies the
compositor input-method path; no second agent, terminal frontend or custom IME
is introduced. A private instance, rather than a racy check followed by a global
Stop/Cancel signal, provides isolation from concurrent desktop shortcuts.
