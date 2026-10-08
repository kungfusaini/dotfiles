{ pkgs, ... }:

{
  services.printing.enable = true;

  environment.systemPackages = [ pkgs.keyd ];

  hardware.bluetooth.enable = true;
  services.blueman.enable = true;

  services.udisks2.enable = true;
  services.gvfs.enable = true;

  services.fprintd.enable = true;
  security.pam.services.greetd.fprintAuth = true;

  services.keyd = {
    enable = true;
    keyboards.default = {
      ids = [ "*" ];
      extraConfig = ''
        [global]
        chord_timeout = 100

        [main]
        # Microsoft Copilot key emits LeftMeta+LeftShift+F23.
        # Treat that exact chord as plain F23 when pressed by itself.
        leftmeta+leftshift+f23 = f23

        [shift]
        # If Super is already held, the Copilot key arrives as Shift+F23.
        # Drop only Shift so Hyprland sees Super+F23.
        f23 = f23
      '';
    };
  };
}
