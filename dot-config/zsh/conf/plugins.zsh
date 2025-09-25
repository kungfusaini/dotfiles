PLUGIN_DIR=/Users/sumeet/.config/zsh/conf/plugins
SCRIPT_DIR=/Users/sumeet/.config/zsh/conf/scripts

eval "$(starship init zsh)"
export STARSHIP_CONFIG=$XDG_CONFIG_HOME/starship/starship.toml

export ATUIN_NOBIND="true"
eval "$(atuin init zsh)"

eval "$(zoxide init zsh)"

eval "$(direnv hook zsh)" 

source <(fzf --zsh)

source "$PLUGIN_DIR/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh"
source "$PLUGIN_DIR/zsh-vi-mode/zsh-vi-mode.plugin.zsh"
source "$PLUGIN_DIR/zsh-autosuggestions/zsh-autosuggestions.zsh"

# This is custom so doesn't get overritten by git pull to update plugins
source "$SCRIPT_DIR/fzf-git.sh"

bindkey -M vicmd -r "^G" # Unbind list-expand in command mode (allowed in insert mode)

# Ensure keyboard->shortcuts->inputsources are turned off if this doesn't work !
bindkey -M viins '^ ' autosuggest-accept 
bindkey -M vicmd '^ ' autosuggest-accept
bindkey -M viins '^h' atuin-search
bindkey -M vicmd '^h' atuin-search

