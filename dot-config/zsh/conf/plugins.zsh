PLUGIN_DIR=/Users/sumeet/.config/zsh/conf/plugins

eval "$(atuin init zsh)"

source "$PLUGIN_DIR/zsh-autosuggestions/zsh-autosuggestions.zsh"
source "$PLUGIN_DIR/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh"
source "$PLUGIN_DIR/fzf-git.sh/fzf-git.sh"
source "$PLUGIN_DIR/zsh-vi-mode/zsh-vi-mode.plugin.zsh"

source <(fzf --zsh)

