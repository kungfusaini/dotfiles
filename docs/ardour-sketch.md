# Ardour Musical Sketch workspace

The `Musical Sketch` session template is deployed by Home Manager from
`home/config/ardour/musical-sketch.template`. It uses Ardour's built-in
ACE Reasonable Synth (default piano), a stereo master, a tall MIDI lane,
and only the bars/beats ruler. No external instruments or MIDI hardware are
required. The template was based on Ardour 9.7's native template export;
it deliberately excludes recordings, engine/device selection, plugin state
paths, control surfaces, and saved window positions.

On first activation while Ardour is closed, `home/scripts/ardour-sketch.py`:

- Hides the editor mixer/list/properties panels, recording/punch toolbar,
  secondary clock, and optional auxiliary toolbar groups.
- Selects the pencil tool, quarter-note grid, snapping, and a closer zoom.
- Creates `~/Music/ardour/Musical Sketch/Musical Sketch.ardour` with a blank
  four-bar MIDI region named **Your first idea** and the instrument loaded.
- Leaves the existing 125% scale, audio configuration, and sessions alone.

The layout migration is marked by `~/.config/ardour9/.musical-sketch-layout-v1`.
Later changes to panel visibility are respected: this is a starting point,
not a permanent restriction. An existing `Musical Sketch` folder is never
replaced. The session and MIDI file are ordinary editable user music, not
Home Manager symlinks. The managed template is read-only; save customized
session templates under another name.

## First use

Open **Musical Sketch**. Click inside **Your first idea** to draw a note;
vertical position chooses pitch, horizontal position chooses time. Stack
notes vertically for a chord. Press **Space** for play/stop and **Ctrl+S**
to save. No recording or track arming is needed for drawing MIDI notes.

For another song, choose **Musical Sketch** in the new-session template
list. Session templates preserve instruments and track layout, not musical
regions: draw a region across the piano lane before entering notes in a new
session. The first-use starter already includes that blank region.

## Reveal more when needed

- **Shift+E**: editor mixer (instrument/effects and mixer strip).
- **Shift+L**: editor list.
- **Shift+P**: editor properties.
- **Shift+S**: timeline summary.
- **View → Rulers**: restore tempo, markers, timecode, etc.
- Right-click the transport toolbar to restore hidden toolbar groups.
- **Session → Add New Track, Bus, VCA or Foldback**: add another instrument.

## Verification

`python3 -m unittest discover -s tests -p 'test_ardour_*.py'`

The real Ardour GUI was exercised on an isolated Xvfb display with temporary
preferences and a private PulseAudio null sink (no microphone or hardware
output). Drawing a chord and playing it produced nonzero stereo PCM at the
private sink. The starter was visually checked at 125% scale. CLI session
utilities in this Ardour build aborted during teardown, so activation does
not depend on them; session/template files are also checked in the GUI.

Upstream references:
- https://manual.ardour.org/working-with-sessions/session-templates/
- https://manual.ardour.org/working-with-midi/add-new-notes/
- https://manual.ardour.org/ardours-interface/main-menu/View-menu/
