{ pkgs, ... }:

{
  boot.loader.systemd-boot.enable = true;
  boot.loader.efi.canTouchEfiVariables = true;

  # Use latest kernel.
  boot.kernelPackages = pkgs.linuxPackages_latest;

  # The Panther Lake UCSI PPM can briefly report zero connectors during boot.
  # Retry initialization instead of leaving Type-C unavailable for the session.
  # Remove once the selected kernel contains upstream commit 254261381538.
  boot.kernelPatches = [
    {
      name = "ucsi-retry-early-ppm-errors";
      patch = ./patches/ucsi-retry-early-ppm-errors.patch;
    }
  ];

  # Keep the internal keyboard available when the convertible is folded into
  # tablet posture. We still read ThinkPad tablet mode separately from
  # /sys/devices/platform/thinkpad_acpi/hotkey_tablet_mode.
  boot.kernelParams = [
    "intel_hid.enable_sw_tablet_mode=0"
  ];
}
