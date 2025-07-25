# Init Modular System
config_files=(
    "options"
    "aliases"
    "functions"
    "prompt"
    "plugins"
)

for file in "${config_files[@]}"; do
    [[ -f "$ZDOTDIR/conf/$file.zsh" ]] && source "$ZDOTDIR/conf/$file.zsh" || \
        echo "Warning: Configuration file not found: $ZDOTDIR/conf/$file.zsh" >&2
done

# Use XDG dirs for history
[ -d "$XDG_STATE_HOME/zsh" ] || mkdir -p "$XDG_STATE_HOME/zsh"
HISTFILE="$XDG_STATE_HOME/zsh/history"

# Completion cache setup
# [ -d "$XDG_CACHE_HOME/zsh" ] || mkdir -p "$XDG_CACHE_HOME/zsh"
zstyle ':completion:*' cache-path "$XDG_CACHE_HOME/zsh/zcompcache"
