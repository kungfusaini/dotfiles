{ clamshellMode, config, displayKeyHandler, displayLayoutOpen, headlessMonitorWatch, lib, micMuteButton, pkgs, tabletFoldWatch, ... }:

let
  lua = lib.generators.mkLuaInline;
  bind = keys: action: options: { _args = [ keys (lua action) options ]; };
  execWith = keys: command: bind keys "hl.dsp.exec_cmd(${lib.generators.toLua { } command})";
  exec = keys: command: execWith keys command { };
  screenshotFull = pkgs.writeShellScript "hypr-screenshot-full" ''
    set -eu
    dir="$HOME/Pictures/Screenshots"
    mkdir -p "$dir"
    file="$dir/screenshot-$(date +%Y%m%d-%H%M%S).png"
    ${pkgs.grim}/bin/grim "$file"
    ${pkgs.wl-clipboard}/bin/wl-copy < "$file"
    ${pkgs.libnotify}/bin/notify-send "Screenshot saved" "$file"
  '';
  screenshotSelection = pkgs.writeShellScript "hypr-screenshot-selection" ''
    set -eu
    dir="$HOME/Pictures/Screenshots"
    mkdir -p "$dir"
    file="$dir/screenshot-$(date +%Y%m%d-%H%M%S).png"
    geometry="$(${pkgs.slurp}/bin/slurp)"
    ${pkgs.grim}/bin/grim -g "$geometry" "$file"
    ${pkgs.wl-clipboard}/bin/wl-copy < "$file"
    ${pkgs.libnotify}/bin/notify-send "Screenshot saved" "$file"
  '';
  classRule = class: effects: { match = { inherit class; }; } // effects;
  titleRule = title: effects: { match = { inherit title; }; } // effects;
  animation = leaf: speed: bezier: style: { inherit leaf speed bezier; enabled = true; } // lib.optionalAttrs (style != "") { inherit style; };
  curve = name: points: { _args = [ name { type = "bezier"; inherit points; } ]; };
