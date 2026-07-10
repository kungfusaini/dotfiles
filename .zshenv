# ~ cleanup
export XDG_CONFIG_HOME="$HOME/.config"
export XDG_CACHE_HOME="$HOME/.cache"
export XDG_DATA_HOME="$HOME/.local/share"
export XDG_STATE_HOME="$HOME/.local/state"
export XDG_CONFIG_DIRS="/etc/xdg"
export XDG_DATA_DIRS="/usr/local/share:/usr/share"
export ANDROID_USER_HOME=$XDG_CONFIG_HOME/android

export LESSHISTFILE=-
export DOCKER_CONFIG=$XDG_CONFIG_HOME/docker
export NPM_CONFIG_USERCONFIG=$XDG_CONFIG_HOME/npm/npmrc
export STREAMLIT_CONFIG_DIR=$XDG_CONFIG_HOME/streamlit
export TEXMFVAR="$XDG_CACHE_HOME/texlive/texmf-var"
export PYENV_ROOT=$XDG_DATA_HOME/pyenv
export PYTHON_HISTORY="$XDG_STATE_HOME/python_history"
export PYTHONPYCACHEPREFIX="$XDG_CACHE_HOME/python"
export PYTHONUSERBASE="$XDG_DATA_HOME/python"
export SSH_AUTH_SOCK="$HOME/.ssh/.bitwarden-ssh-agent.sock"
export ZDOTDIR="$HOME/.config/zsh"

case ":$PATH:" in
  *:"$HOME/.local/bin":*) ;;
  *) export PATH="$HOME/.local/bin:$PATH" ;;
esac

# Python Setup
export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init --path)"
# eval "$(pyenv virtualenv-init -)" # Include this if you use pyenv-virtualenv
#


## Not really sure how I feel about this but I guess it's okay for now. Gotta not back this up and be aware of it!!
export PINGLINE_API_KEY=7EA2ZHHFNKY2VDGDAVRG6DMQ
