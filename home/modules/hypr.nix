{ clamshellMode, displayKeyHandler, displayLayoutOpen, headlessMonitorWatch, lib, micMuteButton, pkgs, ... }:

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

in
{
  wayland.windowManager.hyprland = {
    enable = true;
    configType = "hyprlang";

    # Hyprland is launched through NixOS/UWSM. Do not let Home Manager inject
    # its unconditional dbus-update-activation-environment exec-once: nested or
    # test Hyprland instances also read this config and can poison the user
    # systemd/dbus environment with a stale WAYLAND_DISPLAY, which breaks
    # xdg-desktop-portal-hyprland screen sharing.
    systemd.enable = false;

    # The NixOS module installs/launches Hyprland. Home Manager only owns the
    # user config.
    package = null;
    portalPackage = null;
    xwayland.enable = true;

    # Disabled for now: the current crash logs show Hyprland coredumping with
    # libhyprgrass loaded. Hyprland plugins are ABI-sensitive, so keep this off
    # until hyprgrass is known-good for this exact Hyprland build.
    plugins = [ ];

    settings = {
      "$mod" = "SUPER";
      "$terminal" = "kitty";
      "$fileManager" = "dolphin";
      "$menu" = "wofi --show drun";
      "$browserWorkspace" = "name:browser";
      "$commsWorkspace" = "name:comms";
      "$musicWorkspace" = "name:music";

      monitor = [ ", preferred, auto, 1.25" ];

      # Avoid blurry XWayland apps at fractional monitor scale. XWayland apps
      # may need their own scale flags if they become too small.
      xwayland.force_zero_scaling = true;

      env = [
        "XCURSOR_SIZE,24"
        "HYPRCURSOR_SIZE,24"
      ];

      exec-once = [
        "${pkgs.swaybg}/bin/swaybg -i /home/sumeet/Pictures/Wallpapers/Bliss-HD.png -m fill"
        "sleep 1; pgrep -x waybar >/dev/null || waybar"
        "${pkgs.blueman}/bin/blueman-applet"
        "${pkgs.hyprsunset}/bin/hyprsunset"
        # graphical-session.target is not active in this Hyprland/UWSM setup,
        # so start the daemon from the compositor environment.
        "systemctl --user start voxtype.service"
        "${headlessMonitorWatch}/bin/headless-monitor-watch"
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
        # Keep app min/max size hints from fighting the tiling layout.
        size_limits_tiled = false;
      };

      bind = [
        "$mod, Q, exec, $terminal"
        "$mod, Return, exec, $terminal"
        "$mod, W, killactive"

        # Resolve Super+B to the active project's persistent browser, with the
        # original global browser workspace as the non-project fallback.
        "$mod, B, exec, project-browser focus"

        "$mod, C, workspace, $commsWorkspace"
        "$mod, C, exec, /home/sumeet/.config/hypr/scripts/hypr-comms-workspace-launch"
        "$mod SHIFT, C, movetoworkspace, $commsWorkspace"

        "$mod, M, workspace, $musicWorkspace"
        "$mod, M, exec, /home/sumeet/.config/hypr/scripts/hypr-music-workspace-launch"
        "$mod SHIFT, M, movetoworkspace, $musicWorkspace"

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

        # Screenshot keys: keyd reports Print Screen as sysrq and the selection key as f16.
        # Hyprland/xkb usually exposes sysrq as Print.
        ", Print, exec, ${screenshotFull}"
        ", F16, exec, ${screenshotSelection}"

        # Single F7 switches mirror/extended after the double-tap window;
        # double F7 primes or restores headless mode.
        ", XF86Display, exec, ${displayKeyHandler}/bin/display-key-handler"
        "SHIFT, XF86Display, exec, ${displayLayoutOpen}/bin/display-layout-open"

        ", F23, exec, voxtype record start"
        "MOD5, F23, exec, voxtype record toggle"
        "$mod, F23, exec, $terminal -e pi"

        "$mod, J, layoutmsg, togglesplit"
        "$mod, L, workspace, previous"

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
      ];

      bindm = [
        "$mod, mouse:272, movewindow"
        "$mod, mouse:273, resizewindow"
      ];

      bindel = [
        ", XF86AudioRaiseVolume, exec, wpctl set-volume -l 1 @DEFAULT_AUDIO_SINK@ 5%+"
        ", XF86AudioLowerVolume, exec, wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%-"
        ", XF86AudioMute, exec, wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle"
        ", XF86MonBrightnessUp, exec, brightnessctl set 5%+"
        ", XF86MonBrightnessDown, exec, brightnessctl set 5%-"
      ];

      bindl = [
        # Display-only clamshell transitions also work while locked. logind
        # still suspends on a normal (no external display) lid close.
        ", switch:on:Lid Switch, exec, ${clamshellMode}/bin/clamshell-mode close"
        ", switch:off:Lid Switch, exec, ${clamshellMode}/bin/clamshell-mode open"
        # Single press toggles mute; double press switches laptop/headset source.
        ", XF86AudioMicMute, exec, ${micMuteButton}/bin/mic-mute-button"
        ", XF86AudioNext, exec, playerctl next"
        ", XF86AudioPause, exec, playerctl play-pause"
        ", XF86AudioPlay, exec, playerctl play-pause"
        ", XF86AudioPrev, exec, playerctl previous"
      ];

      windowrule = [
        "match:title ^Display Layout$, float on"
        "match:title ^Display Layout$, center on"
        "match:title ^Display Layout$, size 760 560"

        "match:class ^(dev.project_object.Picker|project-picker)$, float on"
        "match:class ^(dev.project_object.Picker|project-picker)$, center on"
        "match:class ^(dev.project_object.Picker|project-picker)$, size 760 570"
        "match:class ^(dev.project_object.Picker|project-picker)$, pin on"

        # Generic fix for small fixed-size dialogs/popups: don't force modal
        # windows into the tiling layout.
        "match:modal true, float on"
        "match:modal true, center on"

        "match:class .*, suppress_event maximize"
        "match:class ^(thunderbird|Thunderbird)$, workspace name:comms"
        "match:class ^(slack|Slack)$, workspace name:comms"
        "match:class ^com\\.rtosta\\.zapzap$, workspace name:comms"
        # Keep only the main Teams window eligible for the comms tab group.
        # Auxiliary Teams windows such as the screen-sharing status window
        # should not get swept into the group when switching workspaces.
        "match:class ^teams-for-linux$, match:title ^Teams for Linux - .*, float on"
        "match:class ^teams-for-linux$, match:title ^Teams for Linux - .*, center on"
        "match:class ^teams-for-linux$, match:title ^Teams for Linux - .*, group barred"
        "match:class ^teams-for-linux$, workspace name:comms"
        "match:class ^(spotify|Spotify)$, workspace name:music"
        "match:class ^$, match:title ^$, match:xwayland true, match:float true, match:fullscreen false, match:pin false, no_focus on"
        "match:class ^hyprland-run$, move 20 monitor_h-120"
        "match:class ^hyprland-run$, float on"
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
      # Hyprland 0.55 reports spring-based animation names as missing beziers
      # here, so use the equivalent bezier-backed curve names.

      animation = global, 1, 10, default
      animation = border, 1, 5.39, easeOutQuint
      animation = windows, 1, 4.79, easeOutQuint
      animation = windowsIn, 1, 4.1, easeOutQuint, popin 87%
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

      # Hyprgrass touchscreen gestures disabled with the plugin above.
      # hyprgrass-gesture = swipe, 3, horizontal, scale:1.0, workspace
      # hyprgrass-bind = , tap:3, togglefloating
      # hyprgrass-bindm = , longpress:3, movewindow
      # hyprgrass-bind = , edge:d:u, exec, tablet-osk toggle
      # hyprgrass-bind = , swipe:3:d, exec, tablet-osk hide
    '';
  };

  # Keep support files/scripts that are not part of generated hyprland.conf.
  xdg.configFile."hypr/scripts".source = ../config/hypr/scripts;
  xdg.configFile."hypr/dms".source = ../config/hypr/dms;
  xdg.configFile."hypr/zapzap-whatsapp-title".source = ../config/hypr/zapzap-whatsapp-title;
  # Default the picker to offering a restore token. Applications that reuse
  # it can avoid repeated selection prompts; token-less Slack requests may
  # still prompt separately for the preview and the actual stream.
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
