{ ... }:

{
  # Keep shell history out of $HOME and under the XDG state directory.
  environment.sessionVariables = {
    HISTFILE = "/home/sumeet/.local/state/bash/history";

    # npm defaults to ~/.npm; keep its config, cache and global prefix in XDG locations.
    NPM_CONFIG_USERCONFIG = "/home/sumeet/.config/npm/npmrc";
    NPM_CONFIG_CACHE = "/home/sumeet/.cache/npm";
    NPM_CONFIG_PREFIX = "/home/sumeet/.local/share/npm";

    # Vim does not fully follow XDG by default; bootstrap it from XDG config.
    VIMINIT = "source /home/sumeet/.config/vim/vimrc";
  };

  programs.bash.interactiveShellInit = ''
    mkdir -p \
      "''${XDG_STATE_HOME:-$HOME/.local/state}/bash" \
      "''${XDG_CONFIG_HOME:-$HOME/.config}/npm" \
      "''${XDG_CACHE_HOME:-$HOME/.cache}/npm" \
      "''${XDG_DATA_HOME:-$HOME/.local/share}/npm/bin" \
      "''${XDG_STATE_HOME:-$HOME/.local/state}/vim/undo" \
      "''${XDG_STATE_HOME:-$HOME/.local/state}/vim/backup" \
      "''${XDG_CACHE_HOME:-$HOME/.cache}/vim/swap"
  '';
}
