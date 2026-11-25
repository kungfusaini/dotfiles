# Desktop notification policy

`home/modules/mako.nix` is the single source registry and mode policy. Add a
source there before enabling its desktop notifications. Each registration has
an explicit category and one or more exact Mako matches. The compiler in
`home/lib/notification-policy.nix` rejects missing/unknown categories, duplicate
matches, and unsafe/broad match fields.

| Category | All | No contact | DND |
| --- | --- | --- | --- |
| People | yes | no | no |
| Task results | yes | yes | no |
| System/tools | yes | yes | no |
| Media | yes | yes | no |
| Device safety | yes | yes | yes |
| Navigation feedback | yes | yes | yes |
| Muted / unregistered | no | no | no |

The registry includes Slack, Teams, ZapZap, Steam and Nicotine+ as People.
Steam and Nicotine+ have social features: without verified per-notification
metadata, allowing their entire identity as Media would undermine No contact.
Spotify and VLC are Media. Desktop entry identities and app-name aliases are
explicitly listed, not wildcarded.

Source-verified custom senders are Pi, Command Center, Agent Techniques,
Codex One-shot, Screenshots, Kirax1 Backup, Sony headphones, Bluetooth controls,
On-screen keyboard, Tablet workspace/voice/playback/game, Project browser,
Project terminal, Project picker, Project restoration, Project file open,
Longshot, Steam session, Power, and Project Workspace. Pi was also observed in
live metadata. Third-party identities remain conservative registrations, not
claims that every application/version has been observed sending each identity.
A different identity remains denied until verified and added.

`Power` with critical urgency is the only registered device-safety route;
normal Power notifications remain routine. Critical urgency alone never grants
an exception. Project Workspace is short-lived navigation feedback, not an
agent completion: its existing DND exception is now registered centrally.
Thunderbird is always denied, including if other metadata matches an allowance.

Browser-wide notifications, generic `notify-send`, and unidentified sources are
**not registered**. Website notifications need a narrow verified identity/type
before approval; not all browsers expose enough metadata to distinguish sites
safely. Other installed applications (for example Bitwarden, Zotero and editors)
are not automatically approved just because they are installed. Do not add an
app-name/desktop-entry allowance that also admits an unclassified communication
channel. Prefer splitting our own producers into explicit identities.

## Behavior

The Waybar bell cycles **All → No contact → DND → All**. Its packaged command
uses no runtime dependency on the Nix checkout. It preserves unrelated Mako
modes and serializes rapid clicks. DND wins if both restrictive modes have been
set externally. Mako restarts currently reset to All; all sources still require
registration in that mode.

Unknown and suppressed notifications are invisible, expire in 1 ms regardless
of the app's requested timeout, and are not retained in history. Before entering
a more restrictive mode the button clears existing popups without history,
preventing already displayed conversations from resurfacing on return to All.
This also clears any currently displayed safety/navigation popup; newly sent
safety/navigation feedback remains allowed. Direct external `makoctl` mode
changes do not perform that cleanup.

This controls Mako desktop popups, not application sounds, in-app badges, tray
indicators, or separate app-owned windows. Notification identities are
self-reported: this is interruption policy, not a security boundary against a
malicious local client.

## Verification

Evaluate the actual combined Home Manager config (not just the registry):

```sh
nix eval --raw '.#nixosConfigurations.kirax1.config.home-manager.users.sumeet.xdg.configFile."mako/config".text' > /tmp/notifications-mako.conf
python3 tests/notifications.py /tmp/notifications-mako.conf
nix eval --impure --raw --expr 'import ./tests/notification-policy.nix { lib = (builtins.getFlake (toString ./.)).inputs.nixpkgs.lib; }'
```

For real daemon integration, build `sway-unwrapped` from the pinned nixpkgs and
pass `--sway /nix/store/.../bin/sway` to the Python test. It launches a headless
Pixman compositor with Xwayland explicitly disabled and a private D-Bus session
with no service activation directories. It sends only synthetic notifications,
checks 24 sender/mode combinations, expiry/history, and the actual button cycle.
It never sends test notifications to the desktop session.

Mako criteria are order-dependent; the compiler deliberately uses Home Manager's
ordered `extraConfig`, after presentation settings. Do not add independent
visibility rules in application modules.

References: [Mako criteria and modes](https://github.com/emersion/mako/blob/master/doc/mako.5.scd),
[Home Manager's Mako generator](https://github.com/nix-community/home-manager/blob/master/modules/services/mako.nix).
