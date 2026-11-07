# Receiver-first Network Displays

This is a small override of the flake's existing GNOME Network Displays package,
not a new casting implementation. Upstream 0.99.0 opens the ScreenCast picker
when constructing its window. `receiver-first.patch` instead:

- discovers and lists receivers without requesting screen access;
- retains the selected sink, then requests explicit portal permission;
- starts that selected sink only after successful permission;
- leaves discovery available after cancel/error and permits retry;
- ignores duplicate selections while permission is pending;
- rejects a receiver which disappeared while the picker was open;
- releases the portal session on disconnect or window close;
- protects asynchronous window/sink lifetimes and ignores stale callbacks;
- never falls back to unselected X11 capture after a portal error/cancel.

No receiver protocols, discovery settings, network ports or codec choices are
changed. The existing upstream audio initialization and streaming machinery are
retained. The patch also removes the duplicate cancellable allocation so window
close cancels both pending initialization and sharing operations reliably.

## Tests

Package checks compile the actual patched permission/selection callbacks into a
GLib test probe. Portal results, receiver availability and unchanged UI plumbing
are faked; real GObject references, signals and GTask completion test ordering,
cancel/retry, duplicate selection, disappearing receivers, close during create or
start, stale completion, portal failure and stream-start failure. Audio completion
racing with close also executes the actual production finalizer: it must tolerate
an uninitialized audio sink and unload a completed one exactly once. Startup source
assertions ensure no capture request and no silent X11 fallback. The ordinary
Meson build compiles the entire actual application against GTK/libportal.

```sh
nix build --impure --no-link --print-build-logs --expr \
  'let f = builtins.getFlake (toString ./.); in f.nixosConfigurations.kirax1.pkgs.callPackage ./home/packages/gnome-network-displays { }'
nix build --impure --no-link --print-build-logs --expr \
  'let f = builtins.getFlake (toString ./.); in import ./tests/network-displays-startup.nix { pkgs = f.nixosConfigurations.kirax1.pkgs; }'
```

The second check launches the real packaged GTK client inside a private headless
Wayland compositor and a private D-Bus with no service activation. Both session
and system bus addresses point to this private bus; audio points to a nonexistent
private socket. A fake portal counts ScreenCast requests but implements no screen
selection, PipeWire remote or media sharing. No real devices or host desktop are
accessed. The patched app must make zero startup requests. A negative control with
`client = pkgs.gnome-network-displays; expectRequest = true;` confirms the same
fixture observes the original app making a startup request.

These tests do not establish real receiver connectivity or actual media streaming.

Upstream: [window implementation](https://gitlab.gnome.org/GNOME/gnome-network-displays/-/blob/master/src/app/nd-window.c).
