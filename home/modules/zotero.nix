{ config, pkgs, ... }:

let
  profile = "${config.xdg.configHome}/zotero/profile";
  data = "${config.xdg.dataHome}/zotero";
  zotero = pkgs.symlinkJoin {
    name = "zotero-persistent";
    paths = [ pkgs.zotero ];
    nativeBuildInputs = [ pkgs.makeWrapper ];
    postBuild = ''
      wrapProgram "$out/bin/zotero" \
        --run 'mkdir -p ${profile} ${data}' \
        --add-flags '-profile ${profile}'
    '';
  };
in
{
  home.packages = [ zotero ];

  # Keep the writable profile and library in XDG locations, not a temporary trial
  # or the separate Calibre library. Zotero manages prefs.js and all library data.
  xdg.configFile."zotero/profile/user.js".text = ''
    user_pref("extensions.zotero.useDataDir", true);
    user_pref("extensions.zotero.dataDir", "${data}");
  '';
}
