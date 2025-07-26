PLUGIN_DIR=/Users/sumeet/.config/zsh/conf/plugins

eval "$(atuin init zsh)"
eval "$(zoxide init zsh)"

source "$PLUGIN_DIR/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh"
source "$PLUGIN_DIR/zsh-vi-mode/zsh-vi-mode.plugin.zsh"

source "$PLUGIN_DIR/zsh-autosuggestions/zsh-autosuggestions.zsh"
bindkey '^ ' autosuggest-accept

source <(fzf --zsh)
source "$PLUGIN_DIR/fzf-git.sh/fzf-git.sh"
bindkey -M vicmd -r "^G" # Unbind list-expand in command mode (allowed in insert mode)

