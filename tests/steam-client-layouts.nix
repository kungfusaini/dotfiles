# Opt-in immutable, private-compositor proof for old and new Steam layouts.
# Uses a synthetic C client; no real Steam, account, game or host input access.
{ pkgs, hyprland }:
let
  sources = pkgs.runCommand "steam-client-layout-test-sources" {} ''
    mkdir -p "$out/project-object/"{bin,lib,tests} "$out/steam-session/scripts"
    cp ${../home/packages/project-object/bin/project-workspace-exec} "$out/project-object/bin/project-workspace-exec"
    chmod +x "$out/project-object/bin/project-workspace-exec"
    cp ${../home/packages/project-object/lib/agent_browser.py} "$out/project-object/lib/agent_browser.py"
    cp ${../home/packages/project-object/tests/steam_workspace_integration.py} "$out/project-object/tests/steam_workspace_integration.py"
    cp ${../home/packages/project-object/tests/workspace_exec_integration.py} "$out/project-object/tests/workspace_exec_integration.py"
    cp ${../home/packages/steam-session/scripts/steamctl.py} "$out/steam-session/scripts/steamctl.py"
    cp ${../home/packages/steam-session/scripts/session.py} "$out/steam-session/scripts/session.py"
    cp ${../home/packages/steam-session/scripts/manual.py} "$out/steam-session/scripts/manual.py"
  '';
in pkgs.writeShellApplication {
  name = "steam-client-layout-test";
  runtimeInputs = [ pkgs.python3 pkgs.dbus pkgs.gcc pkgs.coreutils hyprland pkgs.labwc pkgs.kitty ];
  text = ''
    export PYTHONDONTWRITEBYTECODE=1
    export XKB_CONFIG_ROOT=${pkgs.xkeyboard_config}/share/X11/xkb
    export FONTCONFIG_FILE=${pkgs.makeFontsConf { fontDirectories = [ pkgs.dejavu_fonts ]; }}
    for layout in ubuntu12_32 steamrt64; do
      echo "Testing Steam client layout: $layout"
      python3 ${sources}/project-object/tests/steam_workspace_integration.py \
        --hyprland ${hyprland}/bin/Hyprland --hyprctl ${hyprland}/bin/hyprctl \
        --labwc ${pkgs.labwc}/bin/labwc --kitty ${pkgs.kitty}/bin/kitty \
        --cc ${pkgs.gcc}/bin/cc --client-layout "$layout"
    done
  '';
}
