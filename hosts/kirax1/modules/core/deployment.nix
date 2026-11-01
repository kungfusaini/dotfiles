{ pkgs, ... }:

let
  deployKirax1 = pkgs.writeShellApplication {
    name = "deploy-kirax1";
    runtimeInputs = with pkgs; [ coreutils git util-linux ];
    text = builtins.readFile ../../scripts/system/deploy-kirax1;
  };
in
{
  environment.systemPackages = [ deployKirax1 ];

  # This no-argument helper deploys only a clean, committed main revision of
  # this machine's canonical flake. The helper itself rejects all arguments.
  security.sudo.extraRules = [
    {
      users = [ "sumeet" ];
      commands = [
        {
          command = "/run/current-system/sw/bin/deploy-kirax1";
          options = [ "NOPASSWD" ];
        }
      ];
    }
  ];
}
