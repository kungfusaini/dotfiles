{ lib
, stdenvNoCC
, makeWrapper
, wrapGAppsHook4
, gobject-introspection
, python3
, gtk4
, libadwaita
, kitty
, hyprland
, libnotify
, fd
}:

let
  pythonEnv = python3.withPackages (packages: [ packages.pygobject3 ]);
in
stdenvNoCC.mkDerivation {
  pname = "project-object";
  version = "0.4.0";
  src = lib.cleanSourceWith {
    src = ./.;
    filter = path: type:
      let relative = lib.removePrefix (toString ./. + "/") (toString path);
      in relative == "bin" || lib.hasPrefix "bin/" relative
        || relative == "lib" || lib.hasPrefix "lib/" relative
        || relative == "integrations" || lib.hasPrefix "integrations/" relative;
  };

  nativeBuildInputs = [ makeWrapper wrapGAppsHook4 gobject-introspection pythonEnv ];
  buildInputs = [ gtk4 libadwaita ];
  dontWrapGApps = true;

  installPhase = ''
    runHook preInstall
    mkdir -p "$out/bin" "$out/lib" "$out/share/project-object/pi/skills"
    cp bin/project-picker bin/project-picker-gui bin/project-picker-tui bin/project-snapshot bin/project-terminal "$out/bin/"
    cp lib/project_object.py "$out/lib/"
    cp integrations/pi/project-object.ts "$out/share/project-object/pi/"
    cp -R integrations/pi/skills/init "$out/share/project-object/pi/skills/"
    chmod 0555 "$out/bin/project-picker" "$out/bin/project-picker-gui" "$out/bin/project-picker-tui" "$out/bin/project-snapshot" "$out/bin/project-terminal" "$out/share/project-object/pi/skills/init/scripts/guard.py"
    patchShebangs "$out/bin"
    runHook postInstall
  '';

  postFixup = ''
    wrapGApp "$out/bin/project-picker-gui" \
      --prefix PATH : ${lib.makeBinPath [ fd hyprland libnotify ]} \
      --set PROJECT_OBJECT_TERMINAL "$out/bin/project-terminal"
    wrapProgram "$out/bin/project-picker-tui" \
      --prefix PATH : ${lib.makeBinPath [ kitty hyprland libnotify ]} \
      --set PROJECT_OBJECT_TERMINAL "$out/bin/project-terminal"
    wrapProgram "$out/bin/project-snapshot" \
      --prefix PATH : ${lib.makeBinPath [ hyprland ]}
    wrapProgram "$out/bin/project-terminal" \
      --prefix PATH : ${lib.makeBinPath [ kitty hyprland ]}
  '';

  meta = {
    description = "System-wide Hyprland project picker and project-aware terminal";
    platforms = lib.platforms.linux;
    license = lib.licenses.mit;
  };
}
