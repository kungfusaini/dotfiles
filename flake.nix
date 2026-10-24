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
    spicetify-nix.url = "github:Gerg-L/spicetify-nix";
    sops-nix = {
      url = "github:Mic92/sops-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = { self, nixpkgs, nixpkgs-unstable, wshowkeys, mewtion, home-manager, spicetify-nix, sops-nix }:
    let
      system = "x86_64-linux";
      pkgs = import nixpkgs {
        inherit system;
        config.allowUnfree = true;
      };
      unstable = import nixpkgs-unstable {
        inherit system;
        config.allowUnfree = true;
        overlays = [
          (_final: prev: {
            # Paste delivery is asynchronous. Voxtype 1.0.1 sends Return as soon
            # as wtype exits, which can submit before the target processes Ctrl+V.
            voxtype-onnx = prev.voxtype-onnx.overrideAttrs (oldAttrs: {
              postPatch = (oldAttrs.postPatch or "") + ''
                substituteInPlace src/output/paste.rs \
                  --replace-fail \
                    '        if self.auto_submit {
                            self.send_enter().await?;
                        }' \
                    '        if self.auto_submit {
                            tokio::time::sleep(std::time::Duration::from_millis(200)).await;
                            self.send_enter().await?;
                        }'
              '';
            });
          })
        ];
      };
    in {
      devShells.${system} = let
        pythonShell = pkgs.mkShell {
          packages = [
            pkgs.python3
            pkgs.python3Packages.python-docx
            pkgs.uv
            pkgs.ruff
          ];
        };
      in {
        python = pythonShell;
        default = pythonShell;
      };

      nixosConfigurations.kirax1 = nixpkgs.lib.nixosSystem {
        inherit system;
        specialArgs = {
          inherit unstable wshowkeys mewtion spicetify-nix;
        };
        modules = [
          ./hosts/kirax1/configuration.nix
          # The module comes from unstable because NordVPN is not yet in 26.05.
          # Drop its documentation metadata: mixing that into the stable manual
          # introduces an identifier unknown to the stable redirects database.
          ({ config, lib, pkgs, ... }@args:
            builtins.removeAttrs
              ((import "${nixpkgs-unstable}/nixos/modules/services/networking/nordvpn.nix") args)
              [ "meta" ])
          spicetify-nix.nixosModules.spicetify
          sops-nix.nixosModules.sops
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
