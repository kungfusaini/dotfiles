{ ... }:

{
  services.mako = {
    enable = true;
    # Expire notifications even when an app requests that they stay open.
    settings.default-timeout = 5000;
    settings.ignore-timeout = true;
    # Keep mail syncing, but never show or retain Thunderbird notifications.
    settings."app-name=\"Thunderbird\"" = {
      invisible = true;
      history = false;
      ignore-timeout = true;
      default-timeout = 1;
    };
    settings."mode=do-not-disturb" = {
      invisible = 1;
    };
  };
}
