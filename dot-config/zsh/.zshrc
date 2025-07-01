# Pyenv setup
eval "$(pyenv init --path)"
# eval "$(pyenv virtualenv-init -)" # Include this if you use pyenv-virtualenv (highly recommended)

## Use XDG dirs for completion and history files
 [ -d "$XDG_STATE_HOME"/zsh ] || mkdir -p "$XDG_STATE_HOME"/zsh
 HISTFILE="$XDG_STATE_HOME"/zsh/history
 [ -d "$XDG_CACHE_HOME"/zsh ] || mkdir -p "$XDG_CACHE_HOME"/zsh
 zstyle ':completion:*' cache-path "$XDG_CACHE_HOME"/zsh/zcompcache
 compinit -d "$XDG_CACHE_HOME"/zsh/zcompdump-$ZSH_VERSION
