{ pkgs, ... }:

{
  virtualisation.docker.enable = true;

  users.users.sumeet.extraGroups = [ "docker" ];

  environment.systemPackages = [
    pkgs.docker-compose
    (pkgs.azure-cli.withExtensions [
      pkgs.azure-cli-extensions.azure-devops
    ])
  ];
}
