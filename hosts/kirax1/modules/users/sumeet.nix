{ pkgs, unstable, ... }:

{
  users.users.sumeet = {
    isNormalUser = true;
    description = "Sumeet Saini";
    extraGroups = [ "networkmanager" "nordvpn" "wheel" ];
    packages = with pkgs; [
      (unstable.callPackage ../../../../home/packages/pi-coding-agent { })
    ];
  };
}
