{ pkgs, ... }:

{
  boot.loader.systemd-boot.enable = true;
  boot.loader.efi.canTouchEfiVariables = true;

  # Use latest kernel.
  boot.kernelPackages = pkgs.linuxPackages_latest;

  # Keep the internal keyboard available when the convertible is folded into
  # tablet posture. We still read ThinkPad tablet mode separately from
  # /sys/devices/platform/thinkpad_acpi/hotkey_tablet_mode.
  boot.kernelParams = [
    "intel_hid.enable_sw_tablet_mode=0"
  ];
}
