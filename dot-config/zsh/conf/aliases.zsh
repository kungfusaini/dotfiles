########## ZSH Aliases ##########
alias rspwn="clear; cd ~; zsh;"
### Base ###
alias zconf="vim "$ZDOTDIR"/.zshrc"
alias zenv="vim "$HOME"/.zshenv"
### Modules ###
alias zalias="vim "$ZDOTDIR"/conf/aliases.zsh"
alias zplug="vim "$ZDOTDIR"/conf/plugins.zsh"
alias zfunc="vim "$ZDOTDIR"/conf/functions.zsh"
alias zopt="vim "$ZDOTDIR"/conf/options.zsh"
alias zprompt="vim "$ZDOTDIR"/conf/prompt.zsh"

########## Git Aliases ##########
alias gs="git status"
alias gb="git branch --v"
alias gp="git push"
alias gpf="git push --force"
alias gin="git pull"
alias gcm="git commit -m"
alias ga="git add"
alias gaa="git add ." # Git add all

########## Config Aliases ##########
alias dotfiles="cd ~/.dotfiles"
alias config="cd ~/.config"
alias aerospace="vim ~/.config/aerospace/aerospace.toml"
alias kittyedit="vim ~/.config/kitty/kitty.conf"
alias hammer="vim ~/.config/hammerspoon/init.lua"

########## NIX Aliases ##########
alias nixedit="vim ~/.config/nix/flake.nix"
alias nixbuild="sudo darwin-rebuild switch --flake ~/.config/nix"
alias nixrspwn="nix flake update --flake ~/.config/nix; nixbuild; brew upgrade"
 
########## Shell Aliases ##########
alias cat="bat"
alias cd="z"
alias vim="nvim"
