{ config, lib, pkgs, mewtion, ... }:

let
  cfg = config.programs.mewtion;
  system = pkgs.stdenv.hostPlatform.system;

  package = mewtion.packages.${system}.default.overrideAttrs (old: {
    patches = (old.patches or [ ]) ++ [
      ../../../../packages/mewtion-buffered-iio.patch
    ];
  });

  setIioPermissions = pkgs.writeShellScript "mewtion-iio-permissions" ''
    sensor="$1"
    device="/dev/''${sensor##*/}"

    if [ -e "$device" ]; then
      ${pkgs.coreutils}/bin/chgrp iio "$device"
      ${pkgs.coreutils}/bin/chmod 0660 "$device"
    fi

    ${pkgs.coreutils}/bin/chgrp iio "$sensor/buffer/enable" "$sensor/buffer/length"
    ${pkgs.coreutils}/bin/chmod g+rw "$sensor/buffer/enable" "$sensor/buffer/length"
    for attribute in "$sensor"/scan_elements/in_*_en; do
      ${pkgs.coreutils}/bin/chgrp iio "$attribute"
      ${pkgs.coreutils}/bin/chmod g+rw "$attribute"
    done
  '';
in
{
  options.programs.mewtion = {
    enable = lib.mkEnableOption "Mewtion vehicle-motion cues";

    users = lib.mkOption {
      type = lib.types.listOf lib.types.str;
      default = [ ];
      description = "Users allowed to access buffered IIO motion sensors.";
    };
  };

  config = lib.mkIf cfg.enable {
    environment.systemPackages = [ package ];

    users.groups.iio = { };
    users.users = lib.genAttrs cfg.users (_: {
      extraGroups = [ "iio" ];
    });

    services.udev.extraRules = ''
      SUBSYSTEM=="iio", KERNEL=="iio:device*", ATTR{name}=="accel_3d", GROUP="iio", MODE="0660", RUN+="${setIioPermissions} /sys$env{DEVPATH}"
    '';

    # `udevadm trigger` is unnecessary after a switch: immediately update any
    # accelerometer that was already present when the new rule was installed.
    system.activationScripts.mewtionIioPermissions.text = ''
      for sensor in /sys/bus/iio/devices/iio:device*; do
        [ -r "$sensor/name" ] || continue
        [ "$(${pkgs.coreutils}/bin/cat "$sensor/name")" = "accel_3d" ] || continue
        ${setIioPermissions} "$sensor"
      done
    '';
  };
}
