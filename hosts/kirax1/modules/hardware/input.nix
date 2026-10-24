{ pkgs, ... }:

{
  environment.systemPackages = [ pkgs.keyd ];

  services.keyd = {
    enable = true;
    keyboards.default = {
      ids = [ "*" ];
      extraConfig = ''
        [global]
        chord_timeout = 100

        [main]
        # Swap Caps Lock and Escape. Fn+Esc/FnLock is handled by firmware
        # before Linux sees the key, so this should not interfere with it.
        capslock = esc
        esc = capslock

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
