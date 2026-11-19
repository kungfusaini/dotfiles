{ config, lib, pkgs, ... }:

let
  guide = pkgs.runCommand "laptop-keyboard-guide" {
    nativeBuildInputs = [ pkgs.python3 pkgs.resvg ];
  } ''
    mkdir -p "$out"
    python3 ${../scripts/laptop-keyboard-guide.py} \
      ${../config/vmpk/home-row.xml} "$out/guide.svg"
    resvg --use-fonts-dir ${pkgs.dejavu_fonts}/share/fonts \
      "$out/guide.svg" "$out/guide.png"
  '';
  guideLauncher = pkgs.writeShellApplication {
    name = "laptop-keyboard-guide";
    text = ''
      exec ${pkgs.swayimg}/bin/swayimg --scale=fit \
        --class=laptop-keyboard-guide ${guide}/guide.png "$@"
    '';
  };

  # Ardour's stock build links JACK2. Use PipeWire's compatible client library,
  # without starting jackd or changing the desktop-wide audio environment.
  ardourPipewire = pkgs.symlinkJoin {
    name = "ardour-pipewire";
    paths = [ pkgs.ardour ];
    nativeBuildInputs = [ pkgs.makeWrapper ];
    postBuild = ''
      wrapProgram "$out/bin/ardour9" \
        --prefix LD_LIBRARY_PATH : ${pkgs.pipewire.jack}/lib \
        --set-default PIPEWIRE_PROPS '{ jack.default-as-system = true }'
    '';
  };
in
{
  home.packages = [ ardourPipewire pkgs.vmpk guideLauncher ];

  xdg.desktopEntries.laptop-keyboard-guide = {
    name = "Laptop Keyboard Guide";
    comment = "See the laptop keys and piano notes for VMPK";
    exec = "${guideLauncher}/bin/laptop-keyboard-guide";
    icon = "input-keyboard";
    categories = [ "AudioVideo" "Music" ];
    terminal = false;
  };

  xdg.configFile."vmpk/home-row.xml".source = ../config/vmpk/home-row.xml;
  xdg.dataFile."soundfonts/FluidR3_GM.sf2".source =
    "${pkgs.soundfont-fluid}/share/soundfonts/FluidR3_GM2-2.sf2";

  # Both applications own their writable preferences. Seed once, and skip
  # running applications rather than racing their eventual preference writes.
  home.activation.laptopInstrument = lib.hm.dag.entryAfter [ "ardourScale" ] ''
    run ${pkgs.python3}/bin/python3 ${../scripts/laptop-instrument-setup.py} \
      "${config.xdg.configHome}" \
      "${config.home.homeDirectory}/Music/ardour" \
      ${../config/ardour/musical-sketch.template} \
      "$(${pkgs.procps}/bin/pgrep -u "$UID" -x 'vmpk|\.vmpk-wrapped' >/dev/null && echo running || echo stopped)" \
      "$(${pkgs.procps}/bin/pgrep -u "$UID" -x ArdourGUI >/dev/null && echo running || echo stopped)" \
      "${config.xdg.dataHome}/soundfonts/FluidR3_GM.sf2"
  '';
}
