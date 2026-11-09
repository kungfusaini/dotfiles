# Evaluate with the host config from the exact committed flake being deployed.
{ config }:
let
  home = config.home-manager.users.sumeet;
  packages = map (p: p.pname or p.name) home.home.packages;
  imageTypes = [
    "image/avif"
    "image/bmp"
    "image/gif"
    "image/heif"
    "image/jpeg"
    "image/jxl"
    "image/png"
    "image/svg+xml"
    "image/tiff"
    "image/webp"
  ];
  defaults = home.xdg.mimeApps.defaultApplications;
in
assert builtins.elem "swayimg" packages;
assert home.xdg.mimeApps.enable;
assert builtins.all (mime: defaults.${mime} == [ "swayimg.desktop" ]) imageTypes;
# Installing a photo viewer must not change ordinary browsing.
assert defaults."text/html" == [ "vivaldi-stable.desktop" ];
assert defaults."x-scheme-handler/http" == [ "project-browser.desktop" ];
assert defaults."x-scheme-handler/https" == [ "project-browser.desktop" ];
{
  packageInstalled = true;
  imageDefaults = builtins.listToAttrs (map (mime: { name = mime; value = defaults.${mime}; }) imageTypes);
}
