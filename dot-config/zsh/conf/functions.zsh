nixtemp() {
  nix shell "nixpkgs#$1"
}

zplug-update() {
  local target_dir="${1:-$ZDOTDIR/conf/plugins}"
  for dir in "$target_dir"/*/; do
    (cd "$dir" && git pull)
  done
}

function y() {
	local tmp="$(mktemp -t "yazi-cwd.XXXXXX")" cwd
	yazi "$@" --cwd-file="$tmp"
	IFS= read -r -d '' cwd < "$tmp"
	[ -n "$cwd" ] && [ "$cwd" != "$PWD" ] && builtin cd -- "$cwd"
	rm -f -- "$tmp"
}

function restart() {
	echo -n "Are you sure you want to restart? [y/n]: "
	read selection
	if [[ $selection == y ]]; then
		echo "Restarting..."
		sudo shutdown -r now
	else
		echo "Abandoining"
	fi
}

function shutdown() {
	echo -n "Are you sure you want to shutdown? [y/n]: "
	read selection
	if [[ $selection == y ]]; then
		echo "Shutting down..."
		sudo shutdown -h now
	else
		echo "Abandoining"
	fi
}


# Function to pipe a command's help output to bat
function rd() {
    "$@" | bat --paging=always -l help
}

function jqp() {	
cd ~/codex/
  git add .
  git commit -m "$(date +'%Y-%m-%d %H:%M:%S')"
  git push
}

# Path completion for task-note starting from ~/codex/
_task-note() {
  if [[ $CURRENT -eq 3 ]]; then
    local actions=(add open show)
    _describe 'command actions' actions
  elif [[ $CURRENT -eq 4 ]]; then
    _path_files -W ~/codex/
  else
    _default
  fi
}
compdef _task-note task-note

function tunnel-status() {
  if launchctl list 2>/dev/null | grep -q "reverse-ssh-tunnel"; then
    local pid=$(launchctl list | grep "reverse-ssh-tunnel" | awk '{print $1}')
    echo "Reverse SSH tunnel is running (PID: $pid)"
  else
    echo "Reverse SSH tunnel is not running"
  fi
}

function tunnel-restart() {
  echo -n "Restart reverse SSH tunnel? [y/n]: "
  read selection
  if [[ $selection == y ]]; then
    launchctl unload ~/Library/LaunchAgents/org.nixos.reverse-ssh-tunnel.plist 2>/dev/null
    launchctl load ~/Library/LaunchAgents/org.nixos.reverse-ssh-tunnel.plist
    echo "Tunnel restarted"
  else
    echo "Aborted"
  fi
}

# Create a new Python project with modular environment setup
pyproj() {
  if [[ -z "$1" ]]; then
    echo "Usage: pyproj <project-name>"
    return 1
  fi
  
  local script_path="$ZDOTDIR/conf/scripts/pyproj"
  if [[ -f "$script_path" ]]; then
    "$script_path" "$1"
  else
    echo "Error: pyproj script not found at $script_path"
    return 1
  fi
}

# Tab completion for pyproj
_pyproj() {
  _description 'create new python project'
  _message 'project name'
}
compdef _pyproj pyproj
