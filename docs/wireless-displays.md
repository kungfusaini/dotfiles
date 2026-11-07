# Wireless displays: client and discovery

`home/modules/display.nix` installs the existing Nixpkgs
`gnome-network-displays` package. It brings the client, desktop launcher,
GStreamer plugins and on-demand streaming helpers without a custom sender,
Flatpak runtime or global codec environment changes.

## Using the display-button menu

Press **Shift+F7** (Shift plus the display key), then choose **Wireless display…**.
The display menu closes and opens the packaged Network Displays client. Select
an available receiver and approve the screen-sharing prompt when it appears.
Keep the laptop lid open for wireless casting.

The menu also opens with only the laptop screen or in an external-only session;
arrangement and Apply are disabled unless the laptop and an external output are
both enabled. Wireless display… does not apply or save a wired layout. Single F7
still toggles mirror/extended, and double F7 still controls folded-keyboard mode.
Escape closes the menu, including when its wireless button has keyboard focus.

You can also launch **Network Displays** from the application menu, or run
`gnome-network-displays`. No autostart or automatic casting is configured.

## What this does and does not establish

The pinned 0.99.0 package contains Chromecast and Miracast providers and uses
libportal's ScreenCast API with a PipeWire source on Wayland. This is a reasonable
fit for the existing Hyprland portal setup, but advertising a capability is not
proof of working end-to-end casting. A receiver and a real permission-selection
session are still needed for that test. In particular, do not promise wireless
extended desktops simply because the application requests virtual sources.

This setup does **not** alter wired clamshell mode, folded-keyboard mode, lid
policy, Wi-Fi backend or DNS resolution. A wireless stream does not count as a
physical external DRM display for the existing clamshell policy. Keep the lid open
until a separately approved wireless keep-awake policy is implemented.

## Wi-Fi-only discovery

Chromecast discovery uses Avahi/mDNS (`_googlecast._tcp`). Host-level discovery is
configured in `hosts/kirax1/modules/core/networking.nix`:

- Avahi listens only on `wlp0s20f3`, not VPN, Docker or other interfaces.
- UDP 5353 is allowed only on that Wi-Fi interface. Avahi's global firewall
  opening is disabled, and no broad streaming ports are opened.
- Publishing, multicast reflection, wide-area discovery and Avahi `.local`
  name-resolution integration remain disabled.
- Automatic printer discovery (`cups-browsed`), which NixOS otherwise enables
  alongside Avahi, stays disabled as it was before this setup.

This discovers receivers on the connected Wi-Fi network, including public Wi-Fi;
there is no trusted-SSID filter. It does not publish the laptop's services, create
an automatic cast connection, or bypass VPN routing/client isolation. The receiver
and laptop normally need a mutually reachable LAN. Discovery does not prove
successful streaming or receiver compatibility.

Miracast requires a compatible Wi-Fi Direct device managed by NetworkManager
using `wpa_supplicant`; the client upstream does not support `iwd`. Finding a P2P
device is only a prerequisite, not a successful connection test. Receiver-specific
DHCP/RTSP/firewall issues may still need investigation. The package's firewalld
zone is not a substitute for configuring the NixOS firewall. Do not open broad
streaming port ranges speculatively or make Wi-Fi/VPN changes just to find a TV.

## Headless verification

The menu test runs real Quickshell using Qt's offscreen platform with fake launch
commands. It tests laptop-only, disabled-panel and wired geometry handling,
wireless launch without layout mutation, Apply behavior and Escape. It does not
open a visible window or launch the real casting client.

```sh
nix build --impure --no-link --print-build-logs --expr \
  'let f = builtins.getFlake (toString ./.); in import ./tests/display-menu.nix { pkgs = f.nixosConfigurations.kirax1.pkgs; }'
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
