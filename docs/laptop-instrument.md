# Laptop keyboard instrument: VMPK → Ardour

VMPK is the playable controller; Ardour's **ACE Fluid Synth** with the
**FluidR3 GM2** SoundFont supplies the General MIDI sounds. No physical MIDI device, recording, or running transport
is needed. Start **VMPK** first, then open
`~/Music/ardour/Laptop Instrument/Laptop Instrument.ardour` in **Ardour**.
Keep VMPK focused while playing. Its Program selector and sustain control can
also be touched directly; touching another application's window changes focus.
This initial setup does not implement global key interception or a separate
touchscreen dashboard.

## Visual first-use view

Open **Laptop Keyboard Guide** from the app launcher (or run
`laptop-keyboard-guide`) beside VMPK. It shows a large two-octave piano with
laptop-key letters, plus all four typing rows with each mapped note labelled.
The home row, black-key row, lower notes and upper notes use different colours.
The PNG/SVG reference is generated from the managed XML map at build time,
not maintained as a second hand-written mapping.

VMPK itself starts with **all note names visible**, using C4 for MIDI note60,
and highlights notes while they are played. Its visible piano is limited to
the mapped C3–G6 span (44 semitones), rather than shrinking the keys to show
unused higher octaves. Its Program selector shows the
selected sound. VMPK does not natively put this custom typing-key mapping on
its piano, so the companion image supplies that reference without patching
VMPK or replacing it with a custom instrument.

The guide is **static**, not a playable touch keyboard or a live display:
keep VMPK focused for key input and highlighting. It represents Base Octave4,
Transpose0 and the managed baseline; octave shifts and custom maps can make
the reference differ from the current instrument. Existing user preferences
are not overwritten just to force labels on: if VMPK was configured earlier,
choose **View → Show Note Names → Always** to enable them.

## Playing layout

43 typing keys are mapped. At the initial Base Octave of **4**:

```text
Home white keys: A  S  D  F  G  H  J  K  L  ;  '
Notes:          C4 D4 E4 F4 G4 A4 B4 C5 D5 E5 F5
Black keys:     W=C#4 E=D#4 T=F#4 Y=G#4 U=A#4
                O=C#5 P=D#5 [=F#5 ]=G#5 \=A#5
Lower whites:   Z  X  C  V  B  N  M  ,  .  /
Notes:          C3 D3 E3 F3 G3 A3 B3 C4 D4 E4
Higher whites:  1  2  3  4  5  6  7  8  9  0  -  =
Notes:          C5 D5 E5 F5 G5 A5 B5 C6 D6 E6 F6 G6
```

Some keys intentionally duplicate notes. This is not a complete chromatic
C3–G6 range: the outer white-key rows extend the main piano layout. Use octave
shifts to reach other accidentals with the same home-row fingering.

- **Left / Right:** octave down / up.
- **Page Up / Page Down:** next / previous sound (MIDI program change).
- **Home / End:** decrease / increase note velocity.
- **Esc:** all notes off (panic).
- **Edit → Keyboard Map:** inspect or customize the note mapping.
- **Edit → Shortcuts:** customize the actions, separately from note mappings.

The managed baseline is `~/.config/vmpk/home-row.xml`. Save an edited map under
another filename and select it in VMPK; do not try to overwrite the Home Manager
symlink. VMPK remembers that choice. Its preferences are ordinary writable app
state, seeded only if absent, never reset on subsequent deployments. The
controller can feed other instruments too, but arbitrary plugin presets need
not support General MIDI program changes.

## Audio and routing

The Home Manager Ardour package wraps `ardour9` with PipeWire's JACK client
library, without starting jackd or changing the whole desktop's environment.
Default hardware ports appear as `system:playback_1` and `system:playback_2`
for compatibility with the session's saved master connections.

A one-time migration selects **JACK/Pipewire** in Ardour's Audio/MIDI Setup;
PulseAudio mode cannot receive this external MIDI. Existing configuration is
backed up at `~/.config/ardour9/config.pre-laptop-instrument`, and later manual
audio changes are respected. Running applications are skipped during activation;
close them before a deployment if their initial setup is still pending.

