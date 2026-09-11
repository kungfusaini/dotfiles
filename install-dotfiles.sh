#!/bin/sh
set -eu

if ! command -v stow >/dev/null 2>&1; then
  echo "error: GNU Stow is not installed or not on PATH" >&2
  exit 1
fi

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
config_dir=${XDG_CONFIG_HOME:-"$HOME/.config"}
nix_source="$repo_dir/dot-config/nix"
nix_target="$config_dir/nix"

mkdir -p "$config_dir"

if [ -L "$nix_target" ]; then
  actual=$(CDPATH= cd -- "$nix_target" && pwd -P)
  expected=$(CDPATH= cd -- "$nix_source" && pwd -P)
  if [ "$actual" != "$expected" ]; then
    echo "error: $nix_target points to $actual, expected $expected" >&2
    exit 1
  fi
elif [ -e "$nix_target" ]; then
  echo "error: $nix_target exists and is not a symlink" >&2
  exit 1
else
  ln -s "$nix_source" "$nix_target"
fi

stow \
  --restow \
  --no-folding \
  --ignore='^nix($|/)' \
  --dir="$repo_dir" \
  --target="$config_dir" \
  dot-config
