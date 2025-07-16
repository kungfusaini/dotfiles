# Init Modular System
if [[ -f "$ZDOTDIR/conf/options.zsh" ]]; then
    source "$ZDOTDIR/conf/options.zsh"
fi

if [[ -f "$ZDOTDIR/conf/aliases.zsh" ]]; then
    source "$ZDOTDIR/conf/aliases.zsh"
fi

if [[ -f "$ZDOTDIR/conf/functions.zsh" ]]; then
    source "$ZDOTDIR/conf/functions.zsh"
fi

if [[ -f "$ZDOTDIR/conf/prompt.zsh" ]]; then
    source "$ZDOTDIR/conf/prompt.zsh"
fi

# Use XDG dirs for history
[ -d "$XDG_STATE_HOME/zsh" ] || mkdir -p "$XDG_STATE_HOME/zsh"
HISTFILE="$XDG_STATE_HOME/zsh/history"

# Completion cache setup
[ -d "$XDG_CACHE_HOME/zsh" ] || mkdir -p "$XDG_CACHE_HOME/zsh"
zstyle ':completion:*' cache-path "$XDG_CACHE_HOME/zsh/zcompcache"
