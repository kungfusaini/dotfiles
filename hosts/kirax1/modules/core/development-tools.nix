{ pkgs, ... }:

{
  virtualisation.docker.enable = true;

  users.users.sumeet.extraGroups = [ "docker" ];

  environment.systemPackages = [
    pkgs.python3
    pkgs.htop
    pkgs.docker-compose
    (pkgs.azure-cli.withExtensions [
      pkgs.azure-cli-extensions.azure-devops
    ])
    pkgs.google-cloud-sdk
    (pkgs.texlive.combine {
      inherit (pkgs.texlive) scheme-small latexmk;
    })
  ];
}
