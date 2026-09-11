{
  description = "kiraMBP nix-darwin system flake";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-25.11-darwin";
    nix-darwin.url = "github:nix-darwin/nix-darwin/nix-darwin-25.11";
    nix-darwin.inputs.nixpkgs.follows = "nixpkgs";
    nix-homebrew.url = "github:zhaofengli/nix-homebrew";
  };

  outputs =
    { self, nix-darwin, nix-homebrew, ... }:
    {
      # Build with: darwin-rebuild build --flake .#kiraMBP
      darwinConfigurations.kiraMBP = nix-darwin.lib.darwinSystem {
        specialArgs = { inherit self; };
        modules = [
          ./modules/common.nix
          ./modules/darwin.nix
          ./hosts/kiraMBP.nix
          nix-homebrew.darwinModules.nix-homebrew
        ];
      };
    };
}
