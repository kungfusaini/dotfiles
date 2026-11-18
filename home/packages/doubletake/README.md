# Doubletake: experimental AirPlay sender

Pinned upstream [Doubletake v0.6.0](https://github.com/omarroth/doubletake/tree/v0.6.0)
adds a manual Linux AirPlay sender alongside Network Displays, not a replacement
for it. UxPlay is an AirPlay **receiver** and does not solve this task.

The package builds both CLIs from source with in-process GStreamer and FDK-AAC.
The FDK loader uses an absolute Nix-store library path; GStreamer tools, plugins
and pactl are scoped to the sender wrapper, not exported into the user session.
No desktop launcher, service, autostart, receiver IP, pairing material, portal
upgrade, firewall exception or network change is installed.

## Safety and compatibility

- LG OLED65C14LB advertises AirPlay, but upstream's tested receiver list does not
  include LG. Discovery is not proof of working mirroring.
- [Upstream compatibility notes](https://github.com/omarroth/doubletake/blob/v0.6.0/docs/compatibility.md)
  require `xdg-desktop-portal-hyprland` 1.5.0 or newer; the existing 1.4.1 portal
  may exhaust its capture buffer pool. This change deliberately does not upgrade
  it. Stop and diagnose a failed/stalled stream rather than claiming success.
- The current Nixpkgs GStreamer bad plugin set disables the new VA plugin, so
  `vapostproc` is not provided. Upstream notes AMD/Intel DMA-BUF capture may need
  it even with software encoding. Live capture is therefore not yet qualified.
- Upstream warns its largely LLM-written implementation is unsuitable for
  security-sensitive use. Treat it as an experimental local-network trial.
- Plain `doubletake`, `-target`, and `doubletake-ctl connect` can initiate pairing
  and then capture. They are **not** discovery-only diagnostics. Do not run them
  against a real receiver without permission to pair and share.
- First-use credentials are saved under the user's configuration directory by
  upstream. Never put a pairing code on a command line, in logs, or in Git.
  Pairing and screen selection are a separate user-approved step.

After separate approval for an actual video-only trial, a bounded starting point
is `doubletake -target TV_IP -no-audio -hwaccel none -s 1280x720@30`. This initiates
an actual receiver connection and can open the screen-sharing portal. `-test`
uses synthetic video instead of the desktop, but still pairs/connects to the TV;
it is not an offline test. Ctrl+C ends the foreground sender.

## Capture-free verification

The package runs upstream Go tests inside the Nix sandbox. Optional private
PulseAudio integrations are skipped unless explicitly configured by upstream;
no real desktop, microphone, speakers or receiver are used.

```sh
nix build --impure --no-link --print-build-logs --expr \
  'let f = builtins.getFlake (toString ./.); in import ./tests/doubletake-smoke.nix { pkgs = f.nixosConfigurations.kirax1.pkgs; }'
```

The smoke test verifies both CLI versions, help, PipeWire/audio/software-H.264
plugins, synthetic encoding to a discard sink, and an idle daemon's private Unix
socket status and shutdown. Before any external GStreamer tool can prime a
plugin registry, it also runs a linked C pipeline under a copy of the installed
sender wrapper (only its final executable is replaced), with an empty inherited
environment and fresh registry. This catches missing core plugins such as
`queue`: GStreamer's Nix default output is `bin`, whereas its core plugins live
in its `lib` output. The original broken package fails this regression with
`no element "queue"`, while the corrected package reaches end-of-stream. The daemon is test-owned, unconnected and sandboxed;
it is not a deployed user service. These checks do **not** establish LG pairing,
real capture, audio, firewall reachability or successful streaming.
