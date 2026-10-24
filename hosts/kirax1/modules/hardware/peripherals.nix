{ pkgs, unstable, ... }:

let
  # Panther Lake's xe/Type-C stack can miss a USB-C display hotplug even though
  # the sink advertises DisplayPort. Asking DRM to reprobe the existing
  # connectors is sufficient and avoids resetting UCSI or reloading drivers.
  usbCDisplayRescan = pkgs.writeShellScript "usb-c-display-rescan" ''
    set -u

    for delay in 0.2 0.8 2; do
      sleep "$delay"

      for status in /sys/class/drm/card*-DP-*/status /sys/class/drm/card*-HDMI-*/status; do
        [[ -w "$status" ]] || continue
        printf 'detect' > "$status"
      done

    done

    for status in /sys/class/drm/card*-DP-*/status /sys/class/drm/card*-HDMI-*/status; do
      [[ -r "$status" ]] || continue
      echo "USB-C display rescan: ''${status%/status}=$(<"$status")"
    done
  '';
in
{
  services.printing.enable = true;

  hardware.bluetooth = {
    enable = true;
    package = unstable.bluez;
  };
  services.blueman.enable = true;

  services.udisks2.enable = true;
  services.gvfs.enable = true;

  # Trigger a short, asynchronous DRM rescan when a USB-C partner or one of its
  # alternate modes appears, changes, or disappears. This also makes detach
  # reliable if the same missed-hotplug race leaves a connector stale.
  services.udev.extraRules = ''
    ACTION=="add|remove|change", SUBSYSTEM=="typec", KERNEL=="port[0-9]*-partner*", RUN+="${pkgs.systemd}/bin/systemctl --no-block start usb-c-display-rescan.service"
  '';

  systemd.services.usb-c-display-rescan = {
    description = "Rescan DRM connectors after USB-C display hotplug";
    wantedBy = [ "multi-user.target" ];
    after = [ "systemd-udevd.service" ];
    serviceConfig = {
      Type = "oneshot";
      ExecStart = usbCDisplayRescan;
    };
  };

  services.fprintd.enable = true;
  security.pam.services.greetd.fprintAuth = true;
}
