# Clickable local files

Kitty's managed `open-actions.conf` routes `file://` and scheme-less absolute-path
hyperlinks to `project-file-open`. Pi emits OSC-8 hyperlinks for Markdown links,
including targets such as `/home/user/image.png`; Kitty treats the absent scheme
as `file` for routing but passes the original target unchanged. The opener
normalizes single-slash absolute hrefs to local file URIs before validation.
No Pi renderer patch or additional click gesture is required. This does not
turn arbitrary plain-text paths into hyperlinks. HTTP(S) keeps its existing
`project-browser` route.

The opener accepts existing local ordinary files and directories, decodes URL
paths once, and asks GIO for the desktop MIME default. Relative paths,
protocol-relative targets (`//host/path`), remote file authorities,
queries, malformed escapes, control characters, missing files and special device
files are rejected. A clicked desktop file is a document, not an instruction to
execute its contents. Arguments are never evaluated by a shell. Launch/placement
failures return nonzero, print diagnostics and send a desktop notification.

The supported installed defaults are normal Vivaldi (`%U`), Zathura
(`%U`/`%f`/`%F`), Swayimg (`%F`, a new viewer process per launch), our
independent Loupe (`%U`), Neovim (`%F`, opened in a new managed Kitty), and Kitty's
`+open %U` for directories only. Unknown command shapes and DBus-activated apps
are rejected **before launch**: blindly invoking arbitrary defaults can activate
an unrelated singleton before placement/focus can be checked. New default apps
need an audited safe route rather than an optimistic generic fallback. Kitty's
script/executable launching is intentionally not used for clicked files.

Loupe/Swayimg/Zathura/folder defaults launch through GIO with launch-scoped compositor rules
suppressing initial focus and activation. The opener reuses `project-workspace-exec`'s
existing new-window identity/placement verifier. The opener does not change MIME
associations; Home Manager selects Loupe for images.

`home/packages/loupe.nix` makes the packaged Loupe application `NON_UNIQUE` and
sets `DBusActivatable=false` in its desktop entry, so each click starts a new
independently verifiable process instead of activating a singleton elsewhere.
The narrow source substitution fails on upstream changes. No private bus,
disabled image-loader sandbox, profile copy or mutable launcher is needed.
Only `org.gnome.Loupe.desktop` with `Exec=loupe %U` and our
`X-ProjectObject-Independent=true` marker is accepted; stock singleton Loupe
remains rejected. Loupe is the installed default; the Swayimg route remains
supported if that viewer is installed separately.

Loupe's [documented controls](https://help.gnome.org/loupe/viewing-images.html.en)
include touchpad and touchscreen pinch zoom, single-finger touchscreen panning,
and two-finger rotation. These upstream gesture handlers are unchanged by our
instance patch. Hidden-window tests verify launching and rendering, not physical
touchscreen/touchpad gestures on the laptop.

Vivaldi needs a dedicated local-document route because HTTP-to-file navigation is
blocked and ordinary browser singleton handoff loses the new process's identity.
A tiny private local bootstrap redirects to the clicked file. Its random path
provides a unique Chromium app class; an exact-class compositor rule suppresses
focus and places only that new window beside the invoking terminal. Launches are
serialized while the rule is enabled. The normal Vivaldi profile is shared; no
CDP, automation browser, profile copy, web server or content upload is involved.
The existing HTTP(S)-only browser API remains HTTP(S)-only.

Bootstrap files contain only the destination URI, not document contents. They
remain under `$XDG_RUNTIME_DIR/project-object-file-opens/` (private directories)
until logout/runtime cleanup, since deleting on initial mapping would race file
navigation. Each click creates one small bootstrap file/directory.

## Checks

```sh
python -m unittest discover -s tests -p test_file_open.py
python tests/file_open_integration.py \
  --hyprland /path/to/Hyprland --hyprctl /path/to/hyprctl \
  --labwc /path/to/labwc --kitty /path/to/kitty --vivaldi /path/to/vivaldi \
  --swayimg /path/to/swayimg --loupe /path/to/patched/loupe --grim /path/to/grim \
  --opener /nix/store/...-project-object-0.4.0/bin/project-file-open
```

The acceptance test uses private headless compositors, DBus, HOME, MIME defaults
and a disposable browser profile. It exercises Kitty's real `open_url` action and
configured background launcher, rather than global mouse input. Cases cover
explicit file URIs, encoded absolute hrefs and raw absolute image hrefs with
Unicode/spaces. HTML is opened
in real Vivaldi (including singleton handoff); relative-image loading sets
a checked title. Image MIME dispatch opens real Swayimg and independently
packaged Loupe windows, checks image titles, verifies separate Loupe process IDs
on repeat clicks, and checks decoded test-image pixels in hidden screenshots.
Loupe launches are checked both while elsewhere and on the invoking workspace. PDF MIME dispatch uses a fixture desktop viewer,
not a claim about production PDF rendering. Folder and text routes use real
Kitty and Neovim. Mapping and transient focus
are checked from compositor events, both on the active workspace and while the
user is elsewhere. No private files/accounts are opened.

Implementation uses existing [Kitty file actions](https://sw.kovidgoyal.net/kitty/open_actions/)
and [GIO desktop launching](https://docs.gtk.org/gio/method.AppInfo.launch.html),
not a custom MIME database or desktop Exec parser.
