{
  description = "Sumeet's NixOS configuration";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";
    nixpkgs-unstable.url = "github:NixOS/nixpkgs/nixos-unstable";
    wshowkeys = {
      url = "github:DreamMaoMao/wshowkeys";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    mewtion = {
      url = "github:aayuxh-vim/Mewtion";
      inputs.nixpkgs.follows = "nixpkgs-unstable";
    };
    home-manager = {
      url = "github:nix-community/home-manager/release-26.05";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = { self, nixpkgs, nixpkgs-unstable, wshowkeys, mewtion, home-manager }:
    let
      system = "x86_64-linux";
      pkgs = import nixpkgs {
        inherit system;
        config.allowUnfree = true;
      };
      unstable = import nixpkgs-unstable {
        inherit system;
        config.allowUnfree = true;
      };
    in {
      devShells.${system} = let
        pythonShell = pkgs.mkShell {
          packages = [
            pkgs.python3
            pkgs.uv
            pkgs.ruff
          ];
        };
      in {
        python = pythonShell;
        default = pythonShell;
      };

      nixosConfigurations.nixos = nixpkgs.lib.nixosSystem {
        inherit system;
        specialArgs = {
          inherit unstable wshowkeys mewtion;
        };
        modules = [
          ./hosts/nixos/configuration.nix
          home-manager.nixosModules.home-manager
          {
            home-manager.useGlobalPkgs = true;
            home-manager.useUserPackages = true;
            home-manager.backupFileExtension = "hm-backup";
            home-manager.users.sumeet = import ./home/sumeet.nix;
          }
        ];
      };
    };
}
