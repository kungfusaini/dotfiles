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
alias gl="git log"

########## Config Aliases ##########
alias dotfiles="cd ~/.dotfiles"
alias config="cd ~/.config"
alias kittyedit="vim ~/.config/kitty/kitty.conf"
alias hammer="vim ~/.config/hammerspoon/init.lua"
alias herdrconf="vim ~/.config/herdr/config.toml"
alias muxconf="vim ~/.config/herdr/config.toml"

########## NIX Aliases ##########
alias nixedit="vim ~/.config/nix/flake.nix"
alias nixbuild="sudo darwin-rebuild switch --flake ~/.config/nix"
alias nixrspwn="nix flake update --flake ~/.config/nix; nixbuild; brew upgrade"
 
########## Tool Aliases ##########
alias cat="bat"
alias cd="z"
alias vim="nvim"
alias c="pbcopy"
alias p="pbpaste"
alias t="task"
alias tn="task-note"
alias bucket="/Users/sumeet/matrix/web/bucket/bucket.py"
alias oc="OPENCODE_FAST_BOOT=1 opencode"
alias occ="OPENCODE_FAST_BOOT=1 OPENCODE_DISABLE_PROJECT_CONFIG=1 opencode"

########## Network Aliases ##########
# alias ssh="kitty +kitten ssh"

########## Project Aliases ##########
alias aether-up="cd /Users/sumeet/matrix/web/aether; docker compose -f docker-compose.yml -f docker-compose-dev.yml up --build"

########## Action Aliases ##########
alias colima-rspwn="colima delete --force && colima start"
