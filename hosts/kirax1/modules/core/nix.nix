{ ... }:

{
  nix.settings = {
    experimental-features = [ "nix-command" "flakes" ];
    use-xdg-base-directories = true;
  };
  nixpkgs.config.allowUnfree = true;
}
