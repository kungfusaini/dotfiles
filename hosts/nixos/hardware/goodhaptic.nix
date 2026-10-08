{ pkgs, ... }:

let
  goodhaptic = pkgs.callPackage ../packages/goodhaptic.nix { };
in
{
  environment.systemPackages = [
    goodhaptic
  ];

  # Stable symlink for the internal Goodix GXTP5420 haptic touchpad hidraw node.
  services.udev.extraRules = ''
    SUBSYSTEM=="hidraw", KERNELS=="0018:27C6:0F95.*", SYMLINK+="goodhaptic-touchpad"
  '';

  # goodhaptic's GUI talks to this privileged daemon over /run/goodhaptic/sock.
  systemd.services.goodhapticd = {
    description = "Goodix haptic touchpad control daemon";
    wantedBy = [ "multi-user.target" ];
    after = [ "systemd-udev-settle.service" ];
    wants = [ "systemd-udev-settle.service" ];
    preStart = ''
      if [ -e /etc/goodhaptic.conf ]; then
        ${pkgs.gnused}/bin/sed -i 's#^device .*#device /dev/goodhaptic-touchpad#' /etc/goodhaptic.conf
      fi
    '';
    serviceConfig = {
      ExecStart = "${goodhaptic}/libexec/goodhapticd";
      Restart = "on-failure";
      RestartSec = "3s";
    };
  };

  # Keep this mutable so the GUI/daemon can save chosen strength/force values,
  # but always pin the device line to the actual Goodix touchpad symlink.
  system.activationScripts.goodhapticDefaultConfig.text = ''
    if [ ! -e /etc/goodhaptic.conf ]; then
      cat > /etc/goodhaptic.conf <<'EOF'
    device /dev/goodhaptic-touchpad
    strength 50
    threshold 2
    inputmode 3
    selective_surface 1
    selective_button 1
    persist 1
    stepless 0
    EOF
    elif ${pkgs.gnugrep}/bin/grep -q '^device ' /etc/goodhaptic.conf; then
      ${pkgs.gnused}/bin/sed -i 's#^device .*#device /dev/goodhaptic-touchpad#' /etc/goodhaptic.conf
    else
      ${pkgs.gnused}/bin/sed -i '1idevice /dev/goodhaptic-touchpad' /etc/goodhaptic.conf
    fi
  '';
}
