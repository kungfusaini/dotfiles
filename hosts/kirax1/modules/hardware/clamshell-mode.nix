{ ... }:

{
  # logind remains the single owner of lid-triggered suspend, including on
  # battery. Powering off eDP in Hyprland must not disable normal lid policy.
  # An enabled external DRM output counts as docked; no peripheral is required.
  services.logind.settings.Login = {
    HandleLidSwitch = "suspend";
    HandleLidSwitchExternalPower = "suspend";
    HandleLidSwitchDocked = "ignore";
  };
}