The new session uses input monitoring, ACE Fluid Synth, and a saved
connection from `Midi-Bridge:VMPK Output:out (capture)` to `Sketch Piano`.
The original Musical Sketch template remains unchanged. Only the known
fixed piano in `Laptop Instrument` is migrated, while Ardour is closed.
Its snapshot is backed up as `Laptop Instrument.ardour.pre-general-midi`;
recordings, track settings and saved output links are retained. A user-replaced
instrument is not touched. The SoundFont is deployed declaratively at
`~/.local/share/soundfonts/FluidR3_GM.sf2`; the LV2 state references that stable
path, with no runtime dependency on the repository checkout.

The initial implementation incorrectly used ACE Reasonable Synth, which
**explicitly ignores MIDI Control and Program Messages**. Seeing a VMPK patch
label change, or capturing a program-change message, did not verify that the
instrument actually changed sound. ACE Fluid Synth with an SF2 bank fixes
that receiving-end limitation.
If VMPK was opened after the session and the connection has not returned,
Ardour's MIDI Connections window can connect that source to Sketch Piano.

Prefer speakers or wired headphones for an immediate response. Bluetooth's
latency remains, regardless of the controller. Laptop-keyboard simultaneous-key
limits and touchscreen focus behavior require a physical playing trial; a
synthetic chord test does not establish the ThinkPad's key rollover capability.

## Verification

```sh
python3 -m unittest discover -s tests -p 'test_laptop_instrument.py'
python3 -m unittest discover -s tests -p 'test_ardour_*.py'
```

The packaged Ardour wrapper and VMPK 0.9.2 were also exercised on an isolated
Xvfb display with temporary preferences and a disposable copy of the new
session. ALSA event capture verified A=60 (middle C), W=61, home-row white
notes, Z=48, `=`=91, simultaneous notes, octave shifts, note releases,
program change, and panic. VMPK's PipeWire/JACK source name was verified through
the JACK API. Routing its MIDI into ACE Reasonable Synth produced nonzero
stereo float PCM at a task-owned recorder, with Ardour's hardware playback
connections disabled. This verifies the software path, not audible playback,
hardware key rollover, touch behavior, or measured input-to-sound latency.
The visual defaults were also checked on an isolated Xvfb display: all piano
notes were labelled, holding A highlighted C4, and the status showed MIDI60.
The guide's43 labelled typing keys are checked against the XML map in tests,
and its build-rendered PNG is visually inspected for readability.

### Actual patch-audio regression

`tests/fluid_patch_audio.py` must run via `private-x11-run`. It starts a private
JACK dummy server (no physical devices) and hosts ACE Fluid Synth either in
jalv or in an actual generated Ardour session. Pass the test tools' `bin`
directory (jalv/jackd), SF2 file, Ardour's LV2 directory, JACK client library,
and optionally the unwrapped Ardour binary as positional arguments. Adding
xdotool/xwd/ImageMagick to the runner's PATH enables private failure diagnostics.
No live desktop X server, socket, focus, MIDI device, or audio output is used.

For MIDI note60/velocity90, GM programs0 (piano),24 (nylon guitar) and80
(square lead) each produce nonzero recorded float PCM. The regression requires
all three waveforms to differ, rather than merely checking event transmission.
The generated Ardour session passed: RMS approximately0.038,0.048 and0.147;
normalized pairwise differences all exceeded1.1 (required minimum0.3).
The snapshot upgrade also has preservation/idempotence/failure-retry unit tests.
This establishes distinct software output, not headphone audibility.

Primary references:
- [Ardour bundled instruments: ACE Fluid Synth requires an SF2](https://manual.ardour.org/plugins-instruments/)
- [VMPK documentation and editable mappings](https://vmpk.sourceforge.io/index.shtml)
- [VMPK action shortcuts](https://sourceforge.net/p/vmpk/support-requests/37/)
- [Ardour virtual keyboard](https://manual.ardour.org/midi/midi-recording/the-virtual-midi-keyboard/)
