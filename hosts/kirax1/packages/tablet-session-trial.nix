{ pkgs, lib }:
let
  kde = pkgs.kdePackages;
  returnDesktop = pkgs.makeDesktopItem {
    name = "tablet-trial-return";
    desktopName = "Return to laptop";
    comment = "Return to the existing laptop session without logging out";
    icon = "computer-laptop";
    exec = "${pkgs.systemd}/bin/systemctl start tablet-session-trial-return.service";
    categories = [ "System" ];
  };
  browser = pkgs.writeShellApplication {
    name = "tablet-trial-browser";
    runtimeInputs = [ pkgs.chromium ];
    text = ''
      exec chromium --no-first-run --no-default-browser-check --ozone-platform=wayland \
        --enable-wayland-ime --wayland-text-input-version=3 "$@"
    '';
  };
  browserDesktop = pkgs.makeDesktopItem {
    name = "tablet-trial-browser";
    desktopName = "Trial browser";
    comment = "Separate trial profile; no personal browser data";
    icon = "chromium";
    exec = "${browser}/bin/tablet-trial-browser %U";
    categories = [ "Network" "WebBrowser" ];
  };
  # The mobile quick-settings UI imports this QML module even when no power
  # daemon is active. Do not autostart a second idle/suspend policy in this trial.
  powerWidgets = pkgs.runCommand "tablet-trial-power-widgets" {} ''
    mkdir -p "$out/lib/qt-6/qml/org/kde/plasma/private"
    ln -s ${kde.powerdevil}/lib/qt-6/qml/org/kde/plasma/private/batterymonitor \
      "$out/lib/qt-6/qml/org/kde/plasma/private/batterymonitor"
  '';
  environment = pkgs.buildEnv {
    name = "tablet-trial-plasma-environment";
    paths = (with kde; [
      plasma-mobile plasma-workspace plasma-desktop plasma-keyboard kwin
      kded kglobalacceld kactivitymanagerd kscreen libkscreen kscreenlocker
      kde-cli-tools systemsettings plasma-settings kservice kio kio-extras
      kio-fuse kimageformats qtimageformats frameworkintegration plasma-integration
      polkit-kde-agent-1 plasma-nm plasma-pa bluez-qt breeze breeze-icons
      qqc2-breeze-style qqc2-desktop-style kirigami kirigami-addons
      qtsvg qtsensors qtwayland
    ]) ++ [ powerWidgets returnDesktop browserDesktop pkgs.hicolor-icon-theme ];
    pathsToLink = [ "/bin" "/share" "/libexec" "/etc/xdg" "/lib/qt-6/qml" "/lib/qt-6/plugins" ];
    ignoreCollisions = true;
  };
  defaults = pkgs.runCommand "tablet-trial-defaults" {} ''
    mkdir -p "$out"
    cat > "$out/startkderc" <<'EOF'
    [General]
    systemdBoot=false
    EOF
    cat > "$out/kscreenlockerrc" <<'EOF'
    [Daemon]
    Autolock=false
    LockOnResume=false
    EOF
    cat > "$out/kwinrc" <<'EOF'
    [Wayland]
    InputMethod=${kde.plasma-keyboard}/share/applications/org.kde.plasma.keyboard.desktop
    VirtualKeyboardEnabled=true
    EOF
    cat > "$out/baloofilerc" <<'EOF'
    [Basic Settings]
    Indexing-Enabled=false
    EOF
  '';
  session = pkgs.writeShellApplication {
    name = "tablet-session-trial-session";
    runtimeInputs = [ environment pkgs.coreutils pkgs.dbus pkgs.systemd pkgs.glib pkgs.xwayland ];
    text = ''
      # The trial has its own PAM/logind session and user bus. Never import the
      # laptop's environment, cookies, D-Bus address or WAYLAND_DISPLAY.
      unset DISPLAY WAYLAND_DISPLAY HYPRLAND_INSTANCE_SIGNATURE
      export XDG_SESSION_TYPE=wayland XDG_CURRENT_DESKTOP=KDE XDG_SESSION_DESKTOP=KDE
      export QT_QPA_PLATFORM=wayland
      export XDG_DATA_DIRS=${environment}/share:/run/current-system/sw/share
      export XDG_CONFIG_DIRS=${defaults}:${environment}/etc/xdg:/etc/xdg
      export XDG_MENU_PREFIX=plasma-
      export LD_LIBRARY_PATH=${lib.makeLibraryPath [ pkgs.pipewire ]}
      export QML_IMPORT_PATH=${environment}/lib/qt-6/qml
      export NIXPKGS_QT6_QML_IMPORT_PATH=${environment}/lib/qt-6/qml
      export QT_PLUGIN_PATH=${environment}/lib/qt-6/plugins
      XDG_RUNTIME_DIR="/run/user/$(id -u)"
      export XDG_RUNTIME_DIR
      export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"
      export __ETC_PROFILE_SOURCED=1
      mkdir -p "$HOME/.config"
      for name in startkderc kscreenlockerrc kwinrc baloofilerc; do
        if [[ ! -e "$HOME/.config/$name" ]]; then
          install -m 600 "${defaults}/$name" "$HOME/.config/$name"
        fi
      done
      cd "$HOME"
      exec ${kde.plasma-mobile}/bin/startplasmamobile
    '';
  };
  controller = pkgs.writeShellApplication {
    name = "tablet-session-trial";
    runtimeInputs = [ pkgs.python3 pkgs.systemd pkgs.util-linux pkgs.glib ];
    text = ''
      exec python3 ${../scripts/desktop/tablet-session-trial.py} "$@"
    '';
  };
in { inherit session controller environment defaults; }
