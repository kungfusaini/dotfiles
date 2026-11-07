{ lib, stdenvNoCC, makeWrapper, python3, bluez, pipewire, wireplumber }:

stdenvNoCC.mkDerivation {
  pname = "sony-headset-policy";
  version = "1.0.0";
  src = ./.;
  nativeBuildInputs = [ makeWrapper ];
  nativeCheckInputs = [ python3 ];
  dontBuild = true;
  doCheck = true;
  checkPhase = ''
    runHook preCheck
    python3 -m unittest discover -s tests -v
    runHook postCheck
  '';
  installPhase = ''
    runHook preInstall
    mkdir -p "$out/lib/sony-headset-policy" "$out/bin"
    cp policy.py "$out/lib/sony-headset-policy/policy.py"
    makeWrapper ${python3}/bin/python3 "$out/bin/sony-headset-playback" \
      --add-flags "$out/lib/sony-headset-policy/policy.py" \
      --prefix PATH : ${lib.makeBinPath [ bluez pipewire wireplumber ]}
    runHook postInstall
  '';
  meta = {
    description = "Coordinated Sony headset playback selection for controller gaming";
    mainProgram = "sony-headset-playback";
    platforms = lib.platforms.linux;
  };
}
