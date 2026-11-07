# VOYEE NS S08: positional defaults, native Nintendo games

The Bluetooth controller identifies as Pro Controller (`057e:2009`). Connect with
HOME after initial pairing. These profiles target the captured **Bluetooth** mode,
not Android mode, USB mode, or an Xbox-emulation mode.

## Policy

Outside Nintendo games, ignore the printed face letters and use Xbox/PlayStation
**positions**. In Pegasus, bottom selects and right goes back. Individual games
still decide whether Cross or Circle confirms; do not swap PS buttons globally to
compensate for a particular game's regional convention.

| Physical VOYEE | Position | Xbox | PlayStation | Nintendo diamond |
|---|---|---|---|---|
| B | bottom | A | Cross | B |
| A | right | B | Circle | A |
| Y | left | X | Square | Y |
| X | top | Y | Triangle | X |
| L / R | shoulders | LB / RB | L1 / R1 | L / R |
| ZL / ZR | triggers | LT / RT | L2 / R2 | ZL / ZR |
| click left / right stick | clicks | LS / RS | L3 / R3 | L-stick / R-stick |
| − / + | centre | Back / Start | Select / Start | − / + |

ZL/ZR are **digital**, not pressure-sensitive triggers. Do not promise PS2
pressure-sensitive face buttons, analogue trigger travel, motion aiming or rumble
based on the button capture. Sticks reached full travel and returned near centre;
PCSX2 and Ryubing use a modest 10% deadzone.

## Implemented apps

- **PCSX2:** Player 1 DualShock2, SDL3 positional FaceSouth/East/West/North;
  all shoulders, triggers, clicks, D-pad and sticks. Existing keyboard alternatives
  remain separate INI entries, never `&` chords. Named `VOYEE S08` input profile.
- **SymphonyRecomp:** Port 1 analog pad; explicit bundled-SDL2 face bindings
  Cross=1, Circle=0, Square=3, Triangle=2. Keyboard bindings and Port 2 unchanged.
  Digital pad mode also lets the left stick drive D-pad directions.
- **Ryubing:** Player 1 native Nintendo Pro Controller, printed A/B/X/Y labels,
  matching the actual bundled SDL2 library. Named `VOYEE S08` profile. Bluetooth
  device ID uses Ryubing's .NET GUID byte order and zeroed CRC prefix. Existing
  other players and this controller's motion/rumble/LED preferences are retained.
  A previous Player 1 keyboard configuration, if present, is saved as the
  `Before VOYEE` keyboard profile: Ryubing supports only one device per player.
- **Pegasus:** keep its existing positional SDL defaults; do not introduce a
  global Nintendo label override. Its SDL A maps to SOUTH and selects; SDL B maps
  to EAST and goes back. No unnecessary frontend config mutation.

No global SDL environment override, virtual controller daemon or new dependency
at runtime beyond Python. Per-app mappings avoid turning Nintendo games into Xbox
layouts. Steam-specific settings are not changed by this helper.

## Applying / recovering

Canonical sources: `home/packages/voyee-controller/` and `home/modules/pegasus.nix`.
Emulator settings intentionally remain writable (as documented in that module).
The packaged command is explicit opt-in, not an activation/startup hook:

```sh
voyee-controller-setup          # preview paths only
voyee-controller-setup --apply  # all three emulators must be closed
```

It requires existing emulator configs, validates all inputs before writing,
backs up each changed existing file under
`~/.local/state/voyee-controller/backups`, refuses final-path symlinks, and writes
atomically per file with private permissions. Backup filenames are a hash of the
absolute original path followed by the SHA256 of its original bytes. No saves,
ROMs, BIOS/keys, firmware or credentials are part of the Nix sources or edited.
It is idempotent, but deliberately **not** a continuous enforcer: change profiles
in the apps normally; rerunning explicitly restores this policy. Do not run the
helper while launching an emulator. Keep other configuration writers stopped.

With another controller connected first, PCSX2 may require choosing the correct
SDL device instead of SDL-0. Symphony's empty device preference automatically
uses the first available controller. Ryubing's profile must be associated with
the newly selected device if switching to USB or another controller mode.
Per-game input overrides, if created later, can supersede the global profiles.

## Other major consoles: layout reference, not installed/configured

Only the installed apps above are configured. For future emulators:

- PS1/PS2/PS3/PS4/PS5 and PSP: preserve the PlayStation diamond above. Missing
  PS touchpad, adaptive triggers and other specialised hardware need separate
  game-specific choices.
- Xbox/360/One/Series: use the Xbox column, not the VOYEE letters.
- NES, GB/GBC/GBA: native Nintendo A=right and B=bottom; Start=+, Select=−.
  GBA L/R use the matching shoulders.
- SNES/DS/3DS/Switch/Wii U: native Nintendo diamond, matching shoulders and
  sticks where present. DS/3DS/Wii U touchscreens and extra screens need separate
  controls; they cannot be inferred from a PlayStation pad.
- GameCube: its large A/B and bean-shaped X/Y do not form a conventional diamond.
  Map by Nintendo button identity as a starting point; review per game. This
  VOYEE cannot reproduce GameCube analogue trigger travel.
- N64: no unique one-to-one mapping (six face buttons and Z). A common starting
  point is A=right, B=bottom, C-buttons=right stick, Z=ZL, L/R=shoulders, Start=+;
  review games that require holding C-buttons while using the stick.
- Wii: sideways, classic-controller and motion/pointer games require different
  profiles. Do not claim that one universal face mapping handles them all.
- Sega Master System/Mega Drive/Saturn/Dreamcast: three/six-button arrangements
  and Dreamcast's face labels need explicit console/game profiles, not a blind
  Nintendo or PlayStation translation.

## Evidence and sources

Guided Linux evdev capture: B=304, A=305, Y=308, X=307; L/R=310/311,
ZL/ZR=312/313; −/+=314/315; clicks=317/318; D-pad hats=16/17;
left stick axes=0/1; right=3/4. A brief diagonal appeared during the Down press,
not a reversed axis. Capture was gamepad-only and stopped afterward.

The **actual installed** SymphonyRecomp and Ryubing processes were launched on an
isolated Xvfb display with isolated writable data, and `/proc/PID/maps` confirmed
both load their bundled native SDL2, not the system SDL2-compat library. Their
Nintendo mapping reports A=right and B=bottom. Pegasus uses SDL2-compat/SDL3
positional mapping instead. This is why simply copying identical face indices
across the apps would be wrong. Full physical in-game verification remains a
separate test, not implied by config validation.

Primary references:
- [PCSX2 controller configuration](https://pcsx2.net/docs/configuration/controllers/)
- [SDL2 Nintendo button-label hint](https://wiki.libsdl.org/SDL2/SDL_HINT_GAMECONTROLLER_USE_BUTTON_LABELS)
- [Pegasus default controls](https://pegasus-frontend.org/docs/user-guide/controls/)
- [Ryubing setup guide](https://docs.ryujinx.app/guides/setup-guide/)

Verification: `python3 -m unittest discover -s tests -p test_voyee_controller.py -v`.
