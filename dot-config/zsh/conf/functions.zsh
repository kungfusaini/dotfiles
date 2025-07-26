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
		sudo shutdown now
	else
		echo "Abandoining"
	fi
}


