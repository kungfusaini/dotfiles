{
  description = "kiraMBP nix-darwin system flake";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    nix-darwin.url = "github:nix-darwin/nix-darwin/master";
    nix-darwin.inputs.nixpkgs.follows = "nixpkgs";
    nix-homebrew.url = "github:zhaofengli/nix-homebrew";
  };

  outputs = inputs@{ self, nix-darwin, nixpkgs, nix-homebrew}:
  let
    configuration = { pkgs, ... }: {

      nixpkgs.config.allowUnfree = true;
      # List packages installed in system profile. To search by name, run:
      # $ nix-env -qaP | grep wget
      environment.systemPackages =
        [ 
          pkgs.alt-tab-macos
          pkgs.aerospace
          pkgs.bitwarden
          pkgs.brave
          pkgs.hidden-bar
	  pkgs.iina
          pkgs.karabiner-elements
	  pkgs.neovim
          pkgs.obsidian
          pkgs.raycast
          pkgs.stats
          pkgs.the-unarchiver
          pkgs.tldr
          pkgs.tmux
          pkgs.whatsapp-for-mac
        ];

	# TODO: move this to the readme when I make it	{
	# regular brew packages
	# system services
	# macos appstore apps # mas-cli can help with this (getting ids etc) }
	homebrew = {
		enable = true;
		onActivation.cleanup = "zap"; # Removes all packages apart from the ones below
		onActivation.autoUpdate = true;
		onActivation.upgrade = true;
		casks = [
			 "itsycal" # this didn't work in nix as it needs to go into the application folder
			 "time-out"
			];
		};

	system.defaults = {
	 	dock.autohide = true;
		dock.wvous-br-corner = 1;
		dock.tilesize = 1;
		finder.FXPreferredViewStyle = "clmv";
		finder.ShowStatusBar = true;
		finder.ShowPathbar = true;
		finder.AppleShowAllExtensions = true;
		finder.FXEnableExtensionChangeWarning = false;
		finder.NewWindowTarget = "Other";
		finder.NewWindowTargetPath = "file:///Users/sumeet";
		trackpad.Clicking = true;
		controlcenter.Bluetooth = true;
		controlcenter.Sound = true;
		controlcenter.BatteryShowPercentage = true;

	};
      # Necessary for using flakes on this system.
      nix.settings.experimental-features = "nix-command flakes";

      # Enable alternative shell support in nix-darwin.
      programs.zsh.enable = true;
      # programs.fish.enable = true;

      # Set Git commit hash for darwin-version.
      system.configurationRevision = self.rev or self.dirtyRev or null;

      # Used for backwards compatibility, please read the changelog before changing.
      # $ darwin-rebuild changelog
      system.stateVersion = 6;

      # homebrew.enable requires this to be set
      # as nix-darwin is moing to system-wide, activations run as root
      # we need this user option, so we must set a primary user
      system.primaryUser = "sumeet";

      # The platform the configuration will be used on.
      nixpkgs.hostPlatform = "x86_64-darwin";
    };
  in
  {
    # Build darwin flake using:
    # $ darwin-rebuild build --flake .#kiraMBP
    darwinConfigurations."kiraMBP" = nix-darwin.lib.darwinSystem {
      modules = 
	[ configuration 
	  nix-homebrew.darwinModules.nix-homebrew # TODO: move this dude to a different locay
        {
          nix-homebrew = {
            # Install Homebrew under the default prefix
            enable = true;
            # User owning the Homebrew prefix, if you change your username, you gotta change this buddy
            user = "sumeet"; 
          };
        }
      ];
    };
  };
}
