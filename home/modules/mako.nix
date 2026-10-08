{ ... }:

{
  services.mako = {
    enable = true;
    settings."mode=do-not-disturb" = {
      invisible = 1;
    };
  };
}
