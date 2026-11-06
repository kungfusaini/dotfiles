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

  # This no-argument helper validates and deploys only a pinned, committed main
  # revision. Uncommitted files are excluded; the helper rejects all arguments.
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
