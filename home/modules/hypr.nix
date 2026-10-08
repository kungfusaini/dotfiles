{ lib, pkgs, ... }:

let
  # Keep this pinned to the same Hyprland-compatible hyprgrass build used by
  # the NixOS Hyprland module.
  hyprgrass = pkgs.hyprlandPlugins.hyprgrass.overrideAttrs (_old: {
    version = "0.8.2-pin-v0.55.4";
    src = pkgs.fetchFromGitHub {
      owner = "horriblename";
      repo = "hyprgrass";
      rev = "d094a3e62f6ecaeb41515982d3e13edefaf8a4e7";
      hash = "sha256-tCt7FNc1RBHou/ym7B0XzoOqqNq8Df+dizEDkAgJ4U0=";
    };
  });

  tabletOsk = "/home/sumeet/.config/nixos/hosts/nixos/scripts/desktop/tablet-osk";
  micMuteKey = "/home/sumeet/.config/nixos/hosts/nixos/scripts/desktop/mic-mute-key";
in
{
  wayland.windowManager.hyprland = {
    enable = true;
    configType = "hyprlang";

    # The NixOS module installs/launches Hyprland. Home Manager only owns the
    # user config.
    package = null;
    portalPackage = null;
    xwayland.enable = true;

    plugins = [ hyprgrass ];

    settings = {
      "$mod" = "SUPER";
      "$terminal" = "kitty";
      "$fileManager" = "dolphin";
      "$menu" = "wofi --show drun";
      "$browserWorkspace" = "name:browser";
      "$commsWorkspace" = "name:comms";

      monitor = [ ", preferred, auto, 1.25" ];

      env = [
        "XCURSOR_SIZE,24"
        "HYPRCURSOR_SIZE,24"
      ];

      exec-once = [
        "nix shell nixpkgs#swaybg -c swaybg -i /home/sumeet/Pictures/Wallpapers/Bliss.bmp -m fill"
        "sleep 1; pgrep -x waybar >/dev/null || waybar"
        "${tabletOsk} daemon"
      ];

      general = {
        gaps_in = 5;
        gaps_out = 20;
        border_size = 2;
        "col.active_border" = "rgba(33ccffee) rgba(00ff99ee) 45deg";
        "col.inactive_border" = "rgba(595959aa)";
        resize_on_border = false;
        allow_tearing = false;
        layout = "dwindle";
      };

      decoration = {
        rounding = 10;
        rounding_power = 2;
        active_opacity = 1.0;
        inactive_opacity = 1.0;
        shadow = {
          enabled = true;
          range = 4;
          render_power = 3;
          color = "rgba(1a1a1aee)";
        };
        blur = {
          enabled = true;
          size = 3;
          passes = 1;
          vibrancy = 0.1696;
        };
      };

      animations = {
        enabled = true;
      };

      group = {
        auto_group = false;
        drag_into_group = 2;
        groupbar = {
          enabled = true;
          height = 1;
          font_size = 1;
          render_titles = false;
          scrolling = true;
        };
      };

      input = {
        kb_layout = "gb";
        kb_variant = "";
        kb_model = "";
        kb_options = "";
        kb_rules = "";
        follow_mouse = 1;
        sensitivity = 0;
        force_no_accel = false;
        touchpad.natural_scroll = false;
        touchdevice.enabled = true;
        virtualkeyboard = {
          share_states = 2;
          release_pressed_on_close = true;
        };
      };

      gestures = {
        workspace_swipe_touch = true;
        workspace_swipe_cancel_ratio = 0.15;
      };

      # Hyprgrass uses the legacy `touch_gestures` config namespace when
      # Hyprland is configured with hyprland.conf. The `hyprgrass` namespace is
      # for Lua config only.
      plugin.touch_gestures = {
        sensitivity = 4.0;
        long_press_delay = 400;
        resize_on_border_long_press = true;
        edge_margin = 10;
      };

      dwindle = {
        preserve_split = true;
        force_split = 2;
      };

      master.new_status = "master";
      scrolling.fullscreen_on_one_column = true;

      misc = {
        force_default_wallpaper = -1;
        disable_hyprland_logo = false;
      };

      bind = [
        "$mod, Q, exec, $terminal"
        "$mod, Return, exec, $terminal"
        "$mod, W, killactive"

        "$mod, B, workspace, $browserWorkspace"
        "$mod, B, exec, /home/sumeet/.config/hypr/scripts/hypr-browser-workspace-launch"
        "$mod SHIFT, B, movetoworkspace, $browserWorkspace"

        "$mod, C, workspace, $commsWorkspace"
        "$mod, C, exec, /home/sumeet/.config/hypr/scripts/hypr-comms-workspace-launch"
        "$mod SHIFT, C, movetoworkspace, $commsWorkspace"

        "$mod, G, togglegroup"
        "$mod, TAB, changegroupactive, f"
        "$mod SHIFT, TAB, changegroupactive, b"
        "$mod, bracketright, changegroupactive, f"
        "$mod, bracketleft, changegroupactive, b"
        "$mod SHIFT, G, lockactivegroup, toggle"

        "$mod, E, exec, $fileManager"
        "$mod, F, fullscreen"
        "$mod, V, togglefloating"
        "$mod, SPACE, exec, $menu"

        ", F23, exec, voxtype record start"
        # Short press toggles mic mute; hold toggles laptop/headset mic source.
        ", XF86AudioMicMute, exec, ${micMuteKey} press"
        "$mod, F23, exec, $terminal -e pi"

        "$mod, P, pseudo"
        "$mod, J, togglesplit"

        "$mod, left, movefocus, l"
        "$mod, right, movefocus, r"
        "$mod, up, movefocus, u"
        "$mod, down, movefocus, d"

        "$mod, 1, workspace, 1"
        "$mod, 2, workspace, 2"
        "$mod, 3, workspace, 3"
        "$mod, 4, workspace, 4"
        "$mod, 5, workspace, 5"
        "$mod, 6, workspace, 6"
        "$mod, 7, workspace, 7"
        "$mod, 8, workspace, 8"
        "$mod, 9, workspace, 9"
        "$mod, 0, workspace, 10"
        "$mod SHIFT, 1, movetoworkspace, 1"
        "$mod SHIFT, 2, movetoworkspace, 2"
        "$mod SHIFT, 3, movetoworkspace, 3"
        "$mod SHIFT, 4, movetoworkspace, 4"
        "$mod SHIFT, 5, movetoworkspace, 5"
        "$mod SHIFT, 6, movetoworkspace, 6"
        "$mod SHIFT, 7, movetoworkspace, 7"
        "$mod SHIFT, 8, movetoworkspace, 8"
        "$mod SHIFT, 9, movetoworkspace, 9"
        "$mod SHIFT, 0, movetoworkspace, 10"

        "$mod, S, togglespecialworkspace, magic"
        "$mod SHIFT, S, movetoworkspace, special:magic"

        "$mod, mouse_down, workspace, e+1"
        "$mod, mouse_up, workspace, e-1"
      ];

      bindr = [
        ", F23, exec, voxtype record stop"
        ", XF86AudioMicMute, exec, ${micMuteKey} release"
      ];

      bindm = [
        "$mod, mouse:272, movewindow"
        "$mod, mouse:273, resizewindow"
      ];

      bindel = [
        ", XF86AudioRaiseVolume, exec, wpctl set-volume -l 1 @DEFAULT_AUDIO_SINK@ 5%+"
        ", XF86AudioLowerVolume, exec, wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%-"
        ", XF86AudioMute, exec, wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle"
        ", XF86MonBrightnessUp, exec, brightnessctl set 10%+"
        ", XF86MonBrightnessDown, exec, brightnessctl set 10%-"
      ];

      bindl = [
        ", XF86AudioNext, exec, playerctl next"
        ", XF86AudioPause, exec, playerctl play-pause"
        ", XF86AudioPlay, exec, playerctl play-pause"
        ", XF86AudioPrev, exec, playerctl previous"
      ];

      windowrulev2 = [
        "suppressevent maximize, class:.*"
        "workspace name:comms, class:^(thunderbird|Thunderbird)$"
        "workspace name:browser, class:^vivaldi.*$"
        "workspace name:comms, class:^(slack|Slack)$"
        "workspace name:comms, class:^com\\.rtosta\\.zapzap$"
        "workspace name:comms, class:^teams-for-linux$"
        "nofocus, class:^$, title:^$, xwayland:1, floating:1, fullscreen:0, pinned:0"
        "move 20 monitor_h-120, class:^hyprland-run$"
        "float, class:^hyprland-run$"
      ];
    };

    extraConfig = ''
      # TrackPoint tuning. Device name from `hyprctl devices`.
      device {
        name = tpps/2-elan-trackpoint
        sensitivity = -0.50
        accel_profile = adaptive
        scroll_method = on_button_down
        scroll_button = 274
      }

      # Curves and animations ported from the Lua defaults/customisation.
      bezier = easeOutQuint, 0.23, 1, 0.32, 1
      bezier = easeInOutCubic, 0.65, 0.05, 0.36, 1
      bezier = linear, 0, 0, 1, 1
      bezier = almostLinear, 0.5, 0.5, 0.75, 1
      bezier = quick, 0.15, 0, 0.1, 1
      spring = easy, 1, 71.2633, 15.8273644

      animation = global, 1, 10, default
      animation = border, 1, 5.39, easeOutQuint
      animation = windows, 1, 4.79, easy
      animation = windowsIn, 1, 4.1, easy, popin 87%
      animation = windowsOut, 1, 1.49, linear, popin 87%
      animation = fadeIn, 1, 1.73, almostLinear
      animation = fadeOut, 1, 1.46, almostLinear
      animation = fade, 1, 3.03, quick
      animation = layers, 1, 3.81, easeOutQuint
      animation = layersIn, 1, 4, easeOutQuint, fade
      animation = layersOut, 1, 1.5, linear, fade
      animation = fadeLayersIn, 1, 1.79, almostLinear
      animation = fadeLayersOut, 1, 1.39, almostLinear
      animation = workspaces, 1, 1.94, almostLinear, fade
      animation = workspacesIn, 1, 1.21, almostLinear, fade
      animation = workspacesOut, 1, 1.94, almostLinear, fade
      animation = zoomFactor, 1, 7, quick

      # Hyprland's built-in trackpad-style gesture.
      gesture = 3, horizontal, workspace

      # Hyprgrass touchscreen gestures.
      hyprgrass-gesture = swipe, 3, horizontal, scale:1.0, workspace
      hyprgrass-bind = , tap:3, togglefloating
      hyprgrass-bindm = , longpress:3, movewindow
      hyprgrass-bind = , edge:d:u, exec, ${tabletOsk} toggle
      hyprgrass-bind = , swipe:3:d, exec, ${tabletOsk} hide
    '';
  };

  # Keep support files/scripts that are not part of generated hyprland.conf.
  xdg.configFile."hypr/scripts".source = ../config/hypr/scripts;
  xdg.configFile."hypr/dms".source = ../config/hypr/dms;
  xdg.configFile."hypr/zapzap-whatsapp-title".source = ../config/hypr/zapzap-whatsapp-title;

  # If this machine had the previous Lua setup activated, leave no exact
  # hyprland.lua alongside the generated hyprland.conf. Hyprland config format
  # selection is file-name based, so an old Lua entrypoint would be confusing.
  home.activation.archiveOldHyprLua = lib.hm.dag.entryAfter [ "writeBoundary" ] ''
    if [ -e "$HOME/.config/hypr/hyprland.lua" ] && [ ! -e "$HOME/.config/hypr/hyprland.lua.hm-lua-backup" ]; then
      mv "$HOME/.config/hypr/hyprland.lua" "$HOME/.config/hypr/hyprland.lua.hm-lua-backup"
    fi
    if [ -d "$HOME/.config/hypr/conf" ] && [ ! -e "$HOME/.config/hypr/conf.hm-lua-backup" ]; then
      mv "$HOME/.config/hypr/conf" "$HOME/.config/hypr/conf.hm-lua-backup"
    fi
  '';
}
