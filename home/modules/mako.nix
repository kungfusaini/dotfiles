{ ... }:

{
  services.mako = {
    enable = true;
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
