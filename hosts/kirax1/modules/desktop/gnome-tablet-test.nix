{ pkgs, unstable, ... }:

{
  # Optional, separate Wayland session in the existing DMS greeter. No GDM,
  # fold-triggered session switching, or changes to Hyprland's input/layout.
  services.desktopManager.gnome.enable = true;
  services.displayManager.defaultSession = "hyprland-uwsm";

  # Expose the accelerometer to GNOME/Mutter over D-Bus. Actual orientation
  # and convertible-posture behaviour still need testing on this hardware.
  hardware.sensor.iio.enable = true;

  # Both desktops need their own portal preference files. An explicit list
  # avoids competing mkDefault definitions from their NixOS modules.
  xdg.portal.configPackages = [
    unstable.hyprland
    pkgs.gnome-session
  ];
}
