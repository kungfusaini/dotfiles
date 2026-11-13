# Evaluate against the exact committed host configuration before deployment.
{ config }:
let
  defaults = config.home-manager.users.sumeet.xdg.mimeApps.defaultApplications;
  mailTypes = [
    "x-scheme-handler/mailto"
    "x-scheme-handler/mid"
    "message/rfc822"
    "text/calendar"
    "application/x-extension-ics"
  ];
in
assert builtins.all (mime: defaults.${mime} == [ "thunderbird.desktop" ]) mailTypes;
assert defaults."x-scheme-handler/https" == [ "project-browser.desktop" ];
{
  mailDefaults = builtins.listToAttrs (map (mime: { name = mime; value = defaults.${mime}; }) mailTypes);
}
