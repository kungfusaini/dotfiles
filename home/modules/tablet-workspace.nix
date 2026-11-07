{ config, pkgs, lib, osConfig, ... }:

let
  tabletOskPackage = pkgs.writeShellApplication {
    name = "tablet-osk";
    runtimeInputs = with pkgs; [ coreutils procps util-linux libnotify wvkbd wtype python3 osConfig.programs.hyprland.package ];
    text = builtins.readFile ../../hosts/kirax1/scripts/desktop/tablet-osk;
  };
  # Hyprland 0.56's getoption cannot query device-specific values. Preserve
  # declared overrides; only absent keys fall back to the live global option.
  devicePolicy = name: kind:
    let
      entries = builtins.filter (entry: (entry.name or "") == name)
        (config.wayland.windowManager.hyprland.settings.device or [ ]);
      declared = builtins.foldl' (result: entry: result // entry) { } entries;
    in {
      inherit name kind;
      transform = declared.transform or null;
      output = declared.output or null;
    };
  orientationPolicy = pkgs.writeText "tablet-orientation-policy.json" (builtins.toJSON {
    monitor = "eDP-1";
    devices = [
      (devicePolicy "wacom-hid-5430-finger" "touch")
      (devicePolicy "wacom-hid-5430-pen" "pen")
    ];
  });
  tabletOrientation = pkgs.writeShellApplication {
    name = "tablet-orientation";
    runtimeInputs = with pkgs; [ coreutils procps python3 quickshell osConfig.hardware.sensor.iio.package osConfig.programs.hyprland.package ];
    text = ''
      export TABLET_ORIENTATION_POLICY=${orientationPolicy}
      export TABLET_ROTATION_FADE_QML=${../config/quickshell/tablet-rotation-fade}
      exec python3 ${../scripts/desktop/tablet-orientation.py} "$@"
    '';
  };
  tabletHomePreview = pkgs.writeShellApplication {
    name = "tablet-home-preview";
    runtimeInputs = [ tabletChat ];
    text = ''
      # Home and Pi are views of one supervised tablet session. Never launch a
      # standalone Home that starts a second interface when Pi is tapped.
      exec ${tabletChat}/bin/tablet-chat start
    '';
  };
  voxtype = lib.findFirst (package: lib.hasPrefix "voxtype" (package.pname or package.name))
    (throw "Tablet iteration requires the existing host Voxtype package") osConfig.environment.systemPackages;
  tabletVoiceConfig = pkgs.writeText "tablet-voxtype.toml" (lib.replaceStrings
    [ "on_demand_loading = false" "auto_submit = true" "[osd]\nenabled = true" ]
    [ "on_demand_loading = true" "auto_submit = false" "[osd]\nenabled = false" ]
    (builtins.readFile ../config/voxtype/config.toml));
  tabletPi = lib.findFirst (package: (package.pname or "") == "pi-coding-agent")
    (throw "Native tablet chat requires the existing Pi package") osConfig.users.users.sumeet.packages;
  modelPolicy = builtins.fromJSON (builtins.readFile ../config/pi/model-modes.json);
  tabletModel = builtins.head (builtins.filter (mode: mode.id == modelPolicy.default) modelPolicy.modes);
  # Live replacement is restricted to presentation changes. A different agent,
  # input lifecycle/model/runtime needs an explicit trial restart, not a reload.
  tabletUiBackend = builtins.hashString "sha256" (builtins.toJSON [
    (builtins.readFile ../scripts/desktop/tablet-iterate.py)
    (builtins.readFile ../scripts/desktop/tablet_apps.py)
    (builtins.readFile ../config/quickshell/tablet-home-preview/apps.json)
    (builtins.readFile ../config/quickshell/tablet-home-preview/agent.qml)
    (builtins.readFile ../config/quickshell/tablet-home-preview/PiRpc.qml)
    (builtins.readFile ../config/quickshell/tablet-home-preview/stage.qml)
    (builtins.readFile ../config/quickshell/tablet-home-preview/FrameWitness.qml)
    (builtins.readFile ../config/quickshell/tablet-home-preview/tablet-context.md)
    "${tabletPi}" "${pkgs.quickshell}" "${tabletVoiceConfig}"
    "${../config/squeekboard-preview}" tabletModel
  ]);
  tabletUiBundle = pkgs.runCommand "tablet-ui-bundle" { } ''
    mkdir -p "$out/share/tablet-ui"
    cp -r ${../config/quickshell/tablet-home-preview}/. "$out/share/tablet-ui/"
    printf '%s\n' ${lib.escapeShellArg (builtins.toJSON { protocol = 1; backend = tabletUiBackend; })} > "$out/share/tablet-ui/ui-manifest.json"
  '';
  mkTabletTrial = name: native: pkgs.writeShellApplication {
    inherit name;
    runtimeInputs = with pkgs; [ coreutils python3 procps glib dconf squeekboard quickshell wtype wl-clipboard libnotify voxtype vivaldi tabletWorkspace osConfig.programs.hyprland.package ] ++ lib.optionals native [ tabletPi osConfig.nix.package ];
    text = ''
      export QT_QUICK_CONTROLS_STYLE=Basic
      export TABLET_NATIVE_CHAT=${if native then "1" else "0"}
      export TABLET_CHAT_PI=${tabletPi}/bin/pi
      export TABLET_CHAT_PROMPT=${../config/quickshell/tablet-home-preview}/tablet-context.md
      export TABLET_CHAT_PROVIDER=${lib.escapeShellArg tabletModel.provider}
      export TABLET_CHAT_MODEL=${lib.escapeShellArg tabletModel.model}
      export TABLET_ITERATE_BIN
      TABLET_ITERATE_BIN="$(readlink -f "$0")"
      export TABLET_UI_BACKEND=${tabletUiBackend}
      export TABLET_APPS_MODULE=${../scripts/desktop/tablet_apps.py}
      export TABLET_APPS_REGISTRY=${../config/quickshell/tablet-home-preview}/apps.json
      export TABLET_AGENT_QML=${../config/quickshell/tablet-home-preview}/agent.qml
      export TABLET_STAGE_SCREEN=eDP-1
      export TABLET_STAGE_QML=${../config/quickshell/tablet-home-preview}/stage.qml
      export TABLET_ITERATION_QML=${tabletUiBundle}/share/tablet-ui/iteration.qml
      export TABLET_NORMAL_PANEL=${../config/quickshell/tablet-workspace/shell.qml}
      export TABLET_VOICE_CONFIG=${tabletVoiceConfig}
      export GTK_THEME=Adwaita:dark
      export G_RESOURCE_OVERLAYS=/sm/puri/squeekboard=${../config/squeekboard-preview}/resource
      export SQUEEKBOARD_KEYBOARDSDIR=${../config/squeekboard-preview}/keyboards
      export GIO_EXTRA_MODULES=${lib.getLib pkgs.dconf}/lib/gio/modules
      export XDG_DATA_DIRS=${pkgs.squeekboard}/share/gsettings-schemas/${pkgs.squeekboard.name}:${pkgs.gsettings-desktop-schemas}/share/gsettings-schemas/${pkgs.gsettings-desktop-schemas.name}:"''${XDG_DATA_DIRS:-/run/current-system/sw/share}"
      exec python3 ${../scripts/desktop/tablet-iterate.py} "$@"
    '';
  };
  tabletIterate = mkTabletTrial "tablet-iterate" false;
  tabletChat = assert tabletModel.provider != "nanogpt"; mkTabletTrial "tablet-chat" true;
  tabletFoldWatch = pkgs.writeShellApplication {
    name = "tablet-fold-watch";
    runtimeInputs = [ pkgs.python3 tabletChat tabletWorkspace ];
    text = ''
      export TABLET_WORKSPACE_SOURCE=${../scripts/desktop/tablet-workspace.py}
      exec python3 ${../scripts/desktop/tablet-fold-watch.py}
    '';
  };
  tabletWorkspace = pkgs.writeShellApplication {
    name = "tablet-workspace";
    runtimeInputs = with pkgs; [ python3 libnotify vivaldi osConfig.programs.hyprland.package quickshell tabletOskPackage tabletOrientation ];
    text = ''
      export TABLET_PANEL_QML=${../config/quickshell/tablet-workspace/shell.qml}
      exec python3 ${../scripts/desktop/tablet-workspace.py} "$@"
    '';
  };
