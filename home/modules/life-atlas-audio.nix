{ lib, pkgs, osConfig, ... }:

let
  pi = lib.findFirst (p: (p.pname or "") == "pi-coding-agent")
    (throw "Audio transcript editing requires the managed Pi package")
    osConfig.users.users.sumeet.packages;
in
{
  # Standalone approved text editor only. No queue access, timer or backfill until
  # the phone's filename selection and recording-day metadata are verified.
  home.packages = [ (pkgs.callPackage ../packages/life-atlas-audio-editor { inherit pi; }) ];
}
