{ lib
, stdenvNoCC
, makeWrapper
, python3
, kitty
, hyprland
, libnotify
}:

stdenvNoCC.mkDerivation {
  pname = "project-object";
  version = "0.2.0";
  src = lib.cleanSourceWith {
    src = ./.;
    filter = path: type:
      let relative = lib.removePrefix (toString ./. + "/") (toString path);
      in relative == "bin" || lib.hasPrefix "bin/" relative
        || relative == "lib" || lib.hasPrefix "lib/" relative
        || relative == "integrations" || lib.hasPrefix "integrations/" relative;
  };

  nativeBuildInputs = [ makeWrapper ];

  installPhase = ''
    runHook preInstall
    mkdir -p "$out/bin" "$out/lib" "$out/share/project-object/pi"
    cp bin/project-picker bin/project-terminal "$out/bin/"
    cp lib/project_object.py "$out/lib/"
    cp integrations/pi/project-object.ts "$out/share/project-object/pi/"
    chmod 0555 "$out/bin/project-picker" "$out/bin/project-terminal"
    patchShebangs "$out/bin"
    wrapProgram "$out/bin/project-picker" \
      --prefix PATH : ${lib.makeBinPath [ kitty hyprland libnotify ]} \
      --set PROJECT_OBJECT_TERMINAL "$out/bin/project-terminal"
    wrapProgram "$out/bin/project-terminal" \
      --prefix PATH : ${lib.makeBinPath [ kitty hyprland ]}
    runHook postInstall
  '';

  meta = {
    description = "System-wide Hyprland project picker and project-aware terminal";
    platforms = lib.platforms.linux;
    license = lib.licenses.mit;
  };
}
