{ ... }:

{
  # Provide the freedesktop Secret Service used by applications such as
  # project-api. greetd's PAM integration unlocks the login keyring.
  services.gnome.gnome-keyring.enable = true;
}
