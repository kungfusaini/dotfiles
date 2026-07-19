# Keep XDG/env exports active even when ZDOTDIR is already exported.
# zsh reads $ZDOTDIR/.zshenv instead of ~/.zshenv in that case.
[[ -f "$HOME/.zshenv" ]] && source "$HOME/.zshenv"
