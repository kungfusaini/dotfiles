{ lib, fetchurl, writeShellApplication, symlinkJoin, appimage-run, python3
, curl, libnotify, systemd, coreutils, cacert
}:
let
  # Only redistributable tools enter the store. Game code, assets and saves do not.
  builder = fetchurl {
    url = "https://git-cdn.magicbean.dev/MagicBeanDev/Longshot/releases/download/v3.2.0/Longshot-v3.2.0-x86_64.AppImage";
    # Executable fetches use a NAR hash; signed file SHA-256: 70b8269b03c8bfd48385f7cb18bc0a493985219e6645d1eef104ae93cd1f2506.
    hash = "sha256-RJD8EJisv3FH2aVbFb7tMpoC1lQVxSKeBcW2vZkrkWk=";
    executable = true;
  };
  launcher = fetchurl {
    url = "https://git-cdn.magicbean.dev/MagicBeanDev/LongshotLauncher/releases/download/v1.2.0/LongshotLauncher-v1.2.0-x86_64.AppImage";
    # Signed file SHA-256: c1e9e68ed7de78895f5c43c6edbec5bc25254d80b23a46f856dfb281e598833a.
    hash = "sha256-+XAqpS5HDh7lqUuXzBVpj71OukyzaF7I+PNem8TvkC4=";
    executable = true;
  };
  play = writeShellApplication {
    name = "longshot-play";
    runtimeInputs = [ appimage-run systemd ];
    text = ''
      game="$HOME/matrix/projects/longshot/game"
      if [[ ! -x "$game/bin/longshot" ]]; then
        echo "Longshot is not built at $game" >&2
        exit 1
      fi
      # The checker has its own bounded service and lock: never wait for networking.
      systemctl --user start --no-block longshot-update-check.service 2>/dev/null || true
      export SSL_CERT_FILE=${cacert}/etc/ssl/certs/ca-bundle.crt
      exec appimage-run ${builder} --play "$game" "$@"
    '';
  };
  updateLauncher = writeShellApplication {
    name = "longshot-launcher";
    runtimeInputs = [ appimage-run coreutils ];
    text = ''
      # A writable copy lets upstream self-update without modifying a store file.
      root="''${XDG_DATA_HOME:-$HOME/.local/share}/longshot/launcher-app"
      mkdir -p "$root"
      if [[ ! -e "$root/LongshotLauncher.AppImage" ]]; then
        install -m755 ${launcher} "$root/LongshotLauncher.AppImage"
      fi
      export SSL_CERT_FILE=${cacert}/etc/ssl/certs/ca-bundle.crt
      exec appimage-run "$root/LongshotLauncher.AppImage" --launch "$HOME/matrix/projects/longshot/game" "$@"
    '';
  };
  checker = writeShellApplication {
    name = "longshot-update-check";
    runtimeInputs = [ python3 curl libnotify ];
    text = ''exec python3 ${./update_check.py} "$@"'';
  };
in symlinkJoin {
  name = "longshot-integration";
  paths = [ play updateLauncher checker ];
  meta = {
    description = "Longshot launchers and non-blocking stable-release notifications";
    license = lib.licenses.mit;
    platforms = [ "x86_64-linux" ];
    mainProgram = "longshot-play";
  };
}
