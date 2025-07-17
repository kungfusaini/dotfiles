nixtemp() {
  nix shell "nixpkgs#$1"
}

zplug-update() {
  local target_dir="${1:-$ZDOTDIR/conf/plugins}"
  for dir in "$target_dir"/*/; do
    (cd "$dir" && git pull)
  done
}

