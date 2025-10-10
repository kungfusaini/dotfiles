#!/bin/sh

CACHE_SECONDS=600
CACHE_FILE="$HOME/.config/tmux/tmp/cached_fortune.txt"

mkdir -p "$(dirname "$CACHE_FILE")"

# --- handle --fresh flag ---------------------------------------------
FORCE_FRESH=0
if [ "${1:-}" = "--fresh" ]; then
    FORCE_FRESH=1
fi
# ---------------------------------------------------------------------

current_time=$(date +%s)

file_mtime=0
if [ -f "$CACHE_FILE" ]; then
    file_mtime=$(stat -c %Y "$CACHE_FILE" 2>/dev/null || \
                 stat -f %m "$CACHE_FILE" 2>/dev/null || echo 0)
fi

age=$((current_time - file_mtime))

# Update cache if --fresh was given OR the cache is stale / missing
if [ "$FORCE_FRESH" -eq 1 ] || [ ! -f "$CACHE_FILE" ] || [ "$age" -gt "$CACHE_SECONDS" ]; then
	f=$(fortune -s -n 30 | tr -d '\n')
    printf "%s" "$f" > "$CACHE_FILE"
fi

printf '%30.30s' "$(cat "$CACHE_FILE")"
