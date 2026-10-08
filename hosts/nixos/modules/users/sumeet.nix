{ pkgs, unstable, ... }:

{
  users.users.sumeet = {
    isNormalUser = true;
    description = "Sumeet Saini";
    extraGroups = [ "networkmanager" "wheel" ];
    packages = with pkgs; [
      unstable.pi-coding-agent
    ];
  };
}
