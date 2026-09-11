# ~ cleanup
export XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-$HOME/.cache}"
export XDG_DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
export XDG_STATE_HOME="${XDG_STATE_HOME:-$HOME/.local/state}"
export XDG_CONFIG_DIRS="${XDG_CONFIG_DIRS:-/etc/xdg}"
export XDG_DATA_DIRS="${XDG_DATA_DIRS:-/usr/local/share:/usr/share}"
export ANDROID_USER_HOME=$XDG_CONFIG_HOME/android
export PI_CODING_AGENT_DIR="$XDG_CONFIG_HOME/pi/agent"

export LESSHISTFILE=-
export DOCKER_CONFIG=$XDG_CONFIG_HOME/docker
export NPM_CONFIG_USERCONFIG=$XDG_CONFIG_HOME/npm/npmrc
export STREAMLIT_CONFIG_DIR=$XDG_CONFIG_HOME/streamlit
export TEXMFVAR="$XDG_CACHE_HOME/texlive/texmf-var"
export PYENV_ROOT=$XDG_DATA_HOME/pyenv
export PYTHON_HISTORY="$XDG_STATE_HOME/python_history"
export PYTHONPYCACHEPREFIX="$XDG_CACHE_HOME/python"
export PYTHONUSERBASE="$XDG_DATA_HOME/python"
if [[ "$OSTYPE" == darwin* ]]; then
  export SSH_AUTH_SOCK="$HOME/.ssh/.bitwarden-ssh-agent.sock"
fi
export ZDOTDIR="$XDG_CONFIG_HOME/zsh"
# Skip the generated global interactive zshrc; user config below sets prompt/completion.
# This avoids slow global compinit/compaudit on every Herdr pane startup.
export NOSYSZSHRC=1

case ":$PATH:" in
  *:"$HOME/.local/bin":*) ;;
  *) export PATH="$HOME/.local/bin:$PATH" ;;
esac

# Python Setup
# Keep .zshenv cheap: it runs for every zsh invocation, including scripts.
# pyenv init --path also runs `pyenv rehash`, which makes shell startup slow.
case ":$PATH:" in
  *:"$PYENV_ROOT/bin":*) ;;
  *) export PATH="$PYENV_ROOT/bin:$PATH" ;;
esac
case ":$PATH:" in
  *:"$PYENV_ROOT/shims":*) ;;
  *) export PATH="$PYENV_ROOT/shims:$PATH" ;;
esac
# eval "$(pyenv virtualenv-init -)" # Include this if you use pyenv-virtualenv
#
