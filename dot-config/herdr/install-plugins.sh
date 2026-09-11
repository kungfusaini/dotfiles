#!/bin/sh
set -eu

if ! command -v herdr >/dev/null 2>&1; then
  echo "error: herdr is not installed or not on PATH" >&2
  exit 1
fi

config_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

for plugin in \
  exe-dev-usage \
  pi-workspace-sync
do
  plugin_dir="$config_dir/plugins/$plugin"

  if [ ! -f "$plugin_dir/herdr-plugin.toml" ]; then
    echo "error: missing plugin manifest: $plugin_dir/herdr-plugin.toml" >&2
    exit 1
  fi

  herdr plugin link "$plugin_dir" --enabled
done
