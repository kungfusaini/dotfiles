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

# open/create daily note
function today() {
  local date=$(date +"%Y-%m-%d")
  local file=~/codex/Journal/${date}.md

  if ! [ -f "$file" ]; then
    echo "# ${date}" > "$file"
  fi

  nvim "$file"
}

# open compass
function compass() {
  local file=~/codex/compass.md
  nvim "$file"
}

function jqp() {	
cd ~/codex/
  git add .
  git commit -m "$(date +'%Y-%m-%d %H:%M:%S')"
  git push
}

