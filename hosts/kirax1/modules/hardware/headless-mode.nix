{ pkgs, ... }:

let
  headlessModeControl = pkgs.writeShellApplication {
    name = "headless-mode-control";
    runtimeInputs = with pkgs; [ coreutils kmod python3 systemd ];
    text = builtins.readFile ../../scripts/headless/headless-mode-control;
  };
in
{
  environment.systemPackages = [ headlessModeControl ];

  # This helper exposes only fixed, audited headless-mode transitions. It does
  # not accept paths, module names, commands, or arbitrary sysfs values.
  security.sudo.extraRules = [
    {
      users = [ "sumeet" ];
      commands = [
        {
          command = "/run/current-system/sw/bin/headless-mode-control";
          options = [ "NOPASSWD" ];
        }
      ];
    }
  ];
}
