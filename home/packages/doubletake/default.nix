{ lib, buildGoModule, fetchFromGitHub, pkg-config, makeWrapper
, gst_all_1, pipewire, libpulseaudio, fdk_aac, xrandr }:

let
  plugins = with gst_all_1; [
    gstreamer gst-plugins-base gst-plugins-good gst-plugins-bad
    gst-plugins-ugly gst-libav pipewire
  ];
  pluginPath = lib.makeSearchPath "lib/gstreamer-1.0" plugins;
in
buildGoModule rec {
  pname = "doubletake";
  version = "0.6.0";

  src = fetchFromGitHub {
    owner = "omarroth";
    repo = "doubletake";
    tag = "v${version}";
    hash = "sha256-GPR+6r1yMNvLOaGPBm6msz5NTUGyxn6JqhC6YsAfboE=";
  };
  vendorHash = "sha256-cgvY9MVGe8I3g3Ni2sGucTY6YCyPJ2YnoxxUaYfl1E4=";

  subPackages = [ "cmd/doubletake" "cmd/doubletake-ctl" ];
  tags = [ "gstreamer_cgo" "fdk_aac" ];
  ldflags = [ "-s" "-w" "-X doubletake/internal/version.Version=v${version}" ];
  nativeBuildInputs = [ pkg-config makeWrapper ];
  buildInputs = with gst_all_1; [ gstreamer gst-plugins-base fdk_aac ];

  # Upstream dlopens FDK-AAC by soname. Pin it instead of relying on host paths.
  postPatch = ''
    substituteInPlace internal/airplay/aac_eld_fdk_loader.h \
      --replace-fail '"libfdk-aac.so.2"' '"${lib.getLib fdk_aac}/lib/libfdk-aac.so.2"'
  '';

  # Sandboxed tests have no access to the real desktop, TV, or audio server.
  checkPhase = ''
    runHook preCheck
    go test -tags=gstreamer_cgo,fdk_aac -timeout=180s ./...
    runHook postCheck
  '';

  postInstall = ''
    install -Dm644 man/man1/doubletake.1 "$out/share/man/man1/doubletake.1"
    install -Dm644 man/man1/doubletake-ctl.1 "$out/share/man/man1/doubletake-ctl.1"
    wrapProgram "$out/bin/doubletake" \
      --prefix PATH : ${lib.makeBinPath [ gst_all_1.gstreamer libpulseaudio xrandr ]} \
      --set GST_PLUGIN_SYSTEM_PATH_1_0 ${pluginPath} \
      --set GST_PLUGIN_PATH_1_0 ${pluginPath}
  '';

  passthru = { inherit pluginPath; };
  meta = {
    description = "Linux AirPlay screen-mirroring sender (experimental receiver compatibility)";
    homepage = "https://github.com/omarroth/doubletake";
    license = lib.licenses.lgpl3Plus;
    platforms = lib.platforms.linux;
    mainProgram = "doubletake";
  };
}
