# Init Modular System
# /etc/zshrc is skipped via NOSYSZSHRC for startup speed, so keep the essentials here.
SAVEHIST=2000
HISTSIZE=2000
setopt HIST_IGNORE_DUPS SHARE_HISTORY HIST_FCNTL_LOCK

# Fast cached completion init. Run `rm $ZDOTDIR/.zcompdump && exec zsh` to force a full audit/rebuild.
autoload -Uz compinit bashcompinit
if [[ -s "$ZDOTDIR/.zcompdump" ]]; then
    compinit -C -d "$ZDOTDIR/.zcompdump"
else
    compinit -d "$ZDOTDIR/.zcompdump"
fi
bashcompinit

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

source $ZDOTDIR/conf/startup.zsh

. "$HOME/.local/share/../bin/env"
