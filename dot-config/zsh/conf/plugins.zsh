PLUGIN_DIR=/Users/sumeet/.config/zsh/conf/plugins

export ATUIN_NOBIND="true"
eval "$(atuin init zsh)"

eval "$(zoxide init zsh)"

source <(fzf --zsh)

source "$PLUGIN_DIR/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh"
source "$PLUGIN_DIR/zsh-vi-mode/zsh-vi-mode.plugin.zsh"
source "$PLUGIN_DIR/zsh-autosuggestions/zsh-autosuggestions.zsh"
source "$PLUGIN_DIR/fzf-git.sh/fzf-git.sh"

bindkey -M vicmd -r "^G" # Unbind list-expand in command mode (allowed in insert mode)

bindkey -M viins '^ ' autosuggest-accept
bindkey -M vicmd '^ ' autosuggest-accept
bindkey -M viins '^h' atuin-search
bindkey -M vicmd '^h' atuin-search