in
{
  wayland.windowManager.hyprland = {
    enable = true;
    configType = "lua";
    # NixOS/UWSM owns startup. Never import a nested test compositor into the
    # real systemd/DBus environment (in particular, the screen-sharing portals).
    systemd.enable = false;
    package = null;
    portalPackage = null;
    xwayland.enable = true;
    # Deliberately still disabled: libhyprgrass has caused compositor crashes.
    plugins = [ ];

    settings = {
      terminal._var = "kitty";
      monitor = [ { output = ""; mode = "preferred"; position = "auto"; scale = 1.25; } ];
      env = [ { _args = [ "XCURSOR_SIZE" "24" false ]; }
              { _args = [ "HYPRCURSOR_SIZE" "24" false ]; } ];
      on = [{ _args = [ "hyprland.start" (lua ''function()
        hl.exec_cmd(${lib.generators.toLua { } "${pkgs.swaybg}/bin/swaybg -i /home/sumeet/Pictures/Wallpapers/Bliss-HD.png -m fill"})
        hl.exec_cmd("sleep 1; pgrep -x waybar >/dev/null || waybar")
        hl.exec_cmd(${lib.generators.toLua { } "${pkgs.blueman}/bin/blueman-applet"})
        hl.exec_cmd(${lib.generators.toLua { } "${pkgs.hyprsunset}/bin/hyprsunset"})
        hl.exec_cmd("systemctl --user start voxtype.service")
        hl.exec_cmd(${lib.generators.toLua { } "${headlessMonitorWatch}/bin/headless-monitor-watch"})
      end'') ]; }];
      config = {
        xwayland.force_zero_scaling = true;
        general = {
          gaps_in = 5; gaps_out = 20; border_size = 2;
          col.active_border = { colors = [ "rgba(33ccffee)" "rgba(00ff99ee)" ]; angle = 45; };
          col.inactive_border = "rgba(595959aa)";
          resize_on_border = false; allow_tearing = false; layout = "dwindle";
        };
        decoration = {
          rounding = 10; rounding_power = 2; active_opacity = 1.0; inactive_opacity = 1.0;
          shadow = { enabled = true; range = 4; render_power = 3; color = "rgba(1a1a1aee)"; };
          blur = { enabled = true; size = 3; passes = 1; vibrancy = 0.1696; };
        };
        animations.enabled = true;
        group = {
          auto_group = false; drag_into_group = 2;
          groupbar = { enabled = true; height = 1; font_size = 1; render_titles = false; scrolling = true; };
        };
        input = {
          kb_layout = "gb"; kb_variant = ""; kb_model = ""; kb_options = ""; kb_rules = "";
          follow_mouse = 1; sensitivity = 0; force_no_accel = false;
          touchpad.natural_scroll = false;
          touchdevice.enabled = true;
          virtualkeyboard = { share_states = 2; release_pressed_on_close = true; };
        };
        gestures = { workspace_swipe_touch = true; workspace_swipe_cancel_ratio = 0.15; };
        dwindle = { preserve_split = true; force_split = 2; };
        master.new_status = "master";
        scrolling.fullscreen_on_one_column = true;
        misc = { force_default_wallpaper = -1; disable_hyprland_logo = false; size_limits_tiled = false; };
      };
      device = [{
        name = "tpps/2-elan-trackpoint";
        sensitivity = -0.50; accel_profile = "adaptive";
        scroll_method = "on_button_down"; scroll_button = 274;
      }];
      # Disabled hyprgrass tuning from the previous config was inert. Keep its
      # values documented, not a plugin load: sensitivity=4, long_press_delay=400,
      # resize_on_border_long_press=true, edge_margin=10. Touchscreen plugin
      # gestures remain disabled; the native trackpad gesture remains enabled.
      gesture = { fingers = 3; direction = "horizontal"; action = "workspace"; };
      curve = [
        (curve "easeOutQuint" [ [ 0.23 1 ] [ 0.32 1 ] ])
        (curve "easeInOutCubic" [ [ 0.65 0.05 ] [ 0.36 1 ] ])
        (curve "linear" [ [ 0 0 ] [ 1 1 ] ])
        (curve "almostLinear" [ [ 0.5 0.5 ] [ 0.75 1 ] ])
        (curve "quick" [ [ 0.15 0 ] [ 0.1 1 ] ])
      ];
      animation = [
        (animation "global" 10 "default" "")
        (animation "border" 5.39 "easeOutQuint" "")
        (animation "windows" 4.79 "easeOutQuint" "")
        (animation "windowsIn" 4.1 "easeOutQuint" "popin 87%")
        (animation "windowsOut" 1.49 "linear" "popin 87%")
        (animation "fadeIn" 1.73 "almostLinear" "")
        (animation "fadeOut" 1.46 "almostLinear" "")
        (animation "fade" 3.03 "quick" "")
        (animation "layers" 3.81 "easeOutQuint" "")
        (animation "layersIn" 4 "easeOutQuint" "fade")
        (animation "layersOut" 1.5 "linear" "fade")
        (animation "fadeLayersIn" 1.79 "almostLinear" "")
        (animation "fadeLayersOut" 1.39 "almostLinear" "")
        (animation "workspaces" 1.94 "almostLinear" "fade")
        (animation "workspacesIn" 1.21 "almostLinear" "fade")
        (animation "workspacesOut" 1.94 "almostLinear" "fade")
        (animation "zoomFactor" 7 "quick" "")
      ];
      bind = lib.mkMerge [ ([
        (bind "SUPER + Q" "hl.dsp.exec_cmd(terminal)" { })
        (bind "SUPER + Return" "hl.dsp.exec_cmd(terminal)" { })
        (bind "SUPER + W" "hl.dsp.window.close()" { })
        (exec "SUPER + SHIFT + Escape" "agent-screen-sleep")
        (exec "SUPER + B" "project-browser focus")
        (bind "SUPER + C" ''hl.dsp.focus({workspace="name:comms"})'' { })
        (exec "SUPER + C" "/home/sumeet/.config/hypr/scripts/hypr-comms-workspace-launch")
        (bind "SUPER + SHIFT + C" ''hl.dsp.window.move({workspace="name:comms"})'' { })
        (bind "SUPER + M" ''hl.dsp.focus({workspace="name:music"})'' { })
        (exec "SUPER + M" "/home/sumeet/.config/hypr/scripts/hypr-music-workspace-launch")
        (bind "SUPER + SHIFT + M" ''hl.dsp.window.move({workspace="name:music"})'' { })
        (bind "SUPER + G" "hl.dsp.group.toggle()" { })
        (bind "SUPER + TAB" "hl.dsp.group.next()" { })
        (bind "SUPER + SHIFT + TAB" "hl.dsp.group.prev()" { })
        (bind "SUPER + bracketright" "hl.dsp.group.next()" { })
        (bind "SUPER + bracketleft" "hl.dsp.group.prev()" { })
        (bind "SUPER + SHIFT + G" ''hl.dsp.group.lock_active({action="toggle"})'' { })
        (exec "SUPER + E" "dolphin")
        (bind "SUPER + F" "hl.dsp.window.fullscreen()" { })
        (bind "SUPER + V" ''hl.dsp.window.float({action="toggle"})'' { })
        (exec "SUPER + SPACE" "wofi --show drun")
        (exec "Print" "${screenshotFull}")
        (exec "F16" "${screenshotSelection}")
        (exec "XF86Display" "${displayKeyHandler}/bin/display-key-handler")
        (exec "SHIFT + XF86Display" "${displayLayoutOpen}/bin/display-layout-open")
        (exec "F23" "voxtype record start")
        (exec "MOD5 + F23" "voxtype record toggle")
        (bind "SUPER + F23" ''hl.dsp.exec_cmd(terminal .. " -e pi")'' { })
        (bind "SUPER + J" ''hl.dsp.layout("togglesplit")'' { })
        (bind "SUPER + L" ''hl.dsp.focus({workspace="previous"})'' { })
        (bind "SUPER + left" ''hl.dsp.focus({direction="left"})'' { })
        (bind "SUPER + right" ''hl.dsp.focus({direction="right"})'' { })
        (bind "SUPER + up" ''hl.dsp.focus({direction="up"})'' { })
        (bind "SUPER + down" ''hl.dsp.focus({direction="down"})'' { })
      ] ++ (map (i: bind "SUPER + ${toString (lib.mod i 10)}" "hl.dsp.focus({workspace=${toString i}})" { }) (lib.range 1 10))
        ++ (map (i: bind "SUPER + SHIFT + ${toString (lib.mod i 10)}" "hl.dsp.window.move({workspace=${toString i}})" { }) (lib.range 1 10)) ++ [
        (bind "SUPER + S" ''hl.dsp.workspace.toggle_special("magic")'' { })
        (bind "SUPER + SHIFT + S" ''hl.dsp.window.move({workspace="special:magic"})'' { })
        (bind "SUPER + mouse_down" ''hl.dsp.focus({workspace="e+1"})'' { })
        (bind "SUPER + mouse_up" ''hl.dsp.focus({workspace="e-1"})'' { })
      ]) (lib.mkOrder 1600 [
        (execWith "XF86AudioRaiseVolume" "wpctl set-volume -l 1 @DEFAULT_AUDIO_SINK@ 5%+" { repeating = true; locked = true; })
        (execWith "XF86AudioLowerVolume" "wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%-" { repeating = true; locked = true; })
        (execWith "XF86AudioMute" "wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle" { repeating = true; locked = true; })
        (execWith "XF86MonBrightnessUp" "brightnessctl set 5%+" { repeating = true; locked = true; })
        (execWith "XF86MonBrightnessDown" "brightnessctl set 5%-" { repeating = true; locked = true; })
        (execWith "switch:on:Lid Switch" "${clamshellMode}/bin/clamshell-mode close" { locked = true; })
        (execWith "switch:off:Lid Switch" "${clamshellMode}/bin/clamshell-mode open" { locked = true; })
        (execWith "XF86AudioMicMute" "${micMuteButton}/bin/mic-mute-button" { locked = true; })
        (execWith "XF86AudioNext" "playerctl next" { locked = true; })
        (execWith "XF86AudioPause" "playerctl play-pause" { locked = true; })
        (execWith "XF86AudioPlay" "playerctl play-pause" { locked = true; })
        (execWith "XF86AudioPrev" "playerctl previous" { locked = true; })
        (bind "SUPER + mouse:272" "hl.dsp.window.drag()" { })
        (bind "SUPER + mouse:273" "hl.dsp.window.resize()" { })
        (execWith "F23" "voxtype record stop" { release = true; })
      ]) ];
      window_rule = [
        (titleRule "^Display Layout$" { float = true; })
        (titleRule "^Display Layout$" { center = true; })
        (titleRule "^Display Layout$" { size = "760 560"; })
        (classRule "^(dev.project_object.Picker|project-picker)$" { float = true; })
        (classRule "^(dev.project_object.Picker|project-picker)$" { center = true; })
        (classRule "^(dev.project_object.Picker|project-picker)$" { size = "760 570"; })
        (classRule "^(dev.project_object.Picker|project-picker)$" { pin = true; })
        { match.modal = true; float = true; }
        { match.modal = true; center = true; }
        (classRule ".*" { suppress_event = "maximize"; })
        (classRule "^(thunderbird|Thunderbird)$" { workspace = "name:comms"; })
        (classRule "^(slack|Slack)$" { workspace = "name:comms"; })
        (classRule "^com\\.rtosta\\.zapzap$" { workspace = "name:comms"; })
        { match = { class = "^teams-for-linux$"; title = "^Teams for Linux - .*"; }; float = true; }
        { match = { class = "^teams-for-linux$"; title = "^Teams for Linux - .*"; }; center = true; }
        { match = { class = "^teams-for-linux$"; title = "^Teams for Linux - .*"; }; group = "barred"; }
        (classRule "^teams-for-linux$" { workspace = "name:comms"; })
        (classRule "^(spotify|Spotify)$" { workspace = "name:music"; })
        { match = { class = "^$"; title = "^$"; xwayland = true; float = true; fullscreen = false; pin = false; }; no_focus = true; }
        (classRule "^hyprland-run$" { move = "20 monitor_h-120"; })
        (classRule "^hyprland-run$" { float = true; })
      ];
    };
  };

  # Keep the actual legacy configuration present while an old session is still
  # running. Backend selection is cached until restart; deleting it would make
  # an automatic reload regenerate defaults. New sessions prefer Lua.
  xdg.configFile."hypr/hyprland.conf".text = import ../config/hypr/legacy-transition.conf.nix {
    inherit pkgs screenshotFull screenshotSelection displayKeyHandler displayLayoutOpen
      headlessMonitorWatch micMuteButton clamshellMode tabletFoldWatch;
    projectPackage = config.programs.project-object.package;
  };

  xdg.configFile."hypr/scripts".source = ../config/hypr/scripts;
  xdg.configFile."hypr/dms".source = ../config/hypr/dms;
  xdg.configFile."hypr/zapzap-whatsapp-title".source = ../config/hypr/zapzap-whatsapp-title;
  xdg.configFile."hypr/xdph.conf".text = ''
    screencopy {
        allow_token_by_default = true
    }
  '';
  xdg.configFile."hypr/hyprsunset.conf".text = ''
    profile {
        time = 7:00
        identity = true
    }

    profile {
        time = 20:00
        temperature = 5000
    }

    profile {
        time = 22:00
        temperature = 3500
    }
  '';
}
