# Frozen pre-migration canonical desktop (2e2e3550), retained only so an already-running
# Hyprlang backend can reload safely after Home Manager activation. New sessions
# select hyprland.lua first. Do not add new features here or parse Lua into it.
{ pkgs, projectPackage, screenshotFull, screenshotSelection, displayKeyHandler,
  displayLayoutOpen, headlessMonitorWatch, micMuteButton, clamshellMode, tabletFoldWatch }:
''
$browserWorkspace=name:browser
$commsWorkspace=name:comms
$fileManager=dolphin
$menu=wofi --show drun
$mod=SUPER
$musicWorkspace=name:music
$terminal=${projectPackage}/bin/project-terminal
animations {
  enabled=true
}
bind=$mod, Q, exec, $terminal
bind=$mod, Return, exec, $terminal
bind=$mod, W, killactive
bind=$mod SHIFT, Escape, exec, agent-screen-sleep
bind=$mod, B, exec, project-browser focus
bind=$mod, C, workspace, $commsWorkspace
bind=$mod, C, exec, /home/sumeet/.config/hypr/scripts/hypr-comms-workspace-launch
bind=$mod SHIFT, C, movetoworkspace, $commsWorkspace
bind=$mod, M, workspace, $musicWorkspace
bind=$mod, M, exec, /home/sumeet/.config/hypr/scripts/hypr-music-workspace-launch
bind=$mod SHIFT, M, movetoworkspace, $musicWorkspace
bind=$mod, G, togglegroup
bind=$mod, TAB, changegroupactive, f
bind=$mod SHIFT, TAB, changegroupactive, b
bind=$mod, bracketright, changegroupactive, f
bind=$mod, bracketleft, changegroupactive, b
bind=$mod SHIFT, G, lockactivegroup, toggle
bind=$mod, E, exec, $fileManager
bind=$mod, F, fullscreen
bind=$mod, V, togglefloating
bind=$mod, SPACE, exec, $menu
bind=, Print, exec, ${screenshotFull}
bind=, F16, exec, ${screenshotSelection}
bind=, XF86Display, exec, ${displayKeyHandler}/bin/display-key-handler
bind=SHIFT, XF86Display, exec, ${displayLayoutOpen}/bin/display-layout-open
bind=, F23, exec, voxtype record start
bind=MOD5, F23, exec, voxtype record toggle
bind=$mod, F23, exec, $terminal -e pi
bind=$mod, J, layoutmsg, togglesplit
bind=$mod, L, workspace, previous
bind=$mod, left, movefocus, l
bind=$mod, right, movefocus, r
bind=$mod, up, movefocus, u
bind=$mod, down, movefocus, d
bind=$mod, 1, workspace, 1
bind=$mod, 2, workspace, 2
bind=$mod, 3, workspace, 3
bind=$mod, 4, workspace, 4
bind=$mod, 5, workspace, 5
bind=$mod, 6, workspace, 6
bind=$mod, 7, workspace, 7
bind=$mod, 8, workspace, 8
bind=$mod, 9, workspace, 9
bind=$mod, 0, workspace, 10
bind=$mod SHIFT, 1, movetoworkspace, 1
bind=$mod SHIFT, 2, movetoworkspace, 2
bind=$mod SHIFT, 3, movetoworkspace, 3
bind=$mod SHIFT, 4, movetoworkspace, 4
bind=$mod SHIFT, 5, movetoworkspace, 5
bind=$mod SHIFT, 6, movetoworkspace, 6
bind=$mod SHIFT, 7, movetoworkspace, 7
bind=$mod SHIFT, 8, movetoworkspace, 8
bind=$mod SHIFT, 9, movetoworkspace, 9
bind=$mod SHIFT, 0, movetoworkspace, 10
bind=$mod, S, togglespecialworkspace, magic
bind=$mod SHIFT, S, movetoworkspace, special:magic
bind=$mod, mouse_down, workspace, e+1
bind=$mod, mouse_up, workspace, e-1
bind=$mod, P, exec, ${projectPackage}/bin/project-picker
bind=$mod, X, exec, ${projectPackage}/bin/project-picker --close-active-workspace
bind=$mod, n, exec, ${projectPackage}/bin/project-picker --next-attention
bind=$mod SHIFT, n, exec, ${projectPackage}/bin/project-picker --previous-attention
bindel=, XF86AudioRaiseVolume, exec, wpctl set-volume -l 1 @DEFAULT_AUDIO_SINK@ 5%+
bindel=, XF86AudioLowerVolume, exec, wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%-
bindel=, XF86AudioMute, exec, wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle
bindel=, XF86MonBrightnessUp, exec, brightnessctl set 5%+
bindel=, XF86MonBrightnessDown, exec, brightnessctl set 5%-
bindl=, switch:on:Lid Switch, exec, ${clamshellMode}/bin/clamshell-mode close
bindl=, switch:off:Lid Switch, exec, ${clamshellMode}/bin/clamshell-mode open
bindl=, XF86AudioMicMute, exec, ${micMuteButton}/bin/mic-mute-button
bindl=, XF86AudioNext, exec, playerctl next
bindl=, XF86AudioPause, exec, playerctl play-pause
bindl=, XF86AudioPlay, exec, playerctl play-pause
bindl=, XF86AudioPrev, exec, playerctl previous
bindm=$mod, mouse:272, movewindow
bindm=$mod, mouse:273, resizewindow
bindr=, F23, exec, voxtype record stop
decoration {
  blur {
    enabled=true
    passes=1
    size=3
    vibrancy=0.169600
  }
  shadow {
    color=rgba(1a1a1aee)
    enabled=true
    range=4
    render_power=3
  }
  active_opacity=1.000000
  inactive_opacity=1.000000
  rounding=10
  rounding_power=2
}
dwindle {
  force_split=2
  preserve_split=true
}
env=XCURSOR_SIZE,24
env=HYPRCURSOR_SIZE,24
exec-once=${pkgs.swaybg}/bin/swaybg -i /home/sumeet/Pictures/Wallpapers/Bliss-HD.png -m fill
exec-once=sleep 1; pgrep -x waybar >/dev/null || waybar
exec-once=${pkgs.blueman}/bin/blueman-applet
exec-once=${pkgs.hyprsunset}/bin/hyprsunset
exec-once=systemctl --user start voxtype.service
exec-once=${headlessMonitorWatch}/bin/headless-monitor-watch
exec-once=${tabletFoldWatch}/bin/tablet-fold-watch >> "$XDG_RUNTIME_DIR/tablet-fold-watch.log" 2>&1
exec-once=${projectPackage}/bin/project-picker --preload
general {
  allow_tearing=false
  border_size=2
  col.active_border=rgba(33ccffee) rgba(00ff99ee) 45deg
  col.inactive_border=rgba(595959aa)
  gaps_in=5
  gaps_out=20
  layout=dwindle
  resize_on_border=false
}
gestures {
  workspace_swipe_cancel_ratio=0.150000
  workspace_swipe_touch=true
}
group {
  groupbar {
    enabled=true
    font_size=1
    height=1
    render_titles=false
    scrolling=true
  }
  auto_group=false
  drag_into_group=2
}
input {
  touchdevice {
    enabled=true
  }
  touchpad {
    natural_scroll=false
  }
  virtualkeyboard {
    release_pressed_on_close=true
    share_states=2
  }
  follow_mouse=1
  force_no_accel=false
  kb_layout=gb
  kb_model=
  kb_options=
  kb_rules=
  kb_variant=
  sensitivity=0
}
layerrule=match:namespace ^tablet-rotation-fade$, no_anim on
master {
  new_status=master
}
misc {
  disable_hyprland_logo=false
  force_default_wallpaper=-1
  size_limits_tiled=false
}
monitor=, preferred, auto, 1.25
monitor=eDP-1, preferred, auto, 1.25
plugin {
  touch_gestures {
    edge_margin=10
    long_press_delay=400
    resize_on_border_long_press=true
    sensitivity=4.000000
  }
}
scrolling {
  fullscreen_on_one_column=true
}
windowrule=match:class ^(pegasus-fe|org\.pegasus-frontend\.)$, fullscreen on
windowrule=match:title ^Display Layout$, float on
windowrule=match:title ^Display Layout$, center on
windowrule=match:title ^Display Layout$, size 760 560
windowrule=match:class ^(dev.project_object.Picker|project-picker)$, float on
windowrule=match:class ^(dev.project_object.Picker|project-picker)$, center on
windowrule=match:class ^(dev.project_object.Picker|project-picker)$, size 760 570
windowrule=match:class ^(dev.project_object.Picker|project-picker)$, pin on
windowrule=match:modal true, float on
windowrule=match:modal true, center on
windowrule=match:class .*, suppress_event maximize
windowrule=match:class ^(thunderbird|Thunderbird)$, workspace name:comms
windowrule=match:class ^(slack|Slack)$, workspace name:comms
windowrule=match:class ^com\.rtosta\.zapzap$, workspace name:comms
windowrule=match:class ^teams-for-linux$, match:title ^Teams for Linux - .*, float on
windowrule=match:class ^teams-for-linux$, match:title ^Teams for Linux - .*, center on
windowrule=match:class ^teams-for-linux$, match:title ^Teams for Linux - .*, group barred
windowrule=match:class ^teams-for-linux$, workspace name:comms
windowrule=match:class ^(spotify|Spotify)$, workspace name:music
windowrule=match:class ^$, match:title ^$, match:xwayland true, match:float true, match:fullscreen false, match:pin false, no_focus on
windowrule=match:class ^hyprland-run$, move 20 monitor_h-120
windowrule=match:class ^hyprland-run$, float on
windowrule=match:class ^(dev.project_object.Picker|project-picker)$, float on
windowrule=match:class ^(dev.project_object.Picker|project-picker)$, center on
windowrule=match:class ^(dev.project_object.Picker|project-picker)$, size 760 570
xwayland {
  force_zero_scaling=true
}
device {
  name = tpps/2-elan-trackpoint
  sensitivity = -0.50
  accel_profile = adaptive
  scroll_method = on_button_down
  scroll_button = 274
}
bezier = easeOutQuint, 0.23, 1, 0.32, 1
bezier = easeInOutCubic, 0.65, 0.05, 0.36, 1
bezier = linear, 0, 0, 1, 1
bezier = almostLinear, 0.5, 0.5, 0.75, 1
bezier = quick, 0.15, 0, 0.1, 1
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
gesture = 3, horizontal, workspace
''