in
{
  home.packages = [ tabletWorkspace tabletOskPackage tabletOrientation tabletHomePreview tabletIterate tabletChat tabletUiBundle tabletFoldWatch ];
  assertions = [{
    assertion = osConfig.hardware.sensor.iio.enable;
    message = "Tablet orientation requires hardware.sensor.iio.enable.";
  } {
    assertion = builtins.all (name: !(lib.hasInfix name config.wayland.windowManager.hyprland.extraConfig))
      [ "wacom-hid-5430-finger" "wacom-hid-5430-pen" ];
    message = "Declare built-in touch/pen overrides in Hyprland settings.device, not extraConfig, so tablet orientation can restore them.";
  }];

  # A transform-only monitor command is a no-op without a named rule on this
  # Hyprland build. Keep the generic rule for other displays unchanged.
  wayland.windowManager.hyprland.settings.monitor = lib.mkAfter [
    "eDP-1, preferred, auto, 1.25"
  ];

  xdg.desktopEntries.tablet-workspace = {
    name = "Tablet workspace";
    comment = "Open Tablet Home without moving or closing desktop windows";
    exec = "${tabletChat}/bin/tablet-chat start-home";
    icon = "input-tablet";
    terminal = false;
    categories = [ "Utility" ];
  };

  # Shared guarded tablet namespace, also reused by native stage/app surfaces.
  # Keep this deployed policy: Hyprland's layers IPC exposes alpha.goal(), not
  # current fade opacity. Qt animates content inside these opaque surfaces.
  # Do not rename/remove the rule independently of the tablet presentation gate.
  wayland.windowManager.hyprland.settings.layerrule = lib.mkAfter [
    "match:namespace ^tablet-rotation-fade$, no_anim on"
  ];

  wayland.windowManager.hyprland.settings.exec-once = lib.mkAfter [
    "${tabletFoldWatch}/bin/tablet-fold-watch >> \"$XDG_RUNTIME_DIR/tablet-fold-watch.log\" 2>&1"
  ];

  wayland.windowManager.hyprland.settings.bind = lib.mkAfter [
    "$mod CTRL, T, exec, ${tabletChat}/bin/tablet-chat toggle"
  ];
}
