# ~ cleanup
export XDG_CONFIG_HOME="$HOME/.config"
export XDG_CACHE_HOME="$HOME/.cache"
export XDG_DATA_HOME="$HOME/.local/share"
export XDG_STATE_HOME="$HOME/.local/state"
export XDG_CONFIG_DIRS="/etc/xdg"
export XDG_DATA_DIRS="/usr/local/share:/usr/share"

export LESSHISTFILE=-
export PYENV_ROOT=$XDG_DATA_HOME/pyenv
export PYTHON_HISTORY="$XDG_STATE_HOME/python_history"
export PYTHONPYCACHEPREFIX="$XDG_CACHE_HOME/python"
export PYTHONUSERBASE="$XDG_DATA_HOME/python"
export SSH_AUTH_SOCK="$HOME/.ssh/.bitwarden-ssh-agent.sock"
export ZDOTDIR="$HOME/.config/zsh"

# Python Setup
export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init --path)"
# eval "$(pyenv virtualenv-init -)" # Include this if you use pyenv-virtualenv
