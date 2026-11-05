{ lib, stdenv, fetchurl, autoPatchelfHook, makeWrapper
, dotnet-runtime_10, jq, gtk3, libGL, libglvnd
, libX11, libXcursor, libXi, libXinerama, libXrandr, libXrender, libXext
, libxkbcommon, wayland, vulkan-loader, alsa-lib, libpulseaudio, udev
}:

stdenv.mkDerivation rec {
  pname = "symphony-recomp";
  version = "1.1.2p";

  src = fetchurl {
    url = "https://github.com/BlackLabelHQ/SymphonyRecomp/releases/download/v${version}/SymphonyRecomp-v${version}-linux-x64.tar.gz";
    hash = "sha256-itoEzLGsf9/VtLk8b0T8qcUv7/fyNA9k4qIWqSmvsqo=";
  };
  sourceRoot = ".";
  nativeBuildInputs = [ autoPatchelfHook makeWrapper ];
  buildInputs = [ stdenv.cc.cc.lib gtk3 ];
  dontBuild = true;
  strictDeps = true;

  installPhase = ''
    runHook preInstall
    mkdir -p "$out/lib/symphony-recomp" "$out/bin"
    cp -r ./*.dll ./*.so ./*.so.* ./*.json ./mods "$out/lib/symphony-recomp/"
    substitute ${./launch.sh} "$out/bin/symphony-recomp" \
      --subst-var-by app "$out/lib/symphony-recomp" \
      --subst-var-by dotnet "${dotnet-runtime_10}/bin/dotnet" \
      --subst-var-by jq "${jq}/bin/jq" \
      --subst-var-by shell "${stdenv.shell}"
    chmod +x "$out/bin/symphony-recomp"
    # This upstream ReadyToRun image fails under .NET 10.0.12; use its IL/JIT.
    wrapProgram "$out/bin/symphony-recomp" \
      --set DOTNET_ROOT "${dotnet-runtime_10}/share/dotnet" \
      --set DOTNET_ReadyToRun 0 \
      --prefix LD_LIBRARY_PATH : "${lib.makeLibraryPath [
        libGL libglvnd libX11 libXcursor libXi libXinerama libXrandr
        libXrender libXext libxkbcommon wayland vulkan-loader
        alsa-lib libpulseaudio udev
      ]}"
    runHook postInstall
  '';

  meta = {
    description = "Native recompilation of Castlevania: Symphony of the Night (beta)";
    homepage = "https://github.com/BlackLabelHQ/SymphonyRecomp";
    # Upstream has no license grant; do not assume this is free software.
    license = lib.licenses.unfree;
    platforms = [ "x86_64-linux" ];
    mainProgram = pname;
  };
}
