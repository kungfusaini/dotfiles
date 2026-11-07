# Wireless displays: initial client setup

`home/modules/display.nix` installs the existing Nixpkgs
`gnome-network-displays` package. It brings the client, desktop launcher,
GStreamer plugins and on-demand streaming helpers without a custom sender,
Flatpak runtime or global codec environment changes.

After deployment, launch **Network Displays** from the application menu, or run
`gnome-network-displays`. No autostart or automatic casting is configured.

## What this does and does not establish

The pinned 0.99.0 package contains Chromecast and Miracast providers and uses
libportal's ScreenCast API with a PipeWire source on Wayland. This is a reasonable
fit for the existing Hyprland portal setup, but advertising a capability is not
proof of working end-to-end casting. A receiver and a real permission-selection
session are still needed for that test. In particular, do not promise wireless
extended desktops simply because the application requests virtual sources.

This change does **not** alter wired clamshell mode, folded-keyboard mode, lid
policy, Wi-Fi backend, firewall rules, DNS resolution, or Avahi configuration.
A wireless stream does not count as a physical external DRM display for the
existing clamshell policy. Keep the lid open until a separately approved wireless
keep-awake policy is implemented.

## Discovery prerequisites still requiring approval

Chromecast discovery uses Avahi/mDNS (`_googlecast._tcp`). Avahi is currently not
enabled, so this client-only change is **not a completed Chromecast setup**.

The suggested next host-level change is to enable discovery on the actual Wi-Fi
interface only, permit mDNS UDP 5353 only there, disable Avahi publishing, and
leave `.local` name-resolution integration unchanged. That is a separate network
service/firewall change and must be explicitly approved before implementation.

Miracast requires a compatible Wi-Fi Direct device managed by NetworkManager
using `wpa_supplicant`; the client upstream does not support `iwd`. Finding a P2P
device is only a prerequisite, not a successful connection test. Receiver-specific
DHCP/RTSP/firewall issues may still need investigation. The package's firewalld
zone is not a substitute for configuring the NixOS firewall. Do not open broad
streaming port ranges speculatively or make Wi-Fi/VPN changes just to find a TV.

## Headless verification

```sh
nix eval --impure --json .#nixosConfigurations.kirax1.config --apply \
  'config: import ./tests/network-displays-config.nix { inherit config; }'
nix build --impure --no-link --print-build-logs --expr \
  'let f = builtins.getFlake (toString ./.); in import ./tests/network-displays-smoke.nix { pkgs = f.nixosConfigurations.kirax1.pkgs; }'
```

The smoke test uses the exact plugin paths embedded in the packaged Nix wrapper.
It verifies the launcher, desktop entry, PipeWire source, parser/muxer elements,
and software H.264/AAC encoding using generated test patterns and discard sinks.
It opens no windows, captures no screen/audio and discovers/connects to no devices.
It does not establish hardware encoding, receiver discovery, audio routing,
permission selection or Hyprland casting interoperability.

References: [GNOME project](https://gitlab.gnome.org/GNOME/gnome-network-displays),
[GNOME's Chromecast/Miracast announcement](https://thisweek.gnome.org/posts/2024/08/twig-160/).
The package's own current source is authoritative where its README still describes
older GNOME/X11 capture behavior.
