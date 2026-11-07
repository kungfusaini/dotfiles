# Sony headset playback during controller gaming

`sony-headset-prime.service` remains the only automatic Sony playback coordinator.
It calls the packaged `sony-headset-playback` selector after its existing priming
sequence and once per normal loop after the connection is marked primed. No
second profile-switching service competes with it.

## Playback policy

For the Sony WF-1000XM6 only:

- Use AAC when the paired Pro Controller (`98:B6:E9:7C:21:83`) is connected **and**
  a same-user Pegasus, supported emulator, or Steam game process is running.
  Pegasus counts as a gaming session even while browsing or waiting for a game.
- Otherwise return to the existing LDAC playback profile. Its declarative `hq`
  quality setting is unchanged; other Bluetooth devices are unaffected.
- Steam alone, an idle connected controller without a gaming process, and unrelated
  applications do not select AAC. Process identity uses executable names or public
  Steam app IDs, not window titles or whichever workspace is active.
- Available profile indices are discovered from PipeWire rather than hardcoded.
  Missing AAC does not trigger another codec, a Bluetooth reset, or any installation.
- Selection is idempotent. Failed/unacknowledged profile requests are limited to
  three per unchanged connection/current/target combination, at least ten seconds
  apart. A changed connection or policy condition permits a new attempt.

This is an A2DP playback policy, not a replacement for microphone handling.

## Preserve the headset microphone setup

After connection settling, the selector registers the current PipeWire connection
serial before priming. An unavailable graph or active recording defers priming
without resetting Bluetooth. The existing sequence then remains: open and validate
a short mSBC capture, select LC3-SWB as the preferred call codec, then restore the
appropriate **AAC or LDAC** playback profile. The final restore and failure-path
restore both use the shared selector instead of unconditionally forcing LDAC.
The existing bounded stale-SCO recovery is unchanged; that recovery can reset the
whole Bluetooth adapter, so it can briefly affect connected controllers too.

An active recording stream takes priority over playback changes. Normal
reconciliation never pulls an existing HFP/headset profile back into A2DP;
WirePlumber retains ownership of call autoswitch and return-to-playback. If
priming's explicit playback restore is deferred by recording, it is retried after
capture ends. Deferred restoration and retry limits survive temporary graph/profile
unavailability and intervening capture/cooldown polls. A new connection serial or
an intentional off/unknown profile cannot inherit old restoration intent. The
laptop-mic availability/default guard is unchanged.

There is no claim that HFP/LC3-SWB simultaneous gaming has been latency-tested.
Calls keep microphone functionality rather than being forcibly converted to AAC.

## Evidence and validation

A controlled LDAC → AAC → LDAC comparison on this machine kept both devices
connected and audio transmitting throughout each 20-second phase. Controller
report gaps over 100 ms were 43 → 0 → 11. AAC's maximum interval was about 25 ms;
LDAC reached 1.25 seconds. Kernel receive timestamps excluded monitoring-process
scheduling as the explanation. This supports a targeted workaround, not a claim
that every adapter or LDAC implementation has this problem.

Tests never record a real microphone, start games, access Steam credentials, or
change live profiles:

```sh
python3 -m unittest discover -s home/packages/sony-headset-policy/tests -v
python3 -m unittest discover -s tests -p 'test_sony_headset_audio.py' -v
```

After approved deployment, verify `sony-headset-prime.service` runs the new store
closure, its current-connection priming marker remains valid, and PipeWire selects
AAC for the connected-controller gaming session. Verify LDAC restoration after
that session ends, without interrupting gameplay or recordings. Do not claim a
live microphone or gameplay test from unit-test results alone.

References:

- [WirePlumber Bluetooth configuration](https://pipewire.pages.freedesktop.org/wireplumber/daemon/configuration/bluetooth.html)
- [WirePlumber call autoswitch settings](https://pipewire.pages.freedesktop.org/wireplumber/daemon/configuration/settings.html)
- [Supported wpctl profile selection](https://pipewire.pages.freedesktop.org/wireplumber/man/wpctl.html)
