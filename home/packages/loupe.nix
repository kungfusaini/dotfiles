{ loupe }:

# Loupe normally hands files to its D-Bus singleton. Independent processes let
# project-file-open verify each new window's launch identity, workspace and focus
# suppression without touching an unrelated existing viewer. Keep the system bus
# and image-loader sandbox intact; only disable application-instance negotiation.
loupe.overrideAttrs (old: {
  postPatch = (old.postPatch or "") + ''
    substituteInPlace src/application.rs --replace-fail \
      'gio::ApplicationFlags::HANDLES_OPEN)' \
      'gio::ApplicationFlags::HANDLES_OPEN | gio::ApplicationFlags::NON_UNIQUE)'
  '';
  postInstall = (old.postInstall or "") + ''
    substituteInPlace "$out/share/applications/org.gnome.Loupe.desktop" \
      --replace-fail 'DBusActivatable=true' $'DBusActivatable=false\nX-ProjectObject-Independent=true'
  '';
})
