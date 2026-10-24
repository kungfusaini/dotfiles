{ ... }:

{
  # Keep shell history out of $HOME and under the XDG state directory.
  environment.sessionVariables = {
    HISTFILE = "/home/sumeet/.local/state/bash/history";

    # npm defaults to ~/.npm; keep its config, cache and global prefix in XDG locations.
    NPM_CONFIG_USERCONFIG = "/home/sumeet/.config/npm/npmrc";
    NPM_CONFIG_CACHE = "/home/sumeet/.cache/npm";
    NPM_CONFIG_PREFIX = "/home/sumeet/.local/share/npm";

    # Azure CLI defaults to ~/.azure; keep auth/cache/config under XDG config.
    AZURE_CONFIG_DIR = "/home/sumeet/.config/azure";

    # Docker CLI defaults to ~/.docker; keep client/buildx state under XDG config.
    DOCKER_CONFIG = "/home/sumeet/.config/docker";

    # TeX Live defaults generated state to ~/.texliveYYYY; keep it in XDG cache.
    TEXMFVAR = "/home/sumeet/.cache/texlive/texmf-var";

    # Pi defaults to ~/.pi/agent; keep its config/runtime state under XDG config.
    PI_CODING_AGENT_DIR = "/home/sumeet/.config/pi/agent";

    # Vim does not fully follow XDG by default; bootstrap it from XDG config.
    VIMINIT = "source /home/sumeet/.config/vim/vimrc";
  };

  programs.bash.interactiveShellInit = ''
    mkdir -p \
      "''${XDG_STATE_HOME:-$HOME/.local/state}/bash" \
      "''${XDG_CONFIG_HOME:-$HOME/.config}/npm" \
      "''${XDG_CACHE_HOME:-$HOME/.cache}/npm" \
      "''${XDG_DATA_HOME:-$HOME/.local/share}/npm/bin" \
      "''${XDG_CONFIG_HOME:-$HOME/.config}/azure" \
      "''${XDG_CONFIG_HOME:-$HOME/.config}/azure-devops" \
      "''${XDG_CONFIG_HOME:-$HOME/.config}/docker" \
      "''${XDG_CACHE_HOME:-$HOME/.cache}/texlive/texmf-var" \
      "''${XDG_CONFIG_HOME:-$HOME/.config}/pi/agent" \
      "''${XDG_STATE_HOME:-$HOME/.local/state}/vim/undo" \
      "''${XDG_STATE_HOME:-$HOME/.local/state}/vim/backup" \
      "''${XDG_CACHE_HOME:-$HOME/.cache}/vim/swap"
  '';
}
